import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row


def _clean_dsn(dsn: str) -> str:
    if not dsn:
        return ""
    parsed = urlparse(dsn)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop("pgbouncer", None)
    query.pop("prepare_threshold", None)
    query.setdefault("sslmode", "require")
    return urlunparse(parsed._replace(query=urlencode(query)))


def _resolve_dsn() -> str:
    dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing SUPABASE_DB_URL, DIRECT_URL, or DATABASE_URL for database access")
    return _clean_dsn(dsn)


class PgClient:
    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = _clean_dsn(dsn) if dsn else _resolve_dsn()
        self._scoped_connection: ContextVar[psycopg.Connection | None] = ContextVar(
            f"gaia_pg_connection_{id(self)}",
            default=None,
        )
        self._operation_timeout_settings: ContextVar[tuple[int, int] | None] = ContextVar(
            f"gaia_pg_operation_timeouts_{id(self)}",
            default=None,
        )

    @contextmanager
    def operation_timeouts(
        self, *, connect_timeout: int, statement_timeout_ms: int
    ) -> Iterator[None]:
        """Bound new connections and queries without retaining a connection."""
        settings = (int(connect_timeout), int(statement_timeout_ms))
        if min(settings) <= 0:
            raise ValueError("database operation timeouts must be positive")
        token = self._operation_timeout_settings.set(settings)
        try:
            yield
        finally:
            self._operation_timeout_settings.reset(token)

    def _connect(self, *, autocommit: bool = False) -> psycopg.Connection:
        timeouts = self._operation_timeout_settings.get()
        timeout_options = {"connect_timeout": timeouts[0]} if timeouts else {}
        return psycopg.connect(
            self._dsn,
            row_factory=dict_row,
            autocommit=autocommit,
            prepare_threshold=None,
            **timeout_options,
        )

    @contextmanager
    def connection_scope(self) -> Iterator[psycopg.Connection]:
        """Reuse one autocommit connection for a bounded sequential work unit."""
        existing = self._scoped_connection.get()
        if existing is not None:
            yield existing
            return

        conn = self._connect(autocommit=True)
        token = self._scoped_connection.set(conn)
        try:
            yield conn
        finally:
            self._scoped_connection.reset(token)
            conn.close()

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        scoped = self._scoped_connection.get()
        timeouts = self._operation_timeout_settings.get()
        if scoped is not None:
            if timeouts is None:
                yield scoped
            else:
                # Keep SET LOCAL and the operation on one backend even when
                # this autocommit connection uses a transaction pooler.
                with scoped.transaction():
                    scoped.execute(f"SET LOCAL statement_timeout = {timeouts[1]}")
                    yield scoped
            return

        with self._connect() as conn:
            if timeouts is not None:
                # This starts the same transaction as the following operation;
                # commit/rollback clears the setting before connection close.
                conn.execute(f"SET LOCAL statement_timeout = {timeouts[1]}")
            yield conn

    def fetchrow(self, query: str, *params: Any) -> dict | None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                return dict(row) if row else None

    def fetch(self, query: str, *params: Any) -> list[dict]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(r) for r in rows]

    def execute(self, query: str, *params: Any) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)


pg = PgClient()
