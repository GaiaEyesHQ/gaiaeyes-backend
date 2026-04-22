from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app
from app.db import get_db
from app.routers import drivers as drivers_router


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
    try:
        transport = ASGITransport(app=app, lifespan="off")
    except TypeError:
        transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_user_drivers_endpoint_returns_snapshot(monkeypatch, client: AsyncClient):
    user_id = str(uuid4())
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": user_id,
    }

    async def _payload(conn, *, user_id: str, day: date):  # noqa: ARG001
        assert day == date(2026, 3, 26)
        return {
            "generated_at": "2026-03-26T12:00:00Z",
            "asof": "2026-03-26T11:55:00Z",
            "day": "2026-03-26",
            "summary": {
                "active_driver_count": 2,
                "total_count": 3,
                "strongest_category": "Space",
                "primary_state": "Strong",
                "note": "Solar Wind is leading right now.",
                "has_personal_patterns": True,
            },
            "has_personal_patterns": True,
            "filters": [
                {"key": "all", "label": "All"},
                {"key": "space", "label": "Space"},
            ],
            "drivers": [
                {
                    "id": "solar_wind",
                    "key": "solar_wind",
                    "source_key": "sw",
                    "aliases": ["solar_wind", "sw"],
                    "label": "Solar Wind",
                    "category": "space",
                    "category_label": "Space",
                    "role": "leading",
                    "role_label": "Leading now",
                    "state": "strong",
                    "state_label": "Strong",
                    "severity": "high",
                    "reading": "720 km/s",
                    "short_reason": "Solar wind speed is elevated right now.",
                    "personal_reason": "Solar wind often matches fatigue for you.",
                    "current_symptoms": ["Fatigue"],
                    "historical_symptoms": ["Fatigue", "Low Energy"],
                    "pattern_status": "strong",
                    "pattern_status_label": "Strong pattern",
                    "pattern_summary": "Elevated solar wind often matches fatigue for you.",
                    "pattern_evidence_count": 1,
                    "pattern_lag_hours": 12,
                    "pattern_refs": [],
                    "outlook_relevance": "24h",
                    "outlook_summary": "Still worth watching over the next 24 hours.",
                    "updated_at": "2026-03-26T11:55:00Z",
                    "asof": "2026-03-26T11:55:00Z",
                    "what_it_is": "The speed and pressure of charged particles flowing from the Sun.",
                    "active_now_text": "Solar wind speed is running near 720 km/s right now.",
                    "science_note": "Higher solar-wind speed can support more noticeable geomagnetic coupling when conditions line up.",
                    "source_hint": "Current environmental signal",
                    "signal_strength": 0.96,
                    "personal_relevance_score": 1.0,
                    "display_score": 1.0,
                    "is_objectively_active": True,
                }
            ],
            "setup_hints": [],
        }

    monkeypatch.setattr(drivers_router, "build_all_drivers_payload", _payload)

    response = await client.get("/v1/users/me/drivers?day=2026-03-26", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["active_driver_count"] == 2
    assert payload["drivers"][0]["key"] == "solar_wind"
    assert payload["drivers"][0]["aliases"] == ["solar_wind", "sw"]


@pytest.mark.anyio
async def test_user_drivers_endpoint_uses_app_day_when_day_is_omitted(monkeypatch, client: AsyncClient):
    user_id = str(uuid4())
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": user_id,
    }

    monkeypatch.setattr(drivers_router, "_default_driver_day", lambda: date(2026, 3, 27))

    async def _payload(conn, *, user_id: str, day: date):  # noqa: ARG001
        assert day == date(2026, 3, 27)
        return {
            "generated_at": "2026-03-27T12:00:00Z",
            "asof": "2026-03-27T11:55:00Z",
            "day": "2026-03-27",
            "summary": {
                "active_driver_count": 0,
                "total_count": 0,
                "strongest_category": None,
                "primary_state": None,
                "note": "Conditions look relatively calm.",
                "has_personal_patterns": False,
            },
            "has_personal_patterns": False,
            "filters": [{"key": "all", "label": "All"}],
            "drivers": [],
            "setup_hints": [],
        }

    monkeypatch.setattr(drivers_router, "build_all_drivers_payload", _payload)

    response = await client.get("/v1/users/me/drivers", headers=headers)
    assert response.status_code == 200
    assert response.json()["day"] == "2026-03-27"
