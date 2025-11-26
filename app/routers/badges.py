# app/routers/badges.py
#
# Lightweight badge endpoints for KP and Schumann F1.
# This reuses the same underlying tables used by the summary router:
# - ext.space_weather
# - marts.schumann_daily

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

import logging
from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/badges", tags=["badges"])


async def _latest_kp_current(conn) -> Optional[float]:
    """
    Fetch the latest KP index from ext.space_weather.

    Mirrors the logic in summary._fetch_current_space_weather for kp_current.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select kp_index as kp_current
            from ext.space_weather
            where ts_utc <= now() and kp_index is not null
            order by ts_utc desc
            limit 1
            """
        )
        row = await cur.fetchone() or {}

    value = row.get("kp_current")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _latest_schumann_f1(conn) -> Dict[str, Optional[Any]]:
    """
    Fetch the most recent Schumann F1 average from marts.schumann_daily.

    Mirrors the station/ordering logic from summary._fetch_schumann_row:
    prefers 'tomsk' over 'cumiana' for the latest available day.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select station_id, day, f1_avg_hz
            from marts.schumann_daily
            where station_id in ('tomsk','cumiana') and day <= current_date
            order by day desc,
                     case when station_id='tomsk' then 0
                          when station_id='cumiana' then 1
                          else 2 end
            limit 1
            """
        )
        row = await cur.fetchone() or {}

    station = row.get("station_id")
    day_val = row.get("day")
    f1 = row.get("f1_avg_hz")

    if isinstance(day_val, datetime):
        day_iso = day_val.date().isoformat()
    elif isinstance(day_val, date):
        day_iso = day_val.isoformat()
    else:
        day_iso = None

    try:
        f1_val = float(f1) if f1 is not None else None
    except (TypeError, ValueError):
        f1_val = None

    return {
        "value": f1_val,
        "station": station,
        "day": day_iso,
    }


@router.get("/kp_schumann")
async def kp_schumann_badge(conn=Depends(get_db)):
    """
    Compact badge-friendly endpoint exposing current KP and Schumann F1.

    Response shape:

    {
      "ok": true,
      "kp": {
        "value": 3.67
      },
      "schumann_f1": {
        "value": 7.83,
        "station": "tomsk",
        "day": "2025-11-26"
      },
      "error": null
    }
    """
    try:
        kp_current = await _latest_kp_current(conn)
        sch = await _latest_schumann_f1(conn)

        payload: Dict[str, Any] = {
            "kp": {"value": kp_current} if kp_current is not None else None,
            "schumann_f1": sch if sch.get("value") is not None else None,
        }

        return {
            "ok": True,
            **payload,
            "error": None,
        }
    except Exception as exc:
        # Defensive logging to help diagnose badge issues without crashing the app
        logger.exception("kp_schumann_badge failed: %s", exc)
        return {
            "ok": False,
            "kp": None,
            "schumann_f1": None,
            "error": str(exc) or exc.__class__.__name__,
        }