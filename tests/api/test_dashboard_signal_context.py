"""Offline regressions for bounded synchronous dashboard signal work."""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.routers import dashboard as dashboard_router
from bots.gauges import signal_resolver
from services.db import pg

pytestmark = pytest.mark.anyio

DAY = date(2026, 10, 10)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def signal_workers(monkeypatch):
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="test-signals")
    jobs = {}
    lock = threading.Lock()
    gates = []
    monkeypatch.setattr(dashboard_router, "_signal_context_executor", executor)
    monkeypatch.setattr(dashboard_router, "_signal_context_jobs", jobs)
    monkeypatch.setattr(dashboard_router, "_signal_context_jobs_lock", lock)
    monkeypatch.setattr(dashboard_router, "_SIGNAL_CONTEXT_TIMEOUT_SECONDS", 2.0)

    def unexpected_database_connection(*args, **kwargs):
        raise AssertionError("signal-context tests must not connect to a database")

    monkeypatch.setattr(pg, "_connect", unexpected_database_connection)

    def gate():
        event = threading.Event()
        gates.append(event)
        return event

    def job_count():
        with lock:
            return len(jobs)

    yield SimpleNamespace(executor=executor, gate=gate, job_count=job_count)
    # Never leave real worker threads blocked if an assertion fails.
    for event in gates:
        event.set()
    executor.shutdown(wait=True, cancel_futures=True)


async def _wait_until(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), timeout=2.0)


def _wait_for_release(event):
    assert event.wait(5.0), "test did not release the signal worker"


async def test_signal_context_runs_both_stages_with_database_operation_budget(
    monkeypatch, signal_workers
):
    local_payload = {"local": {"temperature_c": 22}}
    active_states = [{"key": "temperature", "state": "normal"}]
    definition = {"signals": {"temperature": {}}}
    stages = []
    caller_thread = threading.get_ident()

    def local(user_id, day):
        stages.append(("local", threading.get_ident(), pg._operation_timeout_settings.get()))
        assert (user_id, day) == ("user-1", DAY)
        return local_payload

    def resolve(user_id, day, **kwargs):
        stages.append(("resolve", threading.get_ident(), pg._operation_timeout_settings.get()))
        assert (user_id, day) == ("user-1", DAY)
        assert kwargs == {"local_payload": local_payload, "definition": definition}
        return active_states

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", resolve)

    assert await dashboard_router._resolve_signal_context("user-1", DAY, definition) == (
        active_states,
        local_payload,
    )
    assert [stage for stage, _, _ in stages] == ["local", "resolve"]
    assert all(thread != caller_thread for _, thread, _ in stages)
    assert stages[0][1] == stages[1][1]
    assert [budget for _, _, budget in stages] == [(2, 5000), (2, 5000)]
    assert pg._operation_timeout_settings.get() is None
    await _wait_until(lambda: signal_workers.job_count() == 0)
    assert signal_workers.executor.submit(pg._operation_timeout_settings.get).result(2) is None


async def test_signal_context_coalesces_same_key_even_when_both_slots_are_full(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = {user: threading.Event() for user in ("user-1", "user-2")}
    calls = []

    def local(user_id, day):
        calls.append((user_id, day))
        entered[user_id].set()
        _wait_for_release(release)
        return {"user": user_id}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [])
    first = asyncio.create_task(dashboard_router._resolve_signal_context("user-1", DAY, {}))
    second = asyncio.create_task(dashboard_router._resolve_signal_context("user-2", DAY, {}))
    await _wait_until(lambda: all(event.is_set() for event in entered.values()))
    shared = asyncio.create_task(dashboard_router._resolve_signal_context("user-1", DAY, {}))
    await asyncio.sleep(0)

    assert not shared.done()
    assert signal_workers.job_count() == 2
    release.set()
    results = await asyncio.gather(first, second, shared)

    assert results == [([], {"user": "user-1"}), ([], {"user": "user-2"}), ([], {"user": "user-1"})]
    assert sorted(calls) == [("user-1", DAY), ("user-2", DAY)]
    await _wait_until(lambda: signal_workers.job_count() == 0)


async def test_signal_context_rejects_new_key_promptly_without_queueing(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = {user: threading.Event() for user in ("user-1", "user-2")}
    calls = []

    def local(user_id, day):
        calls.append(user_id)
        if user_id in entered:
            entered[user_id].set()
            _wait_for_release(release)
        return {"user": user_id}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [])
    pending = [
        asyncio.create_task(dashboard_router._resolve_signal_context(user, DAY, {}))
        for user in entered
    ]
    await _wait_until(lambda: all(event.is_set() for event in entered.values()))

    for index in range(10):
        assert await asyncio.wait_for(
            dashboard_router._resolve_signal_context(f"overflow-{index}", DAY, {}),
            timeout=0.25,
        ) == ([], {})
    assert signal_workers.job_count() == 2
    release.set()
    await asyncio.gather(*pending)
    await _wait_until(lambda: signal_workers.job_count() == 0)
    # A rejected request must not be submitted to the executor's hidden queue.
    signal_workers.executor.shutdown(wait=True)
    assert sorted(calls) == ["user-1", "user-2"]


async def test_signal_context_timeout_keeps_real_workers_and_completed_local_payload(
    monkeypatch, signal_workers
):
    release = {user: signal_workers.gate() for user in ("user-1", "user-2")}
    entered = {user: threading.Event() for user in release}
    calls = []
    monkeypatch.setattr(dashboard_router, "_SIGNAL_CONTEXT_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda user, day: {"user": user})

    def resolve(user_id, day, **kwargs):
        calls.append(user_id)
        if user_id in release:
            entered[user_id].set()
            _wait_for_release(release[user_id])
        return [{"key": user_id}]

    monkeypatch.setattr(dashboard_router, "resolve_signals", resolve)
    pending = [
        asyncio.create_task(dashboard_router._resolve_signal_context(user, DAY, {}))
        for user in release
    ]
    await _wait_until(lambda: all(event.is_set() for event in entered.values()))
    assert await asyncio.gather(*pending) == [([], {"user": "user-1"}), ([], {"user": "user-2"})]
    assert signal_workers.job_count() == 2
    assert await dashboard_router._resolve_signal_context("overflow", DAY, {}) == ([], {})
    # Another caller for the timed-out key must attach to its existing thread.
    assert await dashboard_router._resolve_signal_context("user-1", DAY, {}) == ([], {"user": "user-1"})
    assert sorted(calls) == ["user-1", "user-2"]

    release["user-1"].set()
    await _wait_until(lambda: signal_workers.job_count() == 1)
    assert await dashboard_router._resolve_signal_context("user-1", DAY, {}) == (
        [{"key": "user-1"}],
        {"user": "user-1"},
    )
    assert calls.count("user-1") == 2
    assert await dashboard_router._resolve_signal_context("replacement", DAY, {}) == (
        [{"key": "replacement"}],
        {"user": "replacement"},
    )
    release["user-2"].set()
    await _wait_until(lambda: signal_workers.job_count() == 0)


async def test_signal_context_cancelled_callers_do_not_release_real_worker_slots(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = {user: threading.Event() for user in ("user-1", "user-2")}
    calls = []

    def local(user_id, day):
        calls.append(user_id)
        if user_id in entered:
            entered[user_id].set()
            _wait_for_release(release)
        return {"user": user_id}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [])
    callers = [
        asyncio.create_task(dashboard_router._resolve_signal_context(user, DAY, {}))
        for user in entered
    ]
    await _wait_until(lambda: all(event.is_set() for event in entered.values()))
    for caller in callers:
        caller.cancel()
    outcomes = await asyncio.gather(*callers, return_exceptions=True)

    assert all(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes)
    assert signal_workers.job_count() == 2
    assert await asyncio.wait_for(
        dashboard_router._resolve_signal_context("overflow", DAY, {}), timeout=0.25
    ) == ([], {})
    assert sorted(calls) == ["user-1", "user-2"]
    release.set()
    await _wait_until(lambda: signal_workers.job_count() == 0)
    assert await dashboard_router._resolve_signal_context("replacement", DAY, {}) == (
        [], {"user": "replacement"}
    )


async def test_signal_context_cancelling_coalesced_caller_does_not_cancel_other_waiter(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = threading.Event()
    calls = []

    def local(user_id, day):
        calls.append(user_id)
        entered.set()
        _wait_for_release(release)
        return {"value": 7}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [{"key": "ok"}])
    first = asyncio.create_task(dashboard_router._resolve_signal_context("user-1", DAY, {}))
    await _wait_until(entered.is_set)
    shared = asyncio.create_task(dashboard_router._resolve_signal_context("user-1", DAY, {}))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    assert signal_workers.job_count() == 1
    assert not shared.done()
    release.set()
    assert await shared == ([{"key": "ok"}], {"value": 7})
    assert calls == ["user-1"]


async def test_signal_context_preserves_local_payload_on_resolver_failure_without_logging_data(
    monkeypatch, signal_workers, caplog
):
    local_payload = {"private_marker": "do-not-log-local-payload"}
    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda *args: local_payload)

    def fail_resolver(*args, **kwargs):
        raise RuntimeError("do-not-log-exception-payload")

    monkeypatch.setattr(dashboard_router, "resolve_signals", fail_resolver)
    with caplog.at_level(logging.INFO, logger=dashboard_router.__name__):
        result = await dashboard_router._resolve_signal_context("user-1", DAY, {})

    assert result == ([], local_payload)
    assert "do-not-log-local-payload" not in caplog.text
    assert "do-not-log-exception-payload" not in caplog.text
    assert "stage=local_payload" in caplog.text
    assert "stage=resolve_signals" in caplog.text
    assert "outcome=failed" in caplog.text
    assert "elapsed_ms=" in caplog.text
    await _wait_until(lambda: signal_workers.job_count() == 0)


@pytest.mark.parametrize("active_states", [None, {}, "not-a-list"])
async def test_signal_context_normalizes_non_list_resolver_result(monkeypatch, active_states):
    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda *args: {"value": 7})
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: active_states)

    assert await dashboard_router._resolve_signal_context("user-1", DAY, {}) == ([], {"value": 7})


async def test_signal_context_does_not_fetch_empty_local_payload_twice(monkeypatch):
    calls = []

    def local(*args):
        calls.append("local")
        return {}

    def duplicate_local_fetch(*args):
        calls.append("duplicate")
        return {}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", signal_resolver.resolve_signals)
    monkeypatch.setattr(signal_resolver, "_fetch_local_payload", duplicate_local_fetch)
    monkeypatch.setattr(signal_resolver, "_fetch_space_snapshot", lambda *args: {})
    monkeypatch.setattr(signal_resolver, "_fetch_schumann_stddev_24h", lambda *args: None)
    monkeypatch.setattr(signal_resolver, "_full_moon_days_to", lambda *args: 99.0)

    assert await dashboard_router._resolve_signal_context(
        "user-1", DAY, {"signal_definitions": []}
    ) == ([], {})
    assert calls == ["local"]


async def test_stale_space_refresh_cannot_bypass_full_signal_worker_capacity(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = {user: threading.Event() for user in ("user-1", "user-2")}
    stale_calls = []
    payload = {"gauges": {"sleep": 39}, "signal_bar": {"space": {"kp_now": 0.0}}}

    def local(user_id, day):
        entered[user_id].set()
        _wait_for_release(release)
        return {}

    def stale_refresh(*args, **kwargs):
        stale_calls.append(True)
        return {"space": {"kp_now": 4.0}}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [])
    monkeypatch.setattr(dashboard_router, "refresh_signal_bar_space", stale_refresh)
    pending = [
        asyncio.create_task(dashboard_router._resolve_signal_context(user, DAY, {}))
        for user in entered
    ]
    await _wait_until(lambda: all(event.is_set() for event in entered.values()))

    result = await asyncio.wait_for(
        dashboard_router._refresh_stale_dashboard_space(payload, DAY), timeout=0.25
    )
    assert result is payload
    assert signal_workers.job_count() == 2
    release.set()
    await asyncio.gather(*pending)
    await _wait_until(lambda: signal_workers.job_count() == 0)
    signal_workers.executor.shutdown(wait=True)
    assert not stale_calls


async def test_stale_space_timeout_keeps_slot_and_database_operation_budget(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = threading.Event()
    budgets = []
    payload = {"gauges": {"sleep": 39}, "signal_bar": {"space": {"kp_now": 0.0}}}
    monkeypatch.setattr(dashboard_router, "_SIGNAL_CONTEXT_TIMEOUT_SECONDS", 0.05)

    def stale_refresh(signal_bar, *, day):
        assert signal_bar == payload["signal_bar"]
        assert day == DAY
        budgets.append(pg._operation_timeout_settings.get())
        entered.set()
        _wait_for_release(release)
        return {"space": {"kp_now": 4.0}}

    monkeypatch.setattr(dashboard_router, "refresh_signal_bar_space", stale_refresh)
    pending = asyncio.create_task(dashboard_router._refresh_stale_dashboard_space(payload, DAY))
    await _wait_until(entered.is_set)

    assert await pending is payload
    assert signal_workers.job_count() == 1
    assert budgets == [(2, 5000)]
    assert payload["signal_bar"]["space"]["kp_now"] == 0.0
    release.set()
    await _wait_until(lambda: signal_workers.job_count() == 0)
    assert payload["signal_bar"]["space"]["kp_now"] == 0.0


def test_signal_worker_slots_survive_caller_event_loop_shutdown(monkeypatch, signal_workers):
    release = signal_workers.gate()
    entered = {user: threading.Event() for user in ("user-1", "user-2")}
    calls = []

    def local(user_id, day):
        calls.append(user_id)
        entered[user_id].set()
        _wait_for_release(release)
        return {}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [])

    async def abandon_callers():
        for user in entered:
            asyncio.create_task(dashboard_router._resolve_signal_context(user, DAY, {}))
        await _wait_until(lambda: all(event.is_set() for event in entered.values()))
        # asyncio.run cancels pending callers and closes their event loop.

    asyncio.run(abandon_callers())
    assert signal_workers.job_count() == 2
    assert asyncio.run(dashboard_router._resolve_signal_context("overflow", DAY, {})) == ([], {})
    assert sorted(calls) == ["user-1", "user-2"]
    release.set()
    signal_workers.executor.shutdown(wait=True)
    assert signal_workers.job_count() == 0


async def test_signal_context_does_not_coalesce_distinct_days(monkeypatch, signal_workers):
    release = signal_workers.gate()
    days = (DAY, DAY - timedelta(days=1))
    entered = {day: threading.Event() for day in days}
    calls = []

    def local(user_id, day):
        calls.append((user_id, day))
        entered[day].set()
        _wait_for_release(release)
        return {"day": day.isoformat()}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [])
    pending = [
        asyncio.create_task(dashboard_router._resolve_signal_context("user-1", day, {}))
        for day in days
    ]
    await _wait_until(lambda: all(event.is_set() for event in entered.values()))
    assert signal_workers.job_count() == 2
    release.set()

    assert await asyncio.gather(*pending) == [([], {"day": day.isoformat()}) for day in days]
    assert sorted(calls) == sorted(("user-1", day) for day in days)


async def test_stale_space_refresh_keeps_distinct_personalized_outputs(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    users = ("user-1", "user-2")
    entered = {user: threading.Event() for user in users}
    payloads = [
        {"gauges": {"sleep": 39}, "signal_bar": {"personal": user, "space": {"kp_now": 0.0}}}
        for user in users
    ]

    def stale_refresh(signal_bar, *, day):
        assert day == DAY
        user = signal_bar["personal"]
        entered[user].set()
        _wait_for_release(release)
        return {"personal": user, "space": {"kp_now": 4.0}}

    monkeypatch.setattr(dashboard_router, "refresh_signal_bar_space", stale_refresh)
    pending = [
        asyncio.create_task(dashboard_router._refresh_stale_dashboard_space(payload, DAY))
        for payload in payloads
    ]
    await _wait_until(lambda: all(event.is_set() for event in entered.values()))
    assert signal_workers.job_count() == 2
    release.set()

    results = await asyncio.gather(*pending)
    assert [result["signal_bar"] for result in results] == [
        {"personal": user, "space": {"kp_now": 4.0}} for user in users
    ]
    assert all(result["gauges"] == {"sleep": 39} for result in results)
    assert all(payload["signal_bar"]["space"]["kp_now"] == 0.0 for payload in payloads)


async def test_signal_context_allows_healthy_work_longer_than_one_second(
    monkeypatch, signal_workers
):
    release = signal_workers.gate()
    entered = threading.Event()
    budgets = []
    monkeypatch.setattr(dashboard_router, "_SIGNAL_CONTEXT_TIMEOUT_SECONDS", 6.0)

    def local(user_id, day):
        budgets.append(pg._operation_timeout_settings.get())
        entered.set()
        _wait_for_release(release)
        return {"value": "healthy-slow-result"}

    monkeypatch.setattr(dashboard_router, "get_local_payload", local)
    monkeypatch.setattr(dashboard_router, "resolve_signals", lambda *args, **kwargs: [{"key": "ok"}])
    pending = asyncio.create_task(dashboard_router._resolve_signal_context("user-1", DAY, {}))
    await _wait_until(entered.is_set)
    await asyncio.sleep(1.05)
    assert not pending.done()
    release.set()

    assert await pending == ([{"key": "ok"}], {"value": "healthy-slow-result"})
    assert budgets == [(2, 5000)]


async def test_signal_context_resolver_failure_does_not_cache_negative_result(
    monkeypatch, signal_workers
):
    calls = []
    monkeypatch.setattr(dashboard_router, "get_local_payload", lambda *args: {"value": 7})

    def resolve(user_id, day, **kwargs):
        calls.append(user_id)
        if len(calls) == 1:
            raise RuntimeError("temporary resolver failure")
        return [{"key": "recovered"}]

    monkeypatch.setattr(dashboard_router, "resolve_signals", resolve)

    assert await dashboard_router._resolve_signal_context("user-1", DAY, {}) == ([], {"value": 7})
    await _wait_until(lambda: signal_workers.job_count() == 0)
    assert await dashboard_router._resolve_signal_context("user-1", DAY, {}) == (
        [{"key": "recovered"}], {"value": 7}
    )
    assert calls == ["user-1", "user-1"]
