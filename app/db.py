# app/db.py
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict
from psycopg_pool import AsyncConnectionPool


class Settings(BaseSettings):
    DATABASE_URL: str
    DIRECT_URL: Optional[str] = None
    DEV_BEARER: Optional[str] = None
    CORS_ORIGINS: Optional[str] = "*"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

_pool: AsyncConnectionPool | None = None


def _sanitize_conninfo(dsn: str) -> str:
    """
    Strip any unsupported query params from the DSN (e.g., prepare_threshold if
    it leaked into the URL), and ensure sslmode=require is present.
    """
    u = urlparse(dsn)
    qs = dict(parse_qsl(u.query, keep_blank_values=True))
    # remove keys libpq doesn't know about in the URI
    qs.pop("pgbouncer", None)
    qs.pop("prepare_threshold", None)  # psycopg option -> set via kwargs below
    # ensure sslmode
    qs.setdefault("sslmode", "require")
    new_q = urlencode(qs)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = _sanitize_conninfo(settings.DATABASE_URL)
        # psycopg options live in kwargs:
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=10,
            timeout=30,              # seconds to wait for a connection from pool
            open=False,              # lazy open
            kwargs={
                "prepare_threshold": 0,   # PgBouncer-safe: never prepare
                "connect_timeout": 10,    # fail fast if DSN is wrong
            },
        )
        try:
            await _pool.open()
            # Optional: smoke test; comment out later if you want
            async with _pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("select 1")
                    await cur.fetchone()
        except Exception as e:
            # This shows up in Render logs and makes root cause obvious
            import logging
            logging.exception("Failed to open DB pool: %s", e)
            raise
    return _pool
