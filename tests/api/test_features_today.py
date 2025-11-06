import asyncio
from datetime import date, datetime, timezone
from typing import List
from uuid import uuid4

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
    transport = ASGITransport(app=app)
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


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_refresh_scheduled_on_ingest(monkeypatch, client: AsyncClient):
    ingest._refresh_registry.clear()
    ingest._recent_refresh_requests.clear()
    monkeypatch.setattr(summary, "_REFRESH_DELAY_RANGE", (0.0, 0.0))

    fake_pool = _FakePool()

    async def _fake_get_pool():
        return fake_pool

    scheduled: List[tuple[str, date]] = []

    async def _fake_execute_refresh(user_id: str, day_local: date) -> None:
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
    assert scheduled_day == ingest._today_local(ZoneInfo("UTC"))


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
    assert data["diagnostics"]["source"] == "yesterday"
    assert data["diagnostics"]["day_used"] == yesterday.isoformat()


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
    assert diag["error"] == "boom"
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
    assert diag["error"] == "database unavailable"


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
    assert diag["error"] == "db_timeout"
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
