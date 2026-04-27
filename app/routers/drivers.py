from __future__ import annotations

import asyncio
import copy
import logging
import os
import time
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

_DRIVERS_CACHE_TTL_SECONDS = max(0, int(os.getenv("GAIA_DRIVERS_CACHE_TTL_SECONDS", "300")))
_DRIVERS_CACHE_MAX_ITEMS = max(1, int(os.getenv("GAIA_DRIVERS_CACHE_MAX_ITEMS", "512")))
_drivers_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_drivers_cache_lock = asyncio.Lock()


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


async def _get_cached_drivers(user_id: str, target_day: date) -> tuple[dict[str, Any] | None, float]:
    if _DRIVERS_CACHE_TTL_SECONDS <= 0:
        return None, 0.0
    key = (user_id, target_day.isoformat())
    now = time.monotonic()
    async with _drivers_cache_lock:
        cached = _drivers_cache.get(key)
        if not cached:
            return None, 0.0
        stored_at, payload = cached
        age = now - stored_at
        if age > _DRIVERS_CACHE_TTL_SECONDS:
            _drivers_cache.pop(key, None)
            return None, 0.0
        return copy.deepcopy(payload), age


async def _set_cached_drivers(user_id: str, target_day: date, payload: dict[str, Any]) -> None:
    if _DRIVERS_CACHE_TTL_SECONDS <= 0:
        return
    key = (user_id, target_day.isoformat())
    async with _drivers_cache_lock:
        if len(_drivers_cache) >= _DRIVERS_CACHE_MAX_ITEMS and key not in _drivers_cache:
            oldest_key = min(_drivers_cache, key=lambda item: _drivers_cache[item][0])
            _drivers_cache.pop(oldest_key, None)
        _drivers_cache[key] = (time.monotonic(), copy.deepcopy(payload))


@router.get("/drivers", dependencies=[Depends(require_read_auth)])
async def user_drivers(
    request: Request,
    day: date | None = Query(None),
    force: bool = Query(False),
    conn=Depends(get_db),
):
    started = time.perf_counter()
    user_id = _require_user_id(request)
    target_day = day or _default_driver_day()
    if not force:
        cached_payload, cache_age = await _get_cached_drivers(user_id, target_day)
        if cached_payload is not None:
            logger.info(
                "[drivers] cache hit user=%s day=%s age=%.1fs",
                user_id,
                target_day.isoformat(),
                cache_age,
            )
            return {
                "ok": True,
                "cache_hit": True,
                "cache_age_seconds": round(cache_age, 1),
                **cached_payload,
            }

    try:
        payload = await build_all_drivers_payload(conn, user_id=user_id, day=target_day)
    except Exception as exc:
        return {"ok": False, "error": f"all drivers build failed: {exc}"}

    await _set_cached_drivers(user_id, target_day, payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    logger.info(
        "[drivers] built user=%s day=%s ms=%s drivers=%s",
        user_id,
        target_day.isoformat(),
        elapsed_ms,
        len(payload.get("drivers") or []),
    )
    return {"ok": True, "cache_hit": False, "cache_age_seconds": 0.0, **payload}
