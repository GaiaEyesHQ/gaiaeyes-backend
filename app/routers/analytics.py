from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from app.db import get_db
from app.security.auth import require_write_auth
from app.utils.auth import require_admin


router = APIRouter(tags=["analytics"])

DEFAULT_TIMEZONE = "America/Chicago"
_EVENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
_ALLOWED_PROPERTY_KEYS = {
    "action",
    "active_count",
    "category",
    "count",
    "driver_key",
    "filter",
    "key",
    "prediction_match",
    "role",
    "route",
    "screen",
    "share_type",
    "signal_key",
    "source",
    "status",
    "step",
    "surface",
    "tab",
    "window",
}
_ONBOARDING_EVENTS = [
    "onboarding_started",
    "onboarding_abandoned",
    "onboarding_completed",
    "first_insight_viewed",
]
_HEALTH_SYNC_EVENTS = [
    "healthkit_permission_started",
    "healthkit_permission_completed",
    "healthkit_permission_failed",
    "health_backfill_started",
    "health_backfill_completed",
    "health_backfill_failed",
]
_ENGAGEMENT_EVENTS = [
    "daily_checkin_started",
    "daily_checkin_completed",
    "daily_checkin_skipped",
    "symptom_followup_dismissed",
    "all_drivers_opened",
    "all_driver_expanded",
    "signal_bar_tapped",
    "share_opened",
    "share_rendered",
]
_FEATURE_ADOPTION_EVENTS = [
    "notifications_enabled",
    "notifications_disabled",
    "notifications_denied",
    "lunar_tracking_enabled",
    "lunar_tracking_disabled",
    "lunar_tracking_skipped",
]


class AnalyticsEventIn(BaseModel):
    client_event_id: Optional[str] = None
    event_name: str = Field(..., min_length=1, max_length=96)
    event_ts_utc: Optional[datetime] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None
    device_model: Optional[str] = None
    session_id: Optional[str] = None
    surface: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsEventsIn(BaseModel):
    events: List[AnalyticsEventIn] = Field(default_factory=list)


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return str(user_id)


def _clean_text(value: Optional[str], *, max_len: int, default: Optional[str] = None) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return default
    return text[:max_len]


def _normalize_event_name(value: str) -> str:
    event_name = str(value or "").strip()
    if not _EVENT_NAME_RE.match(event_name):
        raise HTTPException(status_code=400, detail="invalid analytics event name")
    return event_name


def _safe_properties(raw: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in (raw or {}).items():
        normalized_key = str(key or "").strip().lower()
        if normalized_key not in _ALLOWED_PROPERTY_KEYS:
            continue
        if value is None:
            continue
        if isinstance(value, bool):
            safe[normalized_key] = value
        elif isinstance(value, int):
            safe[normalized_key] = value
        elif isinstance(value, float):
            safe[normalized_key] = round(value, 6)
        else:
            safe[normalized_key] = str(value).strip()[:160]
        if len(safe) >= 24:
            break
    return safe


def _event_ts(value: Optional[datetime]) -> datetime:
    ts = value or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if ts > now + timedelta(days=1):
        return now
    return ts.astimezone(timezone.utc)


def _parse_tz(value: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(value or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _parse_day(value: Optional[str], fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date") from exc


def _range_bounds(from_value: Optional[str], to_value: Optional[str], tz_name: str) -> tuple[date, date, datetime, datetime]:
    tz = _parse_tz(tz_name)
    today = datetime.now(tz).date()
    to_day = _parse_day(to_value, today)
    from_day = _parse_day(from_value, to_day)
    if from_day > to_day:
        raise HTTPException(status_code=400, detail="from must be before or equal to to")
    if (to_day - from_day).days > 120:
        raise HTTPException(status_code=400, detail="date range cannot exceed 120 days")

    start_local = datetime.combine(from_day, datetime.min.time(), tzinfo=tz)
    end_local = datetime.combine(to_day + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return from_day, to_day, start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _json_row(row: Optional[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in (row or {}).items():
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def _json_rows(rows: Optional[List[dict[str, Any]]]) -> List[dict[str, Any]]:
    return [_json_row(row) for row in rows or []]


async def _fetch_group(cur, start_utc: datetime, end_utc: datetime, event_names: List[str]) -> List[dict[str, Any]]:
    await cur.execute(
        """
        select event_name,
               count(*)::int as events,
               count(distinct user_id)::int as users
          from raw.app_analytics_events
         where event_ts_utc >= %s
           and event_ts_utc < %s
           and event_name = any(%s)
         group by event_name
         order by events desc, event_name asc
        """,
        (start_utc, end_utc, event_names),
        prepare=False,
    )
    return _json_rows(await cur.fetchall())


@router.post("/v1/analytics/events", dependencies=[Depends(require_write_auth)])
async def ingest_analytics_events(payload: AnalyticsEventsIn, request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    events = payload.events[:200]
    if not events:
        return {"ok": True, "received": 0, "inserted": 0, "error": None}

    inserted = 0
    async with conn.cursor() as cur:
        for event in events:
            event_name = _normalize_event_name(event.event_name)
            safe_props = _safe_properties(event.properties)
            surface = _clean_text(event.surface or safe_props.get("surface"), max_len=64)
            await cur.execute(
                """
                insert into raw.app_analytics_events (
                    user_id,
                    client_event_id,
                    event_name,
                    event_ts_utc,
                    platform,
                    app_version,
                    device_model,
                    session_id,
                    surface,
                    properties
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict do nothing
                """,
                (
                    user_id,
                    _clean_text(event.client_event_id, max_len=96),
                    event_name,
                    _event_ts(event.event_ts_utc),
                    _clean_text(event.platform, max_len=32, default="ios"),
                    _clean_text(event.app_version, max_len=64),
                    _clean_text(event.device_model, max_len=96),
                    _clean_text(event.session_id, max_len=96),
                    surface,
                    json.dumps(safe_props, separators=(",", ":"), sort_keys=True),
                ),
                prepare=False,
            )
            rowcount = getattr(cur, "rowcount", 0)
            if isinstance(rowcount, int) and rowcount > 0:
                inserted += rowcount

    return {"ok": True, "received": len(events), "inserted": inserted, "error": None}


@router.get("/v1/admin/analytics/summary", dependencies=[Depends(require_admin)])
async def analytics_summary(
    from_day: Optional[str] = Query(default=None, alias="from"),
    to_day: Optional[str] = Query(default=None, alias="to"),
    tz: str = Query(default=DEFAULT_TIMEZONE),
    conn=Depends(get_db),
):
    range_from, range_to, start_utc, end_utc = _range_bounds(from_day, to_day, tz)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select count(*)::int as events,
                   count(distinct user_id)::int as users,
                   count(distinct session_id)::int as sessions,
                   min(event_ts_utc) as first_event_at,
                   max(event_ts_utc) as last_event_at
              from raw.app_analytics_events
             where event_ts_utc >= %s
               and event_ts_utc < %s
            """,
            (start_utc, end_utc),
            prepare=False,
        )
        totals = _json_row(await cur.fetchone())

        await cur.execute(
            """
            select (event_ts_utc at time zone %s)::date as day,
                   count(*)::int as events,
                   count(distinct user_id)::int as users,
                   count(distinct session_id)::int as sessions
              from raw.app_analytics_events
             where event_ts_utc >= %s
               and event_ts_utc < %s
             group by 1
             order by 1 asc
            """,
            (tz, start_utc, end_utc),
            prepare=False,
        )
        daily = _json_rows(await cur.fetchall())

        await cur.execute(
            """
            select event_name,
                   count(*)::int as events,
                   count(distinct user_id)::int as users
              from raw.app_analytics_events
             where event_ts_utc >= %s
               and event_ts_utc < %s
             group by event_name
             order by events desc, event_name asc
             limit 25
            """,
            (start_utc, end_utc),
            prepare=False,
        )
        top_events = _json_rows(await cur.fetchall())

        onboarding = await _fetch_group(cur, start_utc, end_utc, _ONBOARDING_EVENTS)
        health_sync = await _fetch_group(cur, start_utc, end_utc, _HEALTH_SYNC_EVENTS)
        engagement = await _fetch_group(cur, start_utc, end_utc, _ENGAGEMENT_EVENTS)
        feature_adoption = await _fetch_group(cur, start_utc, end_utc, _FEATURE_ADOPTION_EVENTS)

        await cur.execute(
            """
            select event_name,
                   count(*)::int as events,
                   count(distinct user_id)::int as users
              from raw.app_analytics_events
             where event_ts_utc >= %s
               and event_ts_utc < %s
               and (
                    event_name like '%%failed%%'
                 or event_name like '%%denied%%'
                 or event_name like '%%abandoned%%'
                 or event_name like '%%error%%'
               )
             group by event_name
             order by events desc, event_name asc
             limit 25
            """,
            (start_utc, end_utc),
            prepare=False,
        )
        errors = _json_rows(await cur.fetchall())

    return {
        "ok": True,
        "range": {
            "from": range_from.isoformat(),
            "to": range_to.isoformat(),
            "tz": tz,
            "start_utc": start_utc.isoformat().replace("+00:00", "Z"),
            "end_utc": end_utc.isoformat().replace("+00:00", "Z"),
        },
        "totals": totals,
        "daily": daily,
        "top_events": top_events,
        "onboarding": onboarding,
        "health_sync": health_sync,
        "engagement": engagement,
        "feature_adoption": feature_adoption,
        "errors": errors,
        "error": None,
    }
