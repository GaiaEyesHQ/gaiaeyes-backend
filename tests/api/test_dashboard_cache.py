from __future__ import annotations

import time
from datetime import date

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
