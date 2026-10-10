"""Opt-in real PostgreSQL checks for refresh transaction and connection mechanics.

Set GAIA_TEST_POSTGRES_DSN to a disposable local PostgreSQL admin URL whose role
can CREATE DATABASE, for example postgresql://test@127.0.0.1:55432/postgres.
Run: python -m pytest tests/integration/test_refresh_postgres.py -q

The fixture creates and drops a uniquely named database. It rejects non-loopback
addresses and never uses DATABASE_URL to select the test server. These synthetic
functions exercise the real application code, psycopg, and PostgreSQL, but do not
validate production function logic/performance or PgBouncer itself.
"""
from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from time import monotonic
from urllib.parse import urlencode
from uuid import uuid4

import psycopg
import pytest
from psycopg import errors, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.pq import TransactionStatus
from psycopg_pool import AsyncConnectionPool

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not os.getenv("GAIA_TEST_POSTGRES_DSN"),
        reason="set GAIA_TEST_POSTGRES_DSN to opt into a disposable local database",
    ),
]
USER = "00000000-0000-4000-8000-000000000001"
DAY = date(2026, 1, 2)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def postgres_dsn():
    options = conninfo_to_dict(os.environ["GAIA_TEST_POSTGRES_DSN"])
    host = options.get("host")
    if host not in {"127.0.0.1", "::1"} or "service" in options:
        pytest.fail("integration tests require an explicit numeric loopback host")
    if options.get("hostaddr", host) != host:
        pytest.fail("integration hostaddr must match the explicit loopback host")
    # Pin the network address as well as the host, ignoring ambient PGHOSTADDR.
    options.update(hostaddr=host, sslmode="disable", connect_timeout="3")
    admin_dsn = make_conninfo(**options)
    name = "gaia_reliability_" + uuid4().hex
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            options["dbname"] = name
            yield make_conninfo(**options)
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def database(postgres_dsn):
    with psycopg.connect(postgres_dsn, autocommit=True) as control:
        control.execute(Path(__file__).with_name("fixtures").joinpath("refresh.sql").read_text())
        yield control
        control.execute("DROP SCHEMA gaia, marts, integration_probe CASCADE")


@pytest.fixture
def pg_client(postgres_dsn, monkeypatch):
    # Application imports need a DSN, but all exercised connections are explicitly
    # pointed at the disposable DB. Never inherit a potentially real service DSN.
    monkeypatch.setenv("DATABASE_URL", postgres_dsn)
    monkeypatch.setenv("SUPABASE_DB_URL", postgres_dsn)
    monkeypatch.setenv("DIRECT_URL", postgres_dsn)
    from services.db import PgClient

    options = conninfo_to_dict(postgres_dsn)
    # PgClient accepts URI DSNs (and normalizes sslmode); retain all local options.
    query = urlencode({k: v for k, v in options.items() if k != "dbname"})
    host = "[::1]" if options["host"] == "::1" else options["host"]
    return PgClient(f"postgresql://{host}/{options['dbname']}?{query}")


@pytest.fixture
async def refresh_state(monkeypatch, postgres_dsn):
    monkeypatch.setenv("DATABASE_URL", postgres_dsn)
    monkeypatch.setenv("SUPABASE_DB_URL", postgres_dsn)
    monkeypatch.setenv("DIRECT_URL", postgres_dsn)
    from app.routers import ingest, summary

    monkeypatch.setattr(summary, "_mart_execution_lock", asyncio.Lock())
    monkeypatch.setattr(summary, "_forced_refresh_lock", asyncio.Lock())
    monkeypatch.setattr(summary, "_forced_refresh_registry", {})
    monkeypatch.setattr(summary, "_forced_refresh_inflight", set())
    monkeypatch.setattr(ingest, "_recent_refresh_lock", asyncio.Lock())
    monkeypatch.setattr(ingest, "_refresh_queue_changed", asyncio.Event())
    monkeypatch.setattr(ingest, "_pending_refresh_requests", {})
    monkeypatch.setattr(ingest, "_recent_refresh_requests", {})
    monkeypatch.setattr(ingest, "_refresh_worker_task", None)
    monkeypatch.setattr(ingest, "_active_refresh_key", None)
    monkeypatch.setattr(ingest, "_refresh_task_factory", asyncio.create_task)
    monkeypatch.setattr(ingest, "REFRESH_DISABLED", False)
    monkeypatch.setattr(ingest, "_DELAYED_REFRESH_DELAY_SECONDS", 0)
    monkeypatch.setattr(ingest, "_DELAYED_REFRESH_PRESSURE_RETRY_SECONDS", 0.01)
    monkeypatch.setattr(summary, "_db_pressure_reason", lambda: None)
    yield summary, ingest
    task = ingest._refresh_worker_task
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def writes(database):
    return database.execute(
        "SELECT stage, backend_pid, transaction_id FROM integration_probe.writes"
    ).fetchall()


def observe_commit_logs(summary, database, monkeypatch):
    """Read on another connection at emission time, not merely after the call."""
    observed = []
    original_info = summary.logger.info

    def info(message, *args, **kwargs):
        if message.startswith("[MART] refresh committed"):
            observed.append((message % args, writes(database)))
        original_info(message, *args, **kwargs)

    monkeypatch.setattr(summary.logger, "info", info)
    return observed


def assert_lock_available(database, summary):
    with database.transaction():
        assert database.execute(
            "SELECT pg_try_advisory_xact_lock(%s, %s)", summary._MART_ADVISORY_LOCK
        ).fetchone() == (True,)


async def wait_for_sleep(database, backend_pid):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        row = database.execute(
            "SELECT wait_event FROM pg_stat_activity WHERE pid = %s", (backend_pid,)
        ).fetchone()
        if row == ("PgSleep",):
            return
        await asyncio.sleep(0.01)
    pytest.fail("refresh never reached the server-side pg_sleep probe")


@pytest.mark.parametrize("stage", ["summary", "sleep", "features"])
async def test_each_stage_failure_rolls_back_every_write_and_reuses_connection(
    stage, postgres_dsn, database, refresh_state
):
    summary, _ = refresh_state
    database.execute("UPDATE integration_probe.control SET fail = true WHERE stage = %s", (stage,))
    async with await psycopg.AsyncConnection.connect(postgres_dsn) as conn:
        pid = conn.info.backend_pid
        with pytest.raises(errors.RaiseException, match=f"injected failure in {stage}"):
            await summary._execute_mart_refresh(USER, DAY, conn=conn)
        assert writes(database) == []
        assert conn.info.transaction_status == TransactionStatus.IDLE
        assert not summary._mart_execution_lock.locked()
        assert_lock_available(database, summary)
        database.execute("UPDATE integration_probe.control SET fail = false")
        await summary._execute_mart_refresh(USER, DAY, conn=conn)
        rows = writes(database)
        assert {row[0] for row in rows} == {"summary", "sleep", "features"}
        assert {row[1] for row in rows} == {pid}
        assert len({row[2] for row in rows}) == 1
        assert conn.info.transaction_status == TransactionStatus.IDLE


async def test_forced_refresh_uses_only_already_checked_out_connection(
    postgres_dsn, database, refresh_state, monkeypatch
):
    summary, _ = refresh_state

    async def forbidden_pool():
        pytest.fail("forced refresh attempted a second pool checkout")

    monkeypatch.setattr(summary, "get_pool", forbidden_pool)
    async with AsyncConnectionPool(postgres_dsn, min_size=1, max_size=1, open=False) as pool:
        await pool.wait()
        async with pool.connection() as conn:
            pid = conn.info.backend_pid
            # Exercise an existing read transaction as used by the request path.
            await conn.execute("SELECT value FROM integration_probe.current_snapshot")
            await summary._execute_mart_refresh(USER, DAY, conn=conn)
            assert {row[1] for row in writes(database)} == {pid}
            assert len(writes(database)) == 3
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert (await (await conn.execute("SHOW statement_timeout")).fetchone()) == ("0",)
            assert (await (await conn.execute("SHOW lock_timeout")).fetchone()) == ("0",)
        assert pool.get_stats()["requests_num"] == 1
    assert_lock_available(database, summary)


async def test_six_second_summary_times_out_interactively_but_commits_in_background(
    postgres_dsn, database, refresh_state, monkeypatch, caplog
):
    summary, _ = refresh_state
    # Exercise the actual deployed budgets once: tiny monkeypatched limits would
    # not catch applying the five-second request allowance to queued histories.
    assert summary._MART_REFRESH_STATEMENT_TIMEOUT_MS == 5000
    assert summary._MART_REFRESH_TIMEOUT_SECONDS == 15.0
    assert summary._BACKGROUND_MART_REFRESH_STATEMENT_TIMEOUT_MS == 60000
    assert summary._BACKGROUND_MART_REFRESH_TIMEOUT_SECONDS == 90.0
    database.execute("UPDATE integration_probe.control SET delay_seconds = 6 WHERE stage = 'summary'")
    caplog.set_level("INFO", logger=summary.logger.name)
    committed = observe_commit_logs(summary, database, monkeypatch)

    async with AsyncConnectionPool(postgres_dsn, min_size=1, max_size=1, open=False) as pool:
        await pool.wait()

        async def get_pool():
            return pool

        monkeypatch.setattr(summary, "get_pool", get_pool)
        async with pool.connection() as conn:
            pid = conn.info.backend_pid
            started = monotonic()
            with pytest.raises(errors.QueryCanceled, match="statement timeout"):
                await summary._execute_mart_refresh(USER, DAY, conn=conn)
            assert monotonic() - started >= 4.5
            assert writes(database) == []
            assert committed == []
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert not summary._mart_execution_lock.locked()
            assert_lock_available(database, summary)

        started = monotonic()
        await summary._execute_mart_refresh(USER, DAY)
        assert monotonic() - started >= 6
        rows = writes(database)
        assert {row[0] for row in rows} == {"summary", "sleep", "features"}
        assert len(rows) == 3
        assert {row[1] for row in rows} == {pid}
        assert len({row[2] for row in rows}) == 1
        assert database.execute(
            "SELECT DISTINCT statement_timeout, lock_timeout FROM integration_probe.writes"
        ).fetchall() == [("1min", "1s")]
        assert len(committed) == 1
        assert "mode=background" in committed[0][0]
        assert committed[0][1] == rows
        assert [
            record.getMessage() for record in caplog.records
            if record.getMessage().startswith("[MART] refresh committed")
        ] == [committed[0][0]]
        assert pool.get_stats()["pool_available"] == 1
        async with pool.connection(timeout=0.5) as conn:
            assert conn.info.backend_pid == pid
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert (await (await conn.execute("SHOW statement_timeout")).fetchone()) == ("0",)
            assert (await (await conn.execute("SHOW lock_timeout")).fetchone()) == ("0",)
    assert_lock_available(database, summary)


async def test_background_total_deadline_rolls_back_and_releases_pool_connection(
    postgres_dsn, database, refresh_state, monkeypatch, caplog
):
    summary, _ = refresh_state
    # The background total deadline must still bound the longer statement limit.
    monkeypatch.setattr(summary, "_BACKGROUND_MART_REFRESH_TIMEOUT_SECONDS", 0.4)
    database.execute("UPDATE integration_probe.control SET delay_seconds = 10 WHERE stage = 'sleep'")
    caplog.set_level("INFO", logger=summary.logger.name)
    committed = observe_commit_logs(summary, database, monkeypatch)

    async with AsyncConnectionPool(postgres_dsn, min_size=1, max_size=1, open=False) as pool:
        await pool.wait()

        async def get_pool():
            return pool

        monkeypatch.setattr(summary, "get_pool", get_pool)
        async with pool.connection() as conn:
            pid = conn.info.backend_pid
        task = asyncio.create_task(summary._execute_mart_refresh(USER, DAY))
        await wait_for_sleep(database, pid)
        with pytest.raises(TimeoutError):
            await task
        assert writes(database) == []
        assert committed == []
        assert not summary._mart_execution_lock.locked()
        assert_lock_available(database, summary)
        assert pool.get_stats()["pool_available"] == 1
        async with pool.connection(timeout=0.5) as conn:
            assert conn.info.backend_pid == pid
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert (await (await conn.execute("SHOW statement_timeout")).fetchone()) == ("0",)
            assert (await (await conn.execute("SHOW lock_timeout")).fetchone()) == ("0",)
        database.execute("UPDATE integration_probe.control SET delay_seconds = 0")
        await summary._execute_mart_refresh(USER, DAY)
        assert len(writes(database)) == 3
        assert {row[1] for row in writes(database)} == {pid}
        assert len(committed) == 1
        assert "mode=background" in committed[0][0]
        assert len(committed[0][1]) == 3
        assert [
            record.getMessage() for record in caplog.records
            if record.getMessage().startswith("[MART] refresh committed")
        ] == [committed[0][0]]
        assert pool.get_stats()["pool_available"] == 1
    assert_lock_available(database, summary)


async def test_other_connection_lock_is_nonblocking_then_retry_succeeds(
    postgres_dsn, database, refresh_state
):
    summary, _ = refresh_state
    with psycopg.connect(postgres_dsn) as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(%s, %s)", summary._MART_ADVISORY_LOCK)
        async with await psycopg.AsyncConnection.connect(postgres_dsn) as conn:
            started = monotonic()
            with pytest.raises(summary.MartRefreshBusy, match="another worker"):
                await asyncio.wait_for(summary._execute_mart_refresh(USER, DAY, conn=conn), 1)
            assert monotonic() - started < 1
            assert writes(database) == []
            assert conn.info.transaction_status == TransactionStatus.IDLE
            blocker.rollback()
            await summary._execute_mart_refresh(USER, DAY, conn=conn)
            assert len(writes(database)) == 3
    assert_lock_available(database, summary)


@pytest.mark.parametrize("interruption", ["cancel", "statement_timeout", "async_timeout"])
async def test_interruption_releases_transaction_lock_and_connection(
    interruption, postgres_dsn, database, refresh_state, monkeypatch
):
    summary, _ = refresh_state
    database.execute("UPDATE integration_probe.control SET delay_seconds = 10 WHERE stage = 'sleep'")
    if interruption == "statement_timeout":
        monkeypatch.setattr(summary, "_MART_REFRESH_STATEMENT_TIMEOUT_MS", 100)
    elif interruption == "async_timeout":
        monkeypatch.setattr(summary, "_MART_REFRESH_TIMEOUT_SECONDS", 0.1)
    async with await psycopg.AsyncConnection.connect(postgres_dsn) as conn:
        assert (await summary._claim_forced_mart_refresh(USER, DAY))[0]
        task = asyncio.create_task(summary._execute_mart_refresh(USER, DAY, conn=conn))
        if interruption == "cancel":
            await wait_for_sleep(database, conn.info.backend_pid)
            task.cancel()
            expected = asyncio.CancelledError
        elif interruption == "statement_timeout":
            expected = errors.QueryCanceled
        else:
            expected = TimeoutError
        with pytest.raises(expected):
            await task
        await summary._release_forced_mart_refresh(USER, DAY, completed=False)
        assert (await summary._claim_forced_mart_refresh(USER, DAY))[0]
        await summary._release_forced_mart_refresh(USER, DAY, completed=False)
        assert writes(database) == []
        assert conn.info.transaction_status == TransactionStatus.IDLE
        assert not summary._mart_execution_lock.locked()
        assert_lock_available(database, summary)
        database.execute("UPDATE integration_probe.control SET delay_seconds = 0")
        await summary._execute_mart_refresh(USER, DAY, conn=conn)
        assert len(writes(database)) == 3


async def test_relation_lock_timeout_rolls_back_and_releases_advisory_lock(
    postgres_dsn, database, refresh_state
):
    summary, _ = refresh_state
    with psycopg.connect(postgres_dsn) as blocker:
        blocker.execute("LOCK TABLE integration_probe.writes IN ACCESS EXCLUSIVE MODE")
        async with await psycopg.AsyncConnection.connect(postgres_dsn) as conn:
            with pytest.raises(errors.LockNotAvailable, match="lock timeout"):
                await summary._execute_mart_refresh(USER, DAY, conn=conn)
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert_lock_available(database, summary)
        blocker.rollback()
    assert writes(database) == []


def test_pgclient_timeout_rollback_reset_and_reuse(database, pg_client):
    with pg_client.connection_scope() as conn:
        pid = conn.info.backend_pid
        with pg_client.operation_timeouts(connect_timeout=2, statement_timeout_ms=100):
            with pytest.raises(errors.QueryCanceled, match="statement timeout"):
                pg_client.execute("SELECT pg_sleep(10)")
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "0"
            assert pg_client.fetchrow("SELECT current_setting('statement_timeout') AS value") == {"value": "100ms"}
            assert pg_client.fetchrow("SELECT pg_backend_pid() AS pid") == {"pid": pid}
        assert pg_client.fetchrow("SELECT current_setting('statement_timeout') AS value") == {"value": "0"}
        assert not conn.closed
    assert conn.closed
    assert pg_client._operation_timeout_settings.get() is None


def test_pgclient_each_operation_releases_connection_and_nested_timeouts(database, pg_client):
    query = "SELECT pg_backend_pid() AS pid, current_setting('statement_timeout') AS value"
    with pg_client.operation_timeouts(connect_timeout=2, statement_timeout_ms=500):
        first = pg_client.fetchrow(query)
        assert first["value"] == "500ms"
        assert database.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = %s", (first["pid"],)).fetchone() == (0,)
        with pg_client.operation_timeouts(connect_timeout=1, statement_timeout_ms=100):
            with pytest.raises(errors.QueryCanceled):
                pg_client.fetchrow("SELECT pg_sleep(10)")
        assert pg_client.fetchrow(query)["value"] == "500ms"
    assert pg_client.fetchrow(query)["value"] == "0"


def test_pgclient_timeout_contexts_are_isolated_across_threads(database, pg_client):
    barrier = threading.Barrier(2)

    def bounded():
        with pg_client.operation_timeouts(connect_timeout=2, statement_timeout_ms=100):
            barrier.wait(timeout=5)
            return pg_client.fetchrow("SELECT current_setting('statement_timeout') AS value")

    def ordinary():
        barrier.wait(timeout=5)
        return pg_client.fetchrow("SELECT current_setting('statement_timeout') AS value")

    with ThreadPoolExecutor(max_workers=2) as executor:
        bounded_result = executor.submit(bounded)
        ordinary_result = executor.submit(ordinary)
        assert bounded_result.result(timeout=5) == {"value": "100ms"}
        assert ordinary_result.result(timeout=5) == {"value": "0"}


async def test_historical_queue_and_current_reads_share_a_two_connection_pool(
    postgres_dsn, database, refresh_state, pg_client, monkeypatch
):
    from bots.gauges import gauge_scorer
    from services import db

    summary, ingest = refresh_state
    original_refresh = ingest._execute_refresh
    active = peak = 0
    gauge_started = threading.Event()
    release_gauge = threading.Event()
    gauge_calls = []
    days = [DAY + timedelta(days=i) for i in range(30)]
    database.execute("UPDATE integration_probe.control SET delay_seconds = 0.005")

    def synthetic_score(user, day, *, force):
        # Exercise the real PgClient path used by the worker with a small SQL
        # probe instead of production gauge schemas, calculations, or providers.
        timeout = pg_client.fetchrow("SELECT current_setting('statement_timeout') AS value")
        assert timeout == {"value": "5s"}
        if not gauge_calls:
            gauge_started.set()
            assert release_gauge.wait(timeout=5)
        pg_client.execute(
            "INSERT INTO integration_probe.writes(stage, user_id, day) VALUES ('gauge', %s, %s)",
            user, day,
        )
        gauge_calls.append(day)
        return {"ok": True, "skipped": False}

    async def observed_refresh(*args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            return await original_refresh(*args)
        finally:
            active -= 1

    monkeypatch.setattr(gauge_scorer, "score_user_day", synthetic_score)
    monkeypatch.setattr(db, "pg", pg_client)
    monkeypatch.setattr(ingest, "_execute_refresh", observed_refresh)
    async with AsyncConnectionPool(postgres_dsn, min_size=2, max_size=2, open=False) as pool:
        await pool.wait()

        async def get_pool():
            return pool

        monkeypatch.setattr(summary, "get_pool", get_pool)
        for day in days:
            assert await ingest._maybe_schedule_refresh(USER, day, 1)
        worker = ingest._refresh_worker_task
        assert worker is not None
        deadline = monotonic() + 5
        try:
            while not gauge_started.is_set():
                assert monotonic() < deadline
                await asyncio.sleep(0.01)
            assert len(ingest._pending_refresh_requests) == len(days) - 1
            # The gauge operation closed its synchronous connection before its
            # synthetic non-DB wait; only pool + observer connections remain.
            assert database.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            ).fetchone() == (3,)
            assert pool.get_stats()["pool_available"] == 2
            async with pool.connection(timeout=0.5) as conn:
                assert (await (await conn.execute("SELECT value FROM integration_probe.current_snapshot")).fetchone()) == (42,)
            assert not worker.done()
        finally:
            release_gauge.set()

        read_durations = []

        async def read_current():
            for _ in range(30):
                started = monotonic()
                async with pool.connection(timeout=1) as conn:
                    assert (await (await conn.execute("SELECT value FROM integration_probe.current_snapshot")).fetchone()) == (42,)
                read_durations.append(monotonic() - started)
                await asyncio.sleep(0.003)

        await asyncio.wait_for(asyncio.gather(worker, read_current(), read_current()), 15)
        assert peak == 1
        assert gauge_calls == days
        assert len(writes(database)) == len(days) * 4
        assert len(read_durations) == 60
        assert max(read_durations) < 1
        assert not ingest._pending_refresh_requests
        assert ingest._refresh_worker_task is None
        stats = pool.get_stats()
        assert stats["pool_size"] == 2
        assert stats["pool_available"] == 2
        assert stats.get("requests_errors", 0) == 0
        assert stats.get("requests_waiting", 0) == 0
        assert stats["requests_num"] == len(days) + 61
