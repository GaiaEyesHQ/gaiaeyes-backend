from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlparse

os.environ.setdefault("DIRECT_URL", "postgresql://example.invalid/test")

import services.db as db_module
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


def test_clean_dsn_strips_unsupported_pgbouncer_params() -> None:
    cleaned = db_module._clean_dsn(
        "postgresql://user:pass@db.example.com:6543/postgres?sslmode=require&pgbouncer=true&prepare_threshold=0&foo=bar"
    )

    parsed = urlparse(cleaned)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    assert parsed.netloc == "user:pass@db.example.com:6543"
    assert query == {"sslmode": "require", "foo": "bar"}


def test_connect_disables_server_side_prepare(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_connect(dsn, **kwargs):
        captured["dsn"] = dsn
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(db_module.psycopg, "connect", fake_connect)

    client = PgClient(
        "postgresql://user:pass@db.example.com:6543/postgres?pgbouncer=true&prepare_threshold=0"
    )
    client._connect(autocommit=True)

    assert captured["dsn"] == "postgresql://user:pass@db.example.com:6543/postgres?sslmode=require"
    assert captured["kwargs"] == {
        "row_factory": db_module.dict_row,
        "autocommit": True,
        "prepare_threshold": None,
    }
