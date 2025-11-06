from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.db import get_db, symptoms as symptoms_db  # noqa: E402

UTC = timezone.utc


class RecordingStore:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.counter = 0

    def insert(
        self,
        user_id: str,
        *,
        symptom_code: str,
        ts_utc: Optional[datetime] = None,
        severity: Optional[int] = None,
        free_text: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
    ) -> dict:
        self.counter += 1
        ts_value = ts_utc
        if ts_value is None:
            ts_value = datetime(2024, 1, 1, tzinfo=UTC)
        elif ts_value.tzinfo is None:
            ts_value = ts_value.replace(tzinfo=UTC)
        else:
            ts_value = ts_value.astimezone(UTC)
        event = {
            "id": f"evt-{self.counter}",
            "user_id": user_id,
            "symptom_code": symptom_code,
            "ts_utc": ts_value,
            "severity": severity,
            "free_text": free_text,
            "tags": list(tags or []),
        }
        self.events.append(event)
        return {"id": event["id"], "ts_utc": ts_value.isoformat()}


@pytest.fixture(autouse=True)
def override_dev_bearer():
    from app import db

    original = db.settings.DEV_BEARER
    db.settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        db.settings.DEV_BEARER = original


@pytest.fixture(autouse=True)
def override_db_dependency():
    async def _fake_db():
        yield object()

    app.dependency_overrides[get_db] = _fake_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def recording_store(monkeypatch):
    store = RecordingStore()

    async def _insert(conn, user_id, **kwargs):  # noqa: ARG001
        return store.insert(user_id, **kwargs)

    async def _codes(conn, include_inactive=True):  # noqa: ARG001
        return [
            {
                "symptom_code": "NERVE_PAIN",
                "label": "Nerve pain",
                "description": None,
                "is_active": True,
            },
            {
                "symptom_code": "OTHER",
                "label": "Other",
                "description": None,
                "is_active": True,
            },
        ]

    monkeypatch.setattr(symptoms_db, "insert_symptom_event", _insert)
    monkeypatch.setattr(symptoms_db, "fetch_symptom_codes", _codes)

    return store


@pytest.mark.anyio
async def test_normalizes_variants(client: AsyncClient, recording_store: RecordingStore):
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": "00000000-0000-0000-0000-000000000001",
    }

    payload = {"symptom_code": "nerve pain"}
    response = await client.post("/v1/symptoms", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert recording_store.events[0]["symptom_code"] == "NERVE_PAIN"

    payload_dash = {"symptom_code": "nerve-pain"}
    response_dash = await client.post("/v1/symptoms", json=payload_dash, headers=headers)
    assert response_dash.status_code == 200
    assert recording_store.events[1]["symptom_code"] == "NERVE_PAIN"


@pytest.mark.anyio
async def test_unknown_strict_vs_default(client: AsyncClient, recording_store: RecordingStore):
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": "00000000-0000-0000-0000-000000000002",
    }

    strict_response = await client.post(
        "/v1/symptoms?strict=1",
        json={"symptom_code": "mystery"},
        headers=headers,
    )
    assert strict_response.status_code == 400
    strict_data = strict_response.json()
    assert strict_data["ok"] is False
    assert strict_data["error"] == "unknown symptom_code"
    assert "valid" in strict_data and "NERVE_PAIN" in strict_data["valid"]
    assert not recording_store.events

    relaxed_response = await client.post(
        "/v1/symptoms",
        json={"symptom_code": "mystery"},
        headers=headers,
    )
    assert relaxed_response.status_code == 200
    relaxed_data = relaxed_response.json()
    assert relaxed_data["ok"] is True
    assert recording_store.events[0]["symptom_code"] == "OTHER"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path, attr, expected_error",
    [
        ("/v1/symptoms/codes", "fetch_symptom_codes", "Failed to load symptom codes"),
        ("/v1/symptoms/today", "fetch_symptoms_today", "Failed to load today's symptoms"),
        ("/v1/symptoms/daily", "fetch_daily_summary", "Failed to load daily symptom summary"),
        ("/v1/symptoms/diag", "fetch_diagnostics", "Failed to load diagnostic summary"),
    ],
)
async def test_symptom_routes_wrap_db_errors(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    attr: str,
    expected_error: str,
):
    async def _boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("db boom")

    monkeypatch.setattr(symptoms_db, attr, _boom)

    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": "00000000-0000-0000-0000-000000000123",
    }

    response = await client.get(path, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] == []
    assert payload["error"] == expected_error


@pytest.mark.anyio
async def test_post_symptom_returns_normalized_error(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": "00000000-0000-0000-0000-000000000001",
    }

    async def _codes(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("no db")

    monkeypatch.setattr(symptoms_db, "fetch_symptom_codes", _codes)

    response = await client.post("/v1/symptoms", json={"symptom_code": "nerve_pain"}, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"] == "Failed to load symptom codes"


@pytest.mark.anyio
async def test_post_symptom_insert_failure_returns_safe_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": "00000000-0000-0000-0000-000000000001",
    }

    async def _codes(*args, **kwargs):  # noqa: ARG001
        return [
            {
                "symptom_code": "HEADACHE",
                "label": "Headache",
                "description": "",
                "is_active": True,
            }
        ]

    async def _boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("db down")

    monkeypatch.setattr(symptoms_db, "fetch_symptom_codes", _codes)
    monkeypatch.setattr(symptoms_db, "insert_symptom_event", _boom)

    response = await client.post(
        "/v1/symptoms",
        json={"symptom_code": "headache"},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"] == "Failed to record symptom event"
