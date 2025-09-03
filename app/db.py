# app/db.py
from __future__ import annotations

import asyncpg
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required
    DATABASE_URL: str

    # Optional/extras (ignore if present)
    DIRECT_URL: Optional[str] = None
    DEV_BEARER: Optional[str] = None
    CORS_ORIGINS: Optional[str] = "*"

    # Allow unknown env vars (e.g., SUPABASE_DB_URL used by scripts)
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()


async def get_pool() -> asyncpg.Pool:
    """
    Lazily create a global connection pool using DATABASE_URL.
    PgBouncer-friendly: disable prepared stmt cache.
    """
    if not hasattr(get_pool, "pool"):
        get_pool.pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            statement_cache_size=0,
            max_inactive_connection_lifetime=300.0,
        )
    return get_pool.pool  # type: ignore[attr-defined]
