from __future__ import annotations

from datetime import datetime, timezone

from scripts import post_launch_monitor as monitor


def _healthy_payload(**queue_overrides):
    queue = {
        "enabled": True,
        "redis_enabled": True,
        "redis_depth": 0,
        "redis_error": None,
        "active_writes": 0,
        "max_active_writes": 4,
        "backlog_batches": 0,
    }
    queue.update(queue_overrides)
    return {
        "ok": True,
        "db": True,
        "db_sticky_age": 1000,
        "monitor": {
            "consec_fail": 0,
            "last_probe": datetime.now(timezone.utc).isoformat(),
            "pool": {"waiting": 0},
        },
        "ingest_queue": queue,
    }


def test_backend_health_reports_ingest_queue(monkeypatch):
    monkeypatch.setattr(monitor, "QUEUE_DEPTH_WARN", 0)
    monkeypatch.setattr(monitor, "_get_json", lambda path: _healthy_payload())

    result = monitor.check_backend_health()

    assert result.status == "pass"
    assert "redis_depth=0" in result.detail
    assert "backlog_batches=0" in result.detail
    assert "active_writes=0/4" in result.detail


def test_backend_health_warns_when_redis_queue_has_backlog(monkeypatch):
    monkeypatch.setattr(monitor, "QUEUE_DEPTH_WARN", 0)
    monkeypatch.setattr(monitor, "_get_json", lambda path: _healthy_payload(redis_depth=2))

    result = monitor.check_backend_health()

    assert result.status == "warn"
    assert "redis_depth=2" in result.detail


def test_backend_health_warns_when_queue_status_missing(monkeypatch):
    payload = _healthy_payload()
    payload.pop("ingest_queue")
    monkeypatch.setattr(monitor, "_get_json", lambda path: payload)

    result = monitor.check_backend_health()

    assert result.status == "warn"
    assert "ingest_queue missing" in result.detail


def test_features_today_skips_without_dev_user_id(monkeypatch):
    monkeypatch.setattr(monitor, "AUTH_BEARER", "token")
    monkeypatch.setattr(monitor, "DEV_USER_ID", "")

    result = monitor.check_features_today()

    assert result.status == "skip"
    assert "GAIA_MONITOR_DEV_USER_ID" in result.detail


def test_user_outlook_skips_without_dev_user_id(monkeypatch):
    monkeypatch.setattr(monitor, "AUTH_BEARER", "token")
    monkeypatch.setattr(monitor, "DEV_USER_ID", "")

    result = monitor.check_user_outlook()

    assert result.status == "skip"
    assert "GAIA_MONITOR_DEV_USER_ID" in result.detail
