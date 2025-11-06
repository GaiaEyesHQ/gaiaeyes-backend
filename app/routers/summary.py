# app/routers/summary.py
import asyncio
import logging
import random
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from os import getenv
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout
from app.cache import get_last_good, set_last_good
from app.db import get_db, get_pool, get_pool_metrics
from app.utils.auth import require_admin

DEFAULT_TIMEZONE = "America/Chicago"
STATEMENT_TIMEOUT_MS = 60000
FRESHEN_TIMEOUT_MS = 3000

DEBUG_FEATURES_DIAG = getenv("DEBUG_FEATURES_DIAG", "1").lower() not in {"0", "false", "no"}

logger = logging.getLogger(__name__)

STATEMENT_TIMEOUT_MS = 60000

MART_REFRESH_DEBOUNCE_SECONDS = 180.0
_REFRESH_DELAY_RANGE = (1.5, 2.0)


@asynccontextmanager
async def _acquire_features_conn():
    """Acquire a database connection for the features endpoint."""

    pool = await get_pool()
    ctx = pool.connection()
    try:
        conn = await ctx.__aenter__()
    except Exception:
        raise

    try:
        await conn.execute(f"set statement_timeout = {STATEMENT_TIMEOUT_MS}")
    except Exception as exc:
        await ctx.__aexit__(type(exc), exc, exc.__traceback__)
        raise

    try:
        yield conn
    finally:
        await ctx.__aexit__(None, None, None)


_refresh_registry: Dict[str, float] = {}
_refresh_inflight: Dict[Tuple[str, date], asyncio.Task] = {}
_refresh_lock = asyncio.Lock()
_refresh_task_factory: Callable[[Awaitable[None]], asyncio.Task] = asyncio.create_task


async def _execute_mart_refresh(user_id: str, day_local: date) -> None:
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "select marts.refresh_daily_features_user(%s, %s::date)",
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
    "sch_f0_hz",
    "sch_f1_hz",
    "sch_f2_hz",
    "sch_f3_hz",
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


def _coerce_day(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


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

    normalized["updated_at"] = _iso_dt(normalized.get("updated_at"))

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
    summary = await _fetch_daily_summary(conn, user_id, day_local)
    if not summary:
        return None
    start_utc, end_utc = _local_bounds(day_local, tzinfo)
    sleep = await _fetch_sleep_aggregate(conn, user_id, start_utc, end_utc)
    daily_wx = await _fetch_space_weather_daily(conn, day_local)
    current_wx = await _fetch_current_space_weather(conn)
    sch = await _fetch_schumann_row(conn, day_local)
    post = await _fetch_daily_post(conn, day_local)

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
    context = {
        "sleep": sleep,
        "daily_wx": daily_wx,
        "current_wx": current_wx,
        "sch": sch,
        "post": post,
    }
    return payload, context


async def _collect_features(
    conn,
    user_id: Optional[str],
    tz_name: str,
    tzinfo: ZoneInfo,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    diag_info: Dict[str, Any] = _init_diag_info(user_id, tz_name)

    response_payload: Dict[str, Any] = {}
    error_text: Optional[str] = None

    try:
        today_local = await _current_day_local(conn, tz_name)
        diag_info["day"] = today_local
        diag_info["day_used"] = today_local

        if not user_id:
            logger.info("[features_today] anonymous request tz=%s", tz_name)
        else:
            context: Dict[str, Any] = {}
            should_enrich = True
            response_payload = {}

            mart_row, mart_error = await _query_mart_with_retry(conn, user_id, today_local)
            if mart_error:
                logger.warning(
                    "[MART] fallback: using cached data (user=%s day=%s): %s",
                    user_id,
                    today_local,
                    mart_error,
                )
                should_enrich = False
                yesterday = today_local - timedelta(days=1)
                yesterday_row = await _fetch_mart_row(conn, user_id, yesterday)
                if yesterday_row:
                    response_payload = dict(yesterday_row)
                    diag_info["mart_row"] = True
                    diag_info["source"] = "yesterday"
                    diag_info["updated_at"] = yesterday_row.get("updated_at")
                    diag_info["day_used"] = yesterday
                else:
                    fallback_row = await _fetch_snapshot_row(conn, user_id)
                    if fallback_row:
                        response_payload = dict(fallback_row)
                        diag_info["mart_row"] = True
                        diag_info["source"] = "snapshot"
                        diag_info["updated_at"] = fallback_row.get("updated_at")
                        fallback_day = fallback_row.get("day")
                        if isinstance(fallback_day, str):
                            try:
                                fallback_day = date.fromisoformat(fallback_day)
                            except ValueError:
                                fallback_day = None
                        diag_info["day_used"] = fallback_day or diag_info.get("day_used")
                    else:
                        cached_payload = await get_last_good(user_id)
                        if cached_payload:
                            response_payload = dict(cached_payload)
                            diag_info["mart_row"] = bool(response_payload)
                            diag_info["source"] = cached_payload.get("source") or "snapshot"
                            diag_info["updated_at"] = response_payload.get("updated_at")
                            cached_day = response_payload.get("day")
                            if isinstance(cached_day, str):
                                try:
                                    cached_day = date.fromisoformat(cached_day)
                                except ValueError:
                                    cached_day = None
                            diag_info["day_used"] = cached_day or diag_info.get("day_used")
                        else:
                            diag_info["source"] = "snapshot"
                            response_payload = {"source": "snapshot"}
            elif mart_row:
                diag_info["mart_row"] = True
                diag_info["source"] = "today"
                diag_info["updated_at"] = mart_row.get("updated_at")
                response_payload = dict(mart_row)
            else:
                freshened = await _freshen_features(conn, user_id, today_local, tzinfo)
                if freshened:
                    response_payload, context = freshened
                    diag_info["source"] = "freshened"
                    diag_info["freshened"] = True
                    diag_info["mart_row"] = False
                    diag_info["updated_at"] = response_payload.get("updated_at")
                else:
                    yesterday = today_local - timedelta(days=1)
                    diag_info["day_used"] = yesterday
                    mart_row = await _fetch_mart_row(conn, user_id, yesterday)
                    if mart_row:
                        response_payload = dict(mart_row)
                        diag_info["mart_row"] = True
                        diag_info["source"] = "yesterday"
                        diag_info["updated_at"] = mart_row.get("updated_at")
                    else:
                        diag_info["source"] = "empty"
                        response_payload = {}

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
                    start_utc, end_utc = _local_bounds(target_day, tzinfo)

                    if not diag_info.get("freshened"):
                        sleep = await _fetch_sleep_aggregate(conn, user_id, start_utc, end_utc)
                        daily_wx = await _fetch_space_weather_daily(conn, target_day)
                        current_wx = await _fetch_current_space_weather(conn)
                        sch = await _fetch_schumann_row(conn, target_day)
                        post = await _fetch_daily_post(conn, target_day)
                    else:
                        sleep = context.get("sleep", {})
                        daily_wx = context.get("daily_wx", {})
                        current_wx = context.get("current_wx", {})
                        sch = context.get("sch", {})
                        post = context.get("post", {})

                    response_payload.update(_compose_sleep_payload(response_payload, sleep))
                    response_payload.update(_compose_space_weather_payload(response_payload, daily_wx, current_wx))
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
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    diag_info = dict(diag_seed)
    base_day = _coerce_day(diag_info.get("day"))
    if not base_day:
        base_day = datetime.now(tzinfo).date()
    diag_info["day"] = base_day
    diag_info.setdefault("day_used", base_day)
    diag_info.setdefault("source", "cache")
    diag_info["cache_fallback"] = True
    if reason:
        diag_info["error"] = reason

    cached_payload = await get_last_good(user_id)
    if cached_payload:
        payload = dict(cached_payload)
        diag_info["mart_row"] = bool(payload)
        diag_info["source"] = payload.get("source") or diag_info.get("source") or "cache"
        diag_info["updated_at"] = payload.get("updated_at")
        cached_day = _coerce_day(payload.get("day"))
        if cached_day:
            diag_info["day_used"] = cached_day
        payload.setdefault("source", diag_info["source"])
        logger.warning(
            "[features_today] serving cached payload user=%s source=%s",
            user_id,
            diag_info.get("source"),
        )
        return payload, diag_info, None

    payload = {"source": diag_info.get("source") or "cache"}
    fallback_error = reason or "database temporarily unavailable"
    logger.error(
        "[features_today] cache unavailable user=%s reason=%s",
        user_id,
        fallback_error,
    )
    return payload, diag_info, fallback_error


def _format_diag_payload(diag_info: Dict[str, Any]) -> Dict[str, Any]:
    return {
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
        "pool_timeout": bool(diag_info.get("pool_timeout")),
        "error": diag_info.get("error"),
    }

router = APIRouter(prefix="/v1")

# -----------------------------
# /v1/features/today (full)
# -----------------------------
@router.get("/features/today")
async def features_today(request: Request, diag: int = 0):
    """Return the daily features snapshot for the caller, honoring timezone overrides."""

    default_media_base = "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main"
    raw_media_base = getenv("MEDIA_BASE_URL")
    media_base = (raw_media_base or default_media_base).rstrip("/")

    tz_param = request.query_params.get("tz", DEFAULT_TIMEZONE)
    tz_name, tzinfo = _normalize_timezone(tz_param)

    user_id = getattr(request.state, "user_id", None)
    if diag:
        logger.debug("[features_today] diagnostics requested tz=%s user=%s", tz_name, user_id)
    diag_seed = _init_diag_info(user_id, tz_name)
    diag_seed["day"] = datetime.now(tzinfo).date()
    diag_seed["day_used"] = diag_seed["day"]

    try:
        async with _acquire_features_conn() as conn:
            response_payload, diag_info, error_text = await _collect_features(conn, user_id, tz_name, tzinfo)
    except PoolTimeout as exc:
        logger.warning(
            "[features_today] pool timeout tz=%s user=%s: %s", tz_name, user_id, exc
        )
        diag_seed["pool_timeout"] = True
        response_payload, diag_info, error_text = await _fallback_from_cache(
            diag_seed,
            user_id,
            tzinfo,
            reason="database temporarily unavailable",
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        reason = str(exc) or exc.__class__.__name__
        logger.exception(
            "[features_today] connection acquisition failed tz=%s user=%s: %s",
            tz_name,
            user_id,
            reason,
        )
        response_payload, diag_info, error_text = await _fallback_from_cache(
            diag_seed,
            user_id,
            tzinfo,
            reason=reason,
        )

    if error_text:
        response: Dict[str, Any] = {"ok": False, "data": None, "error": error_text}
    else:
        payload = _normalize_features_payload(response_payload, diag_info, user_id)
        response = {"ok": True, "data": payload, "error": None}

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

    return {
        "ok": True,
        "pool": {
            "min": pool_min,
            "max": pool_max,
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
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("select 1;")
                await cur.fetchone()
    except Exception as exc:
        logger.warning("[DB] ping failed: %s", exc)
        return {"ok": False, "db": False, "error": "db_unavailable"}
    return {"ok": True, "db": True}

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