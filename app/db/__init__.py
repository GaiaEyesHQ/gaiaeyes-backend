# app/db.py
from __future__ import annotations

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


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = _sanitize_conninfo(settings.DATABASE_URL)
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=3,
            timeout=30,
            max_idle=90,
            max_lifetime=300,
            open=False,  # lazy
            kwargs={
                # Disable server-side prepared statements.
                # Psycopg interprets ``prepare_threshold=None`` as "never prepare",
                # whereas ``0`` actually forces immediate preparation and can trigger
                # DuplicatePreparedStatement errors when connections are pooled.
                "prepare_threshold": None,
                "connect_timeout": 10,
                "autocommit": True,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 3,
            },
        )
        await _pool.open()
        logger.info("[DB] async pool opened against pgBouncer transaction mode on port %s", _PGBOUNCER_PORT)
    return _pool


# ✅ FastAPI dependency: async generator that YIELDS a psycopg3 connection.
#    Do NOT decorate with @asynccontextmanager.
async def get_db() -> AsyncGenerator:
    pool = await get_pool()
    async with pool.connection() as conn:
        try:
            await conn.execute("select 1;")
        except Exception:
            logger.exception("[DB] connection pre-ping failed")
            raise
        yield conn  # FastAPI injects this as `conn` in your endpoints