from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/gaiaeyes_test")

from app.routers import profile


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None, prepare=False):  # noqa: ARG002
        self.conn.queries.append((str(query), params))


class FakeConn:
    def __init__(self) -> None:
        self.queries: list[tuple[str, object]] = []

    def cursor(self, row_factory=None):  # noqa: ARG002
        return FakeCursor(self)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_profile_notifications_disable_turns_off_tokens_and_queued_events(monkeypatch):
    conn = FakeConn()
    request = SimpleNamespace(state=SimpleNamespace(user_id="user-1"))

    async def _fake_columns(_conn, schema: str, table: str):  # noqa: ARG001
        if (schema, table) == ("app", "user_notification_preferences"):
            return [
                "user_id",
                "enabled",
                "signal_alerts_enabled",
                "local_condition_alerts_enabled",
                "personalized_gauge_alerts_enabled",
                "symptom_followups_enabled",
                "symptom_followup_push_enabled",
                "symptom_followup_cadence",
                "symptom_followup_states",
                "symptom_followup_symptom_codes",
                "daily_checkins_enabled",
                "daily_checkin_push_enabled",
                "daily_checkin_cadence",
                "daily_checkin_reminder_time",
                "quiet_hours_enabled",
                "quiet_start",
                "quiet_end",
                "time_zone",
                "sensitivity",
                "families",
                "created_at",
                "updated_at",
            ]
        return []

    async def _fake_fetch_preferences(_conn, user_id: str):  # noqa: ARG001
        return {"enabled": False}

    monkeypatch.setattr(profile, "_table_columns", _fake_columns)
    monkeypatch.setattr(profile, "_fetch_notification_preferences", _fake_fetch_preferences)

    result = await profile.profile_notifications_upsert(
        profile.NotificationPreferencesIn(enabled=False),
        request,
        conn=conn,
    )

    assert result == {"ok": True, "preferences": {"enabled": False}}
    assert len(conn.queries) == 3
    assert "insert into app.user_notification_preferences" in conn.queries[0][0].lower()
    assert "update app.user_push_tokens" in conn.queries[1][0].lower()
    assert "update content.push_notification_events" in conn.queries[2][0].lower()


@pytest.mark.anyio
async def test_profile_notifications_enable_does_not_disable_tokens(monkeypatch):
    conn = FakeConn()
    request = SimpleNamespace(state=SimpleNamespace(user_id="user-1"))

    async def _fake_columns(_conn, schema: str, table: str):  # noqa: ARG001
        if (schema, table) == ("app", "user_notification_preferences"):
            return [
                "user_id",
                "enabled",
                "signal_alerts_enabled",
                "local_condition_alerts_enabled",
                "personalized_gauge_alerts_enabled",
                "quiet_hours_enabled",
                "quiet_start",
                "quiet_end",
                "daily_checkin_reminder_time",
                "time_zone",
                "sensitivity",
                "families",
                "created_at",
                "updated_at",
            ]
        return []

    async def _fake_fetch_preferences(_conn, user_id: str):  # noqa: ARG001
        return {"enabled": True}

    monkeypatch.setattr(profile, "_table_columns", _fake_columns)
    monkeypatch.setattr(profile, "_fetch_notification_preferences", _fake_fetch_preferences)

    result = await profile.profile_notifications_upsert(
        profile.NotificationPreferencesIn(enabled=True),
        request,
        conn=conn,
    )

    assert result == {"ok": True, "preferences": {"enabled": True}}
    assert len(conn.queries) == 1
    assert "insert into app.user_notification_preferences" in conn.queries[0][0].lower()
