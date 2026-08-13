from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.notifications import send_push_notifications as push_send


def _queued_event() -> dict[str, object]:
    return {
        "id": "evt-1",
        "user_id": "user-1",
        "family": "pressure",
        "event_key": "pressure_drop",
        "title": "Pressure changed",
        "body": "Open Gaia Eyes.",
        "payload": {"route": "local"},
        "dedupe_key": "k1",
    }


def test_send_push_notifications_skips_when_notifications_are_currently_disabled(monkeypatch):
    marked: list[tuple[str, str, str | None]] = []
    fetch_user_tokens_called = False

    def _fake_fetch_queued_events(limit=None, user_id=None):  # noqa: ARG001
        return [_queued_event()]

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


def test_send_push_notifications_routes_android_tokens_through_fcm(monkeypatch):
    marked: list[tuple[str, str, str | None]] = []
    sent: list[dict[str, object]] = []

    class _FakeFcmClient:
        def send(self, **kwargs):
            sent.append(kwargs)
            return {"ok": True, "status_code": 200, "body": {"name": "message-1"}}

    class _FakeFcmFactory:
        @classmethod
        def from_environment(cls):
            return _FakeFcmClient()

    monkeypatch.setattr(push_send, "_fetch_queued_events", lambda **kwargs: [_queued_event()])
    monkeypatch.setattr(push_send, "_notifications_enabled", lambda user_id: True)
    monkeypatch.setattr(
        push_send,
        "_fetch_user_tokens",
        lambda user_id: [
            {
                "id": "token-1",
                "platform": "android",
                "device_token": "android-token",
                "environment": "prod",
            }
        ],
    )
    monkeypatch.setattr(
        push_send,
        "_mark_event_status",
        lambda event_id, status, now_utc, error_text=None: marked.append(
            (event_id, status, error_text)
        ),
    )
    monkeypatch.setattr(push_send, "FcmClient", _FakeFcmFactory)
    monkeypatch.setattr(sys, "argv", ["send_push_notifications.py"])

    push_send.main()

    assert marked == [("evt-1", "sent", None)]
    assert sent == [
        {
            "device_token": "android-token",
            "title": "Pressure changed",
            "body": "Open Gaia Eyes.",
            "data": {"route": "local", "family": "pressure", "event_id": "evt-1"},
        }
    ]


def test_send_push_notifications_disables_unregistered_android_token(monkeypatch):
    marked: list[tuple[str, str, str | None]] = []
    disabled: list[tuple[str, str]] = []

    class _FakeFcmClient:
        def send(self, **kwargs):  # noqa: ARG002
            return {
                "ok": False,
                "status_code": 404,
                "body": {
                    "error": {
                        "status": "NOT_FOUND",
                        "details": [{"errorCode": "UNREGISTERED"}],
                    }
                },
            }

    class _FakeFcmFactory:
        @classmethod
        def from_environment(cls):
            return _FakeFcmClient()

    monkeypatch.setattr(push_send, "_fetch_queued_events", lambda **kwargs: [_queued_event()])
    monkeypatch.setattr(push_send, "_notifications_enabled", lambda user_id: True)
    monkeypatch.setattr(
        push_send,
        "_fetch_user_tokens",
        lambda user_id: [
            {
                "id": "token-1",
                "platform": "android",
                "device_token": "expired-token",
                "environment": "prod",
            }
        ],
    )
    monkeypatch.setattr(
        push_send,
        "_mark_event_status",
        lambda event_id, status, now_utc, error_text=None: marked.append(
            (event_id, status, error_text)
        ),
    )
    monkeypatch.setattr(
        push_send,
        "_disable_token",
        lambda token_id, reason, now_utc: disabled.append((token_id, reason)),
    )
    monkeypatch.setattr(push_send, "FcmClient", _FakeFcmFactory)
    monkeypatch.setattr(sys, "argv", ["send_push_notifications.py"])

    push_send.main()

    assert disabled == [("token-1", "UNREGISTERED")]
    assert marked == [("evt-1", "failed", "UNREGISTERED")]
