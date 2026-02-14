from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from app.db import get_db
from app.security.auth import require_read_auth, require_write_auth


router = APIRouter(prefix="/v1/profile", tags=["profile"])


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


class ProfileLocationIn(BaseModel):
    zip: Optional[str] = Field(default=None)
    lat: Optional[float] = Field(default=None)
    lon: Optional[float] = Field(default=None)
    use_gps: Optional[bool] = Field(default=None)
    local_insights_enabled: Optional[bool] = Field(default=None)


def _normalize_zip(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = "".join(ch for ch in value.strip() if ch.isdigit())
    if not cleaned:
        return None
    return cleaned[:10]


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


class ProfileTagsIn(BaseModel):
    tags: List[str] = Field(default_factory=list)


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
    return rows or []


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

    tags = [r.get("tag_key") for r in rows or [] if r.get("tag_key")]
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

    cleaned: List[str] = []
    for tag in payload.tags or []:
        value = str(tag).strip()
        if value and value not in cleaned:
            cleaned.append(value)

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
