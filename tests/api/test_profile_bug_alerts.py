from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers import profile


@pytest.mark.anyio
async def test_bug_report_alert_uses_smtp_when_configured(monkeypatch):
    sent: list[dict] = []

    def _fake_send(payload, details):
        sent.append({"payload": payload, "details": details})

    monkeypatch.setattr(profile.settings, "BUG_REPORT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(profile.settings, "BUG_REPORT_SMTP_PORT", 587)
    monkeypatch.setattr(profile.settings, "BUG_REPORT_SMTP_USERNAME", "help@gaiaeyes.com")
    monkeypatch.setattr(profile.settings, "BUG_REPORT_SMTP_PASSWORD", "secret")
    monkeypatch.setattr(profile.settings, "BUG_REPORT_SMTP_FROM_EMAIL", "help@gaiaeyes.com")
    monkeypatch.setattr(profile.settings, "BUG_REPORT_ALERT_EMAIL", "help@gaiaeyes.com")
    monkeypatch.setattr(profile.settings, "BUG_REPORT_ALERT_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setattr(profile, "_send_bug_report_smtp_sync", _fake_send)

    ok, error, details = await profile._send_bug_report_alert(
        {
            "report_id": "report-1",
            "description": "Test bug",
            "user_id": "user-1",
            "source": "ios_app",
        }
    )

    assert ok is True
    assert error is None
    assert details["channel"] == "smtp"
    assert details["email_sent"] is True
    assert details["email_to"] == "help@gaiaeyes.com"
    assert sent[0]["payload"]["report_id"] == "report-1"
