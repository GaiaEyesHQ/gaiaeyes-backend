import asyncio
from datetime import date, datetime, timezone
from typing import List
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from zoneinfo import ZoneInfo

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.anyio("asyncio")

from app.main import app
from app.db import settings
from app.routers import ingest, summary
from psycopg_pool import PoolTimeout


@pytest.fixture(autouse=True)
def _set_dev_bearer():
    original = settings.DEV_BEARER
    settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        settings.DEV_BEARER = original


@pytest.fixture
def client():
    transport = ASGITransport(app=app, lifespan="off")
    return AsyncClient(transport=transport, base_url="http://test")


class _FakeCursor:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *args, **kwargs):  # noqa: ARG002
        return None

    async def fetchone(self):
        return {}

    async def fetchall(self):
        return []


class _FakeConn:
    def cursor(self, *args, **kwargs):  # noqa: ARG002
        return _FakeCursor()

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def execute(self, *args, **kwargs):  # noqa: ARG002
        return None


class _FakeConnContext:
    async def __aenter__(self):
        return _FakeConn()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def connection(self):
        return _FakeConnContext()


class _RecordingCursor:
    def __init__(self):
        self.calls: List[tuple[str, tuple]] = []
        self.rowcount = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, values=None, **kwargs):  # noqa: ARG002
        self.calls.append((str(query), tuple(values or ())))


class _RecordingConn:
    def __init__(self, cursor: _RecordingCursor):
        self._cursor = cursor

    def cursor(self, *args, **kwargs):  # noqa: ARG002
        return self._cursor

    async def commit(self):
        return None


class _RecordingPool:
    def __init__(self):
        self.cursor = _RecordingCursor()

    def connection(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                return _RecordingConn(pool.cursor)

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()


class _FlakyPool:
    def __init__(self, failures: list[str]):
        self._failures = list(failures)
        self.attempts = 0

    def connection(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                pool.attempts += 1
                if pool._failures:
                    outcome = pool._failures.pop(0)
                    if outcome == "timeout":
                        raise PoolTimeout("timeout")
                    if outcome == "error":
                        raise RuntimeError("boom")
                return _FakeConn()

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_mart_select_falls_back_to_daily_summary_body_fields():
    assert "coalesce(df.steps_total, ds.steps_total) as steps_total" in summary._MART_SELECT
    assert "coalesce(df.sleep_total_minutes, ds.sleep_total_minutes) as sleep_total_minutes" in summary._MART_SELECT
    assert "coalesce(df.spo2_avg, ds.spo2_avg) as spo2_avg" in summary._MART_SELECT
    assert "coalesce(df.respiratory_rate_avg, ds.respiratory_rate_avg) as respiratory_rate_avg" in summary._MART_SELECT
    assert "coalesce(df.resting_hr_avg, ds.resting_hr_avg) as resting_hr_avg" in summary._MART_SELECT


@pytest.mark.anyio
async def test_refresh_scheduled_on_ingest(monkeypatch, client: AsyncClient):
    ingest._refresh_registry.clear()
    ingest._recent_refresh_requests.clear()
    monkeypatch.setattr(summary, "_REFRESH_DELAY_RANGE", (0.0, 0.0))

    fake_pool = _FakePool()

    async def _fake_get_pool():
        return fake_pool

    scheduled: List[tuple[str, date]] = []

    async def _fake_execute_refresh(user_id: str, day_local: date, tz_name: str = "UTC") -> None:  # noqa: ARG001
        scheduled.append((user_id, day_local))

    def _immediate_task_factory(coro):
        return asyncio.create_task(coro)

    monkeypatch.setattr(ingest, "get_pool", _fake_get_pool)
    monkeypatch.setattr(ingest, "_execute_refresh", _fake_execute_refresh)
    monkeypatch.setattr(ingest, "_refresh_task_factory", _immediate_task_factory)

    user_id = str(uuid4())
    payload = {
        "samples": [
            {
                "user_id": user_id,
                "device_os": "ios",
                "source": "watch",
                "type": "heart_rate",
                "start_time": "2024-04-03T12:00:00Z",
                "end_time": "2024-04-03T12:01:00Z",
                "value": 70,
            }
        ]
    }

    resp = await client.post(
        "/v1/samples/batch",
        headers={
            "Authorization": "Bearer test-token",
            "X-Dev-UserId": user_id,
        },
        params={"tz": "UTC"},
        json=payload,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    await asyncio.sleep(0)
    await asyncio.sleep(0.01)
    assert scheduled, "refresh task should be scheduled"
    scheduled_user, scheduled_day = scheduled[0]
    assert scheduled_user == user_id
    assert scheduled_day == date(2024, 4, 3)


@pytest.mark.anyio
async def test_ingest_accepts_supabase_jwt_and_uses_authenticated_user(monkeypatch, client: AsyncClient):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "test-secret")

    fake_pool = _FakePool()

    async def _fake_get_pool():
        return fake_pool

    captured: dict[str, str] = {}

    async def _fake_safe_insert_batch(pool, rows, dev_uid):  # noqa: ARG001
        captured["insert_user"] = dev_uid
        return len(rows), 0, []

    async def _fake_schedule_refresh(user_id, day_local, inserted, tz_name="UTC"):  # noqa: ARG001
        captured["refresh_user"] = user_id
        return True

    monkeypatch.setattr(ingest, "get_pool", _fake_get_pool)
    monkeypatch.setattr(ingest, "safe_insert_batch", _fake_safe_insert_batch)
    monkeypatch.setattr(ingest, "_maybe_schedule_refresh", _fake_schedule_refresh)

    auth_user_id = str(uuid4())
    payload_user_id = str(uuid4())
    token = jwt.encode({"sub": auth_user_id}, "test-secret", algorithm="HS256")
    payload = {
        "samples": [
            {
                "user_id": payload_user_id,
                "device_os": "ios",
                "source": "watch",
                "type": "heart_rate",
                "start_time": "2024-04-03T12:00:00Z",
                "end_time": "2024-04-03T12:01:00Z",
                "value": 70,
            }
        ]
    }

    resp = await client.post(
        "/v1/samples/batch",
        headers={"Authorization": f"Bearer {token}"},
        params={"tz": "UTC"},
        json=payload,
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert captured["insert_user"] == auth_user_id
    assert captured["refresh_user"] == auth_user_id


@pytest.mark.anyio
async def test_insert_batch_provisions_gaia_user_before_samples():
    user_id = str(uuid4())
    pool = _RecordingPool()
    sample = ingest.SampleIn(
        user_id=str(uuid4()),
        device_os="ios",
        source="watch",
        type="heart_rate",
        start_time=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 4, 3, 12, 1, tzinfo=timezone.utc),
        value=70,
    )

    inserted, skipped, errors = await ingest._insert_batch_once(pool, [(sample, 0)], user_id)

    assert inserted == 1
    assert skipped == 0
    assert errors == []
    assert "insert into gaia.users" in pool.cursor.calls[0][0]
    assert pool.cursor.calls[0][1] == (user_id,)
    assert "insert into gaia.samples" in pool.cursor.calls[1][0]
    assert pool.cursor.calls[1][1][0] == user_id


@pytest.mark.anyio
async def test_features_fallback_to_yesterday(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)

    today = date(2024, 4, 3)
    yesterday = date(2024, 4, 2)

    async def _fake_current_day(conn, tz_name):  # noqa: ARG001
        return today

    async def _fake_fetch_mart(conn, user_id: str, day_local: date):  # noqa: ARG001
        if day_local == yesterday:
            return {
                "user_id": user_id,
                "day": yesterday,
                "steps_total": 1234,
                "hr_min": 55,
                "hr_max": 110,
                "updated_at": datetime.now(),
            }
        return None

    async def _fake_freshen(conn, user_id, day_local, tzinfo):  # noqa: ARG001
        return None

    async def _fake_sleep(conn, user_id, start_utc, end_utc):  # noqa: ARG001
        return {"rem_m": 30, "core_m": 50, "deep_m": 40, "awake_m": 10, "inbed_m": 140}

    async def _fake_daily_wx(conn, day_local):  # noqa: ARG001
        return {"kp_max": 5, "bz_min": -3, "sw_speed_avg": 420, "flares_count": 1, "cmes_count": 0}

    async def _fake_current_wx(conn):  # noqa: ARG001
        return {"kp_current": 3, "bz_current": -5, "sw_speed_current": 400}

    async def _fake_sch(conn, day_local):  # noqa: ARG001
        return {"sch_station": "tomsk", "sch_f0_hz": 7.8, "sch_f1_hz": 14.1, "sch_f2_hz": 20.3, "sch_f3_hz": 26.4, "sch_f4_hz": 32.5}

    async def _fake_post(conn, day_local):  # noqa: ARG001
        return {"post_title": "Test", "post_caption": "Cap", "post_body": "Body", "post_hashtags": "#tag"}

    monkeypatch.setattr(summary, "_current_day_local", _fake_current_day)
    monkeypatch.setattr(summary, "_fetch_mart_row", _fake_fetch_mart)
    monkeypatch.setattr(summary, "_freshen_features", _fake_freshen)
    monkeypatch.setattr(summary, "_fetch_sleep_aggregate", _fake_sleep)
    monkeypatch.setattr(summary, "_fetch_space_weather_daily", _fake_daily_wx)
    monkeypatch.setattr(summary, "_fetch_current_space_weather", _fake_current_wx)
    monkeypatch.setattr(summary, "_fetch_schumann_row", _fake_sch)
    monkeypatch.setattr(summary, "_fetch_daily_post", _fake_post)

    user_id = str(uuid4())
    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["data"]["day"] == yesterday.isoformat()
    assert data["data"]["lunar_context"]["utc_date"] == yesterday.isoformat()
    assert data["data"]["moon_phase_label"]
    assert data["diagnostics"]["source"] == "yesterday"
    assert data["diagnostics"]["day_used"] == yesterday.isoformat()


@pytest.mark.anyio
async def test_features_today_includes_geomagnetic_context(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)

    today = date(2026, 3, 22)

    async def _fake_current_day(conn, tz_name):  # noqa: ARG001
        return today

    async def _fake_query_mart(conn, user_id: str, day_local: date):  # noqa: ARG001
        return {
            "user_id": user_id,
            "day": today,
            "steps_total": 1234,
            "updated_at": datetime.now(timezone.utc),
            "ulf_context_class_raw": "Quiet",
            "ulf_context_label": "Quiet",
            "ulf_confidence_score": 0.25,
            "ulf_confidence_label": "Low",
            "ulf_regional_intensity": 22.0,
            "ulf_regional_coherence": None,
            "ulf_regional_persistence": 18.0,
            "ulf_quality_flags": [],
            "ulf_is_provisional": False,
            "ulf_is_usable": True,
            "ulf_is_high_confidence": False,
            "ulf_station_count": 1,
            "ulf_missing_samples": False,
            "ulf_low_history": False,
        }, None

    async def _fake_sleep(conn, user_id, start_utc, end_utc):  # noqa: ARG001
        return {}

    async def _fake_daily_wx(conn, day_local):  # noqa: ARG001
        return {}

    async def _fake_current_wx(conn):  # noqa: ARG001
        return {}

    async def _fake_ulf(conn):  # noqa: ARG001
        return {
            "ts_utc": "2026-03-22T12:00:00Z",
            "stations_used": ["BOU", "CMO"],
            "regional_intensity": 78.95,
            "regional_coherence": 0.765,
            "regional_persistence": 51.88,
            "context_class": "Elevated (coherent)",
            "confidence_score": 0.64,
            "quality_flags": ["low_history"],
        }

    async def _fake_sch(conn, day_local):  # noqa: ARG001
        return {}

    async def _fake_post(conn, day_local):  # noqa: ARG001
        return {}

    monkeypatch.setattr(summary, "_current_day_local", _fake_current_day)
    monkeypatch.setattr(summary, "_query_mart_with_retry", _fake_query_mart)
    monkeypatch.setattr(summary, "_fetch_sleep_aggregate", _fake_sleep)
    monkeypatch.setattr(summary, "_fetch_space_weather_daily", _fake_daily_wx)
    monkeypatch.setattr(summary, "_fetch_current_space_weather", _fake_current_wx)
    monkeypatch.setattr(summary, "_fetch_latest_ulf_context", _fake_ulf)
    monkeypatch.setattr(summary, "_fetch_schumann_row", _fake_sch)
    monkeypatch.setattr(summary, "_fetch_daily_post", _fake_post)

    user_id = str(uuid4())
    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    data = payload["data"]

    assert data["ulf_context_label"] == "Elevated"
    assert data["ulf_confidence_label"] == "Moderate"
    assert data["ulf_station_count"] == 2
    assert data["ulf_is_provisional"] is True
    assert data["ulf_low_history"] is True
    assert data["geomagnetic_context"]["label"] == "Elevated"
    assert data["geomagnetic_context"]["confidence_label"] == "Moderate"
    assert data["geomagnetic_context"]["ts_utc"] == "2026-03-22T12:00:00Z"


@pytest.mark.anyio
async def test_features_today_force_refreshes_before_collect(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    today = date(2026, 4, 24)
    calls: List[str] = []

    async def _fake_current_day(conn, tz_name):  # noqa: ARG001
        calls.append("current_day")
        return today

    async def _fake_execute_mart_refresh(user_id, day_local, tz_name="UTC"):  # noqa: ARG001
        calls.append("refresh")

    async def _fake_collect(conn, user_id, tz_name, tzinfo, cached_payload=None):  # noqa: ARG001
        calls.append("collect")
        return (
            {"user_id": user_id, "day": today, "updated_at": datetime.now(timezone.utc)},
            {"source": "today", "day": today, "day_used": today, "updated_at": datetime.now(timezone.utc)},
            None,
        )

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)
    monkeypatch.setattr(summary, "_current_day_local", _fake_current_day)
    monkeypatch.setattr(summary, "_execute_mart_refresh", _fake_execute_mart_refresh)
    monkeypatch.setattr(summary, "_collect_features", _fake_collect)

    user_id = str(uuid4())
    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC", "force": "1"},
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert calls[:3] == ["current_day", "refresh", "collect"]


@pytest.mark.anyio
async def test_gather_enrichment_recovers_after_component_failure(monkeypatch):
    class _RollbackRecordingConn(_FakeConn):
        def __init__(self):
            self.rollback_calls = 0

        async def rollback(self):
            self.rollback_calls += 1

    conn = _RollbackRecordingConn()
    today = date(2026, 4, 21)
    calls: List[str] = []

    async def _fake_sleep(conn, user_id, start_utc, end_utc):  # noqa: ARG001
        calls.append("sleep")
        return {"rem_m": 30, "core_m": 50, "deep_m": 40, "awake_m": 10, "inbed_m": 140}

    async def _fake_daily_wx(conn, day_local):  # noqa: ARG001
        calls.append("daily_wx")
        return {"kp_max": 5}

    async def _fake_current_wx(conn):  # noqa: ARG001
        calls.append("current_wx")
        return {"kp_current": 3}

    async def _fake_ulf(conn):  # noqa: ARG001
        calls.append("ulf")
        return {"regional_intensity": 42.0}

    async def _fake_sch(conn, day_local):  # noqa: ARG001
        calls.append("sch")
        raise RuntimeError("slow schumann query")

    async def _fake_post(conn, day_local):  # noqa: ARG001
        calls.append("post")
        return {"post_title": "Recovered"}

    monkeypatch.setattr(summary, "_fetch_sleep_aggregate", _fake_sleep)
    monkeypatch.setattr(summary, "_fetch_space_weather_daily", _fake_daily_wx)
    monkeypatch.setattr(summary, "_fetch_current_space_weather", _fake_current_wx)
    monkeypatch.setattr(summary, "_fetch_latest_ulf_context", _fake_ulf)
    monkeypatch.setattr(summary, "_fetch_schumann_row", _fake_sch)
    monkeypatch.setattr(summary, "_fetch_daily_post", _fake_post)

    components, errors = await summary._gather_enrichment(
        conn,
        str(uuid4()),
        today,
        ZoneInfo("UTC"),
    )

    assert calls == ["sleep", "daily_wx", "current_wx", "ulf", "sch", "post"]
    assert conn.rollback_calls == 1
    assert components["sch"] == {}
    assert components["post"]["post_title"] == "Recovered"
    assert errors == ["schumann daily failed: slow schumann query"]


@pytest.mark.anyio
async def test_features_returns_defaults_when_empty(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)

    today = date(2024, 4, 5)

    async def _fake_current_day(conn, tz_name):  # noqa: ARG001
        return today

    async def _fake_query_mart(conn, user_id: str, day_local: date):  # noqa: ARG001
        return None, None

    async def _fake_fetch_mart(conn, user_id: str, day_local: date):  # noqa: ARG001
        return None

    async def _fake_snapshot(conn, user_id: str):  # noqa: ARG001
        return None

    async def _fake_freshen(conn, user_id: str, day_local: date, tzinfo):  # noqa: ARG001
        return None

    async def _fake_get_last_good(user_id: str):  # noqa: ARG001
        return None

    async def _fake_set_last_good(user_id: str, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(summary, "_current_day_local", _fake_current_day)
    monkeypatch.setattr(summary, "_query_mart_with_retry", _fake_query_mart)
    monkeypatch.setattr(summary, "_fetch_mart_row", _fake_fetch_mart)
    monkeypatch.setattr(summary, "_fetch_snapshot_row", _fake_snapshot)
    monkeypatch.setattr(summary, "_freshen_features", _fake_freshen)
    monkeypatch.setattr(summary, "get_last_good", _fake_get_last_good)
    monkeypatch.setattr(summary, "set_last_good", _fake_set_last_good)

    user_id = str(uuid4())

    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["user_id"] == user_id
    assert data["day"] == today.isoformat()
    assert data["steps_total"] == 0
    assert data["sleep_total_minutes"] == 0
    assert data["cycle_tracking_enabled"] is False
    assert data["menstrual_active"] is False
    assert data["temperature_source"] is None
    assert data["flares_count"] == 0
    assert data["kp_alert"] is False
    assert data["source"] in {"snapshot", "empty"}


@pytest.mark.anyio
async def test_features_error_envelope(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)

    async def _fake_collect(conn, user_id, tz_name, tzinfo):  # noqa: ARG001
        return {}, {
            "branch": "scoped",
            "statement_timeout_ms": summary.STATEMENT_TIMEOUT_MS,
            "requested_user_id": user_id,
            "user_id": user_id,
            "day": None,
            "day_used": None,
            "updated_at": None,
            "source": "empty",
            "mart_row": False,
            "freshened": False,
            "max_day": None,
            "total_rows": None,
            "tz": "UTC",
        }, "boom"

    monkeypatch.setattr(summary, "_collect_features", _fake_collect)

    cached_updated_at = "2024-04-05T12:34:56.123456+00:00"

    async def _fake_get_last_good(user_id: str):  # noqa: ARG001
        return {
            "user_id": user_id,
            "day": "2024-04-05",
            "source": "snapshot",
            "steps_total": 3210,
            "updated_at": cached_updated_at,
        }

    async def _noop_set_last_good(user_id: str, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(summary, "get_last_good", _fake_get_last_good)
    monkeypatch.setattr(summary, "set_last_good", _noop_set_last_good)

    user_id = str(uuid4())
    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    data = payload["data"]
    assert data["steps_total"] == 3210
    assert data["day"] == "2024-04-05"
    assert data["updated_at"] == cached_updated_at
    diag = payload["diagnostics"]
    assert diag["cache_fallback"] is True
    assert diag["error"] is None
    assert diag["last_error"] == "boom"
    assert diag["updated_at"] == cached_updated_at


@pytest.mark.anyio
async def test_features_db_error_envelope(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)

    async def _boom_current_day(conn, tz_name):  # noqa: ARG001
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(summary, "_current_day_local", _boom_current_day)

    async def _fake_get_last_good(user_id: str):  # noqa: ARG001
        return {
            "user_id": user_id,
            "day": "2024-04-06",
            "source": "snapshot",
            "steps_total": 1111,
        }

    async def _noop_set_last_good(user_id: str, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(summary, "get_last_good", _fake_get_last_good)
    monkeypatch.setattr(summary, "set_last_good", _noop_set_last_good)

    user_id = str(uuid4())
    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    data = payload["data"]
    assert data["steps_total"] == 1111
    assert data["day"] == "2024-04-06"
    diag = payload["diagnostics"]
    assert diag["cache_fallback"] is True
    assert diag["error"] is None
    assert diag["last_error"] == "database unavailable"


@pytest.mark.anyio
async def test_features_mart_query_error_marks_cache(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)

    today = date(2024, 4, 6)

    async def _fake_current_day(conn, tz_name):  # noqa: ARG001
        return today

    async def _fake_query_mart(conn, user_id, day_local):  # noqa: ARG001
        return None, PoolTimeout("db_timeout")

    async def _fake_fetch_mart(conn, user_id, day_local):  # noqa: ARG001
        return None

    async def _fake_fetch_snapshot(conn, user_id):  # noqa: ARG001
        return None

    cached_updated_at = "2024-04-05T07:30:00+00:00"

    async def _fake_get_last_good(user_id: str):  # noqa: ARG001
        return {
            "user_id": user_id,
            "day": "2024-04-05",
            "source": "snapshot",
            "steps_total": 4321,
            "updated_at": cached_updated_at,
        }

    async def _noop_set_last_good(user_id: str, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(summary, "_current_day_local", _fake_current_day)
    monkeypatch.setattr(summary, "_query_mart_with_retry", _fake_query_mart)
    monkeypatch.setattr(summary, "_fetch_mart_row", _fake_fetch_mart)
    monkeypatch.setattr(summary, "_fetch_snapshot_row", _fake_fetch_snapshot)
    monkeypatch.setattr(summary, "get_last_good", _fake_get_last_good)
    monkeypatch.setattr(summary, "set_last_good", _noop_set_last_good)

    user_id = str(uuid4())
    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["error"] is None

    data = payload["data"]
    assert data["steps_total"] == 4321
    assert data["day"] == "2024-04-05"
    assert data["source"] == "snapshot"
    assert data["updated_at"] == cached_updated_at

    diag = payload["diagnostics"]
    assert diag["cache_fallback"] is True
    assert diag["pool_timeout"] is True
    assert diag["error"] is None
    assert diag["last_error"] == "db_timeout"
    assert diag["day_used"] == "2024-04-05"


@pytest.mark.anyio
async def test_features_mart_error_yesterday_enriched(monkeypatch, client: AsyncClient):
    def _fake_acquire():
        return _FakeConnContext()

    monkeypatch.setattr(summary, "_acquire_features_conn", _fake_acquire)

    today = date(2024, 4, 7)
    yesterday = date(2024, 4, 6)

    async def _fake_current_day(conn, tz_name):  # noqa: ARG001
        return today

    async def _fake_query_mart(conn, user_id, day_local):  # noqa: ARG001
        return None, PoolTimeout("timeout")

    async def _fake_fetch_mart(conn, user_id: str, day_local: date):  # noqa: ARG001
        if day_local == yesterday:
            return {
                "user_id": user_id,
                "day": yesterday,
                "steps_total": 2222,
                "hr_min": 50,
                "hr_max": 105,
                "updated_at": datetime(2024, 4, 6, 12, 0, tzinfo=timezone.utc),
            }
        return None

    async def _fake_snapshot(conn, user_id):  # noqa: ARG001
        return None

    async def _fake_sleep(conn, user_id, start_utc, end_utc):  # noqa: ARG001
        return {
            "rem_m": 40,
            "core_m": 60,
            "deep_m": 50,
            "awake_m": 10,
            "inbed_m": 180,
        }

    async def _fake_daily_wx(conn, day_local):  # noqa: ARG001
        return {
            "kp_max": 6,
            "bz_min": -4.5,
            "sw_speed_avg": 500,
            "flares_count": 2,
            "cmes_count": 1,
        }

    async def _fake_current_wx(conn):  # noqa: ARG001
        return {
            "kp_current": 5,
            "bz_current": -3,
            "sw_speed_current": 480,
        }

    async def _fake_sch(conn, day_local):  # noqa: ARG001
        return {
            "sch_station": "tomsk",
            "sch_f0_hz": 7.9,
            "sch_f1_hz": 14.2,
            "sch_f2_hz": 20.4,
            "sch_f3_hz": 26.5,
            "sch_f4_hz": 32.6,
        }

    async def _fake_post(conn, day_local):  # noqa: ARG001
        return {
            "post_title": "Yesterday",
            "post_caption": "Cached",
            "post_body": "Body",
            "post_hashtags": "#fallback",
        }

    async def _fake_get_last_good(user_id: str):  # noqa: ARG001
        return None

    async def _noop_set_last_good(user_id: str, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(summary, "_current_day_local", _fake_current_day)
    monkeypatch.setattr(summary, "_query_mart_with_retry", _fake_query_mart)
    monkeypatch.setattr(summary, "_fetch_mart_row", _fake_fetch_mart)
    monkeypatch.setattr(summary, "_fetch_snapshot_row", _fake_snapshot)
    monkeypatch.setattr(summary, "_fetch_sleep_aggregate", _fake_sleep)
    monkeypatch.setattr(summary, "_fetch_space_weather_daily", _fake_daily_wx)
    monkeypatch.setattr(summary, "_fetch_current_space_weather", _fake_current_wx)
    monkeypatch.setattr(summary, "_fetch_schumann_row", _fake_sch)
    monkeypatch.setattr(summary, "_fetch_daily_post", _fake_post)
    monkeypatch.setattr(summary, "get_last_good", _fake_get_last_good)
    monkeypatch.setattr(summary, "set_last_good", _noop_set_last_good)

    user_id = str(uuid4())
    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    data = payload["data"]

    assert data["day"] == yesterday.isoformat()
    assert data["steps_total"] == 2222
    # Aggregated fields should be populated despite the mart error
    assert data["sleep_total_minutes"] == 150
    assert data["rem_m"] == 40
    assert data["core_m"] == 60
    assert data["deep_m"] == 50
    assert data["kp_max"] == 6
    assert data["kp_alert"] is True
    assert data["post_title"] == "Yesterday"

    diag = payload["diagnostics"]
    assert diag["source"] == "yesterday"
    assert diag["day_used"] == yesterday.isoformat()
    assert diag["cache_fallback"] is False
    assert diag["pool_timeout"] is True


@pytest.mark.anyio
async def test_features_cache_miss_still_marks_ok(monkeypatch, client: AsyncClient):
    class _FailCtx:
        async def __aenter__(self):
            raise PoolTimeout("timeout")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _boom_acquire():
        return _FailCtx()

    async def _fake_get_last_good(user_id: str):  # noqa: ARG001
        return None

    async def _noop_set_last_good(user_id: str, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(summary, "_acquire_features_conn", _boom_acquire)
    monkeypatch.setattr(summary, "get_last_good", _fake_get_last_good)
    monkeypatch.setattr(summary, "set_last_good", _noop_set_last_good)

    user_id = str(uuid4())

    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    data = payload["data"]
    assert data["user_id"] == user_id
    # defaults are applied even without cache
    assert data["steps_total"] == 0
    assert payload["diagnostics"]["cache_fallback"] is True


@pytest.mark.anyio
async def test_features_pool_timeout_uses_cache(monkeypatch, client: AsyncClient):
    class _FailCtx:
        async def __aenter__(self):
            raise PoolTimeout("timeout")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _boom_acquire():
        return _FailCtx()

    async def _fake_get_last_good(user_id: str):  # noqa: ARG001
        return {
            "user_id": user_id,
            "day": "2024-04-05",
            "source": "snapshot",
            "steps_total": 3210,
        }

    async def _noop_set_last_good(user_id: str, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(summary, "_acquire_features_conn", _boom_acquire)
    monkeypatch.setattr(summary, "get_last_good", _fake_get_last_good)
    monkeypatch.setattr(summary, "set_last_good", _noop_set_last_good)

    user_id = str(uuid4())

    resp = await client.get(
        "/v1/features/today",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
        params={"tz": "UTC"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["steps_total"] == 3210
    assert data["day"] == "2024-04-05"
    assert payload["diagnostics"]["cache_fallback"] is True
    assert payload["diagnostics"]["pool_timeout"] is True



@pytest.mark.anyio
async def test_db_ping_retries_pool_timeout(monkeypatch):
    pool = _FlakyPool(["timeout"])

    async def _fake_get_pool():
        return pool

    pool_timeout_calls: list[str] = []

    async def _fake_handle_pool_timeout(reason: str) -> bool:
        pool_timeout_calls.append(reason)
        return True

    async def _fake_handle_connection_failure(exc):  # noqa: ARG001
        pytest.fail("connection failure handler should not run")

    monkeypatch.setattr(summary, "get_pool", _fake_get_pool)
    monkeypatch.setattr(summary, "handle_pool_timeout", _fake_handle_pool_timeout)
    monkeypatch.setattr(summary, "handle_connection_failure", _fake_handle_connection_failure)

    result = await summary.db_ping()
    assert result == {"ok": True, "db": True}
    assert pool_timeout_calls == ["db_ping connection timeout"]
    assert pool.attempts == 2


@pytest.mark.anyio
async def test_db_ping_retries_connection_failure(monkeypatch):
    pool = _FlakyPool(["error"])

    async def _fake_get_pool():
        return pool

    failure_calls: list[str] = []

    async def _fake_handle_pool_timeout(reason: str) -> bool:  # noqa: ARG001
        pytest.fail("pool timeout handler should not run")

    async def _fake_handle_connection_failure(exc) -> bool:
        failure_calls.append(str(exc))
        return True

    monkeypatch.setattr(summary, "get_pool", _fake_get_pool)
    monkeypatch.setattr(summary, "handle_pool_timeout", _fake_handle_pool_timeout)
    monkeypatch.setattr(summary, "handle_connection_failure", _fake_handle_connection_failure)

    result = await summary.db_ping()
    assert result == {"ok": True, "db": True}
    assert failure_calls == ["boom"]
    assert pool.attempts == 2
