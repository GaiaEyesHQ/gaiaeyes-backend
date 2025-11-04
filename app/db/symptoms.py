from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, List, Optional
from uuid import UUID

from psycopg.rows import dict_row

UTC = timezone.utc


def _normalize_ts(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _serialize_ts(ts: Optional[datetime]) -> Optional[str]:
    value = _normalize_ts(ts)
    return value.isoformat() if value else None


def _serialize_uuid(value: UUID | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return value


def _to_float(value: Decimal | float | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _prepare_tags(tags: Optional[Iterable[str]]) -> Optional[List[str]]:
    if tags is None:
        return None
    tags_list = [str(t) for t in tags if t]
    return tags_list or None


async def insert_symptom_event(
    conn,
    user_id: str,
    *,
    symptom_code: str,
    ts_utc: Optional[datetime] = None,
    severity: Optional[int] = None,
    free_text: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
) -> dict:
    sql = """
    insert into raw.user_symptom_events (
        user_id,
        symptom_code,
        ts_utc,
        severity,
        free_text,
        tags
    ) values (%s, %s, coalesce(%s, now()), %s, %s, %s)
    returning id, ts_utc
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            sql,
            (
                user_id,
                symptom_code,
                _normalize_ts(ts_utc),
                severity,
                free_text,
                _prepare_tags(tags),
            ),
        )
        row = await cur.fetchone()

    if not row:
        raise RuntimeError("Failed to insert symptom event")

    return {
        "id": _serialize_uuid(row.get("id")),
        "ts_utc": _serialize_ts(row.get("ts_utc")),
    }


async def fetch_symptom_codes(conn, *, include_inactive: bool = True) -> List[dict]:
    sql = """
    select
        symptom_code,
        label,
        description,
        is_active
    from dim.symptom_codes
    {where_clause}
    order by label
    """

    where_clause = ""
    if not include_inactive:
        where_clause = "where is_active"

    query = sql.format(where_clause=where_clause)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query)
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "symptom_code": row.get("symptom_code"),
                "label": row.get("label"),
                "description": row.get("description"),
                "is_active": bool(row.get("is_active", False)),
            }
        )
    return result


async def fetch_symptoms_today(conn, user_id: str) -> List[dict]:
    sql = """
    select
        symptom_code,
        ts_utc,
        severity,
        free_text
    from raw.user_symptom_events
    where user_id = %s
      and (ts_utc at time zone 'utc')::date = (now() at time zone 'utc')::date
    order by ts_utc desc
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id,))
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "symptom_code": row.get("symptom_code"),
                "ts_utc": _serialize_ts(row.get("ts_utc")),
                "severity": row.get("severity"),
                "free_text": row.get("free_text"),
            }
        )
    return result


async def fetch_daily_summary(conn, user_id: str, days: int) -> List[dict]:
    sql = """
    select
        (ts_utc at time zone 'utc')::date as day,
        symptom_code,
        count(*) as events,
        avg(severity) filter (where severity is not null) as mean_severity,
        max(ts_utc) as last_ts
    from raw.user_symptom_events
    where user_id = %s
      and ts_utc >= (now() at time zone 'utc') - (%s * interval '1 day')
    group by 1, 2
    order by day desc, symptom_code
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, days))
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        day_value = row.get("day")
        result.append(
            {
                "day": day_value.isoformat() if day_value else None,
                "symptom_code": row.get("symptom_code"),
                "events": int(row.get("events") or 0),
                "mean_severity": _to_float(row.get("mean_severity")),
                "last_ts": _serialize_ts(row.get("last_ts")),
            }
        )
    return result


async def fetch_diagnostics(conn, user_id: str, days: int) -> List[dict]:
    sql = """
    select
        symptom_code,
        count(*) as events,
        max(ts_utc) as last_ts
    from raw.user_symptom_events
    where user_id = %s
      and ts_utc >= (now() at time zone 'utc') - (%s * interval '1 day')
    group by 1
    order by symptom_code
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, days))
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "symptom_code": row.get("symptom_code"),
                "events": int(row.get("events") or 0),
                "last_ts": _serialize_ts(row.get("last_ts")),
            }
        )
    return result
