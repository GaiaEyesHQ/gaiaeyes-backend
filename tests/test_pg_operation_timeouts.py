from __future__ import annotations

import asyncio
from contextlib import contextmanager

import pytest

from services import db


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.conn.events.append(("query", query, params))
        if self.conn.fail_query:
            raise TimeoutError("statement timeout")

    def fetchone(self):
        return {"value": 1}

    def fetchall(self):
        return [{"value": 1}]


class FakeConnection:
    def __init__(self):
        self.events = []
        self.closed = False
        self.fail_query = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *args):
        self.events.append(("rollback" if exc_type else "commit",))
        self.close()
        return False

    def execute(self, query):
        self.events.append(("setting", query))

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True

    @contextmanager
    def transaction(self):
        self.events.append(("begin",))
        try:
            yield
        except BaseException:
            self.events.append(("rollback",))
            raise
        else:
            self.events.append(("commit",))


@pytest.fixture
def client(monkeypatch):
    connections = []

    def connect(dsn, **kwargs):
        conn = FakeConnection()
        connections.append((dsn, kwargs, conn))
        return conn

    monkeypatch.setattr(db.psycopg, "connect", connect)
    return db.PgClient("postgresql://unit:unit@localhost/unit?connect_timeout=99"), connections


@pytest.mark.parametrize("method", ["fetch", "fetchrow", "execute"])
def test_each_operation_gets_timeouts_and_closes_its_connection(client, method):
    pg, connections = client
    with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
        assert connections == []
        for _ in range(2):
            getattr(pg, method)("select %s as value", 1)
            assert connections[-1][2].closed

    assert len(connections) == 2
    for _, kwargs, conn in connections:
        assert kwargs["connect_timeout"] == 5
        assert kwargs["autocommit"] is False
        assert conn.events == [
            ("setting", "SET LOCAL statement_timeout = 5000"),
            ("query", "select %s as value", (1,)),
            ("commit",),
        ]


def test_default_connections_keep_existing_settings(client):
    pg, connections = client
    pg.fetchrow("select 1 as value")
    dsn, kwargs, conn = connections[0]
    assert "connect_timeout=99" in dsn
    assert "connect_timeout" not in kwargs
    assert not any(event[0] == "setting" for event in conn.events)


def test_nested_timeouts_reset_after_exception(client):
    pg, connections = client
    with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
        with pytest.raises(RuntimeError):
            with pg.operation_timeouts(connect_timeout=2, statement_timeout_ms=2000):
                pg.fetchrow("select 1")
                raise RuntimeError("failed unit")
        pg.fetchrow("select 2")
    pg.fetchrow("select 3")
    assert [kwargs.get("connect_timeout") for _, kwargs, _ in connections] == [2, 5, None]
    assert connections[0][2].events[0] == ("setting", "SET LOCAL statement_timeout = 2000")
    assert connections[1][2].events[0] == ("setting", "SET LOCAL statement_timeout = 5000")


def test_operation_failure_rolls_back_and_resets_timeout_scope(client, monkeypatch):
    pg, connections = client
    original_connect = db.psycopg.connect

    def failing_connect(*args, **kwargs):
        conn = original_connect(*args, **kwargs)
        conn.fail_query = True
        return conn

    monkeypatch.setattr(db.psycopg, "connect", failing_connect)
    with pytest.raises(TimeoutError):
        with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
            pg.execute("update example set value = 1")
    assert connections[0][2].events[-1] == ("rollback",)
    assert connections[0][2].closed
    assert pg._operation_timeout_settings.get() is None


def test_scoped_autocommit_connection_keeps_timeout_in_query_transaction(client):
    pg, connections = client
    with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
        with pg.connection_scope():
            pg.fetchrow("select 1")
            pg.fetchrow("select 2")
            assert not connections[0][2].closed
    assert len(connections) == 1
    assert connections[0][1]["autocommit"] is True
    assert connections[0][2].closed
    assert connections[0][2].events == [
        ("begin",), ("setting", "SET LOCAL statement_timeout = 5000"),
        ("query", "select 1", ()), ("commit",),
        ("begin",), ("setting", "SET LOCAL statement_timeout = 5000"),
        ("query", "select 2", ()), ("commit",),
    ]


def test_default_connection_scope_reuses_connection_without_new_settings(client):
    pg, connections = client
    with pg.connection_scope():
        pg.fetchrow("select 1")
        pg.fetchrow("select 2")
        assert not connections[0][2].closed
    assert len(connections) == 1
    assert "connect_timeout" not in connections[0][1]
    assert connections[0][2].closed
    assert connections[0][2].events == [
        ("query", "select 1", ()), ("query", "select 2", ()),
    ]


def test_scoped_operation_failure_rolls_back_before_next_query(client):
    pg, connections = client
    with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
        with pg.connection_scope():
            conn = connections[0][2]
            conn.fail_query = True
            with pytest.raises(TimeoutError):
                pg.fetchrow("select 1")
            assert not conn.closed
            conn.fail_query = False
            assert pg.fetchrow("select 2") == {"value": 1}
    assert len(connections) == 1
    assert conn.closed
    assert conn.events == [
        ("begin",), ("setting", "SET LOCAL statement_timeout = 5000"),
        ("query", "select 1", ()), ("rollback",),
        ("begin",), ("setting", "SET LOCAL statement_timeout = 5000"),
        ("query", "select 2", ()), ("commit",),
    ]


def test_async_children_inherit_timeouts_without_affecting_other_tasks(client):
    pg, connections = client

    async def query(label):
        await asyncio.sleep(0)
        pg.fetchrow(label)

    async def run():
        ordinary = asyncio.create_task(query("ordinary"))
        with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
            bounded = asyncio.create_task(query("bounded"))
        await asyncio.gather(ordinary, bounded)

    asyncio.run(run())
    observed = {
        next(event[1] for event in conn.events if event[0] == "query"): kwargs.get("connect_timeout")
        for _, kwargs, conn in connections
    }
    assert observed == {"ordinary": None, "bounded": 5}


@pytest.mark.parametrize("connect_timeout,statement_timeout_ms", [(0, 5000), (5, 0), (-1, 1)])
def test_invalid_timeouts_do_not_change_context(client, connect_timeout, statement_timeout_ms):
    pg, connections = client
    with pytest.raises(ValueError):
        with pg.operation_timeouts(
            connect_timeout=connect_timeout, statement_timeout_ms=statement_timeout_ms
        ):
            pass
    assert connections == []
    assert pg._operation_timeout_settings.get() is None
