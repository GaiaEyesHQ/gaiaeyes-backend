from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app
from app.db import get_db
from app.db import feedback as feedback_db
from app.routers import symptoms as symptoms_router


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


@pytest.fixture(autouse=True)
def suppress_background_gauge_refresh(monkeypatch):
    async def _noop(user_id: str, ts_utc: str) -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(symptoms_router, "_refresh_gauges_for_symptom", _noop)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_respond_symptom_follow_up_returns_prompt_and_episode(monkeypatch, client: AsyncClient):
    user_id = str(uuid4())
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": user_id,
    }

    async def _respond(conn, user, prompt_id, **kwargs):  # noqa: ARG001
        assert prompt_id == "prompt-1"
        assert kwargs["state"] == "worse"
        assert kwargs["detail_choice"] == "head_pressure"
        return {
            "prompt": {
                "id": "prompt-1",
                "episode_id": "ep-1",
                "symptom_code": "headache",
                "symptom_label": "Headache",
                "question_text": "Still feeling headache?",
                "detail_focus": "pain",
                "status": "answered",
                "push_delivery_enabled": True,
            },
            "episode": {
                "id": "ep-1",
                "symptom_code": "headache",
                "label": "Headache",
                "current_state": "worse",
                "original_severity": 7,
                "current_severity": 8,
                "started_at": "2026-03-26T09:00:00+00:00",
                "state_updated_at": "2026-03-26T11:00:00+00:00",
                "last_interaction_at": "2026-03-26T11:00:00+00:00",
                "latest_note_text": "Pressure ramped up quickly",
            },
        }

    monkeypatch.setattr(feedback_db, "respond_symptom_follow_up", _respond)

    response = await client.post(
        "/v1/symptoms/follow-ups/prompt-1/respond",
        json={
            "state": "worse",
            "detail_choice": "head_pressure",
            "note_text": "Pressure ramped up quickly",
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["prompt"]["status"] == "answered"
    assert payload["data"]["episode"]["current_state"] == "worse"
    assert payload["data"]["episode"]["note_preview"] == "Pressure ramped up quickly"


@pytest.mark.anyio
async def test_daily_check_in_status_route_returns_prompt_and_settings(monkeypatch, client: AsyncClient):
    user_id = str(uuid4())
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": user_id,
    }

    async def _status(conn, user):  # noqa: ARG001
        return {
            "prompt": {
                "id": "daily-1",
                "prompt_day": "2026-03-25",
                "question_text": "How did yesterday feel?",
                "prompt_payload": {
                    "phase": "next_morning",
                    "active_symptom_labels": ["Headache", "Fatigue"],
                    "recent_symptom_codes": ["headache", "fatigue"],
                    "pain_logged_recently": True,
                    "energy_logged_recently": True,
                    "sleep_logged_recently": True,
                    "suggested_pain_types": ["head_pressure"],
                    "suggested_energy_details": ["brain_fog"],
                    "suggested_mood_types": ["anxious"],
                    "suggested_sleep_impacts": ["yes_somewhat"],
                },
                "status": "pending",
                "push_delivery_enabled": True,
            },
            "latest_entry": {
                "day": "2026-03-24",
                "prompt_id": "daily-0",
                "compared_to_yesterday": "same",
                "energy_level": "manageable",
                "usable_energy": "enough",
                "system_load": "moderate",
                "pain_level": "a_little",
                "mood_level": "calm",
                "completed_at": "2026-03-25T02:00:00+00:00",
            },
            "calibration_summary": {
                "window_days": 21,
                "total_checkins": 4,
                "mostly_right": 2,
                "partly_right": 1,
                "not_really": 1,
                "match_rate": 0.5,
                "resolved_count": 3,
                "improving_count": 2,
                "worse_count": 1,
            },
            "settings": {
                "enabled": True,
                "push_enabled": True,
                "cadence": "balanced",
                "reminder_time": "20:00",
            },
        }

    monkeypatch.setattr(feedback_db, "fetch_daily_check_in_status", _status)

    response = await client.get("/v1/feedback/daily-checkin", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["prompt"]["phase"] == "next_morning"
    assert payload["data"]["prompt"]["suggested_pain_types"] == ["head_pressure"]
    assert payload["data"]["settings"]["push_enabled"] is True
    assert payload["data"]["calibration_summary"]["worse_count"] == 1


@pytest.mark.anyio
async def test_submit_daily_check_in_saves_structured_entry(monkeypatch, client: AsyncClient):
    user_id = str(uuid4())
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": user_id,
    }

    async def _save(conn, user, **kwargs):  # noqa: ARG001
        assert kwargs["day"].isoformat() == "2026-03-25"
        assert kwargs["energy_level"] == "low"
        assert kwargs["usable_energy"] == "limited"
        assert kwargs["system_load"] == "heavy"
        assert kwargs["pain_type"] == "head_pressure"
        assert kwargs["prediction_match"] == "not_really"
        return {
            "day": "2026-03-25",
            "prompt_id": "daily-1",
            "compared_to_yesterday": "worse",
            "energy_level": "low",
            "usable_energy": "limited",
            "system_load": "heavy",
            "pain_level": "strong",
            "pain_type": "head_pressure",
            "energy_detail": "brain_fog",
            "mood_level": "noticeable",
            "mood_type": "anxious",
            "sleep_impact": "yes_somewhat",
            "prediction_match": "not_really",
            "note_text": "Head pressure kept building after lunch.",
            "completed_at": "2026-03-26T01:00:00+00:00",
        }

    monkeypatch.setattr(feedback_db, "save_daily_check_in", _save)

    response = await client.post(
        "/v1/feedback/daily-checkin",
        json={
            "prompt_id": "daily-1",
            "day": "2026-03-25",
            "compared_to_yesterday": "worse",
            "energy_level": "low",
            "usable_energy": "limited",
            "system_load": "heavy",
            "pain_level": "strong",
            "pain_type": "head_pressure",
            "energy_detail": "brain_fog",
            "mood_level": "noticeable",
            "mood_type": "anxious",
            "sleep_impact": "yes_somewhat",
            "prediction_match": "not_really",
            "note_text": "Head pressure kept building after lunch."
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["usable_energy"] == "limited"
    assert payload["data"]["prediction_match"] == "not_really"


@pytest.mark.anyio
async def test_dismiss_daily_check_in_returns_updated_prompt(monkeypatch, client: AsyncClient):
    user_id = str(uuid4())
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": user_id,
    }

    async def _dismiss(conn, user, prompt_id, **kwargs):  # noqa: ARG001
        assert prompt_id == "daily-1"
        assert kwargs["action"] == "snooze"
        assert kwargs["snooze_hours"] == 12
        return {
            "id": "daily-1",
            "prompt_day": "2026-03-25",
            "question_text": "How did yesterday feel?",
            "prompt_payload": {"phase": "next_morning"},
            "status": "snoozed",
            "push_delivery_enabled": True,
        }

    monkeypatch.setattr(feedback_db, "dismiss_daily_check_in", _dismiss)

    response = await client.post(
        "/v1/feedback/daily-checkin/daily-1/dismiss",
        json={"action": "snooze", "snooze_hours": 12},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["status"] == "snoozed"
    assert payload["data"]["phase"] == "next_morning"
