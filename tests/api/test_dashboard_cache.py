from __future__ import annotations

from datetime import date

import pytest

from app.routers import dashboard as dashboard_router

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture(autouse=True)
def clear_dashboard_route_cache():
    dashboard_router._dashboard_cache.clear()
    try:
        yield
    finally:
        dashboard_router._dashboard_cache.clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_dashboard_cache_returns_payload_copy(monkeypatch):
    monkeypatch.setattr(dashboard_router, "_DASHBOARD_CACHE_TTL_SECONDS", 60)
    payload = {"day": "2026-04-26", "gauges": {"sleep": 39}}

    await dashboard_router._set_cached_dashboard("user-1", date(2026, 4, 26), payload)
    cached, age = await dashboard_router._get_cached_dashboard("user-1", date(2026, 4, 26))
    assert cached is not None
    assert age >= 0

    cached["gauges"]["sleep"] = 99
    cached_again, _ = await dashboard_router._get_cached_dashboard("user-1", date(2026, 4, 26))
    assert cached_again is not None
    assert cached_again["gauges"]["sleep"] == 39
