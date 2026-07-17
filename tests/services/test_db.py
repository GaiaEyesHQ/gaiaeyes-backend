from __future__ import annotations

from services.db import PgClient


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return {"value": 1}

    def fetchall(self):
        return [{"value": 1}]


class _Connection:
    def __init__(self, *, autocommit: bool) -> None:
        self.autocommit = autocommit
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def cursor(self):
        return _Cursor()

    def close(self):
        self.closed = True


def test_connection_scope_reuses_one_autocommit_connection(monkeypatch) -> None:
    client = PgClient("postgresql://example.invalid/test")
    connections: list[_Connection] = []

    def connect(*, autocommit: bool = False):
        connection = _Connection(autocommit=autocommit)
        connections.append(connection)
        return connection

    monkeypatch.setattr(client, "_connect", connect)

    with client.connection_scope():
        assert client.fetchrow("select 1") == {"value": 1}
        assert client.fetch("select 1") == [{"value": 1}]
        client.execute("select 1")
        with client.connection_scope():
            assert client.fetchrow("select 1") == {"value": 1}

    assert len(connections) == 1
    assert connections[0].autocommit is True
    assert connections[0].closed is True

    assert client.fetchrow("select 1") == {"value": 1}
    assert len(connections) == 2
    assert connections[1].autocommit is False
