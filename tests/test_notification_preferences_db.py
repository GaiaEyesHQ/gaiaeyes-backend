from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import feedback as feedback_db
from app.db import symptoms as symptoms_db


class FakeCursor:
    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None, prepare=False):  # noqa: ARG002
        return None

    async def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, row):
        self.row = row

    def cursor(self, row_factory=None):  # noqa: ARG002
        return FakeCursor(self.row)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_load_feedback_preferences_does_not_infer_push_from_family_when_notifications_off(monkeypatch):
    row = {
        "enabled": False,
        "quiet_hours_enabled": False,
        "quiet_start": "22:00",
        "quiet_end": "08:00",
        "time_zone": "UTC",
        "families": {"symptom_followups": True, "daily_checkins": True},
        "symptom_followups_enabled": True,
        "symptom_followup_push_enabled": False,
        "symptom_followup_cadence": "balanced",
        "symptom_followup_states": ["new"],
        "symptom_followup_symptom_codes": [],
        "daily_checkins_enabled": True,
        "daily_checkin_push_enabled": False,
        "daily_checkin_cadence": "balanced",
        "daily_checkin_reminder_time": "20:00",
    }
    conn = FakeConn(row)

    async def _fake_columns(_conn, schema: str, table: str):  # noqa: ARG001
        if (schema, table) == ("app", "user_notification_preferences"):
            return [
                "enabled",
                "quiet_hours_enabled",
                "quiet_start",
                "quiet_end",
                "time_zone",
                "families",
                "symptom_followups_enabled",
                "symptom_followup_push_enabled",
                "symptom_followup_cadence",
                "symptom_followup_states",
                "symptom_followup_symptom_codes",
                "daily_checkins_enabled",
                "daily_checkin_push_enabled",
                "daily_checkin_cadence",
                "daily_checkin_reminder_time",
            ]
        return []

    monkeypatch.setattr(feedback_db, "_table_columns", _fake_columns)

    prefs = await feedback_db.load_feedback_preferences(conn, "user-1")

    assert prefs["notifications_enabled"] is False
    assert prefs["symptom_followup_push_enabled"] is False
    assert prefs["daily_checkin_push_enabled"] is False


@pytest.mark.anyio
async def test_fetch_symptom_follow_up_settings_does_not_infer_push_from_family_when_notifications_off(monkeypatch):
    row = {
        "enabled": False,
        "families": {"symptom_followups": True},
        "symptom_followups_enabled": True,
        "symptom_followup_cadence": "balanced",
        "symptom_followup_push_enabled": False,
        "symptom_followup_states": ["new"],
        "symptom_followup_symptom_codes": [],
    }
    conn = FakeConn(row)

    async def _fake_columns(_conn, schema: str, table: str):  # noqa: ARG001
        if (schema, table) == ("app", "user_notification_preferences"):
            return [
                "enabled",
                "families",
                "symptom_followups_enabled",
                "symptom_followup_cadence",
                "symptom_followup_push_enabled",
                "symptom_followup_states",
                "symptom_followup_symptom_codes",
            ]
        return []

    monkeypatch.setattr(symptoms_db, "_table_columns", _fake_columns)

    settings = await symptoms_db.fetch_symptom_follow_up_settings(conn, "user-1")

    assert settings["notifications_enabled"] is False
    assert settings["notification_family_enabled"] is True
    assert settings["push_enabled"] is False
