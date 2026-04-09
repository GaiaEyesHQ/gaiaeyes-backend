from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from psycopg import sql
from psycopg.rows import dict_row

from app.db import get_db, settings
from app.security.auth import require_read_auth, require_supabase_jwt, require_write_auth
from services.personalization.health_context import canonicalize_tag_key, canonicalize_tag_keys


router = APIRouter(prefix="/v1/profile", tags=["profile"])

_NOTIFICATION_FAMILY_DEFAULTS: Dict[str, bool] = {
    "geomagnetic": True,
    "solar_wind": True,
    "flare_cme_sep": True,
    "schumann": True,
    "pressure": True,
    "aqi": True,
    "temp": True,
    "gauge_spikes": True,
    "symptom_followups": False,
    "daily_checkins": False,
}
_NOTIFICATION_SENSITIVITIES = {"minimal", "normal", "detailed"}
_FEEDBACK_CADENCES = {"minimal", "balanced", "detailed", "gentle", "frequent"}
_SYMPTOM_FOLLOWUP_STATES = {"new", "ongoing", "improving", "worse"}
_EXPERIENCE_MODES = {"scientific", "mystical"}
_GUIDE_TYPES = {"cat", "robot", "dog"}
_TONE_STYLES = {"straight", "balanced", "humorous"}
_TEMP_UNITS = {"F", "C"}
_DEFAULT_TEMP_UNIT = "F"
_TRACKED_STAT_KEYS = {
    "resting_hr",
    "respiratory",
    "spo2",
    "hrv",
    "temperature",
    "steps",
    "heart_range",
    "blood_pressure",
}
_DEFAULT_TRACKED_STAT_KEYS = ["resting_hr", "respiratory", "hrv", "spo2", "steps"]
_MAX_FAVORITE_SYMPTOM_CODES = 6
_ACCOUNT_DELETE_SCHEMAS = ["raw", "app", "content", "marts", "gaia"]
_ONBOARDING_STEPS = {
    "welcome",
    "mode",
    "guide",
    "tone",
    "temperature_unit",
    "sensitivities",
    "health_context",
    "location",
    "healthkit",
    "backfill",
    "notifications",
    "activation",
}


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


def _pick(columns: List[str], candidates: List[str]) -> Optional[str]:
    lookup = {c.lower(): c for c in columns}
    for cand in candidates:
        found = lookup.get(cand.lower())
        if found:
            return found
    return None


async def _table_columns(conn, schema: str, table: str) -> List[str]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select column_name
              from information_schema.columns
             where table_schema = %s
               and table_name = %s
             order by ordinal_position
            """,
            (schema, table),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [r.get("column_name") for r in rows or [] if r.get("column_name")]


async def _list_user_scoped_tables(conn) -> List[tuple[str, str]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select c.table_schema, c.table_name
              from information_schema.columns c
              join information_schema.tables t
                on t.table_schema = c.table_schema
               and t.table_name = c.table_name
             where c.column_name = 'user_id'
               and t.table_type = 'BASE TABLE'
               and c.table_schema = any(%s)
             order by
               case c.table_schema
                 when 'raw' then 1
                 when 'app' then 2
                 when 'content' then 3
                 when 'marts' then 4
                 when 'gaia' then 5
                 else 99
               end,
               c.table_name
            """,
            (_ACCOUNT_DELETE_SCHEMAS,),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [
        (str(row.get("table_schema")), str(row.get("table_name")))
        for row in rows or []
        if row.get("table_schema") and row.get("table_name")
    ]


def _positive_rowcount(cursor) -> int:
    rowcount = getattr(cursor, "rowcount", 0)
    return rowcount if isinstance(rowcount, int) and rowcount > 0 else 0


async def _delete_user_scoped_rows(conn, user_id: str) -> Dict[str, Any]:
    deleted: Dict[str, int] = {}
    for schema, table in await _list_user_scoped_tables(conn):
        async with conn.cursor() as cur:
            await cur.execute(
                sql.SQL("delete from {}.{} where {} = %s").format(
                    sql.Identifier(schema),
                    sql.Identifier(table),
                    sql.Identifier("user_id"),
                ),
                (user_id,),
                prepare=False,
            )
            deleted[f"{schema}.{table}"] = _positive_rowcount(cur)

    gaia_user_columns = await _table_columns(conn, "gaia", "users")
    if "id" in gaia_user_columns:
        async with conn.cursor() as cur:
            await cur.execute(
                sql.SQL("delete from {}.{} where {} = %s").format(
                    sql.Identifier("gaia"),
                    sql.Identifier("users"),
                    sql.Identifier("id"),
                ),
                (user_id,),
                prepare=False,
            )
            deleted["gaia.users"] = _positive_rowcount(cur)

    return {
        "rows_deleted": sum(deleted.values()),
        "tables_touched": len([key for key, count in deleted.items() if count > 0]),
        "deleted_by_table": deleted,
    }


async def _delete_supabase_auth_user(user_id: str) -> None:
    supabase_url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    service_role_key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if not supabase_url or not service_role_key:
        raise HTTPException(status_code=500, detail="Supabase admin deletion is not configured")

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    endpoint = f"{supabase_url}/auth/v1/admin/users/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(endpoint, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Supabase auth deletion failed: {exc}") from exc

    if response.status_code in {200, 204, 404}:
        return

    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = str(
                payload.get("msg")
                or payload.get("error_description")
                or payload.get("error")
                or payload.get("message")
                or ""
            )
    except Exception:
        detail = ""
    if not detail:
        detail = response.text[:240]
    raise HTTPException(
        status_code=502,
        detail=f"Supabase auth deletion failed ({response.status_code}): {detail or 'unknown error'}",
    )


class ProfileLocationIn(BaseModel):
    zip: Optional[str] = Field(default=None)
    lat: Optional[float] = Field(default=None)
    lon: Optional[float] = Field(default=None)
    use_gps: Optional[bool] = Field(default=None)
    local_insights_enabled: Optional[bool] = Field(default=None)


class ProfilePreferencesIn(BaseModel):
    mode: Optional[str] = Field(default=None)
    guide: Optional[str] = Field(default=None)
    tone: Optional[str] = Field(default=None)
    temp_unit: Optional[str] = Field(default=None)
    tracked_stat_keys: Optional[List[str]] = Field(default=None)
    smart_stat_swap_enabled: Optional[bool] = Field(default=None)
    favorite_symptom_codes: Optional[List[str]] = Field(default=None)
    lunar_sensitivity_declared: Optional[bool] = Field(default=None)
    onboarding_step: Optional[str] = Field(default=None)
    onboarding_completed: Optional[bool] = Field(default=None)
    healthkit_requested: Optional[bool] = Field(default=None)
    last_backfill_at: Optional[datetime] = Field(default=None)


class GuideSeenIn(BaseModel):
    signature: str = Field(default="")
    viewed_at: Optional[datetime] = Field(default=None)


def _normalize_zip(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = "".join(ch for ch in value.strip() if ch.isdigit())
    if not cleaned:
        return None
    return cleaned[:10]


def _normalize_experience_mode(value: Optional[str], *, fallback: str) -> str:
    candidate = str(value or fallback).strip().lower() or fallback
    if candidate not in _EXPERIENCE_MODES:
        raise HTTPException(status_code=400, detail="invalid experience mode")
    return candidate


def _normalize_guide_type(value: Optional[str], *, fallback: str) -> str:
    candidate = str(value or fallback).strip().lower() or fallback
    if candidate not in _GUIDE_TYPES:
        raise HTTPException(status_code=400, detail="invalid guide type")
    return candidate


def _normalize_tone_style(value: Optional[str], *, fallback: str) -> str:
    candidate = str(value or fallback).strip().lower() or fallback
    if candidate not in _TONE_STYLES:
        raise HTTPException(status_code=400, detail="invalid tone style")
    return candidate


def _normalize_temp_unit(value: Optional[str], *, fallback: str) -> str:
    candidate = str(value or fallback).strip().upper() or fallback
    if candidate not in _TEMP_UNITS:
        raise HTTPException(status_code=400, detail="invalid temperature unit")
    return candidate


def _normalize_onboarding_step(value: Optional[str], *, fallback: str) -> str:
    candidate = str(value or fallback).strip().lower() or fallback
    if candidate not in _ONBOARDING_STEPS:
        raise HTTPException(status_code=400, detail="invalid onboarding step")
    return candidate


def _normalize_tracked_stat_keys(value: Any) -> List[str]:
    if value is None:
        return list(_DEFAULT_TRACKED_STAT_KEYS)
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="invalid tracked stat keys")
    normalized: List[str] = []
    for item in value:
        token = str(item or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not token:
            continue
        if token not in _TRACKED_STAT_KEYS:
            raise HTTPException(status_code=400, detail="invalid tracked stat keys")
        if token not in normalized:
            normalized.append(token)
        if len(normalized) >= 5:
            break
    return normalized or list(_DEFAULT_TRACKED_STAT_KEYS)


def _normalize_favorite_symptom_codes(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="invalid favorite symptom codes")
    normalized: List[str] = []
    for item in value:
        token = str(item or "").strip().upper().replace("-", "_").replace(" ", "_")
        if not token:
            continue
        if token not in normalized:
            normalized.append(token)
        if len(normalized) >= _MAX_FAVORITE_SYMPTOM_CODES:
            break
    return normalized


def _normalize_clock_hhmm(value: Optional[str], *, fallback: str) -> str:
    candidate = (value or "").strip() or fallback
    try:
        parsed = datetime.strptime(candidate, "%H:%M")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="quiet hours must use HH:MM format") from exc
    return parsed.strftime("%H:%M")


def _normalize_notification_sensitivity(value: Optional[str]) -> str:
    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized not in _NOTIFICATION_SENSITIVITIES:
        raise HTTPException(status_code=400, detail="invalid notification sensitivity")
    return normalized


def _normalize_time_zone(value: Optional[str]) -> str:
    candidate = (value or "").strip() or "UTC"
    try:
        ZoneInfo(candidate)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid time_zone") from exc
    return candidate


def _normalize_feedback_cadence(value: Optional[str], *, detail: str) -> str:
    normalized = str(value or "balanced").strip().lower() or "balanced"
    if normalized not in _FEEDBACK_CADENCES:
        raise HTTPException(status_code=400, detail=detail)
    if normalized == "gentle":
        return "minimal"
    if normalized == "frequent":
        return "detailed"
    return normalized


def _normalize_followup_cadence(value: Optional[str]) -> str:
    try:
        return _normalize_feedback_cadence(value, detail="invalid symptom follow-up cadence")
    except HTTPException:
        raise HTTPException(status_code=400, detail="invalid symptom follow-up cadence")


def _normalize_daily_checkin_cadence(value: Optional[str]) -> str:
    try:
        return _normalize_feedback_cadence(value, detail="invalid daily check-in cadence")
    except HTTPException:
        raise HTTPException(status_code=400, detail="invalid daily check-in cadence")


def _normalize_followup_states(value: Any) -> List[str]:
    if value is None:
        return ["new", "ongoing", "improving", "worse"]
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="invalid symptom follow-up states")
    normalized: List[str] = []
    for item in value:
        token = str(item or "").strip().lower()
        if not token:
            continue
        if token not in _SYMPTOM_FOLLOWUP_STATES:
            raise HTTPException(status_code=400, detail="invalid symptom follow-up states")
        if token not in normalized:
            normalized.append(token)
    return normalized or ["new", "ongoing", "improving", "worse"]


def _normalize_followup_codes(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="invalid symptom follow-up symptom codes")
    normalized: List[str] = []
    for item in value:
        token = str(item or "").strip().lower().replace("-", "_").replace(" ", "_")
        if token and token not in normalized:
            normalized.append(token)
    return normalized


def _normalize_notification_families(value: Any) -> Dict[str, bool]:
    merged = dict(_NOTIFICATION_FAMILY_DEFAULTS)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = None
    if isinstance(value, dict):
        for key in _NOTIFICATION_FAMILY_DEFAULTS:
            if key in value:
                merged[key] = bool(value.get(key))
    return merged


def _default_notification_preferences() -> Dict[str, Any]:
    return {
        "enabled": False,
        "signal_alerts_enabled": True,
        "local_condition_alerts_enabled": True,
        "personalized_gauge_alerts_enabled": True,
        "symptom_followups_enabled": False,
        "symptom_followup_push_enabled": False,
        "symptom_followup_cadence": "balanced",
        "symptom_followup_states": ["new", "ongoing", "improving", "worse"],
        "symptom_followup_symptom_codes": [],
        "daily_checkins_enabled": False,
        "daily_checkin_push_enabled": False,
        "daily_checkin_cadence": "balanced",
        "daily_checkin_reminder_time": "20:00",
        "quiet_hours_enabled": False,
        "quiet_start": "22:00",
        "quiet_end": "08:00",
        "time_zone": "UTC",
        "sensitivity": "normal",
        "families": dict(_NOTIFICATION_FAMILY_DEFAULTS),
    }


def _default_profile_preferences() -> Dict[str, Any]:
    return {
        "mode": "scientific",
        "guide": "cat",
        "tone": "balanced",
        "temp_unit": None,
        "tracked_stat_keys": list(_DEFAULT_TRACKED_STAT_KEYS),
        "smart_stat_swap_enabled": True,
        "favorite_symptom_codes": [],
        "lunar_sensitivity_declared": False,
        "onboarding_step": "welcome",
        "onboarding_completed": False,
        "onboarding_completed_at": None,
        "healthkit_requested_at": None,
        "last_backfill_at": None,
    }


def _notification_pref_select(column_names: List[str], column: str, fallback_sql: str) -> str:
    if column in column_names:
        return f"{column} as {column}"
    return f"{fallback_sql} as {column}"


def _notification_pref_placeholder(column: str) -> str:
    if column in {"quiet_start", "quiet_end", "daily_checkin_reminder_time"}:
        return "%s::time"
    if column in {"symptom_followup_states", "symptom_followup_symptom_codes"}:
        return "%s::text[]"
    if column == "families":
        return "%s::jsonb"
    return "%s"


def _normalize_device_token(value: str) -> str:
    cleaned = (
        value.strip()
        .replace(" ", "")
        .replace("<", "")
        .replace(">", "")
    )
    if not cleaned:
        raise HTTPException(status_code=400, detail="device_token is required")
    return cleaned.lower()


async def _fetch_location_row(conn, user_id: str) -> Optional[Dict[str, Any]]:
    cols = await _table_columns(conn, "app", "user_locations")
    if not cols:
        return None

    user_col = _pick(cols, ["user_id"])
    zip_col = _pick(cols, ["zip", "postal_code"])
    lat_col = _pick(cols, ["lat", "latitude"])
    lon_col = _pick(cols, ["lon", "lng", "longitude"])
    label_col = _pick(cols, ["label", "name"])
    primary_col = _pick(cols, ["is_primary", "primary", "is_default"])
    gps_col = _pick(cols, ["use_gps", "gps_enabled", "gps_allowed"])
    local_col = _pick(cols, ["local_insights_enabled", "local_enabled", "is_local_enabled"])
    updated_col = _pick(cols, ["updated_at", "created_at"])
    if not user_col:
        return None

    select_parts = []
    select_parts.append(f"{zip_col} as zip" if zip_col else "null::text as zip")
    select_parts.append(f"{lat_col} as lat" if lat_col else "null::double precision as lat")
    select_parts.append(f"{lon_col} as lon" if lon_col else "null::double precision as lon")
    select_parts.append(f"{label_col} as label" if label_col else "null::text as label")
    if primary_col:
        select_parts.append(f"coalesce({primary_col}, false) as is_primary")
    else:
        select_parts.append("true as is_primary")
    select_parts.append(f"{gps_col} as use_gps" if gps_col else "null::boolean as use_gps")
    select_parts.append(f"{local_col} as local_insights_enabled" if local_col else "null::boolean as local_insights_enabled")
    select_parts.append(f"{updated_col} as updated_at" if updated_col else "null::timestamptz as updated_at")

    order_parts = []
    if primary_col:
        order_parts.append(f"{primary_col} desc")
    if updated_col:
        order_parts.append(f"{updated_col} desc")
    order_sql = f" order by {', '.join(order_parts)}" if order_parts else ""

    sql = (
        f"select {', '.join(select_parts)} "
        f"from app.user_locations "
        f"where {user_col} = %s"
        f"{order_sql} "
        f"limit 1"
    )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id,), prepare=False)
        return await cur.fetchone()


async def _fetch_profile_preferences(conn, user_id: str) -> Dict[str, Any]:
    defaults = _default_profile_preferences()
    columns = await _table_columns(conn, "app", "user_experience_profiles")
    if not columns or "user_id" not in columns:
        return defaults

    select_parts = [
        "mode",
        "guide",
        "tone",
        "temp_unit",
        "tracked_stat_keys",
        "smart_stat_swap_enabled",
        "favorite_symptom_codes",
        "lunar_sensitivity_declared",
        "onboarding_step",
        "onboarding_completed",
        "onboarding_completed_at",
        "healthkit_requested_at",
        "last_backfill_at",
    ]
    select_sql = ", ".join(column for column in select_parts if column in columns)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            (
                f"select {select_sql} "
                "from app.user_experience_profiles "
                "where user_id = %s "
                "limit 1"
            ),
            (user_id,),
            prepare=False,
        )
        row = await cur.fetchone()

    if not row:
        return defaults

    return {
        "mode": _normalize_experience_mode(row.get("mode"), fallback=defaults["mode"]),
        "guide": _normalize_guide_type(row.get("guide"), fallback=defaults["guide"]),
        "tone": _normalize_tone_style(row.get("tone"), fallback=defaults["tone"]),
        "temp_unit": _normalize_temp_unit(row.get("temp_unit"), fallback=_DEFAULT_TEMP_UNIT) if row.get("temp_unit") else None,
        "tracked_stat_keys": _normalize_tracked_stat_keys(row.get("tracked_stat_keys")),
        "smart_stat_swap_enabled": (
            bool(row.get("smart_stat_swap_enabled"))
            if row.get("smart_stat_swap_enabled") is not None
            else bool(defaults["smart_stat_swap_enabled"])
        ),
        "favorite_symptom_codes": _normalize_favorite_symptom_codes(row.get("favorite_symptom_codes")),
        "lunar_sensitivity_declared": bool(row.get("lunar_sensitivity_declared")),
        "onboarding_step": _normalize_onboarding_step(row.get("onboarding_step"), fallback=defaults["onboarding_step"]),
        "onboarding_completed": bool(row.get("onboarding_completed")),
        "onboarding_completed_at": row.get("onboarding_completed_at"),
        "healthkit_requested_at": row.get("healthkit_requested_at"),
        "last_backfill_at": row.get("last_backfill_at"),
    }


@router.get("/location", dependencies=[Depends(require_read_auth)])
async def profile_location(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    row = await _fetch_location_row(conn, user_id)
    if not row:
        return {"ok": True, "location": None}
    return {"ok": True, "location": row}


@router.put("/location", dependencies=[Depends(require_write_auth)])
async def profile_location_upsert(
    payload: ProfileLocationIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    cols = await _table_columns(conn, "app", "user_locations")
    if not cols:
        return {"ok": False, "error": "app.user_locations table unavailable"}

    user_col = _pick(cols, ["user_id"])
    zip_col = _pick(cols, ["zip", "postal_code"])
    lat_col = _pick(cols, ["lat", "latitude"])
    lon_col = _pick(cols, ["lon", "lng", "longitude"])
    label_col = _pick(cols, ["label", "name"])
    primary_col = _pick(cols, ["is_primary", "primary", "is_default"])
    gps_col = _pick(cols, ["use_gps", "gps_enabled", "gps_allowed"])
    local_col = _pick(cols, ["local_insights_enabled", "local_enabled", "is_local_enabled"])
    updated_col = _pick(cols, ["updated_at"])
    created_col = _pick(cols, ["created_at"])
    if not user_col:
        return {"ok": False, "error": "app.user_locations missing user_id"}

    values: Dict[str, Any] = {}
    if zip_col:
        values[zip_col] = _normalize_zip(payload.zip)
    if lat_col:
        values[lat_col] = payload.lat
    if lon_col:
        values[lon_col] = payload.lon
    if gps_col and payload.use_gps is not None:
        values[gps_col] = bool(payload.use_gps)
    if local_col and payload.local_insights_enabled is not None:
        values[local_col] = bool(payload.local_insights_enabled)
    if updated_col:
        values[updated_col] = datetime.now(timezone.utc)

    where = f"{user_col} = %s"
    if primary_col:
        where += f" and coalesce({primary_col}, false) = true"

    if values:
        set_sql = ", ".join([f"{k} = %s" for k in values.keys()])
        params = list(values.values()) + [user_id]
        sql = f"update app.user_locations set {set_sql} where {where}"
        async with conn.cursor() as cur:
            await cur.execute(sql, params, prepare=False)
            updated = cur.rowcount or 0
    else:
        updated = 0

    if updated == 0:
        insert_values: Dict[str, Any] = {user_col: user_id}
        insert_values.update(values)
        if label_col:
            insert_values.setdefault(label_col, "home")
        if primary_col:
            insert_values.setdefault(primary_col, True)
        if created_col:
            insert_values.setdefault(created_col, datetime.now(timezone.utc))
        if updated_col:
            insert_values.setdefault(updated_col, datetime.now(timezone.utc))

        cols_sql = ", ".join(insert_values.keys())
        val_sql = ", ".join(["%s"] * len(insert_values))
        sql = f"insert into app.user_locations ({cols_sql}) values ({val_sql})"
        async with conn.cursor() as cur:
            await cur.execute(sql, list(insert_values.values()), prepare=False)

    row = await _fetch_location_row(conn, user_id)
    return {"ok": True, "location": row}


@router.get("/preferences", dependencies=[Depends(require_read_auth)])
async def profile_preferences(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    return {"ok": True, "preferences": await _fetch_profile_preferences(conn, user_id)}


@router.delete("/account", dependencies=[Depends(require_supabase_jwt)])
async def profile_delete_account(
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    if not (settings.SUPABASE_URL or "").strip() or not (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip():
        raise HTTPException(status_code=500, detail="Supabase admin deletion is not configured")
    deletion_summary = await _delete_user_scoped_rows(conn, user_id)
    await conn.commit()
    await _delete_supabase_auth_user(user_id)
    return {
        "ok": True,
        "data": {
            "deleted_user_id": user_id,
            "rows_deleted": deletion_summary["rows_deleted"],
            "tables_touched": deletion_summary["tables_touched"],
        },
    }


@router.put("/preferences", dependencies=[Depends(require_write_auth)])
async def profile_preferences_upsert(
    payload: ProfilePreferencesIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    defaults = _default_profile_preferences()
    current = await _fetch_profile_preferences(conn, user_id)
    columns = await _table_columns(conn, "app", "user_experience_profiles")
    if not columns or "user_id" not in columns:
        return {"ok": False, "error": "app.user_experience_profiles table unavailable"}

    required_columns_for_payload = {
        "temp_unit": payload.temp_unit is not None,
        "tracked_stat_keys": payload.tracked_stat_keys is not None,
        "smart_stat_swap_enabled": payload.smart_stat_swap_enabled is not None,
        "favorite_symptom_codes": payload.favorite_symptom_codes is not None,
        "lunar_sensitivity_declared": payload.lunar_sensitivity_declared is not None,
    }
    missing_columns = [
        column
        for column, requested in required_columns_for_payload.items()
        if requested and column not in columns
    ]
    if missing_columns:
        return {
            "ok": False,
            "error": "missing_profile_preference_columns",
            "missing_columns": missing_columns,
        }

    now = datetime.now(timezone.utc)
    onboarding_completed = (
        bool(payload.onboarding_completed)
        if payload.onboarding_completed is not None
        else bool(current.get("onboarding_completed"))
    )
    onboarding_completed_at = current.get("onboarding_completed_at")
    if payload.onboarding_completed is False:
        onboarding_completed_at = None
    elif onboarding_completed:
        onboarding_completed_at = onboarding_completed_at or now

    healthkit_requested_at = current.get("healthkit_requested_at")
    if payload.healthkit_requested:
        healthkit_requested_at = now

    values_by_column: Dict[str, Any] = {
        "user_id": user_id,
        "mode": _normalize_experience_mode(payload.mode, fallback=str(current.get("mode") or defaults["mode"])),
        "guide": _normalize_guide_type(payload.guide, fallback=str(current.get("guide") or defaults["guide"])),
        "tone": _normalize_tone_style(payload.tone, fallback=str(current.get("tone") or defaults["tone"])),
        "temp_unit": _normalize_temp_unit(payload.temp_unit, fallback=str(current.get("temp_unit") or _DEFAULT_TEMP_UNIT)),
        "tracked_stat_keys": _normalize_tracked_stat_keys(
            payload.tracked_stat_keys if payload.tracked_stat_keys is not None else current.get("tracked_stat_keys")
        ),
        "smart_stat_swap_enabled": (
            bool(payload.smart_stat_swap_enabled)
            if payload.smart_stat_swap_enabled is not None
            else bool(current.get("smart_stat_swap_enabled", defaults["smart_stat_swap_enabled"]))
        ),
        "favorite_symptom_codes": _normalize_favorite_symptom_codes(
            payload.favorite_symptom_codes
            if payload.favorite_symptom_codes is not None
            else current.get("favorite_symptom_codes")
        ),
        "lunar_sensitivity_declared": (
            bool(payload.lunar_sensitivity_declared)
            if payload.lunar_sensitivity_declared is not None
            else bool(current.get("lunar_sensitivity_declared"))
        ),
        "onboarding_step": _normalize_onboarding_step(
            payload.onboarding_step,
            fallback=str(current.get("onboarding_step") or defaults["onboarding_step"]),
        ),
        "onboarding_completed": onboarding_completed,
        "onboarding_completed_at": onboarding_completed_at,
        "healthkit_requested_at": healthkit_requested_at,
        "last_backfill_at": payload.last_backfill_at or current.get("last_backfill_at"),
        "updated_at": now,
    }
    if "created_at" in columns:
        values_by_column["created_at"] = now

    insert_columns = [column for column in values_by_column.keys() if column in columns]
    placeholders = ["%s"] * len(insert_columns)
    update_columns = [column for column in insert_columns if column not in {"user_id", "created_at"}]
    update_set_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    insert_values = [values_by_column[column] for column in insert_columns]

    async with conn.cursor() as cur:
        await cur.execute(
            (
                "insert into app.user_experience_profiles ("
                f"{', '.join(insert_columns)}) "
                "values ("
                f"{', '.join(placeholders)}) "
                "on conflict (user_id) do update set "
                f"{update_set_sql}"
            ),
            insert_values,
            prepare=False,
        )

    return {"ok": True, "preferences": await _fetch_profile_preferences(conn, user_id)}


@router.post("/guide/seen", dependencies=[Depends(require_write_auth)])
async def profile_guide_seen(
    payload: GuideSeenIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    columns = await _table_columns(conn, "app", "user_experience_profiles")
    if not columns or "user_id" not in columns:
        return {"ok": False, "error": "app.user_experience_profiles table unavailable"}

    required_columns = ["guide_last_viewed_signature", "guide_last_viewed_at"]
    missing_columns = [column for column in required_columns if column not in columns]
    if missing_columns:
        return {
            "ok": False,
            "error": "missing_guide_seen_columns",
            "missing_columns": missing_columns,
        }

    now = datetime.now(timezone.utc)
    signature = str(payload.signature or "").strip()
    viewed_at = payload.viewed_at or now
    values_by_column: Dict[str, Any] = {
        "user_id": user_id,
        "guide_last_viewed_signature": signature or None,
        "guide_last_viewed_at": viewed_at if signature else None,
        "updated_at": now,
    }
    if "created_at" in columns:
        values_by_column["created_at"] = now

    insert_columns = [column for column in values_by_column.keys() if column in columns]
    placeholders = ["%s"] * len(insert_columns)
    update_columns = [column for column in insert_columns if column not in {"user_id", "created_at"}]
    update_set_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    insert_values = [values_by_column[column] for column in insert_columns]

    async with conn.cursor() as cur:
        await cur.execute(
            (
                "insert into app.user_experience_profiles ("
                f"{', '.join(insert_columns)}) "
                "values ("
                f"{', '.join(placeholders)}) "
                "on conflict (user_id) do update set "
                f"{update_set_sql}"
            ),
            insert_values,
            prepare=False,
        )

    return {
        "ok": True,
        "guide_state": {
            "signature": signature,
            "has_unseen": False,
            "last_viewed_signature": signature or None,
            "last_viewed_at": viewed_at.astimezone(timezone.utc).isoformat() if signature else None,
        },
    }


class ProfileTagsIn(BaseModel):
    tags: List[str] = Field(default_factory=list)


class NotificationPreferencesIn(BaseModel):
    enabled: bool = False
    signal_alerts_enabled: bool = True
    local_condition_alerts_enabled: bool = True
    personalized_gauge_alerts_enabled: bool = True
    symptom_followups_enabled: bool = False
    symptom_followup_push_enabled: bool = False
    symptom_followup_cadence: str = "balanced"
    symptom_followup_states: List[str] = Field(default_factory=lambda: ["new", "ongoing", "improving", "worse"])
    symptom_followup_symptom_codes: List[str] = Field(default_factory=list)
    daily_checkins_enabled: bool = False
    daily_checkin_push_enabled: bool = False
    daily_checkin_cadence: str = "balanced"
    daily_checkin_reminder_time: str = "20:00"
    quiet_hours_enabled: bool = False
    quiet_start: str = "22:00"
    quiet_end: str = "08:00"
    time_zone: str = "UTC"
    sensitivity: str = "normal"
    families: Dict[str, bool] = Field(default_factory=lambda: dict(_NOTIFICATION_FAMILY_DEFAULTS))


class PushTokenUpsertIn(BaseModel):
    platform: str = "ios"
    device_token: str
    app_version: Optional[str] = None
    environment: str = "prod"
    enabled: bool = True


class PushTokenDisableIn(BaseModel):
    device_token: str


async def _fetch_catalog_rows(conn) -> List[Dict[str, Any]]:
    cols = await _table_columns(conn, "dim", "user_tag_catalog")
    if not cols:
        return []
    key_col = _pick(cols, ["tag_key", "key", "code", "slug", "id"])
    label_col = _pick(cols, ["label", "name", "title"])
    desc_col = _pick(cols, ["description", "details", "help_text"])
    section_col = _pick(cols, ["section", "tag_type", "category", "group_name", "group"])
    active_col = _pick(cols, ["is_active", "active", "enabled"])
    if not key_col:
        return []

    select_parts = [f"{key_col} as tag_key"]
    select_parts.append(f"{label_col} as label" if label_col else "null::text as label")
    select_parts.append(f"{desc_col} as description" if desc_col else "null::text as description")
    select_parts.append(f"{section_col} as section" if section_col else "null::text as section")
    if active_col:
        select_parts.append(f"coalesce({active_col}, true) as is_active")
    else:
        select_parts.append("true as is_active")

    where_sql = f"where coalesce({active_col}, true)" if active_col else ""
    sql = (
        f"select {', '.join(select_parts)} "
        f"from dim.user_tag_catalog "
        f"{where_sql} "
        f"order by section nulls last, label nulls last, tag_key"
    )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, prepare=False)
        rows = await cur.fetchall()
    deduped: Dict[str, Dict[str, Any]] = {}
    for raw_row in rows or []:
        row = dict(raw_row or {})
        canonical_key = canonicalize_tag_key(row.get("tag_key"))
        if not canonical_key:
            continue
        row["tag_key"] = canonical_key
        existing = deduped.get(canonical_key)
        raw_matches_canonical = str(raw_row.get("tag_key") or "").strip().lower() == canonical_key
        if existing is None or raw_matches_canonical:
            deduped[canonical_key] = row
    return list(deduped.values())


@router.get("/tags/catalog", dependencies=[Depends(require_read_auth)])
async def profile_tags_catalog(conn=Depends(get_db)):
    rows = await _fetch_catalog_rows(conn)
    return {"ok": True, "items": rows}


@router.get("/tags", dependencies=[Depends(require_read_auth)])
async def profile_tags(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    cols = await _table_columns(conn, "app", "user_tags")
    if not cols:
        return {"ok": True, "tags": []}

    user_col = _pick(cols, ["user_id"])
    tag_col = _pick(cols, ["tag_key", "key", "tag", "code", "tag_id"])
    active_col = _pick(cols, ["is_active", "active", "enabled", "selected"])
    if not user_col or not tag_col:
        return {"ok": True, "tags": []}

    where_sql = f"where {user_col} = %s"
    if active_col:
        where_sql += f" and coalesce({active_col}, true)"
    sql = f"select {tag_col} as tag_key from app.user_tags {where_sql} order by {tag_col}"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id,), prepare=False)
        rows = await cur.fetchall()

    tags = canonicalize_tag_keys([r.get("tag_key") for r in rows or [] if r.get("tag_key")])
    return {"ok": True, "tags": tags}


@router.put("/tags", dependencies=[Depends(require_write_auth)])
async def profile_tags_upsert(
    payload: ProfileTagsIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    cols = await _table_columns(conn, "app", "user_tags")
    if not cols:
        return {"ok": False, "error": "app.user_tags table unavailable"}

    user_col = _pick(cols, ["user_id"])
    tag_col = _pick(cols, ["tag_key", "key", "tag", "code", "tag_id"])
    active_col = _pick(cols, ["is_active", "active", "enabled", "selected"])
    created_col = _pick(cols, ["created_at"])
    updated_col = _pick(cols, ["updated_at"])
    if not user_col or not tag_col:
        return {"ok": False, "error": "app.user_tags schema unsupported"}

    cleaned = canonicalize_tag_keys(payload.tags or [])

    async with conn.cursor() as cur:
        await cur.execute(f"delete from app.user_tags where {user_col} = %s", (user_id,), prepare=False)
        now = datetime.now(timezone.utc)
        for tag in cleaned:
            data: Dict[str, Any] = {user_col: user_id, tag_col: tag}
            if active_col:
                data[active_col] = True
            if created_col:
                data[created_col] = now
            if updated_col:
                data[updated_col] = now

            cols_sql = ", ".join(data.keys())
            vals_sql = ", ".join(["%s"] * len(data))
            await cur.execute(
                f"insert into app.user_tags ({cols_sql}) values ({vals_sql})",
                list(data.values()),
                prepare=False,
            )

    return {"ok": True, "tags": cleaned}


async def _fetch_notification_preferences(conn, user_id: str) -> Dict[str, Any]:
    defaults = _default_notification_preferences()
    columns = await _table_columns(conn, "app", "user_notification_preferences")
    if not columns:
        return defaults

    select_parts = [
        _notification_pref_select(columns, "enabled", "false"),
        _notification_pref_select(columns, "signal_alerts_enabled", "true"),
        _notification_pref_select(columns, "local_condition_alerts_enabled", "true"),
        _notification_pref_select(columns, "personalized_gauge_alerts_enabled", "true"),
        _notification_pref_select(columns, "symptom_followups_enabled", "false"),
        _notification_pref_select(columns, "symptom_followup_push_enabled", "false"),
        _notification_pref_select(columns, "symptom_followup_cadence", "'balanced'::text"),
        _notification_pref_select(columns, "symptom_followup_states", "array['new','ongoing','improving','worse']::text[]"),
        _notification_pref_select(columns, "symptom_followup_symptom_codes", "array[]::text[]"),
        _notification_pref_select(columns, "daily_checkins_enabled", "false"),
        _notification_pref_select(columns, "daily_checkin_push_enabled", "false"),
        _notification_pref_select(columns, "daily_checkin_cadence", "'balanced'::text"),
        "to_char(daily_checkin_reminder_time, 'HH24:MI') as daily_checkin_reminder_time" if "daily_checkin_reminder_time" in columns else f"'{defaults['daily_checkin_reminder_time']}'::text as daily_checkin_reminder_time",
        _notification_pref_select(columns, "quiet_hours_enabled", "false"),
        "to_char(quiet_start, 'HH24:MI') as quiet_start" if "quiet_start" in columns else f"'{defaults['quiet_start']}'::text as quiet_start",
        "to_char(quiet_end, 'HH24:MI') as quiet_end" if "quiet_end" in columns else f"'{defaults['quiet_end']}'::text as quiet_end",
        _notification_pref_select(columns, "time_zone", "'UTC'::text"),
        _notification_pref_select(columns, "sensitivity", "'normal'::text"),
        _notification_pref_select(columns, "families", "'{}'::jsonb"),
    ]

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            (
                f"select {', '.join(select_parts)} "
                "from app.user_notification_preferences "
                "where user_id = %s "
                "limit 1"
            ),
            (user_id,),
            prepare=False,
        )
        row = await cur.fetchone()

    if not row:
        return defaults

    return {
        "enabled": bool(row.get("enabled")),
        "signal_alerts_enabled": bool(row.get("signal_alerts_enabled")),
        "local_condition_alerts_enabled": bool(row.get("local_condition_alerts_enabled")),
        "personalized_gauge_alerts_enabled": bool(row.get("personalized_gauge_alerts_enabled")),
        "symptom_followups_enabled": bool(row.get("symptom_followups_enabled")),
        "symptom_followup_push_enabled": bool(row.get("symptom_followup_push_enabled")),
        "symptom_followup_cadence": _normalize_followup_cadence(row.get("symptom_followup_cadence")),
        "symptom_followup_states": _normalize_followup_states(row.get("symptom_followup_states")),
        "symptom_followup_symptom_codes": _normalize_followup_codes(row.get("symptom_followup_symptom_codes")),
        "daily_checkins_enabled": bool(row.get("daily_checkins_enabled")),
        "daily_checkin_push_enabled": bool(row.get("daily_checkin_push_enabled")),
        "daily_checkin_cadence": _normalize_daily_checkin_cadence(row.get("daily_checkin_cadence")),
        "daily_checkin_reminder_time": _normalize_clock_hhmm(row.get("daily_checkin_reminder_time"), fallback=defaults["daily_checkin_reminder_time"]),
        "quiet_hours_enabled": bool(row.get("quiet_hours_enabled")),
        "quiet_start": _normalize_clock_hhmm(row.get("quiet_start"), fallback=defaults["quiet_start"]),
        "quiet_end": _normalize_clock_hhmm(row.get("quiet_end"), fallback=defaults["quiet_end"]),
        "time_zone": _normalize_time_zone(row.get("time_zone")),
        "sensitivity": _normalize_notification_sensitivity(row.get("sensitivity")),
        "families": _normalize_notification_families(row.get("families")),
    }


@router.get("/notifications", dependencies=[Depends(require_read_auth)])
async def profile_notifications(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    return {"ok": True, "preferences": await _fetch_notification_preferences(conn, user_id)}


@router.put("/notifications", dependencies=[Depends(require_write_auth)])
async def profile_notifications_upsert(
    payload: NotificationPreferencesIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    now = datetime.now(timezone.utc)
    quiet_start = _normalize_clock_hhmm(payload.quiet_start, fallback="22:00")
    quiet_end = _normalize_clock_hhmm(payload.quiet_end, fallback="08:00")
    daily_checkin_reminder_time = _normalize_clock_hhmm(payload.daily_checkin_reminder_time, fallback="20:00")
    time_zone_name = _normalize_time_zone(payload.time_zone)
    sensitivity = _normalize_notification_sensitivity(payload.sensitivity)
    families = _normalize_notification_families(payload.families)
    families["symptom_followups"] = bool(payload.symptom_followups_enabled)
    families["daily_checkins"] = bool(payload.daily_checkins_enabled)
    followup_cadence = _normalize_followup_cadence(payload.symptom_followup_cadence)
    followup_states = _normalize_followup_states(payload.symptom_followup_states)
    followup_codes = _normalize_followup_codes(payload.symptom_followup_symptom_codes)
    daily_checkin_cadence = _normalize_daily_checkin_cadence(payload.daily_checkin_cadence)
    columns = await _table_columns(conn, "app", "user_notification_preferences")
    if not columns or "user_id" not in columns:
        return {"ok": False, "error": "app.user_notification_preferences table unavailable"}

    values_by_column: Dict[str, Any] = {
        "user_id": user_id,
        "enabled": bool(payload.enabled),
        "signal_alerts_enabled": bool(payload.signal_alerts_enabled),
        "local_condition_alerts_enabled": bool(payload.local_condition_alerts_enabled),
        "personalized_gauge_alerts_enabled": bool(payload.personalized_gauge_alerts_enabled),
        "quiet_hours_enabled": bool(payload.quiet_hours_enabled),
        "quiet_start": quiet_start,
        "quiet_end": quiet_end,
        "daily_checkin_reminder_time": daily_checkin_reminder_time,
        "time_zone": time_zone_name,
        "sensitivity": sensitivity,
        "families": json.dumps(families, separators=(",", ":"), sort_keys=True),
    }
    if "symptom_followups_enabled" in columns:
        values_by_column["symptom_followups_enabled"] = bool(payload.symptom_followups_enabled)
    if "symptom_followup_push_enabled" in columns:
        values_by_column["symptom_followup_push_enabled"] = bool(payload.symptom_followup_push_enabled)
    if "symptom_followup_cadence" in columns:
        values_by_column["symptom_followup_cadence"] = followup_cadence
    if "symptom_followup_states" in columns:
        values_by_column["symptom_followup_states"] = followup_states
    if "symptom_followup_symptom_codes" in columns:
        values_by_column["symptom_followup_symptom_codes"] = followup_codes
    if "daily_checkins_enabled" in columns:
        values_by_column["daily_checkins_enabled"] = bool(payload.daily_checkins_enabled)
    if "daily_checkin_push_enabled" in columns:
        values_by_column["daily_checkin_push_enabled"] = bool(payload.daily_checkin_push_enabled)
    if "daily_checkin_cadence" in columns:
        values_by_column["daily_checkin_cadence"] = daily_checkin_cadence
    if "created_at" in columns:
        values_by_column["created_at"] = now
    if "updated_at" in columns:
        values_by_column["updated_at"] = now

    insert_columns = [column for column in values_by_column.keys() if column in columns]
    placeholders = [_notification_pref_placeholder(column) for column in insert_columns]
    update_columns = [column for column in insert_columns if column not in {"user_id", "created_at"}]
    update_set_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    insert_values = [values_by_column[column] for column in insert_columns]

    async with conn.cursor() as cur:
        await cur.execute(
            (
                "insert into app.user_notification_preferences ("
                f"{', '.join(insert_columns)}) "
                "values ("
                f"{', '.join(placeholders)}) "
                "on conflict (user_id) do update set "
                f"{update_set_sql}"
            ),
            insert_values,
            prepare=False,
        )

    return {"ok": True, "preferences": await _fetch_notification_preferences(conn, user_id)}


@router.post("/push-tokens", dependencies=[Depends(require_write_auth)])
async def profile_push_token_upsert(
    payload: PushTokenUpsertIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    platform = str(payload.platform or "ios").strip().lower() or "ios"
    if platform != "ios":
        raise HTTPException(status_code=400, detail="unsupported push platform")
    environment = str(payload.environment or "prod").strip().lower() or "prod"
    if environment not in {"dev", "prod"}:
        raise HTTPException(status_code=400, detail="invalid push environment")

    device_token = _normalize_device_token(payload.device_token)
    now = datetime.now(timezone.utc)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            update app.user_push_tokens
               set enabled = false,
                   updated_at = %s
             where device_token = %s
               and user_id <> %s
            """,
            (now, device_token, user_id),
            prepare=False,
        )
        await cur.execute(
            """
            insert into app.user_push_tokens (
                user_id,
                platform,
                device_token,
                app_version,
                environment,
                enabled,
                created_at,
                updated_at,
                last_seen_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (user_id, device_token) do update
               set platform = excluded.platform,
                   app_version = excluded.app_version,
                   environment = excluded.environment,
                   enabled = excluded.enabled,
                   updated_at = excluded.updated_at,
                   last_seen_at = excluded.last_seen_at
            returning id,
                      user_id,
                      platform,
                      device_token,
                      app_version,
                      environment,
                      enabled,
                      created_at,
                      updated_at,
                      last_seen_at
            """,
            (
                user_id,
                platform,
                device_token,
                (payload.app_version or "").strip() or None,
                environment,
                bool(payload.enabled),
                now,
                now,
                now,
            ),
            prepare=False,
        )
        row = await cur.fetchone()

    return {"ok": True, "token": row}


@router.post("/push-tokens/disable", dependencies=[Depends(require_write_auth)])
async def profile_push_token_disable(
    payload: PushTokenDisableIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    device_token = _normalize_device_token(payload.device_token)
    now = datetime.now(timezone.utc)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            update app.user_push_tokens
               set enabled = false,
                   updated_at = %s,
                   last_seen_at = %s
             where user_id = %s
               and device_token = %s
            returning id,
                      user_id,
                      platform,
                      device_token,
                      app_version,
                      environment,
                      enabled,
                      created_at,
                      updated_at,
                      last_seen_at
            """,
            (now, now, user_id, device_token),
            prepare=False,
        )
        row = await cur.fetchone()

    return {"ok": True, "disabled": row is not None, "token": row}
