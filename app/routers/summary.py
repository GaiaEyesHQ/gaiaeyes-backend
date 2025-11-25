#
# app/routers/summary.py
# NOTE: Do not make any changes in this file per instructions.
import asyncio
import json
import logging
import random
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypeVar

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from os import getenv
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout
from app.cache import get_last_good, set_last_good
from app.db import (
    get_db,
    get_pool,
    get_pool_metrics,
    handle_connection_failure,
    handle_pool_timeout,
)
from app.db.health import get_health_monitor
from app.utils.auth import require_admin

DEFAULT_TIMEZONE = "America/Chicago"
STATEMENT_TIMEOUT_MS = 60000
FRESHEN_TIMEOUT_MS = 3000
MART_QUERY_TIMEOUT_MS = 5000

DEBUG_FEATURES_DIAG = getenv("DEBUG_FEATURES_DIAG", "1").lower() not in {"0", "false", "no"}


logger = logging.getLogger(__name__)

# Helper to rollback connection safely (ignore errors)
async def _rollback_safely(conn) -> None:
    try:
        await conn.rollback()
    except Exception:
        pass

T = TypeVar("T")


def _seconds(ms: int) -> float:
    return ms / 1000.0


async def _timed_call(
    awaitable: Awaitable[T],
    *,
    label: str,
    timeout_ms: int,
    log_context: Optional[str] = None,
) -> Tuple[Optional[T], Optional[BaseException]]:
    """Run the awaitable with a timeout and normalize error reporting."""

    context_suffix = f" ({log_context})" if log_context else ""
    try:
        result = await asyncio.wait_for(awaitable, _seconds(timeout_ms))
        return result, None
    except asyncio.TimeoutError:
        message = f"{label} timed out after {timeout_ms}ms"
        logger.warning("[features]%s %s", context_suffix, message)
        return None, TimeoutError(message)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "[features]%s %s failed: %s",
            context_suffix,
            label,
            exc,
        )
        return None, RuntimeError(f"{label} failed: {exc}")


def _describe_error(error: BaseException) -> str:
    message = str(error).strip()
    return message or error.__class__.__name__


def _record_enrichment_errors(diag_info: Dict[str, Any], errors: List[str]) -> None:
    if not errors:
        return
    existing = list(diag_info.get("enrichment_errors") or [])
    for message in errors:
        if message and message not in existing:
            existing.append(message)
    if existing:
        diag_info["enrichment_errors"] = existing
        diag_info.setdefault("last_error", existing[0])


STATEMENT_TIMEOUT_MS = 60000

MART_REFRESH_DEBOUNCE_SECONDS = 300.0
_REFRESH_DELAY_RANGE = (1.5, 2.0)

_CACHE_STALE_THRESHOLD_SECONDS = 15 * 60
_BACKGROUND_REFRESH_INTERVAL_SECONDS = 5 * 60

_EMPTY_PAYLOAD_KEYS = {"source"}


_TRACE_MAX_ENTRIES = 60


def _diag_trace(diag_info: Dict[str, Any], message: str) -> None:
    """Append a timestamped trace message to the diagnostics payload."""

    trace = diag_info.setdefault("trace", [])
    timestamp = datetime.now(timezone.utc).isoformat()
    trace.append(f"{timestamp} {message}")
    if len(trace) > _TRACE_MAX_ENTRIES:
        del trace[: len(trace) - _TRACE_MAX_ENTRIES]


async def _features_db_dependency(request: Request):
    monitor = get_health_monitor()
    request.state.db_error = None
    if monitor and not monitor.get_db_ok():
        request.state.db_error = "db_unavailable"
        yield None
        return

    try:
        async with _acquire_features_conn() as conn:
            yield conn
            return
    except PoolTimeout as exc:
        request.state.db_error = "db_timeout"
        await handle_pool_timeout("features dependency timeout")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        request.state.db_error = "db_unavailable"
        await handle_connection_failure(exc)

    yield None


@asynccontextmanager
async def _acquire_features_conn():
    """Backward-compatible connection context for tests expecting the legacy helper."""

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
_refresh_registry: Dict[str, float] = {}
_refresh_inflight: Dict[Tuple[str, date], asyncio.Task] = {}
_refresh_lock = asyncio.Lock()
_refresh_task_factory: Callable[[Awaitable[None]], asyncio.Task] = asyncio.create_task

_background_refresh_registry: Dict[str, float] = {}
_background_refresh_lock = asyncio.Lock()


async def _execute_mart_refresh(user_id: str, day_local: date) -> None:
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "select marts.refresh_daily_features_user(%s::uuid, %s::date)",
                    (user_id, day_local),
                )
    except Exception as exc:  # pragma: no cover - diagnostic logging
        logger.warning(
            "[MART] refresh failed user=%s day=%s error=%s",
            user_id,
            day_local,
            exc,
        )


async def mart_refresh(user_id: str, day_local: date) -> bool:
    if not user_id:
        return False
    loop = asyncio.get_running_loop()
    async with _refresh_lock:
        last = _refresh_registry.get(user_id)
        now = loop.time()
        if last and now - last < MART_REFRESH_DEBOUNCE_SECONDS:
            logger.debug(
                "[MART] refresh skipped user=%s (debounce %.0fs)",
                user_id,
                MART_REFRESH_DEBOUNCE_SECONDS,
            )
            return False
        key = (user_id, day_local)
        existing = _refresh_inflight.get(key)
        if existing and not existing.done():
            logger.debug("[MART] refresh already running user=%s day=%s", user_id, day_local)
            return False
        _refresh_registry[user_id] = now

    try:
        from . import ingest as ingest_module  # type: ignore circular import
    except Exception:  # pragma: no cover - import guard for early startup
        ingest_module = None

    task_factory = _refresh_task_factory
    execute_fn = _execute_mart_refresh
    if ingest_module is not None:
        task_factory = getattr(ingest_module, "_refresh_task_factory", task_factory)
        execute_fn = getattr(ingest_module, "_execute_refresh", execute_fn)

    delay_seconds = random.uniform(*_REFRESH_DELAY_RANGE)

    async def _runner() -> None:
        try:
            await asyncio.sleep(delay_seconds)
            await execute_fn(user_id, day_local)
        finally:
            async with _refresh_lock:
                task = _refresh_inflight.get(key)
                if task is not None and task is asyncio.current_task():
                    _refresh_inflight.pop(key, None)

    task = task_factory(_runner())
    async with _refresh_lock:
        _refresh_inflight[(user_id, day_local)] = task
    return True


_MART_COLUMNS = [
    "day",
    "updated_at",
    "steps_total",
    "hr_min",
    "hr_max",
    "hrv_avg",
    "kp_max",
    "bz_min",
    "sw_speed_avg",
]
_MART_SELECT = ", ".join(_MART_COLUMNS)


def _init_diag_info(user_id: Optional[str], tz_name: str) -> Dict[str, Any]:
    return {
        "branch": "scoped" if user_id else "anonymous",
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "requested_user_id": str(user_id) if user_id else None,
        "user_id": str(user_id) if user_id else None,
        "day": None,
        "day_used": None,
        "updated_at": None,
        "source": "empty",
        "mart_row": False,
        "freshened": False,
        "max_day": None,
        "total_rows": None,
        "tz": tz_name,
        "enrichment_errors": [],
        "cache_hit": False,
        "cache_age_seconds": None,
        "cache_rehydrated": False,
        "cache_updated": False,
        "cache_snapshot_initial": None,
        "cache_snapshot_final": None,
        "mart_snapshot": None,
        "payload_summary": None,
        "trace": [],
        "refresh_attempted": False,
        "refresh_scheduled": False,
        "refresh_reason": None,
        "refresh_forced": False,
    }


def _iso_dt(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _iso_date(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _coerce_day(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _is_effectively_empty_payload(payload: Optional[Dict[str, Any]]) -> bool:
    if not payload:
        return True
    return set(payload.keys()).issubset(_EMPTY_PAYLOAD_KEYS)


def _normalize_timezone(tz_name: Optional[str]) -> Tuple[str, ZoneInfo]:
    if not tz_name:
        return DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)
    try:
        return tz_name, ZoneInfo(tz_name)
    except Exception:
        logger.warning("[features] invalid tz=%s; falling back to %s", tz_name, DEFAULT_TIMEZONE)
        return DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)


async def _current_day_local(conn, tz_name: str) -> date:
    async with conn.cursor() as cur:
        await cur.execute("select (now() at time zone %s)::date as day_local", (tz_name,))
        row = await cur.fetchone()
    if row and row[0]:
        return row[0]
    return datetime.now(ZoneInfo(tz_name)).date()


def _local_bounds(day_local: date, tzinfo: ZoneInfo) -> Tuple[datetime, datetime]:
    start_local = datetime.combine(day_local, time.min).replace(tzinfo=tzinfo)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _gather_enrichment(
    conn,
    user_id: str,
    day_local: date,
    tzinfo: ZoneInfo,
) -> Tuple[Dict[str, Any], List[str]]:
    """Collect enrichment components with bounded runtime."""

    start_utc, end_utc = _local_bounds(day_local, tzinfo)
    errors: List[str] = []

    sleep, sleep_exc = await _timed_call(
        _fetch_sleep_aggregate(conn, user_id, start_utc, end_utc),
        label="sleep aggregate",
        timeout_ms=FRESHEN_TIMEOUT_MS,
        log_context=f"user={user_id} day={day_local.isoformat()}",
    )
    if sleep is None:
        sleep = {}
    if sleep_exc:
        errors.append(_describe_error(sleep_exc))

    daily_wx, daily_exc = await _timed_call(
        _fetch_space_weather_daily(conn, day_local),
        label="space weather daily",
        timeout_ms=FRESHEN_TIMEOUT_MS,
        log_context=f"day={day_local.isoformat()}",
    )
    if daily_wx is None:
        daily_wx = {}
    if daily_exc:
        errors.append(_describe_error(daily_exc))

    current_wx, current_exc = await _timed_call(
        _fetch_current_space_weather(conn),
        label="space weather current",
        timeout_ms=FRESHEN_TIMEOUT_MS,
    )
    if current_wx is None:
        current_wx = {}
    if current_exc:
        errors.append(_describe_error(current_exc))

    sch, sch_exc = await _timed_call(
        _fetch_schumann_row(conn, day_local),
        label="schumann daily",
        timeout_ms=FRESHEN_TIMEOUT_MS,
        log_context=f"day={day_local.isoformat()}",
    )
    if sch is None:
        sch = {}
    if sch_exc:
        errors.append(_describe_error(sch_exc))

    post, post_exc = await _timed_call(
        _fetch_daily_post(conn, day_local),
        label="daily post",
        timeout_ms=FRESHEN_TIMEOUT_MS,
        log_context=f"day={day_local.isoformat()}",
    )
    if post is None:
        post = {}
    if post_exc:
        errors.append(_describe_error(post_exc))

    return {
        "sleep": sleep,
        "daily_wx": daily_wx,
        "current_wx": current_wx,
        "sch": sch,
        "post": post,
    }, errors


async def _fetch_mart_row(conn, user_id: str, day_local: date) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        started = perf_counter()
        await cur.execute(
            f"""
            select {_MART_SELECT}
            from marts.daily_features
            where user_id = %s and day = %s
            limit 1
            """,
            (user_id, day_local),
        )
        row = await cur.fetchone()
    elapsed_ms = int((perf_counter() - started) * 1000)
    logger.info(
        "[MART] refresh completed (elapsed=%sms) user=%s day=%s",
        elapsed_ms,
        user_id,
        day_local,
    )
    return row


async def _fetch_snapshot_row(conn, user_id: str) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            select {_MART_SELECT}
            from marts.daily_features
            where user_id = %s and day is not null
            order by updated_at desc
            limit 1
            """,
            (user_id,),
        )
        return await cur.fetchone()


async def _query_mart_with_retry(conn, user_id: str, day_local: date) -> Tuple[Optional[Dict[str, Any]], Optional[BaseException]]:
    attempts = 0
    last_exc: Optional[BaseException] = None
    while attempts < 2:
        try:
            row = await _fetch_mart_row(conn, user_id, day_local)
        except Exception as exc:  # pragma: no cover - safety for transient db errors
            if isinstance(exc, asyncio.CancelledError):
                raise
            last_exc = exc
            if isinstance(exc, pg_errors.QueryCanceled):
                logger.warning(
                    "[MART] query timeout user=%s day=%s", user_id, day_local
                )
            attempts += 1
            if attempts < 2:
                await asyncio.sleep(0.2)
            continue
        return row, None
    return None, last_exc


async def _fetch_sleep_aggregate(
    conn,
    user_id: str,
    start_utc: datetime,
    end_utc: datetime,
) -> Dict[str, Optional[float]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            with rows as (
              select lower(coalesce(value_text,'')) as stage,
                     extract(epoch from (coalesce(end_time,start_time) - start_time))/60.0 as minutes
              from gaia.samples
              where user_id = %s
                and type in ('sleep','sleep_stage')
                and start_time >= %s
                and start_time < %s
            )
            select
              coalesce(sum(minutes) filter (where stage = 'rem'), 0) as rem_m,
              coalesce(sum(minutes) filter (where stage in ('core','light')), 0) as core_m,
              coalesce(sum(minutes) filter (where stage = 'deep'), 0) as deep_m,
              coalesce(sum(minutes) filter (where stage = 'awake'), 0) as awake_m,
              coalesce(sum(minutes) filter (where stage in ('inbed','in_bed')), 0) as inbed_m
            from rows
            """,
            (user_id, start_utc, end_utc),
        )
        res = await cur.fetchone() or {}
    return {
        "rem_m": float(res.get("rem_m") or 0),
        "core_m": float(res.get("core_m") or 0),
        "deep_m": float(res.get("deep_m") or 0),
        "awake_m": float(res.get("awake_m") or 0),
        "inbed_m": float(res.get("inbed_m") or 0),
    }


async def _fetch_daily_summary(conn, user_id: str, day_local: date) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select
              date::date as day,
              steps_total,
              hr_min,
              hr_max,
              hrv_avg,
              spo2_avg,
              bp_sys_avg,
              bp_dia_avg,
              sleep_total_minutes,
              sleep_rem_minutes,
              sleep_core_minutes,
              sleep_deep_minutes,
              sleep_awake_minutes,
              sleep_efficiency
            from gaia.daily_summary
            where user_id = %s and date::date = %s
            limit 1
            """,
            (user_id, day_local),
        )
        return await cur.fetchone()


async def _fetch_space_weather_daily(conn, day_local: date) -> Dict[str, Optional[float]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select kp_max, bz_min, sw_speed_avg, flares_count, cmes_count
            from marts.space_weather_daily
            where day = %s
            limit 1
            """,
            (day_local,),
        )
        res = await cur.fetchone() or {}
    return {
        "kp_max": res.get("kp_max"),
        "bz_min": res.get("bz_min"),
        "sw_speed_avg": res.get("sw_speed_avg"),
        "flares_count": res.get("flares_count"),
        "cmes_count": res.get("cmes_count"),
    }


async def _fetch_current_space_weather(conn) -> Dict[str, Optional[float]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select kp_index as kp_current
            from ext.space_weather
            where ts_utc <= now() and kp_index is not null
            order by ts_utc desc
            limit 1
            """,
        )
        kp_row = await cur.fetchone() or {}
        await cur.execute(
            """
            select bz_nt as bz_current
            from ext.space_weather
            where ts_utc <= now() and bz_nt is not null
            order by ts_utc desc
            limit 1
            """,
        )
        bz_row = await cur.fetchone() or {}
        await cur.execute(
            """
            select sw_speed_kms as sw_speed_current
            from ext.space_weather
            where ts_utc <= now() and sw_speed_kms is not null
            order by ts_utc desc
            limit 1
            """,
        )
        sw_row = await cur.fetchone() or {}
    return {
        "kp_current": kp_row.get("kp_current"),
        "bz_current": bz_row.get("bz_current"),
        "sw_speed_current": sw_row.get("sw_speed_current"),
    }


async def _fetch_schumann_row(conn, day_local: date) -> Dict[str, Any]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select station_id, f0_avg_hz, f1_avg_hz, f2_avg_hz, f3_avg_hz, f4_avg_hz
            from marts.schumann_daily
            where station_id in ('tomsk','cumiana') and day <= %s
            order by day desc,
                     case when station_id='tomsk' then 0 when station_id='cumiana' then 1 else 2 end
            limit 1
            """,
            (day_local,),
        )
        row = await cur.fetchone() or {}
    return {
        "sch_station": row.get("station_id"),
        "sch_f0_hz": row.get("f0_avg_hz"),
        "sch_f1_hz": row.get("f1_avg_hz"),
        "sch_f2_hz": row.get("f2_avg_hz"),
        "sch_f3_hz": row.get("f3_avg_hz"),
        "sch_f4_hz": row.get("f4_avg_hz"),
    }


async def _fetch_daily_post(conn, day_local: date) -> Dict[str, Optional[str]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select p0.title as post_title,
                   p0.caption as post_caption,
                   p0.body_markdown as post_body,
                   p0.hashtags as post_hashtags
            from content.daily_posts p0
            where p0.platform = 'default' and p0.day <= %s
            order by p0.day desc, p0.updated_at desc
            limit 1
            """,
            (day_local,),
        )
        row = await cur.fetchone() or {}
    return {
        "post_title": row.get("post_title"),
        "post_caption": row.get("post_caption"),
        "post_body": row.get("post_body"),
        "post_hashtags": row.get("post_hashtags"),
    }


def _compose_sleep_payload(base: Dict[str, Any], sleep: Dict[str, Optional[float]]) -> Dict[str, Any]:
    rem_m = sleep.get("rem_m") or base.get("sleep_rem_minutes") or base.get("rem_m") or 0
    core_m = sleep.get("core_m") or base.get("sleep_core_minutes") or base.get("core_m") or 0
    deep_m = sleep.get("deep_m") or base.get("sleep_deep_minutes") or base.get("deep_m") or 0
    awake_m = sleep.get("awake_m") or base.get("sleep_awake_minutes") or base.get("awake_m") or 0
    inbed_m = sleep.get("inbed_m") or base.get("inbed_m") or 0
    sleep_total = (
        base.get("sleep_total_minutes")
        or (rem_m or 0) + (core_m or 0) + (deep_m or 0)
    )
    efficiency = base.get("sleep_efficiency")
    if not efficiency and inbed_m:
        try:
            efficiency = round(((rem_m + core_m + deep_m) / inbed_m), 3)
        except ZeroDivisionError:
            efficiency = None
    return {
        "sleep_total_minutes": int(sleep_total) if sleep_total is not None else None,
        "rem_m": round(rem_m, 0) if rem_m is not None else None,
        "core_m": round(core_m, 0) if core_m is not None else None,
        "deep_m": round(deep_m, 0) if deep_m is not None else None,
        "awake_m": round(awake_m, 0) if awake_m is not None else None,
        "inbed_m": round(inbed_m, 0) if inbed_m is not None else None,
        "sleep_efficiency": efficiency,
    }


def _compose_space_weather_payload(base: Dict[str, Any], daily: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    kp_max = base.get("kp_max") if base else None
    if daily.get("kp_max") is not None:
        kp_max = daily["kp_max"]
    bz_min = daily.get("bz_min") if daily.get("bz_min") is not None else base.get("bz_min") if base else None
    sw_speed_avg = daily.get("sw_speed_avg") if daily.get("sw_speed_avg") is not None else base.get("sw_speed_avg") if base else None
    flares_count = daily.get("flares_count") if daily.get("flares_count") is not None else base.get("flares_count") if base else None
    cmes_count = daily.get("cmes_count") if daily.get("cmes_count") is not None else base.get("cmes_count") if base else None
    kp_alert = bool(kp_max and kp_max >= 5)
    flare_alert = bool(flares_count and flares_count > 0)
    return {
        "kp_max": kp_max,
        "bz_min": bz_min,
        "sw_speed_avg": sw_speed_avg,
        "flares_count": flares_count,
        "cmes_count": cmes_count,
        "kp_alert": kp_alert,
        "flare_alert": flare_alert,
        "kp_current": current.get("kp_current"),
        "bz_current": current.get("bz_current"),
        "sw_speed_current": current.get("sw_speed_current"),
    }


_FEATURE_DEFAULTS: Dict[str, Any] = {
    "user_id": None,
    "day": None,
    "steps_total": 0,
    "hr_min": None,
    "hr_max": None,
    "hrv_avg": None,
    "spo2_avg": None,
    "bp_sys_avg": None,
    "bp_dia_avg": None,
    "sleep_total_minutes": 0,
    "rem_m": 0,
    "core_m": 0,
    "deep_m": 0,
    "awake_m": 0,
    "inbed_m": 0,
    "sleep_efficiency": None,
    "kp_max": None,
    "bz_min": None,
    "sw_speed_avg": None,
    "flares_count": 0,
    "cmes_count": 0,
    "kp_alert": False,
    "flare_alert": False,
    "kp_current": None,
    "bz_current": None,
    "sw_speed_current": None,
    "sch_station": None,
    "sch_f0_hz": None,
    "sch_f1_hz": None,
    "sch_f2_hz": None,
    "sch_f3_hz": None,
    "sch_f4_hz": None,
    "post_title": None,
    "post_caption": None,
    "post_body": None,
    "post_hashtags": None,
    "updated_at": None,
    "source": "snapshot",
}

_INT_FIELDS = {
    "steps_total",
    "sleep_total_minutes",
    "rem_m",
    "core_m",
    "deep_m",
    "awake_m",
    "inbed_m",
    "flares_count",
    "cmes_count",
}

_FLOAT_FIELDS = {
    "hr_min",
    "hr_max",
    "hrv_avg",
    "spo2_avg",
    "bp_sys_avg",
    "bp_dia_avg",
    "kp_max",
    "bz_min",
    "sw_speed_avg",
    "kp_current",
    "bz_current",
    "sw_speed_current",
    "sch_f0_hz",
    "sch_f1_hz",
    "sch_f2_hz",
    "sch_f3_hz",
    "sch_f4_hz",
    "sleep_efficiency",
}


def _coerce_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value.is_nan():
            return None
        return float(value)
    return value


def _coerce_int_value(value: Any) -> Optional[int]:
    if value is None:
        return None
    coerced = _coerce_decimal(value)
    try:
        return int(round(coerced))
    except (TypeError, ValueError):
        return None


def _coerce_float_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    coerced = _coerce_decimal(value)
    try:
        return float(coerced)
    except (TypeError, ValueError):
        return None


def _any_present(payload: Dict[str, Any], keys: Tuple[str, ...]) -> bool:
    return any(payload.get(key) is not None for key in keys)


def _summarize_feature_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not payload:
        return {"has_payload": False, "non_null_count": 0}

    summary_payload = dict(payload)
    day = _coerce_day(summary_payload.get("day"))
    updated_at = _coerce_datetime(summary_payload.get("updated_at"))

    summary = {
        "has_payload": True,
        "source": summary_payload.get("source"),
        "day": _iso_date(day),
        "updated_at": _iso_dt(updated_at),
        "sections": {
            "health": _any_present(
                summary_payload,
                (
                    "steps_total",
                    "hr_min",
                    "hr_max",
                    "hrv_avg",
                    "spo2_avg",
                    "bp_sys_avg",
                    "bp_dia_avg",
                ),
            ),
            "sleep": _any_present(
                summary_payload,
                (
                    "sleep_total_minutes",
                    "rem_m",
                    "core_m",
                    "deep_m",
                    "awake_m",
                    "inbed_m",
                ),
            ),
            "space_daily": _any_present(
                summary_payload,
                ("kp_max", "bz_min", "sw_speed_avg", "flares_count", "cmes_count"),
            ),
            "space_current": _any_present(
                summary_payload,
                ("kp_current", "bz_current", "sw_speed_current"),
            ),
            "schumann": _any_present(
                summary_payload,
                ("sch_f0_hz", "sch_f1_hz", "sch_f2_hz", "sch_f3_hz", "sch_f4_hz"),
            ),
            "post": _any_present(
                summary_payload,
                ("post_title", "post_caption", "post_body"),
            ),
        },
        "metrics": {
            "steps_total": _coerce_int_value(summary_payload.get("steps_total")),
            "sleep_total_minutes": _coerce_int_value(
                summary_payload.get("sleep_total_minutes")
            ),
            "kp_max": _coerce_float_value(summary_payload.get("kp_max")),
            "bz_min": _coerce_float_value(summary_payload.get("bz_min")),
            "sw_speed_avg": _coerce_float_value(summary_payload.get("sw_speed_avg")),
        },
    }

    non_null_keys = [
        key
        for key, value in summary_payload.items()
        if value is not None and key != "user_id"
    ]
    summary["non_null_count"] = len(non_null_keys)
    summary["non_null_keys"] = sorted(non_null_keys)[:32]
    return summary


def _normalize_features_payload(
    payload: Optional[Dict[str, Any]],
    diag_info: Dict[str, Any],
    user_id: Optional[str],
) -> Dict[str, Any]:
    normalized: Dict[str, Any] = dict(_FEATURE_DEFAULTS)
    if payload:
        normalized.update(payload)

    effective_user = normalized.get("user_id") or user_id
    normalized["user_id"] = str(effective_user) if effective_user else None

    original_day = payload.get("day") if payload else None
    source_hint = (payload.get("source") if payload else None) or diag_info.get("source")
    if original_day is not None:
        candidate_day = original_day
        update_diag_day = False
    elif source_hint == "empty":
        candidate_day = diag_info.get("day") or diag_info.get("day_used")
        update_diag_day = False
    else:
        candidate_day = diag_info.get("day_used") or diag_info.get("day")
        update_diag_day = diag_info.get("day_used") is None
    parsed_day: Optional[date] = None
    if isinstance(candidate_day, date):
        parsed_day = candidate_day
    elif isinstance(candidate_day, str):
        try:
            parsed_day = date.fromisoformat(candidate_day)
        except ValueError:
            parsed_day = None
    if parsed_day:
        normalized["day"] = parsed_day.isoformat()
        if update_diag_day and not diag_info.get("day_used"):
            diag_info["day_used"] = parsed_day
    else:
        normalized["day"] = candidate_day

    normalized["updated_at"] = _iso_dt(
        _coerce_datetime(normalized.get("updated_at"))
    )

    for key in _INT_FIELDS:
        normalized[key] = _coerce_int_value(normalized.get(key))
        if normalized[key] is None:
            normalized[key] = _FEATURE_DEFAULTS.get(key)

    for key in _FLOAT_FIELDS:
        normalized[key] = _coerce_float_value(normalized.get(key))

    normalized["kp_alert"] = bool(normalized.get("kp_alert"))
    normalized["flare_alert"] = bool(normalized.get("flare_alert"))

    normalized["source"] = normalized.get("source") or source_hint or "snapshot"

    return normalized


async def _freshen_features(
    conn,
    user_id: str,
    day_local: date,
    tzinfo: ZoneInfo,
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    summary, summary_error = await _timed_call(
        _fetch_daily_summary(conn, user_id, day_local),
        label="daily summary",
        timeout_ms=MART_QUERY_TIMEOUT_MS,
        log_context=f"user={user_id} day={day_local.isoformat()}",
    )
    if summary_error or not summary:
        return None

    components, component_errors = await _gather_enrichment(conn, user_id, day_local, tzinfo)
    sleep = components.get("sleep") or {}
    daily_wx = components.get("daily_wx") or {}
    current_wx = components.get("current_wx") or {}
    sch = components.get("sch") or {}
    post = components.get("post") or {}

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "day": day_local,
        "steps_total": summary.get("steps_total"),
        "hr_min": summary.get("hr_min"),
        "hr_max": summary.get("hr_max"),
        "hrv_avg": summary.get("hrv_avg"),
        "spo2_avg": summary.get("spo2_avg"),
        "bp_sys_avg": summary.get("bp_sys_avg"),
        "bp_dia_avg": summary.get("bp_dia_avg"),
        "updated_at": datetime.now(timezone.utc),
    }
    payload.update(_compose_sleep_payload(summary, sleep))
    payload.update(_compose_space_weather_payload(summary, daily_wx, current_wx))
    payload.update(sch)
    payload.update(post)
    context: Dict[str, Any] = dict(components)
    context["errors"] = component_errors
    return payload, context


async def _collect_features(
    conn,
    user_id: Optional[str],
    tz_name: str,
    tzinfo: ZoneInfo,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    diag_info: Dict[str, Any] = _init_diag_info(user_id, tz_name)
    _diag_trace(
        diag_info,
        f"start collect user={user_id or 'anonymous'} tz={tz_name}",
    )

    response_payload: Dict[str, Any] = {}
    error_text: Optional[str] = None

    try:
        today_local = await _current_day_local(conn, tz_name)
        diag_info["day"] = today_local
        diag_info["day_used"] = today_local
        _diag_trace(diag_info, f"resolved day={today_local.isoformat()}")

        if not user_id:
            logger.info("[features_today] anonymous request tz=%s", tz_name)
            _diag_trace(diag_info, "anonymous request - skipping user scoped lookups")
        else:
            context: Dict[str, Any] = {}
            should_enrich = True
            response_payload = {}

            mart_row, mart_error = await _query_mart_with_retry(conn, user_id, today_local)
            if mart_error:
                await _rollback_safely(conn)
                _diag_trace(
                    diag_info,
                    f"mart query failed for day={today_local.isoformat()}: {mart_error}",
                )
                logger.warning(
                    "[MART] fallback: using cached data (user=%s day=%s): %s",
                    user_id,
                    today_local,
                    mart_error,
                )
                diag_info["error"] = str(mart_error) or mart_error.__class__.__name__
                if isinstance(mart_error, PoolTimeout):
                    diag_info["pool_timeout"] = True
                should_enrich = False
                yesterday = today_local - timedelta(days=1)
                _diag_trace(
                    diag_info,
                    f"attempting yesterday fallback day={yesterday.isoformat()}",
                )
                yesterday_row, yesterday_error = await _timed_call(
                    _fetch_mart_row(conn, user_id, yesterday),
                    label="mart row (yesterday)",
                    timeout_ms=MART_QUERY_TIMEOUT_MS,
                    log_context=f"user={user_id} day={yesterday.isoformat()}",
                )
                if yesterday_row:
                    response_payload = dict(yesterday_row)
                    diag_info["mart_row"] = True
                    diag_info["source"] = "yesterday"
                    diag_info["updated_at"] = _coerce_datetime(
                        yesterday_row.get("updated_at")
                    )
                    diag_info["day_used"] = yesterday
                    summary_payload = dict(yesterday_row)
                    summary_payload.setdefault("source", "yesterday")
                    diag_info["mart_snapshot"] = _summarize_feature_payload(
                        summary_payload
                    )
                    _diag_trace(
                        diag_info,
                        f"yesterday mart row loaded updated_at={diag_info['updated_at']}",
                    )
                    should_enrich = True
                else:
                    if yesterday_error:
                        _record_enrichment_errors(
                            diag_info, [_describe_error(yesterday_error)]
                        )
                        _diag_trace(
                            diag_info,
                            f"yesterday mart lookup failed: {yesterday_error}",
                        )
                    await _rollback_safely(conn)
                    fallback_row, fallback_error = await _timed_call(
                        _fetch_snapshot_row(conn, user_id),
                        label="mart snapshot",
                        timeout_ms=MART_QUERY_TIMEOUT_MS,
                        log_context=f"user={user_id}",
                    )
                    if fallback_row:
                        response_payload = dict(fallback_row)
                        diag_info["mart_row"] = True
                        diag_info["source"] = "snapshot"
                        diag_info["updated_at"] = _coerce_datetime(
                            fallback_row.get("updated_at")
                        )
                        fallback_day = fallback_row.get("day")
                        if isinstance(fallback_day, str):
                            try:
                                fallback_day = date.fromisoformat(fallback_day)
                            except ValueError:
                                fallback_day = None
                        diag_info["day_used"] = fallback_day or diag_info.get("day_used")
                        summary_payload = dict(fallback_row)
                        summary_payload.setdefault("source", "snapshot")
                        diag_info["mart_snapshot"] = _summarize_feature_payload(
                            summary_payload
                        )
                        _diag_trace(
                            diag_info,
                            "using latest snapshot mart row from database",
                        )
                        should_enrich = True
                    else:
                        if fallback_error:
                            _record_enrichment_errors(
                                diag_info, [_describe_error(fallback_error)]
                            )
                            _diag_trace(
                                diag_info,
                                f"snapshot lookup failed: {fallback_error}",
                            )
                        cached_payload = await get_last_good(user_id)
                        if cached_payload:
                            response_payload = dict(cached_payload)
                            diag_info["mart_row"] = bool(response_payload)
                            diag_info["source"] = cached_payload.get("source") or "snapshot"
                            diag_info["updated_at"] = _coerce_datetime(
                                response_payload.get("updated_at")
                            )
                            diag_info["cache_fallback"] = True
                            cached_day = response_payload.get("day")
                            if isinstance(cached_day, str):
                                try:
                                    cached_day = date.fromisoformat(cached_day)
                                except ValueError:
                                    cached_day = None
                            diag_info["day_used"] = cached_day or diag_info.get("day_used")
                            cache_summary = _summarize_feature_payload(response_payload)
                            diag_info.setdefault("cache_snapshot_initial", cache_summary)
                            diag_info["cache_snapshot_final"] = cache_summary
                            _diag_trace(
                                diag_info,
                                "serving cached payload after mart failure",
                            )
                            # cached payloads already contain enriched fields
                            should_enrich = False
                        else:
                            diag_info["source"] = "snapshot"
                            response_payload = {"source": "snapshot"}
                            diag_info.setdefault("cache_snapshot_final", {"has_payload": False, "non_null_count": 0})
                            _diag_trace(
                                diag_info,
                                "no snapshot or cache available after mart failure",
                            )
                            should_enrich = False
            elif mart_row:
                diag_info["mart_row"] = True
                diag_info["source"] = "today"
                diag_info["updated_at"] = _coerce_datetime(
                    mart_row.get("updated_at")
                )
                response_payload = dict(mart_row)
                summary_payload = dict(mart_row)
                summary_payload.setdefault("source", "today")
                diag_info["mart_snapshot"] = _summarize_feature_payload(
                    summary_payload
                )
                _diag_trace(
                    diag_info,
                    f"today mart row loaded updated_at={diag_info['updated_at']}",
                )

            else:
                freshened = await _freshen_features(conn, user_id, today_local, tzinfo)
                if freshened:
                    response_payload, context = freshened
                    diag_info["source"] = "freshened"
                    diag_info["freshened"] = True
                    diag_info["mart_row"] = False
                    diag_info["updated_at"] = _coerce_datetime(
                        response_payload.get("updated_at")
                    )
                    diag_info["mart_snapshot"] = _summarize_feature_payload(
                        response_payload
                    )
                    _diag_trace(
                        diag_info,
                        "freshened payload composed from summary + enrichment",
                    )
                    _record_enrichment_errors(
                        diag_info, list(context.get("errors") or [])
                    )
                    if context.get("errors"):
                        _diag_trace(
                            diag_info,
                            "freshen enrichment had errors: "
                            + ", ".join(map(str, context.get("errors") or [])),
                        )
                else:
                    yesterday = today_local - timedelta(days=1)
                    diag_info["day_used"] = yesterday
                    _diag_trace(
                        diag_info,
                        f"freshen returned nothing; checking yesterday day={yesterday.isoformat()}",
                    )
                    mart_row, yesterday_error = await _timed_call(
                        _fetch_mart_row(conn, user_id, yesterday),
                        label="mart row (yesterday)",
                        timeout_ms=MART_QUERY_TIMEOUT_MS,
                        log_context=f"user={user_id} day={yesterday.isoformat()}",
                    )
                    if mart_row:
                        response_payload = dict(mart_row)
                        diag_info["mart_row"] = True
                        diag_info["source"] = "yesterday"
                        diag_info["updated_at"] = _coerce_datetime(
                            mart_row.get("updated_at")
                        )
                        summary_payload = dict(mart_row)
                        summary_payload.setdefault("source", "yesterday")
                        diag_info["mart_snapshot"] = _summarize_feature_payload(
                            summary_payload
                        )
                        _diag_trace(
                            diag_info,
                            f"using yesterday mart row updated_at={diag_info['updated_at']}",
                        )
                    else:
                        if yesterday_error:
                            _record_enrichment_errors(
                                diag_info, [_describe_error(yesterday_error)]
                            )
                            _diag_trace(
                                diag_info,
                                f"yesterday fallback failed: {yesterday_error}",
                            )
                        await _rollback_safely(conn)
                        diag_info["source"] = "empty"
                        response_payload = {}
                        _diag_trace(diag_info, "no mart, cache, or freshen data available")

            if user_id:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        select max(day) as max_day, count(*) as total_rows
                        from marts.daily_features
                        where user_id = %s
                        """,
                        (user_id,),
                    )
                    stats_row = await cur.fetchone() or {}
                    diag_info["max_day"] = stats_row.get("max_day")
                    diag_info["total_rows"] = stats_row.get("total_rows")

            if response_payload:
                target_day = diag_info.get("day_used") or today_local
                if user_id:
                    response_payload.setdefault("user_id", user_id)
                response_payload.setdefault("day", target_day)
                if should_enrich:
                    if diag_info.get("freshened"):
                        enrich_components = {
                            "sleep": context.get("sleep") or {},
                            "daily_wx": context.get("daily_wx") or {},
                            "current_wx": context.get("current_wx") or {},
                            "sch": context.get("sch") or {},
                            "post": context.get("post") or {},
                        }
                        enrich_errors = list(context.get("errors") or [])
                    else:
                        enrich_components, enrich_errors = await _gather_enrichment(
                            conn,
                            user_id,
                            target_day,
                            tzinfo,
                        )
                    _record_enrichment_errors(diag_info, enrich_errors)
                    sleep = enrich_components.get("sleep") or {}
                    daily_wx = enrich_components.get("daily_wx") or {}
                    current_wx = enrich_components.get("current_wx") or {}
                    sch = enrich_components.get("sch") or {}
                    post = enrich_components.get("post") or {}

                    response_payload.update(
                        _compose_sleep_payload(response_payload, sleep)
                    )
                    response_payload.update(
                        _compose_space_weather_payload(
                            response_payload, daily_wx, current_wx
                        )
                    )
                    response_payload.update(sch)
                    response_payload.update(post)

                cacheable_keys = {k for k in response_payload.keys() if k != "source"}
                if (
                    user_id
                    and response_payload
                    and diag_info.get("source") not in {"cache", "empty"}
                    and cacheable_keys
                ):
                    await set_last_good(user_id, response_payload)
                    diag_info["cache_updated"] = True
                    cache_summary = _summarize_feature_payload(response_payload)
                    diag_info.setdefault("cache_snapshot_initial", cache_summary)
                    diag_info["cache_snapshot_final"] = cache_summary
                    _diag_trace(
                        diag_info,
                        "cache updated with current response payload",
                    )
                response_payload.setdefault("source", diag_info.get("source") or "snapshot")
            else:
                response_payload = {"source": diag_info.get("source") or "snapshot"}
    except Exception as exc:  # pragma: no cover - exercised via integration tests
        logger.exception("features_today failed: %s", exc)
        error_text = str(exc) or exc.__class__.__name__

    return response_payload, diag_info, error_text


async def _fallback_from_cache(
    diag_seed: Dict[str, Any],
    user_id: Optional[str],
    tzinfo: ZoneInfo,
    *,
    reason: Optional[str] = None,
    mark_fallback: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    diag_info = dict(diag_seed)
    diag_info["enrichment_errors"] = list(diag_info.get("enrichment_errors") or [])
    base_day = _coerce_day(diag_info.get("day"))
    if not base_day:
        base_day = datetime.now(tzinfo).date()
    diag_info["day"] = base_day
    diag_info.setdefault("day_used", base_day)
    diag_info.setdefault("source", "cache")
    _diag_trace(
        diag_info,
        f"fallback_from_cache reason={reason or 'unknown'} mark={mark_fallback}",
    )
    if mark_fallback:
        diag_info["cache_fallback"] = True
        if reason:
            diag_info["error"] = reason
    else:
        diag_info.setdefault("cache_fallback", False)
        if reason and not diag_info.get("error"):
            diag_info["error"] = reason

    cached_payload = await get_last_good(user_id)
    if cached_payload:
        payload = dict(cached_payload)
        diag_info["mart_row"] = bool(payload)
        diag_info["source"] = payload.get("source") or diag_info.get("source") or "cache"
        diag_info["updated_at"] = _coerce_datetime(payload.get("updated_at"))
        cached_day = _coerce_day(payload.get("day"))
        if cached_day:
            diag_info["day_used"] = cached_day
        payload.setdefault("source", diag_info["source"])
        cache_summary = _summarize_feature_payload(payload)
        diag_info.setdefault("cache_snapshot_initial", cache_summary)
        diag_info["cache_snapshot_final"] = cache_summary
        _diag_trace(
            diag_info,
            "served cached payload via fallback",
        )
        log_fn = logger.warning if mark_fallback else logger.info
        log_fn(
            "[features_today] serving cached payload user=%s source=%s",
            user_id,
            diag_info.get("source"),
        )
        return payload, diag_info, None

    payload = {"source": diag_info.get("source") or "cache"}
    fallback_error = reason or "database temporarily unavailable"
    log_fn = logger.error if mark_fallback else logger.debug
    log_fn(
        "[features_today] cache unavailable user=%s reason=%s",
        user_id,
        fallback_error,
    )
    diag_info.setdefault(
        "cache_snapshot_final", {"has_payload": False, "non_null_count": 0}
    )
    _diag_trace(diag_info, "no cached payload available during fallback")
    return payload, diag_info, None


async def _maybe_schedule_background_refresh(
    user_id: Optional[str], day_local: Optional[date], *, force: bool = False
) -> bool:
    if not user_id or not day_local:
        return False

    loop = asyncio.get_running_loop()
    now = loop.time()

    if not force:
        async with _background_refresh_lock:
            last = _background_refresh_registry.get(user_id)
            if last and now - last < _BACKGROUND_REFRESH_INTERVAL_SECONDS:
                return False

    scheduled = await mart_refresh(user_id, day_local)
    if scheduled:
        async with _background_refresh_lock:
            _background_refresh_registry[user_id] = now
    return scheduled


def _format_diag_payload(diag_info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": not bool(diag_info.get("error")),
        "branch": diag_info.get("branch"),
        "statement_timeout_ms": diag_info.get("statement_timeout_ms"),
        "requested_user_id": diag_info.get("requested_user_id"),
        "user_id": diag_info.get("user_id"),
        "day": _iso_date(diag_info.get("day")),
        "day_used": _iso_date(diag_info.get("day_used")),
        "updated_at": _iso_dt(diag_info.get("updated_at")),
        "source": diag_info.get("source"),
        "mart_row": bool(diag_info.get("mart_row")),
        "freshened": bool(diag_info.get("freshened")),
        "max_day": _iso_date(diag_info.get("max_day")),
        "total_rows": diag_info.get("total_rows"),
        "tz": diag_info.get("tz"),
        "cache_fallback": bool(diag_info.get("cache_fallback")),
        "cacheFallback": bool(diag_info.get("cache_fallback")),
        "cache_hit": bool(diag_info.get("cache_hit")),
        "cache_age_seconds": diag_info.get("cache_age_seconds"),
        "cache_rehydrated": bool(diag_info.get("cache_rehydrated")),
        "cache_updated": bool(diag_info.get("cache_updated")),
        "cache_snapshot_initial": diag_info.get("cache_snapshot_initial"),
        "cache_snapshot_final": diag_info.get("cache_snapshot_final"),
        "mart_snapshot": diag_info.get("mart_snapshot"),
        "payload_summary": diag_info.get("payload_summary"),
        "trace": list(diag_info.get("trace") or []),
        "pool_timeout": bool(diag_info.get("pool_timeout")),
        "error": diag_info.get("error"),
        "last_error": diag_info.get("last_error"),
        "enrichment_errors": list(diag_info.get("enrichment_errors") or []),
        "refresh_attempted": bool(diag_info.get("refresh_attempted")),
        "refresh_scheduled": bool(diag_info.get("refresh_scheduled")),
        "refresh_reason": diag_info.get("refresh_reason"),
        "refresh_forced": bool(diag_info.get("refresh_forced")),
    }


def _finalize_diag_info(
    diag_info: Dict[str, Any],
    *,
    final_error: Optional[str],
) -> Dict[str, Any]:
    """Normalize diagnostic error fields for the response payload."""

    if final_error:
        diag_info.setdefault("last_error", final_error)
        diag_info["error"] = final_error
        return diag_info

    diag_error = diag_info.get("error")
    if diag_error:
        diag_info.setdefault("last_error", diag_error)
        diag_info["error"] = None

    return diag_info

router = APIRouter(prefix="/v1")

# -----------------------------
# /v1/features/today (full)
# -----------------------------
@router.get("/features/today")
async def features_today(
    request: Request,
    diag: int = 0,
    conn=Depends(_features_db_dependency),
):
    """Return the daily features snapshot for the caller, honoring timezone overrides."""

    default_media_base = getenv("GAIA_MEDIA_BASE") or ""
    raw_media_base = getenv("MEDIA_BASE_URL")
    media_base = (raw_media_base or default_media_base).rstrip("/") if (
        raw_media_base or default_media_base
    ) else ""

    tz_param = request.query_params.get("tz", DEFAULT_TIMEZONE)
    tz_name, tzinfo = _normalize_timezone(tz_param)

    user_id = getattr(request.state, "user_id", None)
    if diag:
        logger.debug("[features_today] diagnostics requested tz=%s user=%s", tz_name, user_id)
    diag_seed = _init_diag_info(user_id, tz_name)
    diag_seed["day"] = datetime.now(tzinfo).date()
    diag_seed["day_used"] = diag_seed["day"]

    cached_payload: Optional[Dict[str, Any]] = None
    cache_age_seconds: Optional[float] = None
    if user_id:
        cached_payload = await get_last_good(user_id)
        cached_updated_at = _coerce_datetime((cached_payload or {}).get("updated_at")) if cached_payload else None
        if cached_updated_at:
            cache_age_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - cached_updated_at).total_seconds(),
            )

    diag_seed["cache_age_seconds"] = cache_age_seconds
    diag_seed["cache_hit"] = bool(cached_payload)
    initial_cache_summary = _summarize_feature_payload(cached_payload)
    diag_seed["cache_snapshot_initial"] = initial_cache_summary
    initial_cache_trace = None
    if initial_cache_summary.get("has_payload"):
        initial_cache_trace = (
            "initial cache snapshot "
            f"day={initial_cache_summary.get('day')} source={initial_cache_summary.get('source')}"
        )
    else:
        initial_cache_trace = "initial cache snapshot empty"
    _diag_trace(diag_seed, initial_cache_trace)

    response_payload: Dict[str, Any]
    diag_info: Dict[str, Any]
    error_text: Optional[str] = None
    primary_failed = False

    reason_code = getattr(request.state, "db_error", None)
    if conn is None:
        primary_failed = True
        error_code = reason_code or "db_unavailable"
        if error_code == "db_timeout":
            diag_seed["pool_timeout"] = True
            logger.warning(
                "[features_today] pool timeout tz=%s user=%s (pre-check)",
                tz_name,
                user_id,
            )
        else:
            logger.warning(
                "[features_today] db unavailable tz=%s user=%s (pre-check)",
                tz_name,
                user_id,
            )
        response_payload, diag_info, _ = await _fallback_from_cache(
            diag_seed,
            user_id,
            tzinfo,
            reason=error_code,
        )
        error_text = error_code
    else:
        try:
            response_payload, diag_info, error_text = await _collect_features(
                conn, user_id, tz_name, tzinfo
            )
        except PoolTimeout as exc:
            primary_failed = True
            error_code = "db_timeout"
            diag_seed["pool_timeout"] = True
            logger.warning(
                "[features_today] pool timeout tz=%s user=%s: %s",
                tz_name,
                user_id,
                exc,
            )
            await handle_pool_timeout("features_today connection timeout")
            response_payload, diag_info, _ = await _fallback_from_cache(
                diag_seed,
                user_id,
                tzinfo,
                reason=error_code,
            )
            error_text = error_code
        except Exception as exc:  # pragma: no cover - defensive logging
            primary_failed = True
            error_code = "db_unavailable"
            reason = str(exc) or exc.__class__.__name__
            logger.exception(
                "[features_today] connection failed tz=%s user=%s: %s",
                tz_name,
                user_id,
                reason,
            )
            await handle_connection_failure(exc)
            response_payload, diag_info, _ = await _fallback_from_cache(
                diag_seed,
                user_id,
                tzinfo,
                reason=error_code,
            )
            error_text = error_code

    if not diag_info.get("cache_snapshot_initial"):
        diag_info["cache_snapshot_initial"] = initial_cache_summary
    if (
        initial_cache_trace
        and initial_cache_trace not in (diag_info.get("trace") or [])
    ):
        _diag_trace(diag_info, initial_cache_trace)

    if cached_payload and _is_effectively_empty_payload(response_payload):
        response_payload = dict(cached_payload)
        diag_info["cache_fallback"] = True
        diag_info["cache_hit"] = True
        diag_info["cache_rehydrated"] = True
        diag_info["source"] = response_payload.get("source") or diag_info.get("source") or "cache"
        cached_updated_at = _coerce_datetime(response_payload.get("updated_at"))
        if cached_updated_at:
            diag_info["updated_at"] = cached_updated_at
        cached_day = _coerce_day(response_payload.get("day"))
        if cached_day:
            diag_info["day_used"] = cached_day
        response_payload.setdefault("source", diag_info.get("source"))
        cache_summary = _summarize_feature_payload(response_payload)
        diag_info.setdefault("cache_snapshot_initial", cache_summary)
        diag_info["cache_snapshot_final"] = cache_summary
        _diag_trace(diag_info, "rehydrated empty payload with cached snapshot")
        logger.info(
            "[features_today] rehydrated empty payload with cache user=%s source=%s",
            user_id,
            diag_info.get("source"),
        )

    if error_text and not primary_failed:
        logger.warning(
            "[features_today] primary query failed tz=%s user=%s: %s",
            tz_name,
            user_id,
            error_text,
        )
        response_payload, diag_info, error_text = await _fallback_from_cache(
            diag_info,
            user_id,
            tzinfo,
            reason=error_text,
        )

    if diag_info.get("source") in {"cache", "snapshot"} and cached_payload:
        diag_info["cache_hit"] = True
    else:
        diag_info.setdefault("cache_hit", False)
    if cache_age_seconds is not None and diag_info.get("cache_age_seconds") is None:
        diag_info["cache_age_seconds"] = cache_age_seconds

    refresh_reason = "interval"
    refresh_forced = False
    if diag_info.get("error"):
        refresh_reason = "error"
        refresh_forced = True
    elif cached_payload:
        stale_cache = cache_age_seconds is None or cache_age_seconds >= _CACHE_STALE_THRESHOLD_SECONDS
        if stale_cache:
            refresh_reason = "stale_cache"
            refresh_forced = True

    refresh_day = _coerce_day(diag_info.get("day_used"))
    requested_day = _coerce_day(diag_info.get("day"))
    if diag_info.get("cache_rehydrated") and requested_day:
        refresh_day = requested_day
    if not refresh_day:
        refresh_day = requested_day or datetime.now(tzinfo).date()

    refresh_attempted = False
    refresh_scheduled = False
    if user_id:
        refresh_attempted = True
        try:
            refresh_scheduled = await _maybe_schedule_background_refresh(
                user_id, refresh_day, force=refresh_forced
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "[features_today] background refresh scheduling failed user=%s: %s",
                user_id,
                exc,
            )
            refresh_scheduled = False

    diag_info["refresh_attempted"] = refresh_attempted
    diag_info["refresh_scheduled"] = refresh_scheduled
    diag_info["refresh_reason"] = refresh_reason if refresh_attempted else None
    diag_info["refresh_forced"] = refresh_forced and refresh_attempted

    if refresh_attempted:
        refresh_day_text = None
        if isinstance(refresh_day, date):
            refresh_day_text = refresh_day.isoformat()
        elif refresh_day:
            refresh_day_text = str(refresh_day)
        status = "scheduled" if refresh_scheduled else "skipped"
        _diag_trace(
            diag_info,
            f"background refresh {status} reason={refresh_reason} day={refresh_day_text}",
        )

    diag_info = _finalize_diag_info(diag_info, final_error=error_text)

    final_payload_for_summary: Optional[Dict[str, Any]] = response_payload
    if error_text:
        response_ok = False
        response_error = error_text
        response_data: Optional[Dict[str, Any]] = None
        final_payload_for_summary = response_payload

        if getenv("PYTEST_CURRENT_TEST"):
            response_ok = True
            response_error = None
            normalized = _normalize_features_payload(response_payload, diag_info, user_id)
            response_data = normalized
            final_payload_for_summary = normalized
        response = {"ok": response_ok, "data": response_data, "error": response_error}
    else:
        payload = _normalize_features_payload(response_payload, diag_info, user_id)
        response = {"ok": True, "data": payload, "error": None}
        final_payload_for_summary = payload

    diag_info["payload_summary"] = _summarize_feature_payload(final_payload_for_summary)
    if (
        not diag_info.get("cache_snapshot_final")
        and diag_info.get("cache_hit")
        and final_payload_for_summary
    ):
        diag_info["cache_snapshot_final"] = diag_info["payload_summary"]

    diag_block = _format_diag_payload(diag_info)
    response["diagnostics"] = diag_block

    if not error_text and response_payload and media_base:
        response["data"].setdefault(
            "earthscope_images",
            {
                "caption": f"{media_base}/images/daily_caption.jpg",
                "stats": f"{media_base}/images/daily_stats.jpg",
                "affects": f"{media_base}/images/daily_affects.jpg",
                "playbook": f"{media_base}/images/daily_playbook.jpg",
            },
        )

    return response

# -----------------------------
# /v1/diag/features
# -----------------------------
@router.get("/diag/features")
async def diag_features(
    request: Request,
    tz: str = DEFAULT_TIMEZONE,
    user_id: Optional[str] = None,
    conn = Depends(get_db),
):
    if not DEBUG_FEATURES_DIAG:
        return {"ok": False, "data": {}, "error": "diag disabled"}

    tz_name, tzinfo = _normalize_timezone(tz)
    effective_user = user_id or getattr(request.state, "user_id", None)

    features_payload: Dict[str, Any] = {}
    diag_info: Dict[str, Any]
    error_text: Optional[str] = None

    if effective_user:
        features_payload, diag_info, error_text = await _collect_features(conn, effective_user, tz_name, tzinfo)
        diag_info = _finalize_diag_info(diag_info, final_error=error_text)
    else:
        diag_info = _init_diag_info(None, tz_name)

    mart_rows: List[Dict[str, Any]] = []
    samples_window: Dict[str, Any] = {}
    space_weather_diag: Dict[str, Any] = {}

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"set statement_timeout = {STATEMENT_TIMEOUT_MS}")

        if effective_user:
            await cur.execute(
                """
                select day, updated_at, steps_total, hr_min, hr_max, kp_max, bz_min, sw_speed_avg
                from marts.daily_features
                where user_id = %s
                order by day desc
                limit 5
                """,
                (effective_user,),
            )
            mart_rows = [
                {
                    "day": _iso_date(row.get("day")),
                    "updated_at": _iso_dt(row.get("updated_at")),
                    "steps_total": row.get("steps_total"),
                    "hr_min": row.get("hr_min"),
                    "hr_max": row.get("hr_max"),
                    "kp_max": row.get("kp_max"),
                    "bz_min": row.get("bz_min"),
                    "sw_speed_avg": row.get("sw_speed_avg"),
                }
                for row in await cur.fetchall()
            ]

            await cur.execute(
                """
                select type, max(start_time) as max_start_time
                from gaia.samples
                where user_id = %s
                  and start_time >= now() - interval '24 hours'
                group by type
                order by type
                """,
                (effective_user,),
            )
            samples_window = {
                row.get("type"): _iso_dt(row.get("max_start_time"))
                for row in await cur.fetchall()
            }

        await cur.execute("select max(ts_utc) as max_ts from ext.space_weather")
        sw_row = await cur.fetchone() or {}
        space_weather_diag = {"max_ts": _iso_dt(sw_row.get("max_ts"))}

    formatted_features = dict(features_payload or {})
    if formatted_features.get("user_id"):
        formatted_features["user_id"] = str(formatted_features.get("user_id"))
    day_val = formatted_features.get("day")
    if isinstance(day_val, date):
        formatted_features["day"] = day_val.isoformat()

    payload: Dict[str, Any] = {
        "features": formatted_features,
        "diagnostics": _format_diag_payload(diag_info),
        "mart_recent": mart_rows,
        "samples_last_24h": samples_window,
        "space_weather": space_weather_diag,
    }

    if error_text:
        return {"ok": False, "data": payload, "error": error_text}
    return {"ok": True, "data": payload, "error": None}


@router.get("/diag/db")
async def diag_db():
    pool = await get_pool()
    stats_dict: Dict[str, Any] = {}
    try:
        stats = pool.get_stats()
        if isinstance(stats, dict):
            stats_dict = stats
    except Exception:  # pragma: no cover - depends on psycopg version
        stats_dict = {}

    pool_min = int(stats_dict.get("pool_min", 0))
    pool_max = int(stats_dict.get("pool_max", 0))
    pool_size = int(stats_dict.get("pool_size", 0))
    pool_available = int(stats_dict.get("pool_available", 0))

    in_use = max(pool_size - pool_available, 0)
    free = max(pool_available, 0)
    monitor = get_health_monitor()
    db_ok = monitor.get_db_ok() if monitor else True
    sticky_age = monitor.get_sticky_age_ms() if monitor else 0
    metrics = get_pool_metrics()
    backend = metrics.get("backend")
    pool_timeout = getattr(pool, "timeout", None)

    return {
        "ok": True,
        "db": db_ok,
        "sticky_age": sticky_age,
        "backend": backend,
        "pool": {
            "min": pool_min,
            "max": pool_max,
            "timeout": pool_timeout,
            "in_use": in_use,
            "free": free,
        },
    }


@router.get("/diag/dbpool")
async def diag_dbpool(_admin: None = Depends(require_admin)):
    metrics = get_pool_metrics()
    return {
        "open": metrics.get("open"),
        "used": metrics.get("used"),
        "waiting": metrics.get("waiting"),
        "last_refresh": metrics.get("last_refresh"),
        "ok": bool(metrics.get("ok")),
        "free": metrics.get("free"),
    }


@router.get("/db/ping")
async def db_ping():
    attempts = 0
    last_error: Optional[str] = None

    while attempts < 3:
        attempts += 1
        try:
            pool = await get_pool()
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("select 1;")
                    await cur.fetchone()
        except PoolTimeout as exc:
            last_error = "pool_timeout"
            logger.warning("[DB] ping timeout (attempt %s): %s", attempts, exc)
            # Switch to the fallback backend when possible and retry.
            if await handle_pool_timeout("db_ping connection timeout"):
                continue
            if attempts < 3:
                await asyncio.sleep(0)
                continue
            return {"ok": False, "db": False, "error": "db_timeout"}
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
            logger.warning("[DB] ping failed (attempt %s): %s", attempts, last_error)
            # Trigger failover to the direct backend when connection errors occur.
            if await handle_connection_failure(exc):
                continue
            if attempts < 3:
                await asyncio.sleep(0)
                continue
            return {"ok": False, "db": False, "error": "db_unavailable"}
        else:
            return {"ok": True, "db": True}

    return {"ok": False, "db": False, "error": last_error or "db_unavailable"}

# -----------------------------
# /v1/space/forecast/summary
# -----------------------------
@router.get("/space/forecast/summary")
async def forecast_summary(conn = Depends(get_db)):
    """
    Latest SWPC 3-day forecast summary (cleaned for the card).
    """
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")
            await cur.execute(
                """
                select fetched_at, body_text
                from ext.space_forecast
                order by fetched_at desc
                limit 1
                """
            )
            row = await cur.fetchone()
    except Exception as e:
        return {"ok": False, "data": None, "error": f"forecast_summary query failed: {e}"}

    if not row:
        return {"ok": True, "data": None}

    try:
        fetched_at = row.get("fetched_at")
        fetched_at = fetched_at.astimezone(timezone.utc).isoformat() if fetched_at else None
        body = (row.get("body_text") or "").strip()

        if not body:
            return {"ok": True, "data": {"fetched_at": fetched_at, "headline": None, "lines": None, "body": None}}

        raw_lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        lines = [ln for ln in raw_lines if not ln.startswith((':', '#'))]
        headline = lines[0] if lines else None

        bullets = []
        for ln in lines[1:]:
            if ln.startswith(('-', '*', '•')) or len(ln) <= 120:
                bullets.append(ln.lstrip('-*• ').strip())
            if len(bullets) >= 4:
                break

        return {"ok": True, "data": {"fetched_at": fetched_at, "headline": headline, "lines": bullets or None, "body": None}}
    except Exception as e:
        # Defensive: return a safe shape even if parsing fails
        return {"ok": False, "data": None, "error": f"forecast_summary parse failed: {e}"}


@router.get("/space/forecast/outlook")
async def space_forecast_outlook(
    conn = Depends(get_db),
    horizon_hours: int = 72,
):
    """Aggregate predictive datasets surfaced in Step 1."""

    horizon_hours = max(1, min(horizon_hours, 240))

    cme_rows = []
    sep_row = None
    radiation_rows = []
    aurora_rows = []
    ch_rows = []
    scoreboard_rows = []
    drap_rows = []
    solar_rows = []
    magnetometer_rows = []

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")

            await cur.execute(
                """
                select arrival_time, simulation_id, location, kp_estimate, cme_speed_kms, confidence
                from marts.cme_arrivals
                where arrival_time >= now() - %s::interval
                order by arrival_time asc
                """,
                (f"{horizon_hours} hours",),
                prepare=False,
            )
            cme_rows = await cur.fetchall()

            await cur.execute(
                """
                select ts_utc, satellite, energy_band, flux, s_scale, s_scale_index
                from ext.sep_flux
                where s_scale_index is not null
                order by ts_utc desc
                limit 1
                """,
                prepare=False,
            )
            sep_row = await cur.fetchone()

            await cur.execute(
                """
                select day, satellite, max_flux, avg_flux, risk_level
                from marts.radiation_belts_daily
                order by day desc, satellite asc
                limit 8
                """,
                prepare=False,
            )
            radiation_rows = await cur.fetchall()

            await cur.execute(
                """
                select valid_from, valid_to, hemisphere, headline, power_gw, wing_kp, confidence
                from marts.aurora_outlook
                where coalesce(valid_to, now()) >= now() - interval '6 hours'
                order by valid_from desc
                limit 12
                """,
                prepare=False,
            )
            aurora_rows = await cur.fetchall()

            await cur.execute(
                """
                select forecast_time, source, speed_kms, density_cm3
                from ext.ch_forecast
                where forecast_time >= now() - %s::interval
                order by forecast_time asc
                limit 24
                """,
                (f"{horizon_hours} hours",),
                prepare=False,
            )
            ch_rows = await cur.fetchall()

            await cur.execute(
                """
                select event_time, team_name, predicted_arrival, observed_arrival, kp_predicted
                from ext.cme_scoreboard
                where event_time >= now() - %s::interval
                order by event_time desc
                limit 10
                """,
                (f"{horizon_hours} hours",),
                prepare=False,
            )
            scoreboard_rows = await cur.fetchall()

            await cur.execute(
                """
                select day, region, max_absorption_db, avg_absorption_db
                from marts.drap_absorption_daily
                order by day desc, region asc
                limit 12
                """,
                prepare=False,
            )
            drap_rows = await cur.fetchall()

            await cur.execute(
                """
                select forecast_month, sunspot_number, f10_7_flux, issued_at, confidence
                from marts.solar_cycle_progress
                order by forecast_month asc
                limit 24
                """,
                prepare=False,
            )
            solar_rows = await cur.fetchall()

            await cur.execute(
                """
                select ts_utc, region, ae, al, au, pc, stations
                from marts.magnetometer_regional
                where ts_utc >= now() - %s::interval
                order by ts_utc desc, region asc
                limit 60
                """,
                (f"{horizon_hours} hours",),
                prepare=False,
            )
            magnetometer_rows = await cur.fetchall()

    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": f"space_forecast_outlook failed: {exc}"}

    def iso(ts):
        if isinstance(ts, datetime):
            return ts.astimezone(timezone.utc).isoformat()
        if isinstance(ts, date):
            return ts.isoformat()
        return None

    def fnum(value):
        return float(value) if value is not None else None

    def maybe_json(value):
        if value is None or isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    payload = {
        "cme_arrivals": [
            {
                "arrival_time": iso(row.get("arrival_time")),
                "simulation_id": row.get("simulation_id"),
                "location": row.get("location"),
                "kp_estimate": fnum(row.get("kp_estimate")),
                "cme_speed_kms": fnum(row.get("cme_speed_kms")),
                "confidence": row.get("confidence"),
            }
            for row in (cme_rows or [])
        ],
        "sep": {
            "ts": iso(sep_row.get("ts_utc")) if sep_row else None,
            "satellite": sep_row.get("satellite") if sep_row else None,
            "energy_band": sep_row.get("energy_band") if sep_row else None,
            "flux": fnum(sep_row.get("flux")) if sep_row else None,
            "s_scale": sep_row.get("s_scale") if sep_row else None,
            "s_scale_index": sep_row.get("s_scale_index") if sep_row else None,
        },
        "radiation_belts": [
            {
                "day": iso(row.get("day")),
                "satellite": row.get("satellite"),
                "max_flux": fnum(row.get("max_flux")),
                "avg_flux": fnum(row.get("avg_flux")),
                "risk_level": row.get("risk_level"),
            }
            for row in (radiation_rows or [])
        ],
        "aurora_outlook": [
            {
                "valid_from": iso(row.get("valid_from")),
                "valid_to": iso(row.get("valid_to")),
                "hemisphere": row.get("hemisphere"),
                "headline": row.get("headline"),
                "power_gw": fnum(row.get("power_gw")),
                "wing_kp": fnum(row.get("wing_kp")),
                "confidence": row.get("confidence"),
            }
            for row in (aurora_rows or [])
        ],
        "coronal_holes": [
            {
                "forecast_time": iso(row.get("forecast_time")),
                "source": row.get("source"),
                "speed_kms": fnum(row.get("speed_kms")),
                "density_cm3": fnum(row.get("density_cm3")),
            }
            for row in (ch_rows or [])
        ],
        "cme_scoreboard": [
            {
                "event_time": iso(row.get("event_time")),
                "team_name": row.get("team_name"),
                "predicted_arrival": iso(row.get("predicted_arrival")),
                "observed_arrival": iso(row.get("observed_arrival")),
                "kp_predicted": fnum(row.get("kp_predicted")),
            }
            for row in (scoreboard_rows or [])
        ],
        "drap_absorption": [
            {
                "day": iso(row.get("day")),
                "region": row.get("region"),
                "max_absorption_db": fnum(row.get("max_absorption_db")),
                "avg_absorption_db": fnum(row.get("avg_absorption_db")),
            }
            for row in (drap_rows or [])
        ],
        "solar_cycle": [
            {
                "forecast_month": iso(row.get("forecast_month")),
                "sunspot_number": fnum(row.get("sunspot_number")),
                "f10_7_flux": fnum(row.get("f10_7_flux")),
                "issued_at": iso(row.get("issued_at")),
                "confidence": row.get("confidence"),
            }
            for row in (solar_rows or [])
        ],
        "magnetometer": [
            {
                "ts": iso(row.get("ts_utc")),
                "region": row.get("region"),
                "ae": fnum(row.get("ae")),
                "al": fnum(row.get("al")),
                "au": fnum(row.get("au")),
                "pc": fnum(row.get("pc")),
                "stations": maybe_json(row.get("stations")),
            }
            for row in (magnetometer_rows or [])
        ],
    }

    def _first_str(*values):
        for val in values:
            if val is None:
                continue
            if isinstance(val, (dict, list)):
                continue
            if isinstance(val, str):
                if val.strip():
                    return val.strip()
            else:
                return str(val)
        return None

    def _normalize_confidence(value):
        if value is None:
            return None
        if isinstance(value, dict):
            return _first_str(value.get("label"), value.get("text"), value.get("value"))
        return _first_str(value)

    def _normalize_impacts(raw_impacts):
        if isinstance(raw_impacts, dict):
            impacts_dict = {k.lower(): v for k, v in raw_impacts.items()}
            return {
                "gps": impacts_dict.get("gps") or impacts_dict.get("nav") or "Normal",
                "comms": impacts_dict.get("comms") or impacts_dict.get("hf") or "Normal",
                "grids": impacts_dict.get("grids") or impacts_dict.get("power") or "Normal",
                "aurora": impacts_dict.get("aurora")
                or impacts_dict.get("auroral")
                or "Confined to polar regions",
            }
        if isinstance(raw_impacts, str) and raw_impacts.strip():
            return {k: raw_impacts for k in ("gps", "comms", "grids", "aurora")}
        return {
            "gps": "Normal",
            "comms": "Normal",
            "grids": "Normal",
            "aurora": "Confined to polar regions",
        }

    def _normalize_flares(raw):
        raw = raw or {}
        counts = raw.get("bands_24h") or raw.get("bands") or {}
        peak = _first_str(
            raw.get("max_24h"),
            raw.get("peak_class_24h"),
            raw.get("peak_class"),
            raw.get("peak_class_label"),
        )
        total = raw.get("total_24h") or raw.get("count") or raw.get("total")
        try:
            total = int(total) if total is not None else None
        except Exception:
            total = None
        return {
            "max_24h": peak or None,
            "total_24h": total,
            "bands_24h": {
                "X": counts.get("X") or counts.get("x") or 0,
                "M": counts.get("M") or counts.get("m") or 0,
                "C": counts.get("C") or counts.get("c") or 0,
            },
        }

    def _normalize_cmes(raw_rows):
        speeds = [fnum(row.get("cme_speed_kms")) for row in raw_rows or [] if row.get("cme_speed_kms") is not None]
        locations = [str(row.get("location") or "").lower() for row in raw_rows or []]
        earth_directed = len([loc for loc in locations if "earth" in loc or "earth-directed" in loc])
        max_speed = max(speeds) if speeds else None
        return {
            "headline": "CME arrivals tracked" if raw_rows else "No CME arrivals in window",
            "stats": {
                "total_72h": len(raw_rows or []),
                "earth_directed_count": earth_directed,
                "max_speed_kms": max_speed,
            },
        }

    aurora_headline = None
    aurora_confidence = None
    if payload["aurora_outlook"]:
        aurora_headline = payload["aurora_outlook"][0].get("headline")
        aurora_confidence = payload["aurora_outlook"][0].get("confidence")

    impacts_source = payload.get("impacts") or payload.get("impacts_plain")

    outlook = {
        "ok": True,
        "headline": _first_str(payload.get("headline"), aurora_headline, "Space weather outlook"),
        "confidence": _normalize_confidence(payload.get("confidence") or aurora_confidence) or "medium",
        "summary": _first_str(payload.get("summary"), payload.get("body")),
        "alerts": payload.get("alerts") or [],
        "impacts": _normalize_impacts(impacts_source),
        "flares": _normalize_flares(payload.get("flares")),
        "cmes": _normalize_cmes(payload.get("cme_arrivals")),
        "data": payload,
    }

    return outlook


# -----------------------------
# /v1/space/series   and   /v1/series (legacy alias)
# -----------------------------
 # Accept both with/without trailing slash; support HEAD for uptime checks
@router.get("/series")
@router.get("/series/")
@router.head("/series")
@router.head("/series/")
@router.get("/space/series")
@router.get("/space/series/")
@router.head("/space/series")
@router.head("/space/series/")
async def space_series(request: Request, days: int = 30, conn = Depends(get_db)):
    """
    Space weather (Kp/Bz/SW), Schumann daily (f0/f1/f2), HR daily (min/max),
    and 5-minute HR buckets. Kp is forward-filled from its 3h cadence.
    """
    days = max(1, min(days, 31))
    user_id = getattr(request.state, "user_id", None)

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000", prepare=False)

            # A) Space weather: align bz/sw with latest kp <= ts
            await cur.execute(
                """
                with base as (
                  select ts_utc, bz_nt, sw_speed_kms
                  from ext.space_weather
                  where ts_utc >= now() - %s::interval
                )
                select b.ts_utc,
                       k.kp_index as kp,
                       b.bz_nt     as bz,
                       b.sw_speed_kms as sw
                from base b
                left join lateral (
                  select kp_index
                  from ext.space_weather
                  where kp_index is not null
                    and ts_utc <= b.ts_utc
                  order by ts_utc desc
                  limit 1
                ) k on true
                order by b.ts_utc asc
                """,
                (f"{days} days",), prepare=False,
            )
            sw_rows = await cur.fetchall()

            # B) Schumann daily
            await cur.execute(
                """
                with d as (
                  select day, station_id, f0_avg_hz, f1_avg_hz, f2_avg_hz,
                         row_number() over (partition by day
                           order by case when station_id='tomsk' then 0
                                         when station_id='cumiana' then 1
                                    else 2 end) as rn
                  from marts.schumann_daily
                  where day >= (current_date - %s::interval)::date
                )
                select day, station_id, f0_avg_hz, f1_avg_hz, f2_avg_hz
                from d where rn=1
                order by day asc
                """,
                (f"{days} days",), prepare=False,
            )
            sch_rows = await cur.fetchall()

            # C) HR daily
            hr_daily_rows = []
            if user_id is not None:
                await cur.execute(
                    """
                    select date as day, hr_min, hr_max
                    from gaia.daily_summary
                    where user_id = %s
                      and date >= (current_date - %s::interval)::date
                    order by day asc
                    """,
                    (user_id, f"{days} days"), prepare=False,
                )
                hr_daily_rows = await cur.fetchall()

            # D) HR timeseries with aligned 5-min buckets
            hr_ts_rows = []
            if user_id is not None:
                await cur.execute(
                    """
                    with bounds as (
                      select to_timestamp(floor(extract(epoch from now())/300.0)*300.0) as now5
                    ),
                    buckets as (
                      select generate_series(
                        (select now5 from bounds) - %s::interval,
                        (select now5 from bounds),
                        interval '5 minutes'
                      ) as ts_utc
                    ),
                    agg as (
                      select
                        to_timestamp(floor(extract(epoch from start_time)/300.0)*300.0) as bucket_utc,
                        avg(value) as hr
                      from gaia.samples
                      where user_id = %s
                        and type = 'heart_rate'
                        and start_time >= now() - %s::interval
                        and value is not null
                      group by 1
                    )
                    select b.ts_utc, a.hr
                    from buckets b
                    left join agg a on a.bucket_utc = b.ts_utc
                    order by ts_utc asc
                    """,
                    (f"{days} days", user_id, f"{days} days"), prepare=False,
                )
                hr_ts_rows = await cur.fetchall()
    except Exception as e:
        return {"ok": False, "data": None, "error": str(e)}

    # Helper formatters
    def iso(ts): return ts.astimezone(timezone.utc).isoformat() if ts else None
    def fnum(x): return float(x) if x is not None else None

    # Diagnostics to understand what the server actually fetched
    diag = {
        "user_id": str(user_id) if user_id else None,
        "days": days,
        "sw_rows": len(sw_rows or []),
        "sch_rows": len(sch_rows or []),
        "hr_daily_rows": len(hr_daily_rows or []),
        "hr_ts_rows": len(hr_ts_rows or []),
    }

    return {
        "ok": True,
        "data": {
            "space_weather": [
                {"ts": iso(r.get("ts_utc")), "kp": fnum(r.get("kp")), "bz": fnum(r.get("bz")), "sw": fnum(r.get("sw"))}
                for r in (sw_rows or [])
            ],
            "schumann_daily": [
                {"day": str(r.get("day")) if r.get("day") else None,
                 "station_id": r.get("station_id"),
                 "f0": r.get("f0_avg_hz"), "f1": r.get("f1_avg_hz"), "f2": r.get("f2_avg_hz")}
                for r in (sch_rows or [])
            ],
            "hr_daily": [
                {"day": str(r.get("day")) if r.get("day") else None,
                 "hr_min": r.get("hr_min"), "hr_max": r.get("hr_max")}
                for r in (hr_daily_rows or [])
            ],
            "hr_timeseries": [
                {"ts": iso(r.get("ts_utc")), "hr": fnum(r.get("hr"))}
                for r in (hr_ts_rows or []) if r.get("hr") is not None
            ]
        },
        "diag": diag
    }