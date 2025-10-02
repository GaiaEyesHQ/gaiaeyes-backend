# app/db.py
from __future__ import annotations

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
    u = urlparse(dsn)
    qs = dict(parse_qsl(u.query, keep_blank_values=True))
    qs.pop("pgbouncer", None)
    qs.pop("prepare_threshold", None)
    qs.setdefault("sslmode", "require")
    new_q = urlencode(qs)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = _sanitize_conninfo(settings.DATABASE_URL)
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=10,
            timeout=30,
            open=False,  # lazy
            kwargs={
                "prepare_threshold": 0,  # NEVER prepare (PgBouncer-safe)
                "connect_timeout": 10,
            },
        )
        await _pool.open()
    return _pool


# ✅ FastAPI dependency: async generator that YIELDS a psycopg3 connection.
#    Do NOT decorate with @asynccontextmanager.
async def get_db() -> AsyncGenerator:
    pool = await get_pool()
    async with pool.connection() as conn:
        yield conn  # FastAPI injects this as `conn` in your endpoints