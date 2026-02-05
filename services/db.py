import os
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _resolve_dsn() -> str:
    dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing SUPABASE_DB_URL, DIRECT_URL, or DATABASE_URL for database access")
    return dsn


class PgClient:
    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or _resolve_dsn()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def fetchrow(self, query: str, *params: Any) -> dict | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                return dict(row) if row else None

    def fetch(self, query: str, *params: Any) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(r) for r in rows]

    def execute(self, query: str, *params: Any) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                conn.commit()


pg = PgClient()
