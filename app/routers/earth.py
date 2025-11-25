from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db


router = APIRouter(prefix="/v1")


def _iso(ts):
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat()
    if isinstance(ts, date):
        return datetime.combine(ts, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    return None


@router.get("/earth/schumann/latest")
async def schumann_latest(conn=Depends(get_db)):
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select ts_utc, generated_at, f0, f1, f2, f3, f4, f5
                from marts.daily_features
                order by coalesce(generated_at, ts_utc) desc
                limit 1
                """,
                prepare=False,
            )
            row = await cur.fetchone()
    except Exception as exc:  # pragma: no cover - defensive envelope
        return {"ok": False, "error": f"schumann_latest failed: {exc}"}

    if not row:
        return {"ok": True, "generated_at": None, "harmonics": {}}

    harmonics = {}
    for i in range(6):
        key = f"f{i}"
        harmonics[key] = row.get(key)

    return {
        "ok": True,
        "generated_at": _iso(row.get("generated_at") or row.get("ts_utc")),
        "harmonics": harmonics,
    }
