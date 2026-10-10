"""Offline regression coverage for refresh pool pressure and recovery."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, timedelta

import pytest

from app.routers import ingest, summary

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def reset_refresh_state(monkeypatch):
    monkeypatch.setattr(summary, "_mart_execution_lock", asyncio.Lock())
    monkeypatch.setattr(summary, "_forced_refresh_lock", asyncio.Lock())
    summary._forced_refresh_registry.clear()
    summary._forced_refresh_inflight.clear()
    monkeypatch.setattr(ingest, "_recent_refresh_lock", asyncio.Lock())
    monkeypatch.setattr(ingest, "_refresh_queue_changed", asyncio.Event())
    ingest._pending_refresh_requests.clear()
    ingest._recent_refresh_requests.clear()
    ingest._refresh_worker_task = None
    ingest._active_refresh_key = None
    monkeypatch.setattr(ingest, "_DELAYED_REFRESH_DELAY_SECONDS", 0)
    monkeypatch.setattr(ingest, "_DELAYED_REFRESH_PRESSURE_RETRY_SECONDS", 0)
    monkeypatch.setattr(ingest, "_refresh_task_factory", asyncio.create_task)
    monkeypatch.setattr(summary, "_db_pressure_reason", lambda: None)
    yield
    task = ingest._refresh_worker_task
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    ingest._pending_refresh_requests.clear()


class Connection:
    def __init__(self, *, fail=None, gate=None, locked=True):
        self.sql = []
        self.commits = 0
        self.rollbacks = 0
        self.fail = fail
        self.gate = gate
        self.locked = locked
        self.result = None

    @asynccontextmanager
    async def cursor(self):
        yield self

    async def execute(self, query, params=None):
        self.sql.append(query)
        if "pg_try_advisory_xact_lock" in query:
            self.result = (self.locked,)
        elif "to_regprocedure" in query:
            self.result = ("exists",)
        if self.fail and self.fail in query:
            raise RuntimeError("injected SQL failure")
        if self.gate is not None and "gaia.refresh_daily_summary_user" in query:
            await self.gate.wait()

    async def fetchone(self):
        return self.result

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


async def test_forced_refresh_reuses_connection_without_nested_checkout(monkeypatch):
    async def forbidden_pool():
        pytest.fail("refresh attempted a nested pool checkout")

    monkeypatch.setattr(summary, "get_pool", forbidden_pool)
    conn = Connection()
    await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert sum("refresh_" in sql and "to_regprocedure" not in sql for sql in conn.sql) == 3
    assert any("statement_timeout" in sql for sql in conn.sql)
    assert any("lock_timeout" in sql for sql in conn.sql)


@pytest.mark.parametrize("stage", [
    "gaia.refresh_daily_summary_user", "gaia.refresh_daily_summary_sleep_user(%s",
    "marts.refresh_daily_features_user",
])
async def test_refresh_failure_is_atomic_and_recoverable(stage):
    conn = Connection(fail=stage)
    with pytest.raises(RuntimeError, match="injected SQL failure"):
        await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert not summary._mart_execution_lock.locked()
    conn.fail = None
    await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert conn.commits == 1


async def test_other_process_lock_is_nonblocking_and_not_success():
    conn = Connection(locked=False)
    with pytest.raises(summary.MartRefreshBusy):
        await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert conn.rollbacks == 1
    assert conn.commits == 0
    assert not any("gaia.refresh_daily_summary_user" in sql for sql in conn.sql)


async def test_timeout_rolls_back_releases_slot_and_can_recover(monkeypatch):
    monkeypatch.setattr(summary, "_MART_REFRESH_TIMEOUT_SECONDS", 0.01)
    conn = Connection(gate=asyncio.Event())
    with pytest.raises(TimeoutError):
        await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert conn.rollbacks == 1
    assert not summary._mart_execution_lock.locked()
    conn.gate.set()
    await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert conn.commits == 1


async def test_cancel_rolls_back_and_does_not_debounce():
    key = ("u", date.today())
    assert (await summary._claim_forced_mart_refresh(*key))[0]
    conn = Connection(gate=asyncio.Event())
    task = asyncio.create_task(summary._execute_mart_refresh(*key, conn=conn))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await summary._release_forced_mart_refresh(*key, completed=False)
    assert conn.rollbacks == 1
    assert (await summary._claim_forced_mart_refresh(*key))[0]
    await summary._release_forced_mart_refresh(*key, completed=True)
    assert await summary._claim_forced_mart_refresh(*key) == (False, "recent")


async def test_historical_sync_is_serial_and_current_refresh_does_not_wait(monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    active = peak = 0
    done = []

    async def execute(user, day, tz):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        async with summary._mart_execution_lock:
            entered.set()
            await release.wait()
            done.append(day)
        active -= 1

    monkeypatch.setattr(ingest, "_execute_refresh", execute)
    days = [date(2026, 1, 1) + timedelta(days=n) for n in range(100)]
    for day in days:
        assert await ingest._maybe_schedule_refresh("u", day, 1)
    await entered.wait()
    assert len(ingest._pending_refresh_requests) == 99
    # A read already holding a pool connection must immediately use its normal
    # read/fallback path rather than queue for refresh or acquire another slot.
    current_conn = Connection()
    with pytest.raises(summary.MartRefreshBusy):
        await summary._execute_mart_refresh("u", date.today(), conn=current_conn)
    assert not current_conn.sql
    release.set()
    task = ingest._refresh_worker_task
    await task
    assert peak == 1
    assert done == days
    assert ingest._refresh_worker_task is None


async def test_repeated_requests_coalesce_and_inflight_gets_one_trailing_refresh(monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def execute(user, day, tz):
        calls.append((user, day, tz))
        entered.set()
        await release.wait()

    monkeypatch.setattr(ingest, "_execute_refresh", execute)
    day = date.today()
    assert await ingest._maybe_schedule_refresh("u", day, 1)
    assert not await ingest._maybe_schedule_refresh("u", day, 1)
    await entered.wait()
    assert await ingest._maybe_schedule_refresh("u", day, 1, "UTC")
    for _ in range(20):
        assert not await ingest._maybe_schedule_refresh("u", day, 1, "UTC")
    release.set()
    await ingest._refresh_worker_task
    assert len(calls) == 2
    assert calls[-1][-1] == "UTC"


async def test_large_historical_import_preserves_every_unique_date(monkeypatch):
    calls = []

    async def execute(user, day, tz):
        calls.append(day)

    monkeypatch.setattr(ingest, "_execute_refresh", execute)
    days = [date(2023, 1, 1) + timedelta(days=n) for n in range(1200)]
    for day in days:
        assert await ingest._maybe_schedule_refresh("u", day, 1)
    assert len(ingest._pending_refresh_requests) == len(days)
    await ingest._refresh_worker_task
    assert calls == days
    assert not ingest._pending_refresh_requests


async def test_failure_cycles_are_bounded_and_dirty_date_survives_recovery(monkeypatch):
    count = 0
    failed_cycle = asyncio.Event()
    monkeypatch.setattr(ingest, "_REFRESH_FAILURE_COOLDOWN_SECONDS", 0.03)

    async def fail(*args):
        nonlocal count
        count += 1
        if count == ingest._DELAYED_REFRESH_MAX_PRESSURE_RETRIES + 1:
            failed_cycle.set()
        raise RuntimeError("DB unavailable")

    monkeypatch.setattr(ingest, "_execute_refresh", fail)
    key = ("u", date.today())
    assert await ingest._maybe_schedule_refresh(*key, 1)
    await failed_cycle.wait()
    await asyncio.sleep(0)
    assert count == ingest._DELAYED_REFRESH_MAX_PRESSURE_RETRIES + 1
    assert key not in ingest._recent_refresh_requests
    assert key in ingest._pending_refresh_requests

    async def succeed(*args):
        return None

    monkeypatch.setattr(ingest, "_execute_refresh", succeed)
    # No new upload is needed to recover the retained dirty date.
    await ingest._refresh_worker_task
    assert key in ingest._recent_refresh_requests
    assert key not in ingest._pending_refresh_requests


async def test_mart_failure_does_not_start_gauge_scoring(monkeypatch):
    async def fail(*args):
        raise RuntimeError("mart failed")

    async def forbidden(*args):
        pytest.fail("scored gauges after failed mart")

    monkeypatch.setattr(summary, "_execute_mart_refresh", fail)
    monkeypatch.setattr(asyncio, "to_thread", forbidden)
    with pytest.raises(RuntimeError, match="mart failed"):
        await ingest._execute_refresh("u", date.today())


async def test_gauge_failure_is_not_reported_as_success(monkeypatch):
    async def succeed(*args):
        return None

    async def failed_result(*args):
        return {"ok": False}

    monkeypatch.setattr(summary, "_execute_mart_refresh", succeed)
    monkeypatch.setattr(asyncio, "to_thread", failed_result)
    with pytest.raises(RuntimeError, match="did not complete"):
        await ingest._execute_refresh("u", date.today())


async def test_new_samples_during_success_debounce_get_trailing_refresh(monkeypatch):
    monkeypatch.setattr(ingest, "_DELAYED_REFRESH_DEBOUNCE_SECONDS", 0.03)
    calls = []

    async def execute(user, day, tz):
        calls.append(user)

    monkeypatch.setattr(ingest, "_execute_refresh", execute)
    day = date.today()
    await ingest._maybe_schedule_refresh("u", day, 1)
    await ingest._refresh_worker_task
    assert calls == ["u"]
    assert await ingest._maybe_schedule_refresh("u", day, 1)
    assert not await ingest._maybe_schedule_refresh("u", day, 1)
    await asyncio.sleep(0)
    # Another user's ready work wakes a worker waiting on debounce.
    assert await ingest._maybe_schedule_refresh("other", day, 1)
    await ingest._refresh_worker_task
    assert calls == ["u", "other", "u"]


async def test_cancelled_worker_drains_scoring_before_releasing_ownership(monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def mart(*args):
        return None

    async def score(*args):
        entered.set()
        await release.wait()
        return {"ok": True}

    monkeypatch.setattr(summary, "_execute_mart_refresh", mart)
    monkeypatch.setattr(asyncio, "to_thread", score)
    await ingest._maybe_schedule_refresh("u", date.today(), 1)
    await entered.wait()
    task = ingest._refresh_worker_task
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert ingest._refresh_worker_task is task
    assert await ingest._maybe_schedule_refresh("other", date.today(), 1)
    assert ingest._refresh_worker_task is task
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ingest._refresh_worker_task is None


async def test_same_pending_key_restarts_cancelled_worker(monkeypatch):
    gate = asyncio.Event()
    entered = asyncio.Event()

    async def wait(*args):
        entered.set()
        await gate.wait()

    monkeypatch.setattr(ingest, "_execute_refresh", wait)
    await ingest._maybe_schedule_refresh("first", date.today(), 1)
    await ingest._maybe_schedule_refresh("pending", date.today(), 1)
    await entered.wait()
    task = ingest._refresh_worker_task
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ingest._refresh_worker_task is None
    gate.set()
    assert not await ingest._maybe_schedule_refresh("pending", date.today(), 1)
    assert ingest._refresh_worker_task is not None
    # The cancelled active key is preserved too (on its cooldown).
    assert ("first", date.today()) in ingest._pending_refresh_requests


async def test_trailing_dirty_key_cannot_bypass_failure_cooldown(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    failed = asyncio.Event()
    monkeypatch.setattr(ingest, "_DELAYED_REFRESH_MAX_PRESSURE_RETRIES", 0)
    monkeypatch.setattr(ingest, "_REFRESH_FAILURE_COOLDOWN_SECONDS", 30)

    async def fail(*args):
        started.set()
        await release.wait()
        failed.set()
        raise RuntimeError("slow query")

    monkeypatch.setattr(ingest, "_execute_refresh", fail)
    key = ("u", date.today())
    await ingest._maybe_schedule_refresh(*key, 1)
    await started.wait()
    await ingest._maybe_schedule_refresh(*key, 1, "Pacific/Auckland")
    release.set()
    await failed.wait()
    await asyncio.sleep(0)
    tz, ready_at = ingest._pending_refresh_requests[key]
    assert tz == "Pacific/Auckland"
    assert ready_at - asyncio.get_running_loop().time() > 29
    # Another upload coalesces without erasing the retry deadline.
    assert not await ingest._maybe_schedule_refresh(*key, 1, "UTC")
    assert ingest._pending_refresh_requests[key] == ("UTC", ready_at)
    assert key not in ingest._recent_refresh_requests


@pytest.mark.parametrize("pressure", [False, True])
async def test_forced_fallback_queues_requested_day_and_timezone(monkeypatch, pressure):
    from starlette.requests import Request

    today = date(2026, 10, 10)
    yesterday = today - timedelta(days=1)
    queued = []
    request = Request({
        "type": "http", "method": "GET", "path": "/v1/features/today",
        "query_string": b"force=1&tz=Pacific%2FAuckland", "headers": [],
    })
    request.state.user_id = "u"

    async def no_cache(*args, **kwargs):
        return None

    async def current_day(*args):
        return today

    async def fail_refresh(*args, **kwargs):
        raise TimeoutError("interactive budget exhausted")

    async def collect(*args, **kwargs):
        return (
            {"user_id": "u", "day": yesterday, "steps_total": 1},
            {"source": "yesterday", "day": today, "day_used": yesterday},
            None,
        )

    async def queue(user, day, tz_name):
        queued.append((user, day, tz_name))
        return True

    monkeypatch.setattr(summary, "get_last_good", no_cache)
    monkeypatch.setattr(summary, "set_last_good", no_cache)
    monkeypatch.setattr(summary, "_current_day_local", current_day)
    monkeypatch.setattr(summary, "_execute_mart_refresh", fail_refresh)
    monkeypatch.setattr(summary, "_collect_features", collect)
    monkeypatch.setattr(summary, "mart_refresh", queue)
    monkeypatch.setattr(summary, "_db_pressure_reason", lambda: "db_pressure" if pressure else None)
    response = await summary.features_today(request, conn=Connection())
    assert response["ok"] is True
    assert queued == [("u", today, "Pacific/Auckland")]
    assert ("u", today) not in summary._forced_refresh_registry


async def test_commit_log_is_not_emitted_for_failed_write(monkeypatch, caplog):
    caplog.set_level("INFO", logger=summary.__name__)
    conn = Connection(fail="marts.refresh_daily_features_user")
    with pytest.raises(RuntimeError):
        await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert "refresh committed" not in caplog.text
    conn.fail = None
    await summary._execute_mart_refresh("u", date.today(), conn=conn)
    assert "refresh committed mode=interactive" in caplog.text
    assert conn.commits == 1


async def test_mart_select_logs_read_not_write_success(caplog):
    caplog.set_level("INFO", logger=summary.__name__)

    class ReadConnection(Connection):
        @asynccontextmanager
        async def cursor(self, *args, **kwargs):
            yield self

    await summary._fetch_mart_row(ReadConnection(), "u", date.today())
    assert "[MART] read completed" in caplog.text
    assert "refresh completed" not in caplog.text
    assert "refresh committed" not in caplog.text
