# app/db.py
from __future__ import annotations

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

import psycopg
from psycopg_pool import AsyncConnectionPool


class Settings(BaseSettings):
    DATABASE_URL: str

    DIRECT_URL: Optional[str] = None
    DEV_BEARER: Optional[str] = None
    CORS_ORIGINS: Optional[str] = "*"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()

# Lazy global pool
_pool: AsyncConnectionPool | None = None

async def get_pool() -> AsyncConnectionPool:
    """
    Async connection pool using psycopg v3.
    - Uses DATABASE_URL (your Supabase Pooler DSN is fine here).
    - Good with PgBouncer by default.
    """
    global _pool
    if _pool is None:
        # psycopg_pool reads connection args from the conninfo string (sslmode, etc)
        _pool = AsyncConnectionPool(
            conninfo=settings.DATABASE_URL,
            min_size=1,
            max_size=10,
            timeout=30,              # seconds to wait for a connection
            open=False,              # lazy open
        )
        await _pool.open()           # open lazily on first call
    return _pool
