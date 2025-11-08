# app/routers/ingest.py
from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Annotated, Awaitable, Dict, List, Optional, Union, Callable, Tuple, Any

import math
from collections import deque
from psycopg import errors as pg_errors, OperationalError
from psycopg_pool.errors import PoolTimeout

from fastapi import APIRouter, Body, Depends, Request, Header, HTTPException, status, Query
from pydantic import BaseModel

from ..db import (
    get_pool,
    settings,  # settings.DEV_BEARER, async pg pool
    handle_connection_failure,
    handle_pool_timeout,
)
from ..db.health import get_health_monitor
from . import summary as _summary_module

from zoneinfo import ZoneInfo
from os import getenv

import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])

DEFAULT_TIMEZONE = "America/Chicago"
REFRESH_DISABLED = getenv("MART_REFRESH_DISABLE", "0").lower() in {"1", "true", "yes", "on"}

_backlog = deque()
_backlog_lock = asyncio.Lock()
_backlog_drain_lock = asyncio.Lock()
_backlog_task_factory: Callable[[Awaitable[None]], asyncio.Task] = asyncio.create_task
_recent_refresh_requests: Dict[str, float] = {}
_recent_refresh_lock = asyncio.Lock()
_DELAYED_REFRESH_DELAY_SECONDS = 2.0
_DELAYED_REFRESH_DEBOUNCE_SECONDS = 20.0

# Legacy compatibility for tests expecting direct access to the refresh registry
_refresh_registry = _summary_module._refresh_registry
_refresh_task_factory = _summary_module._refresh_task_factory


async def _execute_refresh(user_id: str, day_local: date) -> None:
    await _summary_module._execute_mart_refresh(user_id, day_local)


class BatchInsertError(Exception):
    def __init__(self, reason: str, exc: Optional[BaseException] = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exc = exc


def _sample_to_dict(sample: SampleIn) -> Dict[str, Any]:
    if hasattr(sample, "model_dump"):
        return sample.model_dump()
    return sample.dict()


def _resolve_timezone(value: Optional[str]) -> tuple[str, ZoneInfo]:
    if not value:
        return DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)
    try:
        return value, ZoneInfo(value)
    except Exception:
        logger.warning("[ingest] invalid tz=%s; defaulting to %s", value, DEFAULT_TIMEZONE)
        return DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)


def _today_local(tzinfo: ZoneInfo) -> date:
    return datetime.now(tzinfo).date()


async def _enqueue_backlog(entry: Dict[str, Any]) -> None:
    async with _backlog_lock:
        _backlog.append(entry)
        logger.warning(
            "[BATCH] buffered payload size=%d backlog_len=%d",
            len(entry.get("samples", [])),
            len(_backlog),
        )


async def _drain_backlog(pool) -> None:
    if _backlog_drain_lock.locked():
        return

    async with _backlog_drain_lock:
        while True:
            async with _backlog_lock:
                if not _backlog:
                    return
                entry = _backlog.popleft()

            samples_data = entry.get("samples", [])
            dev_uid = entry.get("dev_uid")
            refresh_user = entry.get("refresh_user")
            tz_name = entry.get("tz") or DEFAULT_TIMEZONE

            models: List[SampleIn] = []
            for payload in samples_data:
                try:
                    models.append(SampleIn(**payload))
                except Exception as exc:
                    logger.warning("[BATCH] dropping buffered sample: %s", exc)

            if not models:
                continue

            prepared = [(sample, idx) for idx, sample in enumerate(models)]
            try:
                inserted, skipped, _ = await safe_insert_batch(pool, prepared, dev_uid)
            except BatchInsertError as exc:
                logger.warning("[BATCH] backlog drain halted: %s", exc.reason)
                async with _backlog_lock:
                    _backlog.appendleft(entry)
                break

            scheduled_refresh = False
            if inserted > 0 and refresh_user and not REFRESH_DISABLED:
                tz_resolved, tzinfo = _resolve_timezone(tz_name)
                day_local = _today_local(tzinfo)
                scheduled_refresh = await _maybe_schedule_refresh(refresh_user, day_local, inserted)
                logger.info(
                    "[BATCH] drained backlog for user=%s tz=%s inserted=%d skipped=%d",
                    refresh_user,
                    tz_resolved,
                    inserted,
                    skipped,
                )
                if scheduled_refresh:
                    logger.debug("[BATCH] backlog refresh scheduled user=%s", refresh_user)


def _start_backlog_drain(pool) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - no running loop
        return
    _backlog_task_factory(_drain_backlog(pool))


async def safe_insert_batch(
    pool,
    rows: List[Tuple[SampleIn, int]],
    dev_uid: Optional[str],
) -> Tuple[int, int, List[Dict[str, Any]]]:
    pool_timeouts = 0
    operational_attempts = 0
    backoff = 0.5

    while True:
        try:
            return await _insert_batch_once(pool, rows, dev_uid)
        except PoolTimeout as exc:
            pool_timeouts += 1
            await handle_pool_timeout("ingest batch connection timeout")
            if pool_timeouts >= 2:
                logger.error("[BATCH] insert failed after consecutive pool timeouts")
                raise BatchInsertError("db_timeout", exc)
            logger.warning("[BATCH] pool timeout on insert; retrying once")
            await asyncio.sleep(0.5)
        except OperationalError as exc:
            operational_attempts += 1
            if operational_attempts >= 3:
                logger.error("[BATCH] insert failed after retries: %s", exc)
                raise BatchInsertError("db_unavailable", exc)
            if await handle_connection_failure(exc):
                await asyncio.sleep(0)
            else:
                logger.warning(
                    "[BATCH] retrying insert after operational error attempt=%d error=%s",
                    operational_attempts,
                    exc,
                )
                await asyncio.sleep(min(backoff * (2 ** (operational_attempts - 1)), 5.0))
        except Exception as exc:
            raise BatchInsertError("db_unavailable", exc)


async def _insert_batch_once(
    pool,
    rows: List[Tuple[SampleIn, int]],
    dev_uid: Optional[str],
) -> Tuple[int, int, List[Dict[str, Any]]]:
    inserted = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for sample, original_index in rows:
                values = (
                    dev_uid or sample.user_id,
                    sample.device_os,
                    sample.source,
                    sample.type,
                    sample.start_time,
                    sample.end_time,
                    sample.value,
                    sample.unit,
                    sample.value_text,
                )
                try:
                    await cur.execute(sql, values, prepare=False)
                    rowcount = getattr(cur, "rowcount", None)
                    if rowcount is None:
                        inserted += 1
                    else:
                        inserted += int(rowcount)
                except pg_errors.UniqueViolation:
                    skipped += 1
                except Exception as exc:
                    skipped += 1
                    if len(errors) < 10:
                        errors.append(
                            {
                                "index": original_index,
                                "type": sample.type,
                                "reason": f"db_error: {type(exc).__name__}",
                                "message": str(exc)[:200],
                            }
                        )
            await conn.commit()

    return inserted, skipped, errors


# ---------- Models ----------
class SampleIn(BaseModel):
    user_id: str
    device_os: str
    source: str
    type: str
    start_time: datetime
    end_time: datetime
    value: Optional[float] = None
    unit: Optional[str] = None
    value_text: Optional[str] = None


class SamplesWrapper(BaseModel):
    samples: List[SampleIn]


# ---------- Validation ----------
def _validate_sample(s: SampleIn) -> tuple[bool, str | None]:
    # basic time sanity
    if s.end_time and s.end_time < s.start_time:
        return False, "end_time < start_time"
    # numeric checks
    if s.value is not None:
        if not math.isfinite(s.value):
            return False, "non-finite value"
    # type-specific ranges (keep permissive; mirror client-side sanitizers)
    t = s.type.lower()
    v = s.value
    if t == "heart_rate" and v is not None:
        if v < 20 or v > 250:
            return False, "heart_rate out of range"
    if t == "spo2" and v is not None:
        if v < 50 or v > 100:
            return False, "spo2 out of range"
    if t == "step_count" and v is not None:
        if v < 0:
            return False, "step_count negative"
    if t == "hrv_sdnn" and v is not None:
        if v < 0 or v > 600:
            return False, "hrv_sdnn out of range"
    return True, None


# ---------- Auth ----------
async def require_bearer(authorization: str = Header(..., alias="Authorization")) -> None:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not settings.DEV_BEARER or token != settings.DEV_BEARER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )


# ---------- Endpoint ----------
# Accept EITHER {"samples":[...]} OR a raw array [...]
Payload = Annotated[Union[SamplesWrapper, List[SampleIn]], Body(..., media_type="application/json")]

# --- keep your models & auth as-is above this ---

# psycopg-style insert with %s placeholders
sql = """
insert into gaia.samples (
  user_id, device_os, source, type,
  start_time, end_time, value, unit, value_text
) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
on conflict (user_id, type, start_time, end_time) do nothing
"""


def _log_batch_summary(user: str, received: int, inserted: int, skipped: int, db_ok: bool) -> None:
    logger.info(
        "[BATCH] result user=%s received=%d inserted=%d skipped=%d db=%s",
        user,
        received,
        inserted,
        skipped,
        db_ok,
    )


@router.post("/samples/batch")
@router.post("/v1/samples/batch")  # compatibility path so clients using /v1/... also hit this handler
async def samples_batch(
    payload: Payload,
    request: Request,
    _auth: None = Depends(require_bearer),
    tz: str = Query(DEFAULT_TIMEZONE, description="IANA timezone for mart refresh scheduling"),
):
    # Normalize payload to list
    items = payload.samples if isinstance(payload, SamplesWrapper) else (payload or [])
    received = len(items)

    if not items:
        _log_batch_summary("<empty>", 0, 0, 0, True)
        return {"ok": True, "received": 0, "inserted": 0, "skipped": 0, "db": True, "errors": [], "error": None}

    x_uid = request.headers.get("X-Dev-UserId", "").strip() or None
    dev_uid = x_uid
    effective_user = dev_uid or "<unknown>"

    monitor = get_health_monitor()
    if monitor and not monitor.get_db_ok():
        logger.warning(
            "[BATCH] db unavailable; rejecting batch size=%d", received
        )
        _log_batch_summary(effective_user, received, 0, received, False)
        return {
            "ok": False,
            "received": received,
            "inserted": 0,
            "skipped": received,
            "db": False,
            "errors": [{"reason": "db_unavailable"}],
            "error": "db_unavailable",
        }

    batch_start_iso: str | None = None
    batch_end_iso: str | None = None
    batch_user_id: str | None = None

    # Debug summary of this batch (types and time window)
    try:
        _types = sorted({s.type for s in items})
        batch_start_iso = min(s.start_time for s in items).isoformat()
        batch_end_iso = max(s.start_time for s in items).isoformat()
        uid_candidates = {s.user_id for s in items if s.user_id}
        batch_user_id = None
        if uid_candidates:
            if len(uid_candidates) == 1:
                batch_user_id = str(next(iter(uid_candidates)))
            else:
                batch_user_id = "<mixed>"
        logger.info(
            "/samples/batch received=%d types=%s window=[%s..%s]",
            len(items),
            _types,
            batch_start_iso,
            batch_end_iso,
        )
    except Exception:
        # best-effort only
        pass

    # Optional header override of user_id (useful for dev/testing)

    tz_name, tzinfo = _resolve_timezone(tz)
    validation_errors: List[Dict[str, Any]] = []
    validation_skipped = 0
    valid_rows: List[Tuple[SampleIn, int]] = []

    for idx, sample in enumerate(items):
        ok, reason = _validate_sample(sample)
        if not ok:
            validation_skipped += 1
            if len(validation_errors) < 10:
                validation_errors.append(
                    {
                        "index": idx,
                        "type": sample.type,
                        "reason": reason,
                        "start_time": sample.start_time.isoformat(),
                    }
                )
            continue
        valid_rows.append((sample, idx))

    refresh_user = None
    if dev_uid:
        refresh_user = dev_uid
    elif batch_user_id and batch_user_id not in {"<mixed>", "<unknown>"}:
        refresh_user = batch_user_id

    buffer_entry = {
        "samples": [_sample_to_dict(sample) for sample, _ in valid_rows],
        "dev_uid": dev_uid,
        "refresh_user": refresh_user,
        "tz": tz_name,
    }

    inserted = 0
    db_skipped = 0
    db_errors: List[Dict[str, Any]] = []
    db_healthy = True

    try:
        pool = await get_pool()
    except PoolTimeout as exc:
        logger.error("/samples/batch pool acquisition failed: %s", exc)
        await handle_pool_timeout("ingest pool acquisition timeout")
        if valid_rows:
            await _enqueue_backlog(buffer_entry)
        errors = list(validation_errors)
        if not errors:
            errors = [{"reason": "db_timeout"}]
        _log_batch_summary(effective_user or "<unknown>", received, 0, validation_skipped + len(valid_rows), False)
        return {
            "ok": False,
            "received": received,
            "inserted": 0,
            "skipped": validation_skipped + len(valid_rows),
            "db": False,
            "errors": errors,
            "error": "db_timeout",
        }
    except Exception as exc:
        logger.exception("/samples/batch unexpected pool error: %s", exc)
        await handle_connection_failure(exc)
        errors = list(validation_errors)
        if not errors:
            errors = [{"reason": "server_error", "message": str(exc)[:200]}]
        _log_batch_summary(effective_user or "<unknown>", received, 0, received, False)
        return {
            "ok": False,
            "received": received,
            "inserted": 0,
            "skipped": received,
            "db": False,
            "errors": errors,
            "error": "server_error",
        }

    if valid_rows:
        try:
            inserted, db_skipped, db_errors = await safe_insert_batch(pool, valid_rows, dev_uid)
        except BatchInsertError as exc:
            db_healthy = False
            if valid_rows:
                await _enqueue_backlog(buffer_entry)
            combined_errors = validation_errors + (db_errors or [])
            if not combined_errors:
                combined_errors = [{"reason": exc.reason}]
            _log_batch_summary(effective_user or "<unknown>", received, 0, validation_skipped + len(valid_rows), False)
            return {
                "ok": False,
                "received": received,
                "inserted": 0,
                "skipped": validation_skipped + len(valid_rows),
                "db": False,
                "errors": combined_errors,
                "error": exc.reason,
            }

    total_skipped = validation_skipped + db_skipped
    combined_errors = validation_errors + db_errors

    effective_user = dev_uid or batch_user_id or effective_user
    logger.info(
        "/samples/batch committed user=%s received=%d inserted=%d skipped=%d window=[%s..%s]",
        effective_user,
        received,
        inserted,
        total_skipped,
        batch_start_iso or "?",
        batch_end_iso or "?",
    )

    if db_healthy:
        if valid_rows and inserted > 0 and refresh_user and not REFRESH_DISABLED:
            day_local = _today_local(tzinfo)
            await _maybe_schedule_refresh(refresh_user, day_local, inserted)
        if valid_rows or _backlog:
            _start_backlog_drain(pool)

    _log_batch_summary(effective_user, received, inserted, total_skipped, db_healthy)

    return {
        "ok": db_healthy,
        "received": received,
        "inserted": inserted,
        "skipped": total_skipped,
        "db": db_healthy,
        "errors": combined_errors,
        "error": None,
    }


async def _maybe_schedule_refresh(user_id: str, day_local: date, inserted: int) -> bool:
    if REFRESH_DISABLED or not user_id:
        return False

    loop = asyncio.get_running_loop()
    now = loop.time()
    async with _recent_refresh_lock:
        last = _recent_refresh_requests.get(user_id)
        if last and now - last < _DELAYED_REFRESH_DEBOUNCE_SECONDS:
            logger.debug(
                "[MART] delayed refresh skipped user=%s (debounce %.0fs)",
                user_id,
                _DELAYED_REFRESH_DEBOUNCE_SECONDS,
            )
            return False
        _recent_refresh_requests[user_id] = now

    delay = _DELAYED_REFRESH_DELAY_SECONDS
    if getenv("PYTEST_CURRENT_TEST"):
        delay = 0.0

    async def _runner() -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            await _execute_refresh(user_id, day_local)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "[MART] delayed refresh failed user=%s error=%s",
                user_id,
                exc,
            )

    _refresh_task_factory(_runner())
    logger.info("[MART] scheduled refresh (delayed) user=%s inserted=%d", user_id, inserted)
    return True
