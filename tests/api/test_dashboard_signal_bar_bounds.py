"""Offline regressions for the complete, bounded dashboard signal-bar path."""
from __future__ import annotations

import asyncio
import copy
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from app.routers import dashboard as dashboard_router
from bots.gauges import signal_resolver
from services import signal_bar as signal_bar_service
from services.db import pg

pytestmark = pytest.mark.anyio

DAY = date(2026, 10, 10)
SPACE = {"kp_now": 5.0, "sw_speed_now_kms": 550.0, "space_now_ts": "2026-10-10T12:00:00Z"}
SCHUMANN = {"label": "Active", "state": "watch", "updated_at": "2026-10-10T12:01:00Z"}
LOCAL = {"weather": {"pressure_hpa": 1009.0}, "asof": "2026-10-10T12:02:00Z"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def signal_workers(monkeypatch):
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-signal-bar")
    jobs = {}
    lock = threading.Lock()
    gates = []
    database_attempts = []
    monkeypatch.setattr(dashboard_router, "_signal_context_executor", executor)
    monkeypatch.setattr(dashboard_router, "_signal_context_jobs", jobs)
    monkeypatch.setattr(dashboard_router, "_signal_context_jobs_lock", lock)
    monkeypatch.setattr(dashboard_router, "_SIGNAL_CONTEXT_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda *args: copy.deepcopy(LOCAL))
    monkeypatch.setattr(dashboard_router, "fetch_signal_space_snapshot", lambda day: SPACE)
    monkeypatch.setattr(dashboard_router, "fetch_signal_schumann_snapshot", lambda: SCHUMANN)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [])

    def unexpected_database_connection(*args, **kwargs):
        database_attempts.append(True)
        raise AssertionError("signal-bar tests must not connect to a database")

    monkeypatch.setattr(pg, "_connect", unexpected_database_connection)

    def gate():
        event = threading.Event()
        gates.append(event)
        return event

    def job_count():
        with lock:
            return len(jobs)

    yield SimpleNamespace(executor=executor, gate=gate, job_count=job_count)
    # Always release real threads, including when the test assertion fails.
    for event in gates:
        event.set()
    executor.shutdown(wait=True, cancel_futures=True)
    assert not database_attempts


async def _wait_until(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), timeout=2.0)


def _wait_for_release(event):
    assert event.wait(5.0), "test did not release the signal-bar worker"


async def _full_context(user_id="user-1", definition=None):
    return await dashboard_router._resolve_signal_context(
        user_id, DAY, definition or {"signal_definitions": []}, include_signal_bar=True
    )


def _items(bar):
    # Keep the existing strict iOS SignalBarState enum decodable.
    assert all(item["state"] in {"quiet", "watch", "elevated", "strong"} for item in bar["items"])
    return {item["key"]: item for item in bar["items"]}


def _assert_unavailable(bar, key):
    assert key not in _items(bar)
    assert key in bar["unavailable_items"]


def _assert_all_unavailable(bar):
    assert bar["items"] == []
    assert bar["unavailable_items"] == ["kp", "solar_wind", "schumann", "pressure"]
    assert bar["availability"] == "unavailable"


async def test_full_signal_context_runs_all_sources_in_one_budgeted_worker(monkeypatch, signal_workers):
    caller_thread = threading.get_ident()
    stages = []
    definition = {"signal_definitions": []}
    active = [{"signal_key": "schumann.variability_24h", "state": "high"}]

    def record(stage):
        stages.append((stage, threading.get_ident(), pg._operation_timeout_settings.get()))

    def local(user, day):
        assert (user, day) == ("user-1", DAY)
        record("local")
        return LOCAL

    def space(day):
        assert day == DAY
        record("space")
        return SPACE

    def schumann():
        record("schumann")
        return SCHUMANN

    def resolve(user, day, **kwargs):
        record("resolve")
        assert (user, day) == ("user-1", DAY)
        assert kwargs["local_payload"] is LOCAL
        assert kwargs["definition"] is definition
        assert kwargs["space_snapshot"] is SPACE
        return active

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "fetch_signal_space_snapshot", space)
    monkeypatch.setattr(dashboard_router, "fetch_signal_schumann_snapshot", schumann)
    monkeypatch.setattr(dashboard_router, "resolve_signals", resolve)

    resolved, local_payload, bar = await _full_context(definition=definition)

    assert (resolved, local_payload) == (active, LOCAL)
    assert bar["space"]["kp_now"] == 5.0
    assert _items(bar)["schumann"]["state"] == "strong"
    assert bar["availability"] == "available"
    assert bar["unavailable_items"] == []
    assert [stage for stage, _, _ in stages] == ["local", "space", "schumann", "resolve"]
    assert len({thread for _, thread, _ in stages}) == 1
    assert all(thread != caller_thread for _, thread, _ in stages)
    assert all(budget == (2, 5000) for _, _, budget in stages)
    assert pg._operation_timeout_settings.get() is None
    await _wait_until(lambda: signal_workers.job_count() == 0)
    assert signal_workers.executor.submit(pg._operation_timeout_settings.get).result(2) is None


@pytest.mark.parametrize("blocked_stage", ["space", "schumann"])
async def test_slow_signal_bar_source_keeps_event_loop_responsive_and_partial_bar(
    monkeypatch, signal_workers, blocked_stage
):
    entered = threading.Event()
    release = signal_workers.gate()
    monkeypatch.setattr(dashboard_router, "_SIGNAL_CONTEXT_TIMEOUT_SECONDS", 0.05)

    def blocked(*args):
        entered.set()
        _wait_for_release(release)
        return SPACE if blocked_stage == "space" else SCHUMANN

    monkeypatch.setattr(dashboard_router, f"fetch_signal_{blocked_stage}_snapshot", blocked)
    pending = asyncio.create_task(_full_context())
    await _wait_until(entered.is_set)
    assert not pending.done()
    heartbeat = []
    for _ in range(3):
        await asyncio.sleep(0.001)
        heartbeat.append(True)
    assert len(heartbeat) == 3
    assert not release.is_set()

    active, local_payload, bar = await pending

    assert active == []
    assert local_payload == LOCAL
    assert bar["availability"] == "partial"
    assert "1009" in _items(bar)["pressure"]["value"]
    _assert_unavailable(bar, "schumann")
    if blocked_stage == "space":
        assert bar["space"]["kp_now"] is None
        _assert_unavailable(bar, "kp")
        _assert_unavailable(bar, "solar_wind")
    else:
        assert bar["space"]["kp_now"] == 5.0
    assert signal_workers.job_count() == 1
    saved_bar = copy.deepcopy(bar)
    release.set()
    await _wait_until(lambda: signal_workers.job_count() == 0)
    assert bar == saved_bar


@pytest.mark.parametrize("blocked_stage", ["space", "schumann"])
async def test_cancelled_full_path_waiters_keep_capacity_until_real_sources_finish(
    monkeypatch, signal_workers, blocked_stage
):
    release = signal_workers.gate()
    entered = []
    calls = []
    stage_lock = threading.Lock()

    def local(user, day):
        calls.append(user)
        return LOCAL

    def blocked(*args):
        with stage_lock:
            entered.append(threading.get_ident())
        _wait_for_release(release)
        return SPACE if blocked_stage == "space" else SCHUMANN

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, f"fetch_signal_{blocked_stage}_snapshot", blocked)
    first = asyncio.create_task(_full_context("user-1"))
    second = asyncio.create_task(_full_context("user-2"))
    await _wait_until(lambda: len(entered) == 2)
    shared = asyncio.create_task(_full_context("user-1"))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not shared.done()
    assert signal_workers.job_count() == 2

    second.cancel()
    shared.cancel()
    cancelled = await asyncio.gather(second, shared, return_exceptions=True)
    assert all(isinstance(result, asyncio.CancelledError) for result in cancelled)
    for index in range(5):
        active, local_payload, bar = await asyncio.wait_for(_full_context(f"overflow-{index}"), 0.25)
        assert (active, local_payload) == ([], {})
        _assert_all_unavailable(bar)
    assert signal_workers.job_count() == 2
    assert sorted(calls) == ["user-1", "user-2"]

    release.set()
    await _wait_until(lambda: signal_workers.job_count() == 0)
    active, local_payload, bar = await _full_context("replacement")
    assert (active, local_payload) == ([], LOCAL)
    assert bar["space"]["kp_now"] == 5.0
    assert sorted(calls) == ["replacement", "user-1", "user-2"]


async def test_slow_resolver_preserves_loaded_bar_and_local_without_freeing_worker_slots(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = []
    monkeypatch.setattr(dashboard_router, "_SIGNAL_CONTEXT_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda user, day: {**LOCAL, "user": user})

    def resolve(user, day, **kwargs):
        entered.append(user)
        _wait_for_release(release)
        return [{"signal_key": "schumann.variability_24h", "state": "high"}]

    monkeypatch.setattr(dashboard_router, "resolve_signals", resolve)
    pending = [asyncio.create_task(_full_context(user)) for user in ("user-1", "user-2")]
    await _wait_until(lambda: len(entered) == 2)
    results = await asyncio.gather(*pending)
    for user, (active, local_payload, bar) in zip(("user-1", "user-2"), results):
        assert active == []
        assert local_payload == {**LOCAL, "user": user}
        assert bar["space"]["kp_now"] == 5.0
        assert _items(bar)["schumann"]["value"] == "Active"
        assert "1009" in _items(bar)["pressure"]["value"]
    assert signal_workers.job_count() == 2
    assert await _full_context("user-1") == results[0]
    assert sorted(entered) == ["user-1", "user-2"]
    active, local_payload, fallback = await _full_context("overflow")
    assert (active, local_payload) == ([], {})
    _assert_all_unavailable(fallback)
    saved_results = copy.deepcopy(results)
    release.set()
    await _wait_until(lambda: signal_workers.job_count() == 0)
    assert results == saved_results


@pytest.mark.parametrize("failed_stage", ["local", "space", "schumann", "resolve"])
async def test_source_failure_returns_completed_bar_without_logging_source_data(
    monkeypatch, signal_workers, caplog, failed_stage
):
    sources = {
        "local": "get_local_payload",
        "space": "fetch_signal_space_snapshot",
        "schumann": "fetch_signal_schumann_snapshot",
        "resolve": "resolve_signals",
    }
    private_local = {**LOCAL, "private_marker": "do-not-log-local-payload"}
    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda *args: private_local)
    resolver_inputs = []

    def resolve(user, day, **kwargs):
        resolver_inputs.append(kwargs)
        return []

    monkeypatch.setattr(dashboard_router, "resolve_signals", resolve)

    def fail(*args, **kwargs):
        raise RuntimeError("do-not-log-source-exception")

    monkeypatch.setattr(dashboard_router, sources[failed_stage], fail)
    with caplog.at_level(logging.INFO, logger=dashboard_router.__name__):
        active, local_payload, bar = await _full_context()

    assert active == []
    assert local_payload == ({} if failed_stage == "local" else private_local)
    items = _items(bar)
    if failed_stage == "local":
        _assert_unavailable(bar, "pressure")
    else:
        assert "1009" in items["pressure"]["value"]
    if failed_stage == "space":
        assert bar["space"]["kp_now"] is None
        _assert_unavailable(bar, "kp")
        _assert_unavailable(bar, "solar_wind")
    else:
        assert bar["space"]["kp_now"] == 5.0
    if failed_stage == "schumann":
        _assert_unavailable(bar, "schumann")
    else:
        assert items["schumann"]["value"] == "Active"
    if failed_stage != "resolve":
        assert len(resolver_inputs) == 1
        assert resolver_inputs[0]["local_payload"] == local_payload
        assert resolver_inputs[0]["space_snapshot"] is (None if failed_stage == "space" else SPACE)
    assert "outcome=failed" in caplog.text
    assert "do-not-log-local-payload" not in caplog.text
    assert "do-not-log-source-exception" not in caplog.text
    await _wait_until(lambda: signal_workers.job_count() == 0)


@pytest.mark.parametrize("snapshot", [None, {}, SPACE])
async def test_full_path_reuses_exact_space_snapshot_without_duplicate_fetches(monkeypatch, snapshot):
    loads = []
    duplicates = []
    resolver_snapshots = []
    real_resolve = signal_resolver.resolve_signals

    def load_space(day):
        loads.append(day)
        return snapshot

    def duplicate(*args, **kwargs):
        duplicates.append(True)
        raise AssertionError("an explicitly loaded snapshot must never be fetched again")

    def resolve(user, day, **kwargs):
        resolver_snapshots.append(kwargs["space_snapshot"])
        return real_resolve(user, day, **kwargs)

    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda *args: {})
    monkeypatch.setattr(dashboard_router, "fetch_signal_space_snapshot", load_space)
    monkeypatch.setattr(dashboard_router, "fetch_signal_schumann_snapshot", lambda: None)
    monkeypatch.setattr(dashboard_router, "resolve_signals", resolve)
    monkeypatch.setattr(signal_resolver, "_fetch_local_payload", duplicate)
    monkeypatch.setattr(signal_resolver, "_fetch_space_snapshot", duplicate)
    monkeypatch.setattr(signal_bar_service, "_fetch_schumann_snapshot", duplicate)
    monkeypatch.setattr(signal_resolver, "_fetch_schumann_stddev_24h", lambda: None)
    monkeypatch.setattr(signal_resolver, "_fetch_schumann_daily_stddev_series", lambda *args: [])
    monkeypatch.setattr(signal_resolver, "_full_moon_days_to", lambda *args: 99.0)

    active, local_payload, bar = await _full_context()

    assert local_payload == {}
    assert loads == [DAY]
    assert len(resolver_snapshots) == 1
    assert resolver_snapshots[0] is snapshot
    assert not duplicates
    assert bar["space"]["kp_now"] == (5.0 if snapshot else None)
    if snapshot:
        assert active, "the real resolver should use the supplied elevated space values"
    else:
        assert active == []
        _assert_all_unavailable(bar)


async def test_full_and_legacy_contexts_do_not_coalesce_incompatible_result_shapes(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    calls = []

    def local(user, day):
        calls.append(user)
        _wait_for_release(release)
        return LOCAL

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    legacy = asyncio.create_task(dashboard_router._resolve_signal_context("user-1", DAY, {}))
    full = asyncio.create_task(_full_context("user-1"))
    await _wait_until(lambda: len(calls) == 2)
    assert signal_workers.job_count() == 2
    release.set()
    legacy_result, full_result = await asyncio.gather(legacy, full)
    assert legacy_result == ([], LOCAL)
    assert full_result[:2] == legacy_result
    assert len(full_result) == 3
    assert full_result[2]["space"]["kp_now"] == 5.0


async def test_dashboard_endpoint_uses_worker_bar_without_synchronous_source_work(monkeypatch):
    caller_thread = threading.get_ident()
    builds = []
    context_calls = []
    real_build = dashboard_router.build_signal_bar
    real_context = dashboard_router._resolve_signal_context

    def build(**kwargs):
        builds.append(threading.get_ident())
        assert threading.get_ident() != caller_thread
        assert "space_snapshot" in kwargs
        assert "schumann_snapshot" in kwargs
        return real_build(**kwargs)

    async def context(*args, **kwargs):
        context_calls.append(kwargs)
        return await real_context(*args, **kwargs)

    async def empty(*args, **kwargs):
        return {}

    async def rpc(*args, **kwargs):
        return {"gauges": {}}, False

    async def build_lock(*args):
        return asyncio.Lock()

    @asynccontextmanager
    async def connection():
        yield object()

    monkeypatch.setattr(dashboard_router, "build_signal_bar", build)
    monkeypatch.setattr(dashboard_router, "_resolve_signal_context", context)
    monkeypatch.setattr(dashboard_router, "_acquire_dashboard_conn", connection)
    monkeypatch.setattr(dashboard_router, "_get_dashboard_build_lock", build_lock)
    monkeypatch.setattr(dashboard_router, "_set_cached_dashboard", empty)
    monkeypatch.setattr(dashboard_router, "_call_dashboard_payload", rpc)
    monkeypatch.setattr(dashboard_router, "_safe_dashboard_definition", lambda: {"signal_definitions": []})
    for name in (
        "_probe_paid_user", "_fetch_public_post", "_fetch_member_post", "_fetch_latest_gauges",
        "_fetch_gauges_delta", "fetch_best_pattern_rows", "fetch_recent_outcome_summary",
        "_fetch_latest_pending_follow_up", "_fetch_guide_seen_state",
    ):
        monkeypatch.setattr(dashboard_router, name, empty)
    monkeypatch.setattr(dashboard_router.ulf_db, "get_latest_ulf_context", empty)
    monkeypatch.setattr(dashboard_router.feedback_db, "fetch_latest_daily_check_in", empty)
    for name in (
        "fetch_health_status_context", "fetch_recent_symptom_gauge_context", "fetch_symptom_summary",
        "fetch_exposure_summary", "build_personalization_profile", "compute_personal_relevance",
        "build_modal_models", "build_earthscope_summary", "_build_guide_state",
    ):
        monkeypatch.setattr(dashboard_router, name, lambda *args, **kwargs: {})
    for name in ("fetch_user_tags", "build_support_items", "build_exposure_driver_rows"):
        monkeypatch.setattr(dashboard_router, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(dashboard_router, "build_ulf_driver_row", lambda *args: None)

    result = await dashboard_router.dashboard(
        SimpleNamespace(state=SimpleNamespace(user_id="user-1")), DAY, debug=False, force=True
    )

    assert context_calls == [{"include_signal_bar": True}]
    assert builds
    assert all(thread != caller_thread for thread in builds)
    assert result["signal_bar"]["space"]["kp_now"] == 5.0
    assert _items(result["signal_bar"])["schumann"]["value"] == "Active"
