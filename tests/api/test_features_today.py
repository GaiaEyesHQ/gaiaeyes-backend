import asyncio
from datetime import date, datetime
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
from app.db import get_db, settings
from app.routers import ingest, summary


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
    assert scheduled, "refresh task should be scheduled"
    scheduled_user, scheduled_day = scheduled[0]
    assert scheduled_user == user_id
    assert scheduled_day == ingest._today_local(ZoneInfo("UTC"))


@pytest.mark.anyio
async def test_features_fallback_to_yesterday(monkeypatch, client: AsyncClient):
    async def _fake_db():
        yield _FakeConn()

    app.dependency_overrides[get_db] = _fake_db

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
    try:
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
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_features_error_envelope(monkeypatch, client: AsyncClient):
    async def _fake_db():
        yield _FakeConn()

    app.dependency_overrides[get_db] = _fake_db

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

    user_id = str(uuid4())
    try:
        resp = await client.get(
            "/v1/features/today",
            headers={"Authorization": "Bearer test-token", "X-Dev-UserId": user_id},
            params={"tz": "UTC"},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is False
        assert payload["data"] == {}
        assert payload["error"] == "boom"
        assert payload["diagnostics"]["source"] == "empty"
    finally:
        app.dependency_overrides.pop(get_db, None)
