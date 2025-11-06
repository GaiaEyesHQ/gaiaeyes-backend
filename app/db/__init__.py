# app/db.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator, Dict, Any
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse, ParseResult

from pydantic_settings import BaseSettings, SettingsConfigDict
from psycopg_pool import AsyncConnectionPool
from psycopg_pool.errors import PoolTimeout


logger = logging.getLogger(__name__)


_PGBOUNCER_PORT = 6543


class Settings(BaseSettings):
    DATABASE_URL: str
    DIRECT_URL: Optional[str] = None
    DEV_BEARER: Optional[str] = None
    CORS_ORIGINS: Optional[str] = "*"
    SUPABASE_JWT_SECRET: Optional[str] = None
    REDIS_URL: Optional[str] = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()
_pool_open = False
_pool_last_refresh: Optional[datetime] = None
_pool_watchdog_task: Optional[asyncio.Task] = None
_pool_metrics_task: Optional[asyncio.Task] = None
_pool_conninfo_primary: Optional[str] = None
_pool_conninfo_fallback: Optional[str] = None
_pool_primary_label: str = "unknown"
_pool_fallback_label: Optional[str] = None
_pool_active_label: str = "unknown"

_STATEMENT_TIMEOUT_MS = 60000


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y", "on"}


def _rebuild_netloc(u: ParseResult, port: int) -> str:
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

    return f"{userinfo}{host}:{port}"


def _clean_database_url(dsn: str) -> tuple[ParseResult, bool]:
    parsed = urlparse(dsn)
    qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    raw_pgbouncer = qs.pop("pgbouncer", None)
    use_pgbouncer = _parse_bool(raw_pgbouncer)
    qs.pop("prepare_threshold", None)
    qs.setdefault("sslmode", "require")
    cleaned = parsed._replace(query=urlencode(qs))
    return cleaned, use_pgbouncer


def _make_conninfo(parsed: ParseResult, *, port: Optional[int] = None) -> str:
    if port is None:
        return urlunparse(parsed)
    return urlunparse(parsed._replace(netloc=_rebuild_netloc(parsed, port)))


def _prepare_conninfo() -> None:
    global _pool_conninfo_primary, _pool_conninfo_fallback
    global _pool_primary_label, _pool_fallback_label, _pool_active_label

    cleaned, use_pgbouncer = _clean_database_url(settings.DATABASE_URL)
    primary_conninfo = _make_conninfo(cleaned)
    primary_label = "direct"
    fallback_conninfo: Optional[str] = None
    fallback_label: Optional[str] = None

    if use_pgbouncer:
        primary_conninfo = _make_conninfo(cleaned, port=_PGBOUNCER_PORT)
        primary_label = "pgbouncer"
        logger.info("[DB] pgBouncer mode requested; primary port=%s", _PGBOUNCER_PORT)

        direct_source = settings.DIRECT_URL or _make_conninfo(cleaned)
        direct_cleaned, _ = _clean_database_url(direct_source)
        candidate = _make_conninfo(direct_cleaned)
        if candidate != primary_conninfo:
            fallback_conninfo = candidate
            fallback_label = "direct"
    elif settings.DIRECT_URL:
        direct_cleaned, _ = _clean_database_url(settings.DIRECT_URL)
        candidate = _make_conninfo(direct_cleaned)
        if candidate != primary_conninfo:
            fallback_conninfo = candidate
            fallback_label = "direct"

    _pool_conninfo_primary = primary_conninfo
    _pool_conninfo_fallback = fallback_conninfo
    _pool_primary_label = primary_label
    _pool_fallback_label = fallback_label
    _pool_active_label = primary_label


async def _check_on_acquire(conn) -> None:
    # Ensure a per-connection statement timeout and a quick ping
    await conn.execute(f"set statement_timeout = {_STATEMENT_TIMEOUT_MS}")
    async with conn.cursor() as cur:
        await cur.execute("select 1;")


def _log_pool_diag(pool: AsyncConnectionPool) -> None:
    try:
        stats = pool.get_stats()
    except Exception:  # pragma: no cover - depends on psycopg internals
        return
    open_count = int(stats.get("pool_size", 0))
    free_count = int(stats.get("pool_available", 0))
    waiting = int(stats.get("requests_waiting", 0))
    logger.info("[DB] diag: open=%s free=%s waiting=%s", open_count, free_count, waiting)


async def _pool_watchdog_loop(pool: AsyncConnectionPool) -> None:
    global _pool_last_refresh
    try:
        while True:
            await asyncio.sleep(60)
            if not _pool_open:
                continue
            try:
                async with pool.connection() as conn:
                    await conn.execute("select 1;")
                _pool_last_refresh = datetime.now(timezone.utc)
            except Exception as exc:  # pragma: no cover - depends on driver state
                logger.warning("[DB] watchdog ping failed: %s", exc)
    except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
        raise


async def _pool_metrics_loop(pool: AsyncConnectionPool) -> None:
    try:
        while True:
            await asyncio.sleep(60)
            if not _pool_open:
                continue
            metrics = get_pool_metrics()
            logger.info(
                "[DB] pool metrics open=%s used=%s waiting=%s",  # logged to stdout
                metrics.get("open"),
                metrics.get("used"),
                metrics.get("waiting"),
            )
    except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
        raise


def _start_pool_monitors(pool: AsyncConnectionPool) -> None:
    global _pool_watchdog_task, _pool_metrics_task
    loop = asyncio.get_running_loop()
    if _pool_watchdog_task is None or _pool_watchdog_task.done():
        _pool_watchdog_task = loop.create_task(_pool_watchdog_loop(pool))
    if _pool_metrics_task is None or _pool_metrics_task.done():
        _pool_metrics_task = loop.create_task(_pool_metrics_loop(pool))


async def _stop_pool_monitors() -> None:
    global _pool_watchdog_task, _pool_metrics_task
    for task in (_pool_watchdog_task, _pool_metrics_task):
        if task is not None:
            task.cancel()
    for task in (_pool_watchdog_task, _pool_metrics_task):
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:  # pragma: no cover - expected on cancel
                pass
    _pool_watchdog_task = None
    _pool_metrics_task = None


def _get_or_create_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _prepare_conninfo()
        conninfo = _pool_conninfo_primary or settings.DATABASE_URL
        # NOTE: Supabase + pgBouncer (transaction mode) favors a small client pool.
        # Large client pools can cause churn and apparent flapping. Keep min small,
        # cap max to single digits, and use short acquire timeout to fail fast.
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=8,
            timeout=8,
            max_idle=300,
            open=False,
            check=_check_on_acquire,
            kwargs={
                "sslmode": "require",
            },
        )
        logger.info(
            "[DB] async pool configured backend=%s", _pool_active_label
        )
    return _pool


async def open_pool() -> AsyncConnectionPool:
    global _pool_open, _pool_last_refresh, _pool_active_label
    async with _pool_lock:
        pool = _get_or_create_pool()
        if not _pool_open:
            try:
                await pool.open()
            except Exception as exc:
                if (
                    _pool_conninfo_fallback
                    and _pool_fallback_label
                    and _pool_active_label == _pool_primary_label
                ):
                    logger.warning(
                        "[DB] primary pool open failed (%s); retrying with %s backend",
                        exc,
                        _pool_fallback_label,
                    )
                    try:
                        await pool.close()
                    except Exception:
                        pass
                    _pool = AsyncConnectionPool(
                        conninfo=_pool_conninfo_fallback,
                        min_size=2,
                        max_size=8,
                        timeout=8,
                        max_idle=300,
                        open=False,
                        check=_check_on_acquire,
                        kwargs={
                            "sslmode": "require",
                        },
                    )
                    pool = _pool
                    _pool_active_label = _pool_fallback_label
                    await pool.open()
                else:
                    raise
            _pool_last_refresh = datetime.now(timezone.utc)
            _pool_open = True
            _log_pool_diag(pool)
            _start_pool_monitors(pool)
    return pool


async def close_pool() -> None:
    global _pool_open
    async with _pool_lock:
        if _pool and _pool_open:
            await _stop_pool_monitors()
            await _pool.close()
            _pool_open = False


async def get_pool() -> AsyncConnectionPool:
    pool = await open_pool()
    return pool


async def get_db() -> AsyncGenerator:
    pool = await get_pool()
    attempts = 0
    ctx = None
    while attempts < 2:
        attempts += 1
        ctx = pool.connection()
        try:
            conn = await ctx.__aenter__()
        except PoolTimeout:
            _log_pool_diag(pool)
            if attempts < 2:
                backoff = 1.5
                logger.warning("[DB] pool timeout; retrying after %.1fs", backoff)
                await asyncio.sleep(backoff)
                continue
            raise

        try:
            await conn.execute(f"set statement_timeout = {_STATEMENT_TIMEOUT_MS}")
        except Exception as exc:
            await ctx.__aexit__(type(exc), exc, exc.__traceback__)
            raise

        try:
            yield conn  # FastAPI injects this as `conn` in your endpoints
        except Exception as exc:  # pragma: no cover - defensive, FastAPI handles
            await ctx.__aexit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            await ctx.__aexit__(None, None, None)
        return

    raise RuntimeError("DB connection acquisition failed")


def get_pool_metrics() -> Dict[str, Any]:
    pool = _get_or_create_pool()
    try:
        stats = pool.get_stats()
    except Exception:  # pragma: no cover - depends on psycopg internals
        stats = {}
    open_count = int(stats.get("pool_size", 0))
    free_count = int(stats.get("pool_available", 0))
    waiting = int(stats.get("requests_waiting", 0))
    used = max(open_count - free_count, 0)
    last_refresh_iso = _pool_last_refresh.isoformat() if _pool_last_refresh else None
    db_ok = bool(_pool_open)
    return {
        "open": open_count,
        "free": free_count,
        "used": used,
        "waiting": waiting,
        "last_refresh": last_refresh_iso,
        "ok": db_ok,
        "backend": _pool_active_label,
        "fallback_available": bool(_pool_conninfo_fallback),
    }
