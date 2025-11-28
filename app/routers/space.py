# app/routers/space.py

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db

router = APIRouter(prefix="/v1/space", tags=["space"])


def _iso(ts) -> Optional[str]:
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat()
    return None


@router.get("/flares")
async def space_flares(conn = Depends(get_db)):
    """
    Summary of solar flares over the last 24 hours using ext.donki_event.

    Returns shape:
      {
        "ok": true,
        "data": {
          "max_24h": "C3.4",
          "total_24h": 7,
          "bands_24h": {"C": 4, "M": 3, "X": 0}
        }
      }
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)

    rows: List[Dict[str, Any]] = []
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")
            await cur.execute(
                """
                select event_type, start_time, peak_time, end_time, class
                from ext.donki_event
                where (peak_time >= %s or (peak_time is null and start_time >= %s))
                  and lower(event_type) like 'flare%%'
                order by coalesce(peak_time, start_time) desc
                """,
                (window_start, window_start),
            )
            rows = await cur.fetchall() or []
    except Exception as exc:
        return {"ok": False, "data": None, "error": f"space_flares query failed: {exc}"}

    if not rows:
        return {"ok": True, "data": {"max_24h": None, "total_24h": 0, "bands_24h": {}}}

    total = len(rows)
    bands: Dict[str, int] = {}
    max_class = None

    def class_key(cls: str) -> float:
        # Rough ordering: X > M > C > B > A; keep decimals
        if not cls:
            return 0.0
        cls = cls.strip().upper()
        if cls[0] == "X":
            base = 40
        elif cls[0] == "M":
            base = 30
        elif cls[0] == "C":
            base = 20
        elif cls[0] == "B":
            base = 10
        else:
            base = 0
        try:
            val = float(cls[1:]) if len(cls) > 1 else 0.0
        except ValueError:
            val = 0.0
        return base + val

    best_score = -1.0
    for row in rows:
        cls = (row.get("class") or "").strip().upper()
        if cls:
            band = cls[0]
            bands[band] = bands.get(band, 0) + 1
            score = class_key(cls)
            if score > best_score:
                best_score = score
                max_class = cls

    return {
        "ok": True,
        "data": {
            "max_24h": max_class,
            "total_24h": total,
            "bands_24h": bands,
        },
        "error": None,
    }


@router.get("/history")
async def space_history(conn = Depends(get_db), hours: int = 24):
    """
    Time-series for Kp, SW speed, and Bz over the last N hours (default 24),
    derived from ext.space_weather.

    Returns shape:
      {
        "ok": true,
        "data": {
          "series24": {
            "kp": [[ts1, val1], ...],
            "sw": [[ts1, val1], ...],
            "bz": [[ts1, val1], ...]
          }
        }
      }
    """
    hours = max(1, min(hours, 72))  # keep it reasonable
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours)

    rows: List[Dict[str, Any]] = []
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")
            await cur.execute(
                """
                select ts_utc, kp_index, bz_nt, sw_speed_kms
                from ext.space_weather
                where ts_utc >= %s
                order by ts_utc asc
                """,
                (window_start,),
            )
            rows = await cur.fetchall() or []
    except Exception as exc:
        return {"ok": False, "data": None, "error": f"space_history query failed: {exc}"}

    kp_series: List[List[Any]] = []
    sw_series: List[List[Any]] = []
    bz_series: List[List[Any]] = []

    for row in rows:
        ts = _iso(row.get("ts_utc"))
        if not ts:
            continue
        kp = row.get("kp_index")
        bz = row.get("bz_nt")
        sw = row.get("sw_speed_kms")
        if kp is not None:
            kp_series.append([ts, float(kp)])
        if sw is not None:
            sw_series.append([ts, float(sw)])
        if bz is not None:
            bz_series.append([ts, float(bz)])

    return {
        "ok": True,
        "data": {
            "series24": {
              "kp": kp_series,
              "sw": sw_series,
              "bz": bz_series,
            }
        },
        "error": None,
    }