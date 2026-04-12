from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.db import settings
from app.routers import analytics


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _set_dev_bearer():
    original = settings.DEV_BEARER
    settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        settings.DEV_BEARER = original


class _RecordingCursor:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.rowcount = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, values=None, **kwargs):  # noqa: ARG002
        self.calls.append((str(query), tuple(values or ())))


class _RecordingConn:
    def __init__(self):
        self.cursor_instance = _RecordingCursor()

    def cursor(self, *args, **kwargs):  # noqa: ARG002
        return self.cursor_instance


@pytest.fixture
def recording_conn():
    return _RecordingConn()


@pytest.fixture
async def client(recording_conn: _RecordingConn):
    app = FastAPI()
    app.include_router(analytics.router)

    async def _override_get_db():
        yield recording_conn

    app.dependency_overrides[analytics.get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_safe_properties_allowlists_expected_keys_only():
    safe = analytics._safe_properties(
        {
            "surface": "onboarding",
            "driver_key": "solar_wind",
            "pain_type": "nerve",
            "note_text": "private note",
            "count": "123",
        }
    )
    assert safe == {
        "surface": "onboarding",
        "driver_key": "solar_wind",
        "count": "123",
    }


@pytest.mark.anyio
async def test_ingest_analytics_uses_authenticated_user_and_sanitizes_properties(
    client: AsyncClient,
    recording_conn: _RecordingConn,
):
    user_id = str(uuid4())
    payload = {
        "events": [
            {
                "client_event_id": "event-1",
                "event_name": "onboarding_started",
                "event_ts_utc": "2026-04-11T23:35:29.000Z",
                "platform": "ios",
                "app_version": "1.2.3",
                "device_model": "iPhone",
                "session_id": "session-1",
                "properties": {
                    "surface": "onboarding",
                    "driver_key": "solar_wind",
                    "pain_type": "nerve",
                    "note_text": "private note",
                },
            }
        ]
    }

    resp = await client.post(
        "/v1/analytics/events",
        headers={
            "Authorization": "Bearer test-token",
            "X-Dev-UserId": user_id,
        },
        json=payload,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["received"] == 1
    assert body["inserted"] == 1

    assert len(recording_conn.cursor_instance.calls) == 1
    _, values = recording_conn.cursor_instance.calls[0]
    assert values[0] == user_id
    assert values[1] == "event-1"
    assert values[2] == "onboarding_started"
    assert values[8] == "onboarding"
    assert json.loads(values[9]) == {
        "driver_key": "solar_wind",
        "surface": "onboarding",
    }
