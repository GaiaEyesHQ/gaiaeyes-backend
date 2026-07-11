from __future__ import annotations

import asyncio
import copy
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db import get_db
from app.security.auth import require_read_auth
from services.drivers.all_drivers import build_all_drivers_payload


router = APIRouter(prefix="/v1/users/me", tags=["drivers"])
DEFAULT_TIMEZONE = os.getenv("GAIA_TIMEZONE", "America/Chicago")
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer env %s=%r; using default %s", name, raw, default)
        return default


_DRIVERS_CACHE_TTL_SECONDS = max(0, _env_int("GAIA_DRIVERS_CACHE_TTL_SECONDS", 300))
_DRIVERS_STALE_TTL_SECONDS = max(
    _DRIVERS_CACHE_TTL_SECONDS,
    _env_int("GAIA_DRIVERS_STALE_TTL_SECONDS", 6 * 60 * 60),
)
_DRIVERS_CACHE_MAX_ITEMS = max(1, _env_int("GAIA_DRIVERS_CACHE_MAX_ITEMS", 512))
_drivers_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_drivers_cache_lock = asyncio.Lock()
_drivers_build_locks: dict[tuple[str, str], asyncio.Lock] = {}
_drivers_build_locks_lock = asyncio.Lock()
_drivers_refresh_tasks: set[asyncio.Task] = set()


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


def _default_driver_day() -> date:
    try:
        return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    except Exception:
        return datetime.now(timezone.utc).date()


async def _get_cached_drivers(
    user_id: str,
    target_day: date,
    *,
    allow_stale: bool = False,
) -> tuple[dict[str, Any] | None, float, bool]:
    if _DRIVERS_CACHE_TTL_SECONDS <= 0:
        return None, 0.0, False
    key = (user_id, target_day.isoformat())
    now = time.monotonic()
    async with _drivers_cache_lock:
        cached = _drivers_cache.get(key)
        if not cached:
            return None, 0.0, False
        stored_at, payload = cached
        age = now - stored_at
        if age <= _DRIVERS_CACHE_TTL_SECONDS:
            return copy.deepcopy(payload), age, False
        if allow_stale and age <= _DRIVERS_STALE_TTL_SECONDS:
            return copy.deepcopy(payload), age, True
        if age > _DRIVERS_STALE_TTL_SECONDS:
            _drivers_cache.pop(key, None)
        return None, 0.0, False


async def _set_cached_drivers(user_id: str, target_day: date, payload: dict[str, Any]) -> None:
    if _DRIVERS_CACHE_TTL_SECONDS <= 0:
        return
    key = (user_id, target_day.isoformat())
    async with _drivers_cache_lock:
        if len(_drivers_cache) >= _DRIVERS_CACHE_MAX_ITEMS and key not in _drivers_cache:
            oldest_key = min(_drivers_cache, key=lambda item: _drivers_cache[item][0])
            _drivers_cache.pop(oldest_key, None)
        _drivers_cache[key] = (time.monotonic(), copy.deepcopy(payload))


async def _get_drivers_build_lock(user_id: str, target_day: date) -> asyncio.Lock:
    key = (user_id, target_day.isoformat())
    async with _drivers_build_locks_lock:
        lock = _drivers_build_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _drivers_build_locks[key] = lock
        return lock


async def _build_and_cache_drivers(conn, user_id: str, target_day: date) -> dict[str, Any]:
    payload = await build_all_drivers_payload(conn, user_id=user_id, day=target_day)
    await _set_cached_drivers(user_id, target_day, payload)
    return payload


@asynccontextmanager
async def _acquire_drivers_conn():
    agen = get_db()
    try:
        try:
            conn = await agen.__anext__()
        except StopAsyncIteration:  # pragma: no cover - defensive guard
            raise RuntimeError("database dependency yielded no connection")

        try:
            yield conn
        except BaseException as exc:
            try:
                await agen.athrow(type(exc), exc, exc.__traceback__)
            except StopAsyncIteration:
                pass
            raise
        else:
            try:
                await agen.asend(None)
            except StopAsyncIteration:
                pass
    finally:
        try:
            await agen.aclose()
        except (RuntimeError, StopAsyncIteration):
            pass


async def _refresh_stale_drivers(user_id: str, target_day: date) -> None:
    lock = await _get_drivers_build_lock(user_id, target_day)
    if lock.locked():
        logger.info("[drivers] stale refresh skipped; build already active user=%s day=%s", user_id, target_day)
        return
    async with lock:
        cached_payload, _, is_stale = await _get_cached_drivers(user_id, target_day, allow_stale=True)
        if cached_payload is not None and not is_stale:
            return
        started = time.perf_counter()
        try:
            payload = await _build_and_cache_drivers(None, user_id, target_day)
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
            logger.info(
                "[drivers] stale refresh built user=%s day=%s ms=%s drivers=%s timings=%s",
                user_id,
                target_day.isoformat(),
                elapsed_ms,
                len(payload.get("drivers") or []),
                payload.get("build_timings_ms"),
            )
        except Exception as exc:
            logger.warning("[drivers] stale refresh failed user=%s day=%s err=%s", user_id, target_day, exc)


def _schedule_drivers_refresh(user_id: str, target_day: date) -> bool:
    try:
        task = asyncio.create_task(_refresh_stale_drivers(user_id, target_day))
    except RuntimeError:
        return False
    _drivers_refresh_tasks.add(task)
    task.add_done_callback(_drivers_refresh_tasks.discard)
    return True


@router.get("/drivers", dependencies=[Depends(require_read_auth)])
async def user_drivers(
    request: Request,
    day: date | None = Query(None),
    force: bool = Query(False),
):
    started = time.perf_counter()
    user_id = _require_user_id(request)
    target_day = day or _default_driver_day()
    if not force:
        cached_payload, cache_age, is_stale = await _get_cached_drivers(user_id, target_day, allow_stale=True)
        if cached_payload is not None:
            refresh_scheduled = False
            if is_stale:
                refresh_scheduled = _schedule_drivers_refresh(user_id, target_day)
            logger.info(
                "[drivers] cache hit user=%s day=%s age=%.1fs stale=%s refresh_scheduled=%s",
                user_id,
                target_day.isoformat(),
                cache_age,
                is_stale,
                refresh_scheduled,
            )
            return {
                "ok": True,
                "cache_hit": True,
                "cache_age_seconds": round(cache_age, 1),
                "stale": is_stale,
                "refresh_scheduled": refresh_scheduled,
                **cached_payload,
            }

    lock = await _get_drivers_build_lock(user_id, target_day)
    async with lock:
        if not force:
            cached_payload, cache_age, _ = await _get_cached_drivers(user_id, target_day)
            if cached_payload is not None:
                return {
                    "ok": True,
                    "cache_hit": True,
                    "cache_age_seconds": round(cache_age, 1),
                    "stale": False,
                    "refresh_scheduled": False,
                    **cached_payload,
                }
        try:
            payload = await _build_and_cache_drivers(None, user_id, target_day)
        except Exception as exc:
            return {"ok": False, "error": f"all drivers build failed: {exc}"}

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    logger.info(
        "[drivers] built user=%s day=%s ms=%s drivers=%s timings=%s",
        user_id,
        target_day.isoformat(),
        elapsed_ms,
        len(payload.get("drivers") or []),
        payload.get("build_timings_ms"),
    )
    return {"ok": True, "cache_hit": False, "cache_age_seconds": 0.0, "stale": False, **payload}
