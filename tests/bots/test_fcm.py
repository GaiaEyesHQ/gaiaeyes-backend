from __future__ import annotations

from bots.notifications import fcm


class _Credentials:
    token = "access-token"

    def refresh(self, _request) -> None:
        return None


class _Response:
    ok = True
    status_code = 200
    text = '{"name":"projects/test/messages/1"}'

    def json(self):
        return {"name": "projects/test/messages/1"}


def test_fcm_uses_data_message_for_background_tap_routing(monkeypatch):
    captured = {}

    def _post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(fcm.requests, "post", _post)
    client = fcm.FcmClient(project_id="test-project", credentials=_Credentials())

    result = client.send(
        device_token="android-token",
        title="Gaia Eyes",
        body="Open today’s read.",
        data={"deep_link": "gaiaeyes://mission-control?family=gauge_spikes"},
    )

    assert result["ok"] is True
    message = captured["json"]["message"]
    assert "notification" not in message
    assert message["data"] == {
        "title": "Gaia Eyes",
        "body": "Open today’s read.",
        "deep_link": "gaiaeyes://mission-control?family=gauge_spikes",
    }
    assert message["android"] == {"priority": "high"}
