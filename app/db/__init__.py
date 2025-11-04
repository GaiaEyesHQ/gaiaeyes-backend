# app/db.py
from __future__ import annotations

import asyncio
import logging
from typing import Optional, AsyncGenerator
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict
from psycopg_pool import AsyncConnectionPool


logger = logging.getLogger(__name__)


_PGBOUNCER_PORT = 6543


class Settings(BaseSettings):
    DATABASE_URL: str
    DIRECT_URL: Optional[str] = None
    DEV_BEARER: Optional[str] = None
    CORS_ORIGINS: Optional[str] = "*"
    SUPABASE_JWT_SECRET: Optional[str] = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()
_pool_open = False


def _rebuild_netloc(u) -> str:
    username = u.username or ""
    password = u.password or ""
    host = u.hostname or ""

    if not host:
        return u.netloc or ""

    userinfo = ""
    if username:
        userinfo = username
        if password:
            userinfo += f":{password}"
        userinfo += "@"

    if host and ":" in host and not host.startswith("["):
        host = f"[{host}]"

    return f"{userinfo}{host}:{_PGBOUNCER_PORT}"


def _sanitize_conninfo(dsn: str) -> str:
    u = urlparse(dsn)
    qs = dict(parse_qsl(u.query, keep_blank_values=True))
    qs.pop("pgbouncer", None)
    qs.pop("prepare_threshold", None)
    qs.setdefault("sslmode", "require")
    new_q = urlencode(qs)
    netloc = u.netloc
    if (u.port or _PGBOUNCER_PORT) != _PGBOUNCER_PORT:
        logger.info("[DB] forcing pgBouncer port %s (was %s)", _PGBOUNCER_PORT, u.port)
        netloc = _rebuild_netloc(u)
    elif u.port is None:
        logger.info("[DB] applying pgBouncer default port %s", _PGBOUNCER_PORT)
        netloc = _rebuild_netloc(u)
    return urlunparse((u.scheme, netloc, u.path, u.params, new_q, u.fragment))


def _get_or_create_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = _sanitize_conninfo(settings.DATABASE_URL)
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=4,
            timeout=5,
            open=False,
            kwargs={
                "sslmode": "require",
                "prepare_threshold": None,
                "autocommit": True,
                "connect_timeout": 10,
            },
        )
        logger.info(
            "[DB] async pool configured for pgBouncer transaction mode on port %s", _PGBOUNCER_PORT
        )
    return _pool


async def open_pool() -> AsyncConnectionPool:
    global _pool_open
    async with _pool_lock:
        pool = _get_or_create_pool()
        if not _pool_open:
            await pool.open()
            _pool_open = True
    return pool


async def close_pool() -> None:
    global _pool_open
    async with _pool_lock:
        if _pool and _pool_open:
            await _pool.close()
            _pool_open = False


async def get_pool() -> AsyncConnectionPool:
    pool = await open_pool()
    return pool


# ✅ FastAPI dependency: async generator that YIELDS a psycopg3 connection.
#    Do NOT decorate with @asynccontextmanager.
async def _pre_ping(conn) -> None:
    async with conn.cursor() as cur:
        await cur.execute("select 1;")


async def get_db() -> AsyncGenerator:
    pool = await get_pool()
    attempt = 0
    last_exc: Optional[BaseException] = None

    while attempt < 2:
        ctx = pool.connection()
        conn = await ctx.__aenter__()
        try:
            await _pre_ping(conn)
        except Exception as exc:  # pragma: no cover - exercised under pool churn
            last_exc = exc
            await ctx.__aexit__(type(exc), exc, exc.__traceback__)
            if attempt == 0:
                logger.warning("[DB] pre_ping failed; reconnecting")
                attempt += 1
                continue
            raise

        try:
            yield conn  # FastAPI injects this as `conn` in your endpoints
        except Exception as exc:  # pragma: no cover - defensive, FastAPI handles
            await ctx.__aexit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            await ctx.__aexit__(None, None, None)
        return

    if last_exc:
        raise last_exc
