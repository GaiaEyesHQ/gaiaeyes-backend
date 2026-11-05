"""Opt-in cancellation tests against a disposable numeric-loopback PostgreSQL.

GAIA_TEST_POSTGRES_DSN must explicitly select a local CREATE DATABASE role.
Every connection uses the uniquely created synthetic database, never an app DSN.
Real driver/pool operations are retained; event spies and actual Python locks
make otherwise rare cancellation windows deterministic. No PgBouncer coverage.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
from time import monotonic
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.pq import TransactionStatus
import pytest

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not os.getenv("GAIA_TEST_POSTGRES_DSN"),
        reason="set GAIA_TEST_POSTGRES_DSN for disposable local PostgreSQL tests",
    ),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def postgres_dsn():
    options = conninfo_to_dict(os.environ["GAIA_TEST_POSTGRES_DSN"])
    host = options.get("host")
    if host not in {"127.0.0.1", "::1"} or "service" in options:
        pytest.fail("pool integration tests require explicit numeric loopback")
    if options.get("hostaddr", host) != host:
        pytest.fail("hostaddr must match the explicit loopback host")
    options.update(hostaddr=host, sslmode="disable", connect_timeout="3")
    name = "gaia_pool_cancel_" + uuid4().hex
    with psycopg.connect(make_conninfo(**options), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            options["dbname"] = name
            yield make_conninfo(**options)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def control(postgres_dsn):
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute("CREATE TABLE cancellation_probe (value integer)")
        yield conn
        conn.execute("DROP TABLE cancellation_probe CASCADE")
        conn.execute("DROP FUNCTION IF EXISTS slow_commit_probe()")


@pytest.fixture
def app_db(postgres_dsn, monkeypatch):
    for key in ("DATABASE_URL", "SUPABASE_DB_URL", "DIRECT_URL"):
        monkeypatch.setenv(key, postgres_dsn)
    from app import db
    return db


@asynccontextmanager
async def local_pool(app_db, postgres_dsn, **kwargs):
    async with app_db._CancellationSafePool(
        postgres_dsn, min_size=1, max_size=1, open=False, timeout=1,
        kwargs={"prepare_threshold": None}, **kwargs,
    ) as pool:
        await pool.wait(timeout=5)
        yield pool


async def wait_for_server_sleep(control, pid):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        if control.execute(
            "SELECT wait_event FROM pg_stat_activity WHERE pid=%s", (pid,)
        ).fetchone() == ("PgSleep",):
            return
        await asyncio.sleep(0.01)
    pytest.fail("server never reached the cancellation probe")


async def assert_reusable(pool, pid, control):
    stats = pool.get_stats()
    assert stats["pool_size"] == stats["pool_available"] == 1
    assert stats.get("requests_waiting", 0) == 0
    async with pool.connection(timeout=1) as conn:
        assert conn.info.backend_pid == pid
        assert conn.info.transaction_status == TransactionStatus.IDLE
        assert await (await conn.execute("SELECT 42")).fetchone() == (42,)
    assert control.execute("SELECT count(*) FROM cancellation_probe").fetchone() == (0,)
    assert pool.get_stats()["pool_available"] == 1


async def test_repeated_request_cancellation_rolls_back_and_reuses_single_slot(
    app_db, postgres_dsn, control, monkeypatch,
):
    async with local_pool(app_db, postgres_dsn) as pool:
        async def get_pool():
            return pool
        monkeypatch.setattr(app_db, "get_pool", get_pool)
        async with pool.connection() as conn:
            pid = conn.info.backend_pid

        async def request():
            async with asynccontextmanager(app_db.get_db)() as conn:
                await conn.execute("INSERT INTO cancellation_probe VALUES (1)")
                await conn.execute("SELECT pg_sleep(10)")

        for _ in range(8):
            task = asyncio.create_task(request())
            try:
                await wait_for_server_sleep(control, pid)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 5)
            await assert_reusable(pool, pid, control)


async def test_checkout_check_cancellation_returns_real_connection(
    app_db, postgres_dsn, control,
):
    checking = True
    observed_pid = asyncio.Future()

    async def check(conn):
        if checking:
            observed_pid.set_result(conn.info.backend_pid)
            await conn.execute("SELECT pg_sleep(10)")

    async with local_pool(app_db, postgres_dsn, check=check) as pool:
        async def request():
            async with pool.connection():
                pytest.fail("cancelled checkout must not reach request body")

        task = asyncio.create_task(request())
        try:
            pid = await asyncio.wait_for(observed_pid, 5)
            await wait_for_server_sleep(control, pid)
        finally:
            checking = False
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        await assert_reusable(pool, pid, control)


@pytest.mark.parametrize("from_checkout", [False, True])
async def test_repeated_cancellation_while_actual_pool_return_lock_is_held(
    app_db, postgres_dsn, control, monkeypatch, from_checkout,
):
    checking = from_checkout
    check_started = asyncio.Event()
    return_started = asyncio.Event()
    request_started = asyncio.Event()
    finish_request = asyncio.Event()
    pid = None

    async def check(conn):
        nonlocal pid
        pid = conn.info.backend_pid
        if checking:
            check_started.set()
            await conn.execute("SELECT pg_sleep(10)")

    async with local_pool(app_db, postgres_dsn, check=check) as pool:
        original_add = pool._add_to_pool

        async def observed_add(conn):
            return_started.set()
            await original_add(conn)

        monkeypatch.setattr(pool, "_add_to_pool", observed_add)

        async def request():
            async with pool.connection() as conn:
                await conn.execute("SELECT 1")
                request_started.set()
                await finish_request.wait()

        task = asyncio.create_task(request())
        try:
            if from_checkout:
                await asyncio.wait_for(check_started.wait(), 5)
                await wait_for_server_sleep(control, pid)
            else:
                await asyncio.wait_for(request_started.wait(), 5)
            async with pool._lock:
                checking = False
                if from_checkout:
                    task.cancel()
                else:
                    finish_request.set()
                await asyncio.wait_for(return_started.wait(), 5)
                for _ in range(3):
                    task.cancel()
                    await asyncio.sleep(0)
                assert not task.done(), "return ownership must not be abandoned"
                assert pool.get_stats()["pool_available"] == 0
        finally:
            finish_request.set()
            if not task.done():
                task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        await assert_reusable(pool, pid, control)


async def test_cancellation_of_real_deferred_commit_rolls_back_and_reuses_slot(
    app_db, postgres_dsn, control,
):
    # A deferred trigger runs during COMMIT, not INSERT. This is a real server
    # cancellation of commit before it completes, not a mocked commit method.
    control.execute("""
        CREATE FUNCTION slow_commit_probe() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN PERFORM pg_sleep(10); RETURN NEW; END $$;
        CREATE CONSTRAINT TRIGGER slow_commit AFTER INSERT ON cancellation_probe
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION slow_commit_probe();
    """)
    async with local_pool(app_db, postgres_dsn) as pool:
        async with pool.connection() as conn:
            pid = conn.info.backend_pid

        async def request():
            async with pool.connection() as conn:
                await conn.execute("INSERT INTO cancellation_probe VALUES (1)")

        task = asyncio.create_task(request())
        try:
            await wait_for_server_sleep(control, pid)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        await assert_reusable(pool, pid, control)


async def test_interrupted_rollback_is_reset_before_real_connection_reuse(
    app_db, postgres_dsn, control, monkeypatch,
):
    async with local_pool(app_db, postgres_dsn) as pool:
        async with pool.connection() as conn:
            pid = conn.info.backend_pid
        rollback_started = asyncio.Event()
        request_started = asyncio.Event()
        fail_request = asyncio.Event()
        original_rollback = conn.rollback

        async def observed_rollback():
            rollback_started.set()
            await original_rollback()

        monkeypatch.setattr(conn, "rollback", observed_rollback)

        async def request():
            async with pool.connection() as borrowed:
                await borrowed.execute("INSERT INTO cancellation_probe VALUES (1)")
                request_started.set()
                await fail_request.wait()
                raise ValueError("synthetic endpoint failure")

        task = asyncio.create_task(request())
        try:
            await asyncio.wait_for(request_started.wait(), 5)
            # Interrupt rollback at psycopg's real connection-lock acquisition.
            # The shielded pool reset must subsequently run a real ROLLBACK.
            async with conn.lock:
                fail_request.set()
                await asyncio.wait_for(rollback_started.wait(), 5)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
        finally:
            fail_request.set()
            if not task.done():
                task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        await assert_reusable(pool, pid, control)
