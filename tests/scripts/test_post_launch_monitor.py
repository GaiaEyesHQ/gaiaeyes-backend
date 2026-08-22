from __future__ import annotations

from http.client import IncompleteRead
from datetime import datetime, timedelta, timezone

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


def test_user_outlook_passes_with_space_only_drivers(monkeypatch):
    monkeypatch.setattr(monitor, "AUTH_BEARER", "token")
    monkeypatch.setattr(monitor, "DEV_USER_ID", "user-123")
    monkeypatch.setattr(
        monitor,
        "_get_json",
        lambda path, **kwargs: {
            "daily_outlook": [
                {
                    "label": "Tomorrow",
                    "top_drivers": [
                        {"key": "kp"},
                        {"key": "solar_wind"},
                        {"key": "cme"},
                    ],
                }
            ]
        },
    )

    result = monitor.check_user_outlook()

    assert result.status == "pass"
    assert "domain=space" in result.detail
    assert "kp" in result.detail


def test_local_forecast_warns_when_current_conditions_are_stale(monkeypatch):
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(minutes=45)).isoformat()
    monkeypatch.setattr(monitor, "LOCAL_CURRENT_WARN_MS", 30 * 60 * 1000)
    monkeypatch.setattr(
        monitor,
        "_get_json",
        lambda path, **kwargs: {
            "forecast_daily": [{"day": "2026-08-21"}],
            "allergens": {},
            "asof": stale,
            "weather": {"obs_time": stale},
        },
    )

    result = monitor.check_local_forecast()

    assert result.status == "warn"
    assert "weather_obs_age_minutes=45" in result.detail
    assert "local_asof_age_minutes=45" in result.detail


def test_local_forecast_passes_when_current_conditions_are_recent(monkeypatch):
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(minutes=5)).isoformat()
    monkeypatch.setattr(monitor, "LOCAL_CURRENT_WARN_MS", 30 * 60 * 1000)
    monkeypatch.setattr(
        monitor,
        "_get_json",
        lambda path, **kwargs: {
            "forecast_daily": [{"day": "2026-08-21"}],
            "allergens": {},
            "asof": fresh,
            "weather": {"obs_time": fresh},
        },
    )

    result = monitor.check_local_forecast()

    assert result.status == "pass"
    assert "weather_obs_age_minutes=5" in result.detail
    assert "local_asof_age_minutes=5" in result.detail


def test_get_json_retries_incomplete_read_once(monkeypatch):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok": true}'

    attempts = {"count": 0}

    def _fake_urlopen(request, timeout):  # noqa: ARG001
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise IncompleteRead(b"partial", 5)
        return _Response()

    monkeypatch.setattr(monitor, "REQUEST_RETRIES", 2)
    monkeypatch.setattr(monitor, "REQUEST_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(monitor.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(monitor.urllib.request, "urlopen", _fake_urlopen)

    result = monitor._get_json("/health")

    assert result == {"ok": True}
    assert attempts["count"] == 2
