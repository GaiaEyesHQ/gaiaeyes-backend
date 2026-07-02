from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db


router = APIRouter(prefix="/v1")


def _iso_day(day: date | None) -> str | None:
    return day.isoformat() if isinstance(day, date) else None


def _quake_month_item(row: dict) -> dict:
    return {
        "month": _iso_day(row.get("day") or row.get("month")),
        "all_quakes": row.get("all_quakes"),
        "m4p": row.get("m4p"),
        "m5p": row.get("m5p"),
        "m6p": row.get("m6p"),
        "m7p": row.get("m7p"),
    }


def _quake_month_has_counts(item: dict) -> bool:
    for key in ("all_quakes", "m4p", "m5p", "m6p", "m7p"):
        try:
            if int(item.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _merge_monthly_with_daily_rollups(monthly_rows: list[dict], daily_rollup_rows: list[dict]) -> list[dict]:
    items_by_month: dict[str, dict] = {}

    for row in monthly_rows:
        item = _quake_month_item(row)
        month = item.get("month")
        if month:
            items_by_month[month] = item

    for row in daily_rollup_rows:
        item = _quake_month_item(row)
        month = item.get("month")
        if not month:
            continue
        existing = items_by_month.get(month)
        if existing is None or (not _quake_month_has_counts(existing) and _quake_month_has_counts(item)):
            items_by_month[month] = item

    return sorted(items_by_month.values(), key=lambda item: item.get("month") or "", reverse=True)


async def _fetch_rows(conn, sql: str, params: tuple | None = None) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params or (), prepare=False)
        return await cur.fetchall()


@router.get("/quakes/daily")
async def quakes_daily(conn=Depends(get_db)):
    """Return the latest month of daily earthquake aggregates."""

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select day, all_quakes, m4p, m5p, m6p, m7p
                from marts.quakes_daily
                order by day desc
                limit 31
                """,
                prepare=False,
            )
            rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"quakes_daily failed: {exc}"}

    items = [
        {
            "day": _iso_day(row.get("day")),
            "all_quakes": row.get("all_quakes"),
            "m4p": row.get("m4p"),
            "m5p": row.get("m5p"),
            "m6p": row.get("m6p"),
            "m7p": row.get("m7p"),
        }
        for row in rows
    ]

    return {"ok": True, "items": items}


# New endpoint: /quakes/events
@router.get("/quakes/events")
async def quakes_events(
    conn=Depends(get_db),
    min_mag: float = 5.0,
    hours: int = 48,
    limit: int = 200,
):
    """
    Return recent individual earthquake events for detail views.

    This endpoint is intended to back the WordPress "Recent events (M5+)" section.
    It filters by minimum magnitude and a trailing time window (in hours), and
    returns a compact, badge-friendly shape.

    NOTE: This assumes a table ext.earthquakes with at least:
      - origin_time (timestamptz)
      - mag (numeric)
      - depth_km (numeric)
      - lat (numeric)
      - lon (numeric)
      - place (text)
      - src (text)
      - meta (jsonb with optional url)
      - event_id (text)
    """
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select
                    origin_time,
                    mag,
                    depth_km,
                    lat,
                    lon,
                    place,
                    src as source,
                    coalesce(meta->>'url', '') as url,
                    event_id
                from ext.earthquakes
                where origin_time >= now() - (%s || ' hours')::interval
                  and (mag is not null and mag >= %s)
                order by origin_time desc
                limit %s
                """,
                (hours, min_mag, limit),
                prepare=False,
            )
            rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {
            "ok": False,
            "items": [],
            "error": f"quakes_events failed: {exc}",
        }

    items: list[dict] = []
    for row in rows:
        ts = row.get("origin_time")
        ts_iso = ts.isoformat().replace("+00:00", "Z") if hasattr(ts, "isoformat") else None
        items.append(
            {
                "time_utc": ts_iso,
                "mag": row.get("mag"),
                "depth_km": row.get("depth_km"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "place": row.get("place"),
                "source": row.get("source"),
                "url": row.get("url"),
                "id": row.get("event_id"),
            }
        )

    return {"ok": True, "items": items}


@router.get("/quakes/latest")
async def quakes_latest(conn=Depends(get_db)):
    """Return the most recent daily earthquake aggregate."""
    try:
        rows = await _fetch_rows(
            conn,
            """
            select day, all_quakes, m4p, m5p, m6p, m7p
            from marts.quakes_daily
            order by day desc
            limit 1
            """,
        )
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"quakes_latest failed: {exc}"}

    if not rows:
        return {"ok": True, "item": None}

    row = rows[0]
    item = {
        "day": _iso_day(row.get("day")),
        "all_quakes": row.get("all_quakes"),
        "m4p": row.get("m4p"),
        "m5p": row.get("m5p"),
        "m6p": row.get("m6p"),
        "m7p": row.get("m7p"),
    }

    return {"ok": True, "item": item}


@router.get("/quakes/monthly")
async def quakes_monthly(conn=Depends(get_db)):
    """Return the latest 3 years of monthly earthquake aggregates."""

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select month as day, all_quakes, m4p, m5p, m6p, m7p
                from marts.quakes_monthly
                order by month desc
                limit 120
                """,
                prepare=False,
            )
            rows = await cur.fetchall()
            await cur.execute(
                """
                select date_trunc('month', day)::date as month,
                       sum(all_quakes)::int as all_quakes,
                       sum(m4p)::int as m4p,
                       sum(m5p)::int as m5p,
                       sum(m6p)::int as m6p,
                       sum(m7p)::int as m7p
                from marts.quakes_daily
                group by 1
                order by 1 desc
                limit 120
                """,
                prepare=False,
            )
            daily_rollups = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"quakes_monthly failed: {exc}"}

    items = _merge_monthly_with_daily_rollups(rows, daily_rollups)[:120]

    return {"ok": True, "items": items}


@router.get("/quakes/history")
async def quakes_history(conn=Depends(get_db)):
    """Return recent monthly earthquake aggregates (alias for quakes/monthly)."""
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select month as day, all_quakes, m4p, m5p, m6p, m7p
                from marts.quakes_monthly
                order by month desc
                """,
                prepare=False,
            )
            rows = await cur.fetchall()
            await cur.execute(
                """
                select date_trunc('month', day)::date as month,
                       sum(all_quakes)::int as all_quakes,
                       sum(m4p)::int as m4p,
                       sum(m5p)::int as m5p,
                       sum(m6p)::int as m6p,
                       sum(m7p)::int as m7p
                from marts.quakes_daily
                group by 1
                order by 1 desc
                """,
                prepare=False,
            )
            daily_rollups = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"quakes_history failed: {exc}"}

    items = _merge_monthly_with_daily_rollups(rows, daily_rollups)

    return {"ok": True, "items": items}
