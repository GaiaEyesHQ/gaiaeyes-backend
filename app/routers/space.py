# app/routers/space.py

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db

import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

GOES_XRS_URL = os.getenv(
    "GOES_XRS_URL",
    "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
)

router = APIRouter(prefix="/v1/space", tags=["space"])


def _iso(ts) -> Optional[str]:
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat()
    return None


def _flare_class_from_flux(flux: float) -> Optional[str]:
    """
    Convert GOES X-ray flux (W/m^2) into a flare class string like C3.4, M1.2, X1.0.
    Very rough bands:
      A: 1e-8–1e-7
      B: 1e-7–1e-6
      C: 1e-6–1e-5
      M: 1e-5–1e-4
      X: >=1e-4
    """
    if flux is None or flux <= 0:
        return None
    bands = [
        ("X", 1e-4),
        ("M", 1e-5),
        ("C", 1e-6),
        ("B", 1e-7),
        ("A", 1e-8),
    ]
    for letter, base in bands:
        if flux >= base:
            factor = flux / base
            # One decimal place to match typical notation (e.g., C3.4)
            return f"{letter}{factor:.1f}"
    return None


def _goes_flares_summary() -> Dict[str, Any]:
    """
    Summarize GOES XRS long-channel (0.1–0.8 nm) flux over the last day.

    Returns:
      {"max_class": "C3.4", "max_flux": 3.4e-06, "band": "C"} or {} if unavailable.
    """
    if not GOES_XRS_URL:
        return {}

    try:
        req = Request(GOES_XRS_URL, headers={"User-Agent": "GaiaEyes/space-flares"})
        with urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except (HTTPError, URLError, ValueError, json.JSONDecodeError):
        return {}

    max_flux = 0.0
    for row in data:
        # SWPC GOES XRS 1-day JSON typically has:
        #   "time_tag", "flux", "energy" (e.g., "0.1-0.8 nm")
        energy = str(row.get("energy") or row.get("energy_range") or "").lower()
        if "0.1-0.8" not in energy:
            continue
        try:
            flux = float(row.get("flux") or 0.0)
        except (TypeError, ValueError):
            continue
        if flux > max_flux:
            max_flux = flux

    cls = _flare_class_from_flux(max_flux)
    if not cls:
        return {}
    return {"max_class": cls, "max_flux": max_flux, "band": cls[0]}


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

    # Incorporate GOES XRS summary: if GOES peak class exists and is stronger, prefer it.
    goes = _goes_flares_summary()
    goes_class = goes.get("max_class")
    if goes_class:
        score_goes = class_key(goes_class)
        if score_goes > best_score:
            max_class = goes_class
            best_score = score_goes
            # Ensure its band is represented in the histogram
            band = goes_class[0]
            bands[band] = bands.get(band, 0) + 1

    # If there were no DONKI rows but GOES had a class, we still want a valid summary
    if total == 0 and goes_class:
        total = 1  # treat as at least one flare-like event in last day

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