# app/db.py
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

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
    Strip unsupported URI params (pgbouncer/prepare_threshold) and
    ensure sslmode=require. psycopg options are set via 'kwargs' below.
    """
    u = urlparse(dsn)
    qs = dict(parse_qsl(u.query, keep_blank_values=True))
    qs.pop("pgbouncer", None)
    qs.pop("prepare_threshold", None)  # libpq URI doesn't accept this
    qs.setdefault("sslmode", "require")
    new_q = urlencode(qs)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))


async def get_pool() -> AsyncConnectionPool:
    """
    Lazily initialize and return a global AsyncConnectionPool.
    Pool is PgBouncer-safe via prepare_threshold=0 and sslmode=require.
    """
    global _pool
    if _pool is None:
        conninfo = _sanitize_conninfo(settings.DATABASE_URL)
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=10,
            timeout=30,
            open=False,                 # lazy
            kwargs={
                "prepare_threshold": 0, # NEVER prepare (PgBouncer-safe)
                "connect_timeout": 10,
            },
        )
        await _pool.open()
    return _pool


@asynccontextmanager
async def get_db() -> AsyncGenerator:
    """
    FastAPI dependency that yields a psycopg3 async connection
    from the global pool. Use it like:

        @router.get("/path")
        async def handler(conn = Depends(get_db)):
            async with conn.cursor() as cur:
                await cur.execute("select 1")
                ...

    The connection is returned to the pool when the request completes.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        yield conn