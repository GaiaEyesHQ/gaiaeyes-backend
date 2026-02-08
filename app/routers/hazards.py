from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db


router = APIRouter(prefix="/v1/hazards", tags=["hazards"])


def _iso(ts):
    if ts is None:
        return None
    return ts.isoformat().replace("+00:00", "Z")


@router.get("/gdacs")
async def gdacs_alerts(conn=Depends(get_db)):
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select code, title, url, published_raw, published_at, details
                from ext.gdacs_alerts
                order by coalesce(published_at, ingested_at) desc
                limit 50
                """,
                prepare=False,
            )
            rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"gdacs_alerts failed: {exc}"}

    alerts = []
    for row in rows:
        alerts.append(
            {
                "code": row.get("code"),
                "title": row.get("title"),
                "url": row.get("url"),
                "published_raw": row.get("published_raw"),
                "published_at": _iso(row.get("published_at")),
                "details": row.get("details"),
            }
        )

    return {"ok": True, "alerts": alerts}


@router.get("/gdacs/full")
async def gdacs_full(
    since_hours: int = 96,
    kinds: Optional[str] = None,
    limit: int = 100,
    conn=Depends(get_db),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=since_hours)

    # Build filters dynamically; keep parameter order stable
    where_clauses: List[str] = [
        "source = 'gdacs'",
        "coalesce(started_at, ingested_at) >= %s",
    ]
    params: List[object] = [since]

    # Optional kind filter: ANY(%s) with a text[]
    if kinds:
        kind_list = [k.strip() for k in kinds.split(",") if k.strip()]
        where_clauses.append("kind = ANY(%s)")
        params.append(kind_list)

    where_sql = " AND ".join(where_clauses)

    sql = f"""
        select id, source, kind, title, location, severity,
               started_at, ended_at, payload, ingested_at
        from ext.global_hazards
        where {where_sql}
        order by coalesce(started_at, ingested_at) desc
        limit %s
    """
    params.append(limit)

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params, prepare=False)
            rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"gdacs_full failed: {exc}"}

    items = []
    for r in rows:
        payload = r.get("payload") or {}
        url = payload.get("url") or payload.get("link") or payload.get("detail_url")

        # Optional extra fields if the bot populates them
        details = payload.get("details") or payload.get("summary")
        lat = payload.get("lat")
        lon = payload.get("lon")

        items.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "url": url,
                "source": r.get("source"),
                "kind": r.get("kind"),
                "location": r.get("location"),
                "severity": r.get("severity"),
                "started_at": (_iso(r.get("started_at")) if r.get("started_at") else None),
                "ended_at": (_iso(r.get("ended_at")) if r.get("ended_at") else None),
                "ingested_at": (_iso(r.get("ingested_at")) if r.get("ingested_at") else None),
                "details": details,
                "lat": lat,
                "lon": lon,
            }
        )

    return {
        "ok": True,
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "items": items,
    }


@router.get("/brief")
async def hazards_brief(conn=Depends(get_db)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=48)

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select source, kind, title, location, severity,
                       started_at, ended_at, payload
                from ext.global_hazards
                where coalesce(started_at, ingested_at) >= %s
                order by coalesce(started_at, ingested_at) desc
                limit 30
                """,
                (since,),
                prepare=False,
            )
            rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"hazards_brief failed: {exc}"}

    items = []
    for row in rows:
        payload = row.get("payload") or {}
        url = payload.get("url") or payload.get("link") or payload.get("detail_url")

        items.append(
            {
                "title": row.get("title"),
                "url": url,
                "source": row.get("source"),
                "kind": row.get("kind"),
                "location": row.get("location"),
                "severity": row.get("severity"),
                "started_at": _iso(row.get("started_at")),
            }
        )

    return {
        "ok": True,
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "items": items,
    }
