from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, conint
from psycopg.rows import dict_row

from app.db import get_db
from app.security.auth import require_read_auth, require_write_auth


router = APIRouter(prefix="/v1/exposures", tags=["exposures"])

DEFAULT_TIMEZONE = os.getenv("GAIA_TIMEZONE", "America/Chicago")
try:
    LOCAL_TZ = ZoneInfo(DEFAULT_TIMEZONE)
except Exception:
    LOCAL_TZ = ZoneInfo("America/Chicago")

_ALLOWED_EXPOSURE_KEYS = {"allergen_exposure", "overexertion"}
_ALLOWED_SOURCES = {"daily_check_in", "guide", "manual", "symptom_log", "system"}


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


def _normalize_exposure_key(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in _ALLOWED_EXPOSURE_KEYS:
        raise HTTPException(status_code=400, detail="invalid exposure key")
    return normalized


def _normalize_source(value: Optional[str]) -> str:
    normalized = str(value or "manual").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in _ALLOWED_SOURCES:
        raise HTTPException(status_code=400, detail="invalid exposure source")
    return normalized


def _normalize_day(value: Optional[str]) -> date:
    if not value:
        return datetime.now(LOCAL_TZ).date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid day") from exc


def _local_day_bounds(day_value: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(day_value, datetime.min.time(), tzinfo=LOCAL_TZ)
    end_local = start_local.replace(hour=0) + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _serialize_ts(value: Any) -> Optional[str]:
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ExposureEnvelope(BaseModel):
    ok: bool = True
    error: Optional[str] = None
    friendly_error: Optional[str] = None


class ExposureEventIn(BaseModel):
    exposure_key: str = Field(..., min_length=1)
    intensity: conint(ge=1, le=3) = 1
    event_ts_utc: Optional[datetime] = None
    source: Optional[str] = None
    note_text: Optional[str] = None


class ExposureEventOut(BaseModel):
    id: str
    exposure_key: str
    intensity: int
    event_ts_utc: str
    source: str
    note_text: Optional[str] = None
    created_at: Optional[str] = None


class ExposureEventEnvelope(ExposureEnvelope):
    data: Optional[ExposureEventOut] = None


class ExposureListEnvelope(ExposureEnvelope):
    data: List[ExposureEventOut] = Field(default_factory=list)


def _row_to_event(row: dict[str, Any]) -> ExposureEventOut:
    return ExposureEventOut(
        id=str(row.get("id") or ""),
        exposure_key=str(row.get("exposure_key") or ""),
        intensity=int(row.get("intensity") or 1),
        event_ts_utc=_serialize_ts(row.get("event_ts_utc")) or "",
        source=str(row.get("source") or "manual"),
        note_text=(str(row.get("note_text")).strip() if row.get("note_text") else None),
        created_at=_serialize_ts(row.get("created_at")),
    )


@router.get("", response_model=ExposureListEnvelope, dependencies=[Depends(require_read_auth)])
async def list_exposures(
    request: Request,
    day: Optional[str] = Query(default=None),
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    target_day = _normalize_day(day)
    start_utc, end_utc = _local_day_bounds(target_day)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select id, exposure_key, intensity, event_ts_utc, source, note_text, created_at
              from raw.user_exposure_events
             where user_id = %s
               and event_ts_utc >= %s
               and event_ts_utc < %s
             order by event_ts_utc desc, created_at desc
            """,
            (user_id, start_utc, end_utc),
            prepare=False,
        )
        rows = await cur.fetchall()

    return ExposureListEnvelope(data=[_row_to_event(row) for row in rows or []])


@router.post("", response_model=ExposureEventEnvelope, dependencies=[Depends(require_write_auth)])
async def create_exposure(
    payload: ExposureEventIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    exposure_key = _normalize_exposure_key(payload.exposure_key)
    source = _normalize_source(payload.source)
    event_ts = payload.event_ts_utc or datetime.now(timezone.utc)
    if event_ts.tzinfo is None:
        event_ts = event_ts.replace(tzinfo=timezone.utc)
    note_text = payload.note_text.strip() if payload.note_text else None

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            insert into raw.user_exposure_events (
                user_id,
                exposure_key,
                intensity,
                event_ts_utc,
                source,
                note_text
            )
            values (%s, %s, %s, %s, %s, %s)
            returning id, exposure_key, intensity, event_ts_utc, source, note_text, created_at
            """,
            (user_id, exposure_key, int(payload.intensity), event_ts, source, note_text),
            prepare=False,
        )
        row = await cur.fetchone()

    return ExposureEventEnvelope(data=_row_to_event(row or {}))
