from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.notifications import send_push_notifications as push_send


def test_send_push_notifications_skips_when_notifications_are_currently_disabled(monkeypatch):
    marked: list[tuple[str, str, str | None]] = []
    fetch_user_tokens_called = False

    def _fake_fetch_queued_events(limit=None, user_id=None):  # noqa: ARG001
        return [
            {
                "id": "evt-1",
                "user_id": "user-1",
                "family": "pressure",
                "event_key": "pressure_drop",
                "title": "Pressure changed",
                "body": "Open Gaia Eyes.",
                "payload": {},
                "dedupe_key": "k1",
            }
        ]

    def _fake_notifications_enabled(user_id: str) -> bool:  # noqa: ARG001
        return False

    def _fake_mark_event_status(event_id: str, status: str, now_utc, error_text: str | None = None):  # noqa: ARG001
        marked.append((event_id, status, error_text))

    def _fake_fetch_user_tokens(user_id: str):  # noqa: ARG001
        nonlocal fetch_user_tokens_called
        fetch_user_tokens_called = True
        return []

    monkeypatch.setattr(push_send, "_fetch_queued_events", _fake_fetch_queued_events)
    monkeypatch.setattr(push_send, "_notifications_enabled", _fake_notifications_enabled)
    monkeypatch.setattr(push_send, "_mark_event_status", _fake_mark_event_status)
    monkeypatch.setattr(push_send, "_fetch_user_tokens", _fake_fetch_user_tokens)
    monkeypatch.setattr(push_send, "_missing_apns_env", lambda: [])
    monkeypatch.setattr(push_send, "_required_env", lambda name: f"test-{name}")
    monkeypatch.setattr(push_send, "create_provider_token", lambda **kwargs: "provider-token")
    monkeypatch.setattr(push_send, "send_apns_notification", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(sys, "argv", ["send_push_notifications.py"])

    push_send.main()

    assert marked == [("evt-1", "skipped", "notifications_disabled")]
    assert fetch_user_tokens_called is False
