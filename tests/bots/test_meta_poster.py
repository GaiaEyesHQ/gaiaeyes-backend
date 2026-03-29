import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post import meta_poster


class FakeResponse:
    def __init__(self, status_code, payload=None, *, headers=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        if text is not None:
            self.text = text
        elif payload is None:
            self.text = ""
        else:
            self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def close(self):
        return None


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise AssertionError("No fake responses left")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_graph_request_retries_transient_oauth_exception(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse(
                500,
                {
                    "error": {
                        "message": "An unexpected error has occurred. Please retry your request later.",
                        "type": "OAuthException",
                        "is_transient": True,
                        "code": 2,
                    }
                },
            ),
            FakeResponse(200, {"id": "child_123"}),
        ]
    )
    monkeypatch.setattr(meta_poster, "session", fake_session)
    monkeypatch.setattr(meta_poster.time, "sleep", lambda _: None)

    result = meta_poster._graph_request(
        "IG carousel child 1",
        "POST",
        "178414/media",
        data={"image_url": "https://example.com/card.jpg"},
        attempts=2,
    )

    assert result["payload"]["id"] == "child_123"
    assert result["retry_count"] == 1
    assert len(fake_session.calls) == 2


def test_preflight_media_url_rejects_wrong_content_type(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse(
                200,
                {},
                headers={"Content-Type": "text/html", "Content-Length": "128"},
            )
        ]
    )
    monkeypatch.setattr(meta_poster, "session", fake_session)

    with pytest.raises(RuntimeError, match="Unexpected content-type"):
        meta_poster.preflight_media_url("https://example.com/not-an-image", "image")


def test_poll_ig_container_waits_until_finished(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse(200, {"id": "cid", "status_code": "IN_PROGRESS", "status": "Processing"}),
            FakeResponse(200, {"id": "cid", "status_code": "FINISHED", "status": "Finished"}),
        ]
    )
    monkeypatch.setattr(meta_poster, "session", fake_session)
    monkeypatch.setattr(meta_poster, "FB_ACCESS_TOKEN", "token")
    monkeypatch.setattr(meta_poster.time, "sleep", lambda _: None)

    poll = meta_poster._poll_ig_container("cid", "IG reel")

    assert poll.ready is True
    assert poll.terminal_status == "FINISHED"
    assert poll.attempts == 2


def test_ig_post_carousel_falls_back_to_single_image(monkeypatch):
    monkeypatch.setattr(meta_poster, "FB_PAGE_ID", "123")
    monkeypatch.setattr(meta_poster, "FB_ACCESS_TOKEN", "token")
    monkeypatch.setattr(meta_poster, "IG_USER_ID", "456")
    monkeypatch.setattr(meta_poster, "IG_CAROUSEL_SINGLE_IMAGE_FALLBACK", True)
    monkeypatch.setattr(
        meta_poster,
        "preflight_media_url",
        lambda url, media_type: {"url": url, "status_code": 200, "content_type": "image/jpeg"},
    )

    def fake_graph_request(label, method, path, **kwargs):
        raise meta_poster.MetaGraphError(
            f"{label} failed",
            status_code=500,
            payload={"error": {"is_transient": True, "type": "OAuthException", "code": 2}},
            retryable=True,
        )

    monkeypatch.setattr(meta_poster, "_graph_request", fake_graph_request)
    monkeypatch.setattr(
        meta_poster,
        "ig_post_single_image",
        lambda image_url, caption, dry_run=False: {
            "platform": "instagram",
            "media_type": "image",
            "success": True,
            "status": "success",
            "post_id": "ig_fallback_post",
            "container_id": "ig_fallback_container",
            "fallback_used": None,
            "retry_count": 0,
            "terminal_error": None,
            "detail": {"image_url": image_url, "caption": caption},
        },
    )

    result = meta_poster.ig_post_carousel(
        [
            "https://example.com/daily_stats.jpg",
            "https://example.com/daily_affects.jpg",
            "https://example.com/daily_playbook.jpg",
        ],
        "caption",
        dry_run=False,
    )

    assert result["success"] is True
    assert result["media_type"] == "image"
    assert result["fallback_used"] == "single_image_from_carousel"
    assert result["post_id"] == "ig_fallback_post"


def test_ig_post_reel_recreates_after_terminal_error(monkeypatch):
    monkeypatch.setattr(meta_poster, "FB_PAGE_ID", "123")
    monkeypatch.setattr(meta_poster, "FB_ACCESS_TOKEN", "token")
    monkeypatch.setattr(meta_poster, "IG_USER_ID", "456")
    monkeypatch.setattr(meta_poster, "IG_REEL_CREATE_CYCLES", 2)
    monkeypatch.setattr(meta_poster.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        meta_poster,
        "preflight_media_url",
        lambda url, media_type: {
            "url": url,
            "status_code": 200,
            "content_type": "video/mp4" if media_type == "reel" else "image/jpeg",
        },
    )

    graph_responses = [
        {"payload": {"id": "container_1"}, "status_code": 200, "attempts": 1, "retry_count": 0},
        {"payload": {"id": "container_2"}, "status_code": 200, "attempts": 1, "retry_count": 0},
        {"payload": {"id": "ig_post_42"}, "status_code": 200, "attempts": 1, "retry_count": 0},
    ]

    def fake_graph_request(label, method, path, **kwargs):
        if not graph_responses:
            raise AssertionError(f"Unexpected Graph request: {label}")
        return graph_responses.pop(0)

    polls = [
        meta_poster.PollResult(False, "ERROR", 2, 10.0, {"status_code": "ERROR"}),
        meta_poster.PollResult(True, "FINISHED", 3, 18.0, {"status_code": "FINISHED"}),
    ]

    monkeypatch.setattr(meta_poster, "_graph_request", fake_graph_request)
    monkeypatch.setattr(meta_poster, "_poll_ig_container", lambda container_id, label: polls.pop(0))

    result = meta_poster.ig_post_reel(
        "https://example.com/reel.mp4",
        "caption",
        cover_url="https://example.com/cover.jpg",
        dry_run=False,
    )

    assert result["success"] is True
    assert result["post_id"] == "ig_post_42"
    assert result["container_id"] == "container_2"
    assert result["detail"]["poll_cycle_1"]["terminal_status"] == "ERROR"
    assert result["detail"]["poll_cycle_2"]["terminal_status"] == "FINISHED"
