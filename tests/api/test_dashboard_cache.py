from __future__ import annotations

import time
from datetime import date
from types import SimpleNamespace

import pytest

from app.routers import dashboard as dashboard_router

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture(autouse=True)
def clear_dashboard_route_cache():
    dashboard_router._dashboard_cache.clear()
    dashboard_router._dashboard_build_locks.clear()
    dashboard_router._dashboard_refresh_tasks.clear()
    try:
        yield
    finally:
        dashboard_router._dashboard_cache.clear()
        dashboard_router._dashboard_build_locks.clear()
        dashboard_router._dashboard_refresh_tasks.clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_dashboard_cache_env_int_falls_back_for_invalid_value(monkeypatch):
    monkeypatch.setenv("GAIA_DASHBOARD_CACHE_TTL_SECONDS", "not-an-int")

    assert dashboard_router._env_int("GAIA_DASHBOARD_CACHE_TTL_SECONDS", 300) == 300


@pytest.mark.anyio
async def test_dashboard_cache_returns_payload_copy(monkeypatch):
    monkeypatch.setattr(dashboard_router, "_DASHBOARD_CACHE_TTL_SECONDS", 60)
    payload = {"day": "2026-04-26", "gauges": {"sleep": 39}}

    await dashboard_router._set_cached_dashboard("user-1", date(2026, 4, 26), payload)
    cached, age, stale = await dashboard_router._get_cached_dashboard("user-1", date(2026, 4, 26))
    assert cached is not None
    assert age >= 0
    assert stale is False

    cached["gauges"]["sleep"] = 99
    cached_again, _, _ = await dashboard_router._get_cached_dashboard("user-1", date(2026, 4, 26))
    assert cached_again is not None
    assert cached_again["gauges"]["sleep"] == 39


@pytest.mark.anyio
async def test_dashboard_cache_can_return_stale_payload(monkeypatch):
    monkeypatch.setattr(dashboard_router, "_DASHBOARD_CACHE_TTL_SECONDS", 60)
    monkeypatch.setattr(dashboard_router, "_DASHBOARD_STALE_TTL_SECONDS", 600)
    target_day = date(2026, 4, 26)
    payload = {"day": target_day.isoformat(), "gauges": {"sleep": 39}}

    await dashboard_router._set_cached_dashboard("user-1", target_day, payload)
    async with dashboard_router._dashboard_cache_lock:
        dashboard_router._dashboard_cache[("user-1", target_day.isoformat())] = (
            time.monotonic() - 120,
            payload,
        )

    cached, age, stale = await dashboard_router._get_cached_dashboard(
        "user-1",
        target_day,
        allow_stale=True,
    )

    assert cached == payload
    assert age >= 120
    assert stale is True


def test_attach_dashboard_freshness_preserves_payload_and_adds_contract():
    target_day = date(2026, 4, 26)
    payload = {"day": target_day.isoformat(), "gauges": {"sleep": 39}}

    out = dashboard_router._attach_dashboard_freshness(
        payload,
        day=target_day,
        source="stale_cache",
        cache_hit=True,
        cache_age_seconds=366.44,
        stale=True,
        refresh_scheduled=True,
    )

    assert payload == {"day": target_day.isoformat(), "gauges": {"sleep": 39}}
    assert out["gauges"] == {"sleep": 39}
    assert out["cache_hit"] is True
    assert out["cache_age_seconds"] == 366.4
    assert out["stale"] is True
    assert out["refresh_scheduled"] is True
    assert out["freshness"]["dashboard"]["kind"] == "dashboard"
    assert out["freshness"]["dashboard"]["source"] == "stale_cache"
    assert out["freshness"]["dashboard"]["status"] == "stale"
    assert out["freshness"]["dashboard"]["served_at"].endswith("Z")


def test_attach_dashboard_freshness_keeps_existing_freshness_keys():
    target_day = date(2026, 4, 26)
    payload = {
        "day": target_day.isoformat(),
        "freshness": {"earthscope": {"status": "fresh"}},
    }

    out = dashboard_router._attach_dashboard_freshness(
        payload,
        day=target_day,
        source="live",
        cache_hit=False,
        cache_age_seconds=0,
        stale=False,
        refresh_scheduled=False,
    )

    assert out["freshness"]["earthscope"] == {"status": "fresh"}
    assert out["freshness"]["dashboard"]["status"] == "fresh"


@pytest.mark.anyio
async def test_refresh_stale_dashboard_space_preserves_personalized_payload(monkeypatch):
    target_day = date(2026, 8, 4)
    payload = {
        "day": target_day.isoformat(),
        "gauges": {"sleep": 39},
        "drivers": [{"key": "schumann", "label": "Schumann"}],
        "signal_bar": {
            "space": {"kp_now": 0.0},
            "items": [{"key": "kp", "value": "0.0"}],
        },
    }

    def fake_refresh(signal_bar, *, day):
        assert signal_bar == payload["signal_bar"]
        assert day == target_day
        return {
            "space": {"kp_now": 2.7},
            "items": [{"key": "kp", "value": "2.7"}],
        }

    monkeypatch.setattr(dashboard_router, "refresh_signal_bar_space", fake_refresh)

    out = await dashboard_router._refresh_stale_dashboard_space(payload, target_day)

    assert payload["signal_bar"]["space"]["kp_now"] == 0.0
    assert out["signal_bar"]["space"]["kp_now"] == 2.7
    assert out["gauges"] == payload["gauges"]
    assert out["drivers"] == payload["drivers"]


@pytest.mark.anyio
async def test_dashboard_refreshes_space_on_fresh_cache_hit(monkeypatch):
    target_day = date(2026, 8, 6)
    cached_payload = {
        "day": target_day.isoformat(),
        "gauges": {"sleep": 39},
        "signal_bar": {
            "space": {"kp_now": 0.0},
            "items": [{"key": "kp", "value": "0.0"}],
        },
    }
    refresh_calls = []

    async def fake_get_cached_dashboard(user_id, day, *, allow_stale=False):
        assert user_id == "user-1"
        assert day == target_day
        assert allow_stale is True
        return cached_payload, 30.0, False

    async def fake_refresh_space(payload, day):
        refresh_calls.append((payload, day))
        refreshed = dict(payload)
        refreshed["signal_bar"] = {
            "space": {"kp_now": 1.3},
            "items": [{"key": "kp", "value": "1.3"}],
        }
        return refreshed

    def fail_if_scheduled(*args, **kwargs):
        raise AssertionError("fresh cache hits must not schedule a full dashboard rebuild")

    monkeypatch.setattr(dashboard_router, "_get_cached_dashboard", fake_get_cached_dashboard)
    monkeypatch.setattr(dashboard_router, "_refresh_stale_dashboard_space", fake_refresh_space)
    monkeypatch.setattr(dashboard_router, "_schedule_dashboard_refresh", fail_if_scheduled)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-1"))
    out = await dashboard_router.dashboard(
        request,
        day=target_day,
        debug=False,
        force=False,
    )

    assert len(refresh_calls) == 1
    assert out["signal_bar"]["space"]["kp_now"] == 1.3
    assert out["cache_hit"] is True
    assert out["stale"] is False
    assert out["refresh_scheduled"] is False


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params, prepare=False):  # noqa: ARG002
        return None

    async def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, rows):
        self._rows = list(rows)

    def cursor(self, row_factory=None):  # noqa: ARG002
        row = self._rows.pop(0) if self._rows else None
        return _FakeCursor(row)


@pytest.mark.anyio
async def test_fetch_member_post_ignores_older_rows():
    target_day = date(2026, 8, 24)
    old_row = {
        "day": date(2026, 3, 7),
        "title": "Your EarthScope — 2026-03-07",
        "caption": "Old caption",
        "body_markdown": "Old body",
        "metrics_json": {},
        "sources_json": {},
        "updated_at": None,
    }

    payload = await dashboard_router._fetch_member_post(_FakeConn([old_row]), "user-1", target_day)

    assert payload is None


@pytest.mark.anyio
async def test_earthscope_member_regenerates_when_only_older_row_exists(monkeypatch):
    target_day = date(2026, 8, 24)
    old_row = {
        "day": date(2026, 3, 7),
        "title": "Your EarthScope — 2026-03-07",
        "caption": "Old caption",
        "body_markdown": "Old body",
        "hashtags": "#Old",
        "metrics_json": {},
        "sources_json": {},
        "updated_at": None,
    }
    new_row = {
        "day": target_day,
        "title": "Your EarthScope",
        "caption": "Fresh caption",
        "body_markdown": "Fresh body",
        "hashtags": "#Fresh",
        "metrics_json": {},
        "sources_json": {},
        "updated_at": None,
    }
    regen_calls = []

    async def fake_to_thread(fn):
        regen_calls.append(True)
        return {"ok": True}

    monkeypatch.setattr(dashboard_router.asyncio, "to_thread", fake_to_thread)

    request = SimpleNamespace(state=SimpleNamespace(user_id="user-1"))
    out = await dashboard_router.earthscope_member(
        request,
        day=target_day,
        conn=_FakeConn([old_row, new_row]),
    )

    assert regen_calls == [True]
    assert out["ok"] is True
    assert out["post"]["day"] == target_day
    assert out["post"]["title"] == "Your EarthScope"
