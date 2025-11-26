from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
                select code, title, url, published_raw, published_at
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
            }
        )

    return {"ok": True, "alerts": alerts}


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
