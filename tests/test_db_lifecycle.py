"""Connection ownership regressions; all connections are local test doubles.

The library regression executes the installed pool's actual checkout loop with
its network/check/return operations stubbed. No database is opened or modified.
"""
import asyncio
from contextlib import asynccontextmanager
from time import monotonic

import pytest
from psycopg import OperationalError, errors
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from app import db


class Connection:
    def __init__(self):
        self.setup_error = None
        self.setup_started = None
        self.setup_release = None
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, query):
        if self.setup_started is not None:
            self.setup_started.set()
            await self.setup_release.wait()
        if self.setup_error:
            raise self.setup_error


class Pool:
    def __init__(self):
        self.conn = Connection()
        self.borrowed = 0
        self.acquisitions = 0
        self.returns = 0
        self.acquire_errors = []
        self.exit_error = None

    @asynccontextmanager
    async def connection(self):
        self.acquisitions += 1
        if self.acquire_errors:
            raise self.acquire_errors.pop(0)
        self.borrowed += 1
        try:
            try:
                yield self.conn
            except BaseException:
                self.conn.rollbacks += 1
                raise
            else:
                self.conn.commits += 1
                if self.exit_error:
                    raise self.exit_error
        finally:
            self.borrowed -= 1
            self.returns += 1

    def get_stats(self):
        return {"pool_size": 1, "pool_available": 1 - self.borrowed}


@pytest.fixture
def pool(monkeypatch):
    pool = Pool()

    async def get_pool():
        return pool

    monkeypatch.setattr(db, "get_pool", get_pool)
    return pool


def test_success_returns_connection_once(pool):
    async def run():
        async with asynccontextmanager(db.get_db)() as conn:
            assert conn is pool.conn
            assert pool.borrowed == 1
        assert pool.borrowed == 0
        assert pool.returns == pool.acquisitions == pool.conn.commits == 1
    asyncio.run(run())


@pytest.mark.parametrize("error", [ValueError("endpoint failed"),
                                    errors.InFailedSqlTransaction("aborted"),
                                    OperationalError("connection failed"),
                                    PoolTimeout("endpoint timed out")])
def test_endpoint_errors_propagate_without_second_yield(pool, monkeypatch, error):
    async def unexpected_failover(*args):
        pytest.fail("endpoint errors must not retry the dependency")

    monkeypatch.setattr(db, "handle_connection_failure", unexpected_failover)
    monkeypatch.setattr(db, "handle_pool_timeout", unexpected_failover)

    async def run():
        async with asynccontextmanager(db.get_db)():
            raise error

    with pytest.raises(type(error)) as caught:
        asyncio.run(run())
    assert caught.value is error
    assert pool.acquisitions == pool.returns == pool.conn.rollbacks == 1
    assert pool.borrowed == 0


def test_generator_close_returns_connection_immediately(pool):
    async def run():
        gen = db.get_db()
        await anext(gen)
        await gen.aclose()
        # Check before GC/event-loop shutdown can finalize an abandoned context.
        assert pool.borrowed == 0
        assert pool.returns == pool.conn.rollbacks == 1
    asyncio.run(run())


def test_cancellation_during_setup_returns_connection(pool):
    async def run():
        pool.conn.setup_started = asyncio.Event()
        pool.conn.setup_release = asyncio.Event()
        gen = db.get_db()
        task = asyncio.create_task(anext(gen))
        await asyncio.wait_for(pool.conn.setup_started.wait(), 1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pool.borrowed == 0
        assert pool.returns == pool.conn.rollbacks == 1
        await gen.aclose()
    asyncio.run(run())


def test_repeated_request_cancellation_does_not_consume_slots(pool):
    async def run():
        async def request(started):
            async with asynccontextmanager(db.get_db)():
                started.set()
                await asyncio.Event().wait()

        for _ in range(16):
            started = asyncio.Event()
            task = asyncio.create_task(request(started))
            await asyncio.wait_for(started.wait(), 1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert pool.borrowed == 0
        assert pool.acquisitions == pool.returns == pool.conn.rollbacks == 16
        async with asynccontextmanager(db.get_db)():
            assert pool.borrowed == 1
        assert pool.borrowed == 0
    asyncio.run(run())


def test_setup_failure_returns_connection_before_failover(pool, monkeypatch):
    pool.conn.setup_error = OperationalError("setup disconnected")
    calls = []

    async def failover(exc):
        assert pool.borrowed == 0
        calls.append(exc)
        pool.conn.setup_error = None
        return True

    monkeypatch.setattr(db, "handle_connection_failure", failover)

    async def run():
        async with asynccontextmanager(db.get_db)():
            pass
    asyncio.run(run())
    assert len(calls) == 1
    assert pool.acquisitions == pool.returns == 2
    assert pool.conn.rollbacks == pool.conn.commits == 1


def test_acquisition_timeouts_remain_bounded(pool, monkeypatch):
    pool.acquire_errors = [PoolTimeout("busy") for _ in range(3)]
    delays = []

    async def no_failover(reason):
        return False

    async def no_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(db, "handle_pool_timeout", no_failover)
    monkeypatch.setattr(db.asyncio, "sleep", no_sleep)

    async def run():
        async with asynccontextmanager(db.get_db)():
            pytest.fail("acquisition should fail before endpoint runs")
    with pytest.raises(PoolTimeout):
        asyncio.run(run())
    assert pool.acquisitions == 3
    assert pool.borrowed == pool.returns == 0
    assert delays == [1.5, 1.5]


def test_commit_error_is_not_retried(pool):
    pool.exit_error = OperationalError("commit failed")

    async def run():
        async with asynccontextmanager(db.get_db)():
            pass
    with pytest.raises(OperationalError, match="commit failed"):
        asyncio.run(run())
    assert pool.acquisitions == pool.returns == 1
    assert pool.borrowed == 0


def test_pool_disables_prepared_statements(monkeypatch):
    options = {}

    def construct(**kwargs):
        options.update(kwargs)
        return object()

    monkeypatch.setattr(db, "_CancellationSafePool", construct)
    db._make_pool("postgresql://unused")
    assert options["kwargs"]["prepare_threshold"] is None


def test_installed_pool_returns_checkout_on_check_cancellation(monkeypatch):
    async def run():
        # Do not open: no real connection or database is used by this test.
        pool = AsyncConnectionPool("", min_size=0, max_size=1, open=False)
        conn = object()
        started = asyncio.Event()
        returned = []

        async def acquire(timeout):
            return conn

        async def check(actual):
            assert actual is conn
            started.set()
            await asyncio.Event().wait()

        async def put(actual, *, from_getconn):
            returned.append((actual, from_getconn))

        monkeypatch.setattr(pool, "_getconn_unchecked", acquire)
        monkeypatch.setattr(pool, "_check_connection", check)
        monkeypatch.setattr(pool, "_putconn", put)
        task = asyncio.create_task(pool._getconn_with_check_loop(monotonic() + 0.5))
        await asyncio.wait_for(started.wait(), 1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1.0)
        assert returned == [(conn, True)]
    asyncio.run(run())


@pytest.mark.parametrize("endpoint_cancelled", [False, True])
def test_cancellation_during_cleanup_waits_for_pool_return(monkeypatch, endpoint_cancelled):
    async def run():
        pool = Pool()
        cleanup_started = asyncio.Event()
        cleanup_release = asyncio.Event()
        request_started = asyncio.Event()

        # Exercise the installed library's native connection() context; emulate
        # a contended pool return lock rather than replacing its cleanup logic.
        native_pool = db._CancellationSafePool("", min_size=0, max_size=1, open=False)

        class NativeConn:
            async def execute(self, query):
                await pool.conn.execute(query)

            async def __aenter__(self):
                pool.borrowed += 1
                return pool.conn

            async def __aexit__(self, exc_type, exc, tb):
                if exc_type is None:
                    pool.conn.commits += 1
                else:
                    pool.conn.rollbacks += 1

        async def getconn(timeout=None):
            return NativeConn()

        async def putconn(conn, *, from_getconn):
            cleanup_started.set()
            await cleanup_release.wait()
            pool.borrowed -= 1
            pool.returns += 1

        async def get_pool():
            return native_pool

        monkeypatch.setattr(native_pool, "getconn", getconn)
        monkeypatch.setattr(native_pool, "_return_connection", putconn)
        monkeypatch.setattr(native_pool, "_check_pool_putconn", lambda conn: None)
        monkeypatch.setattr(native_pool, "_closed", False)
        monkeypatch.setattr(db, "get_pool", get_pool)

        async def request():
            async with asynccontextmanager(db.get_db)():
                request_started.set()
                if endpoint_cancelled:
                    await asyncio.Event().wait()

        task = asyncio.create_task(request())
        await asyncio.wait_for(request_started.wait(), 1.0)
        if endpoint_cancelled:
            task.cancel()
        await asyncio.wait_for(cleanup_started.wait(), 1.0)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "caller must retain ownership until return finishes"
        assert pool.borrowed == 1
        cleanup_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pool.borrowed == 0
        assert pool.returns == 1
        assert pool.conn.rollbacks == int(endpoint_cancelled)
        assert pool.conn.commits == int(not endpoint_cancelled)
        monkeypatch.setattr(native_pool, "_closed", True)
    asyncio.run(run())


@pytest.mark.parametrize("from_checkout", [False, True])
def test_all_pool_return_paths_survive_repeated_cancellation(monkeypatch, from_checkout):
    async def run():
        pool = db._CancellationSafePool("", min_size=0, max_size=1, open=False)
        check_started = asyncio.Event()
        return_started = asyncio.Event()
        return_release = asyncio.Event()
        returned = []

        class Conn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        conn = Conn()

        async def acquire(timeout):
            return conn

        async def check(actual):
            check_started.set()
            if from_checkout:
                await asyncio.Event().wait()

        async def return_connection(actual, *, from_getconn):
            return_started.set()
            await return_release.wait()
            returned.append((actual, from_getconn))

        # Stub only network/bookkeeping boundaries. The checkout check, public
        # connection/putconn and protected _putconn override are real code.
        monkeypatch.setattr(pool, "_getconn_unchecked", acquire)
        monkeypatch.setattr(pool, "_check_connection", check)
        monkeypatch.setattr(pool, "_return_connection", return_connection)
        monkeypatch.setattr(pool, "_check_open_getconn", lambda: None)
        monkeypatch.setattr(pool, "_check_pool_putconn", lambda actual: None)
        monkeypatch.setattr(pool, "_closed", False)

        async def request():
            async with pool.connection():
                pass

        task = asyncio.create_task(request())
        await asyncio.wait_for(check_started.wait(), 1.0)
        if from_checkout:
            task.cancel()
        await asyncio.wait_for(return_started.wait(), 1.0)
        for _ in range(3):
            task.cancel()
            await asyncio.sleep(0)
        assert not task.done()
        assert returned == []
        return_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert returned == [(conn, from_checkout)]
        monkeypatch.setattr(pool, "_closed", True)
    asyncio.run(run())


@pytest.mark.parametrize("during_rollback", [False, True])
def test_native_transaction_cleanup_cancellation_resets_before_return(monkeypatch, during_rollback):
    from types import SimpleNamespace
    from psycopg import AsyncConnection
    from psycopg.pq import TransactionStatus

    async def run():
        pool = db._CancellationSafePool("", min_size=0, max_size=1, open=False)
        cleanup_started = asyncio.Event()
        returned = []

        class Conn:
            # Run the driver's real commit/rollback context-exit logic.
            __aexit__ = AsyncConnection.__aexit__
            closed = False
            _pool = pool
            _created_at = monotonic() + 1
            _expire_at = monotonic() + 60
            pgconn = SimpleNamespace(transaction_status=TransactionStatus.INTRANS)
            rollback_calls = 0

            async def __aenter__(self):
                return self

            async def commit(self):
                assert not during_rollback
                cleanup_started.set()
                await asyncio.Event().wait()

            async def rollback(self):
                self.rollback_calls += 1
                if during_rollback and self.rollback_calls == 1:
                    cleanup_started.set()
                    await asyncio.Event().wait()
                self.pgconn.transaction_status = TransactionStatus.IDLE

        conn = Conn()

        async def getconn(timeout=None):
            return conn

        async def add_to_pool(actual):
            assert actual.pgconn.transaction_status == TransactionStatus.IDLE
            returned.append(actual)

        monkeypatch.setattr(pool, "getconn", getconn)
        monkeypatch.setattr(pool, "_add_to_pool", add_to_pool)
        monkeypatch.setattr(pool, "_check_pool_putconn", lambda actual: None)
        monkeypatch.setattr(pool, "_closed", False)

        async def request():
            async with pool.connection():
                if during_rollback:
                    raise ValueError("endpoint failed")

        task = asyncio.create_task(request())
        await asyncio.wait_for(cleanup_started.wait(), 1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1.0)
        assert returned == [conn]
        assert conn.rollback_calls == (2 if during_rollback else 1)
        monkeypatch.setattr(pool, "_closed", True)
    asyncio.run(run())
