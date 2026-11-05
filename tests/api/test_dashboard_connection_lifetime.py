"""Synthetic dashboard assembly checks; no external services or databases."""
from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from app.routers import dashboard as dashboard_router

pytestmark = pytest.mark.anyio
DAY = date(2026, 11, 5)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def assembly(monkeypatch):
    state = SimpleNamespace(active=0, acquired=0, released=0, events=[])

    @asynccontextmanager
    async def acquire():
        state.active += 1
        state.acquired += 1
        connection = object()
        try:
            yield connection
        finally:
            state.active -= 1
            state.released += 1

    async def sql(*args, **kwargs):
        assert state.active == 1
        return {}

    async def rpc(*args):
        assert state.active == 1
        return {"day": DAY.isoformat(), "gauges": {"sleep": 20}}, False

    async def probe(*args):
        assert state.active == 1
        return {"entitled": True}

    async def context(*args, **kwargs):
        assert state.active == 0
        state.events.append("signal")
        return [], {}, {"items": []}

    def exposure(*args, **kwargs):
        assert state.active == 0
        state.events.append("exposure")
        return {}

    monkeypatch.setattr(dashboard_router, "_acquire_dashboard_conn", acquire)
    monkeypatch.setattr(dashboard_router, "_call_dashboard_payload", rpc)
    monkeypatch.setattr(dashboard_router, "_probe_paid_user", probe)
    monkeypatch.setattr(dashboard_router, "_resolve_signal_context", context)
    for name in (
        "_fetch_public_post", "_fetch_member_post", "_fetch_latest_gauges",
        "_fetch_gauges_delta", "fetch_best_pattern_rows", "fetch_recent_outcome_summary",
        "_fetch_latest_pending_follow_up", "_fetch_guide_seen_state",
    ):
        monkeypatch.setattr(dashboard_router, name, sql)
    monkeypatch.setattr(dashboard_router.ulf_db, "get_latest_ulf_context", sql)
    monkeypatch.setattr(dashboard_router.feedback_db, "fetch_latest_daily_check_in", sql)
    for name in (
        "_safe_dashboard_definition", "fetch_health_status_context",
        "fetch_recent_symptom_gauge_context", "fetch_symptom_summary",
        "build_personalization_profile", "compute_personal_relevance",
        "build_modal_models", "build_earthscope_summary", "_build_guide_state",
    ):
        monkeypatch.setattr(dashboard_router, name, lambda *args, **kwargs: {})
    for name in ("fetch_user_tags", "build_support_items", "build_exposure_driver_rows"):
        monkeypatch.setattr(dashboard_router, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(dashboard_router, "build_ulf_driver_row", lambda *args: None)
    monkeypatch.setattr(dashboard_router, "fetch_exposure_summary", exposure)
    return state


@pytest.mark.parametrize("debug", [False, True])
async def test_builder_releases_before_signal_and_exposure(assembly, debug):
    result, timings = await dashboard_router._build_dashboard_payload("synthetic", DAY, debug=debug)
    assert assembly.events == ["signal", "exposure"]
    assert assembly.active == 0
    assert assembly.acquired == assembly.released == 2
    assert result["gauges"] == {"sleep": 20}
    assert result["entitled"] is True
    assert result["signal_bar"] == {"items": []}
    assert "signal_context" in timings and "personalization_inputs" in timings
    assert ("_debug" in result) == debug


async def test_personalization_connection_released_while_thread_still_running(monkeypatch, assembly):
    started = threading.Event()
    release = threading.Event()

    def slow_tags(*args):
        started.set()
        assert release.wait(5), "test did not release worker"
        return []

    monkeypatch.setattr(dashboard_router, "fetch_user_tags", slow_tags)
    task = asyncio.create_task(dashboard_router._build_dashboard_payload("synthetic", DAY, debug=False))
    try:
        async def wait_for_release():
            while not started.is_set() or assembly.released != 2:
                await asyncio.sleep(0.001)
        await asyncio.wait_for(wait_for_release(), 2)
        assert assembly.active == 0
        assert not task.done()
    finally:
        release.set()
        await task


@pytest.mark.parametrize("stage", ["_call_dashboard_payload", "fetch_best_pattern_rows"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_sql_failure_or_cancellation_returns_connection(monkeypatch, assembly, stage, cancel):
    async def fail(*args, **kwargs):
        assert assembly.active == 1
        if cancel:
            raise asyncio.CancelledError()
        raise RuntimeError("synthetic query failure")

    monkeypatch.setattr(dashboard_router, stage, fail)
    expected = asyncio.CancelledError if cancel else RuntimeError
    with pytest.raises(expected):
        await dashboard_router._build_dashboard_payload("synthetic", DAY, debug=False)
    assert assembly.active == 0
    assert assembly.acquired == assembly.released


async def test_cancel_during_signal_has_no_checked_out_connection(monkeypatch, assembly):
    started = asyncio.Event()

    async def signal(*args, **kwargs):
        assert assembly.active == 0
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(dashboard_router, "_resolve_signal_context", signal)
    task = asyncio.create_task(dashboard_router._build_dashboard_payload("synthetic", DAY, debug=False))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert assembly.active == 0
    assert assembly.acquired == assembly.released == 1


async def test_stale_refresh_caches_after_connections_released(monkeypatch, assembly):
    async def lock(*args):
        return asyncio.Lock()

    async def stale(*args, **kwargs):
        return {"day": DAY.isoformat()}, 999, True

    async def cache(owner, day, payload):
        assert assembly.active == 0
        assert assembly.released == 2
        assert payload["gauges"] == {"sleep": 20}
        assembly.events.append("cache")

    monkeypatch.setattr(dashboard_router, "_get_dashboard_build_lock", lock)
    monkeypatch.setattr(dashboard_router, "_get_cached_dashboard", stale)
    monkeypatch.setattr(dashboard_router, "_set_cached_dashboard", cache)
    await dashboard_router._refresh_stale_dashboard("synthetic", DAY)
    assert assembly.events == ["signal", "exposure", "cache"]


async def test_burst_releases_checkouts_while_waiting_for_optional_signal(monkeypatch, assembly):
    entered = 0
    all_waiting = asyncio.Event()
    release = asyncio.Event()

    async def signal(*args, **kwargs):
        nonlocal entered
        entered += 1
        if entered == 24:
            all_waiting.set()
        await release.wait()
        return [], {}, {"items": []}

    monkeypatch.setattr(dashboard_router, "_resolve_signal_context", signal)
    tasks = [
        asyncio.create_task(dashboard_router._build_dashboard_payload(f"synthetic-{i}", DAY, debug=False))
        for i in range(24)
    ]
    try:
        await asyncio.wait_for(all_waiting.wait(), 2)
        assert assembly.acquired == assembly.released == 24
        assert assembly.active == 0
        assert all(not task.done() for task in tasks)
    finally:
        # Stop at the signal stage so this specifically measures its idle holds.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert assembly.active == 0
