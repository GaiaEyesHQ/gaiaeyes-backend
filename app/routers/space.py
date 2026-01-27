from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

def _bucket_geo_risk(r0: Optional[float]) -> str:
    if r0 is None:
        return "unknown"
    # Rough buckets; you can tune thresholds later
    if r0 < 6.6:
        return "elevated"
    if r0 < 8.0:
        return "watch"
    return "low"


def _bucket_kpi(symh_est: Optional[int]) -> str:
    if symh_est is None:
        return "unknown"
    if symh_est >= -20:
        return "quiet"
    if symh_est >= -50:
        return "active"
    if symh_est >= -100:
        return "storm"
    return "strong_storm"


def _dbdt_tag_from_proxy(val: Optional[float]) -> str:
    if val is None:
        return "unknown"
    if val < 0.5:
        return "low"
    if val < 1.5:
        return "moderate"
    return "high"
# app/routers/space.py

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

# Proton flux feed for S-scale
GOES_PROTONS_URL = os.getenv(
    "GOES_PROTONS_URL",
    "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json",
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


# --- Helper functions for S, G, R scales and fetching proton flux ---
def _s_scale_from_pfu(pfu: Optional[float]) -> str:
    """
    Return NOAA S-scale from ≥10 MeV proton flux (pfu).
    S1 ≥ 10, S2 ≥ 100, S3 ≥ 1,000, S4 ≥ 10,000, S5 ≥ 100,000.
    """
    if pfu is None:
        return "S0"
    try:
        v = float(pfu)
    except (TypeError, ValueError):
        return "S0"
    if v >= 100000:
        return "S5"
    if v >= 10000:
        return "S4"
    if v >= 1000:
        return "S3"
    if v >= 100:
        return "S2"
    if v >= 10:
        return "S1"
    return "S0"


def _g_from_kp(kp: Optional[float]) -> int:
    """
    Map Kp to NOAA G-scale integer (0..5).
    """
    if kp is None:
        return 0
    try:
        v = float(kp)
    except (TypeError, ValueError):
        return 0
    if v >= 9:
        return 5
    if v >= 8:
        return 4
    if v >= 7:
        return 3
    if v >= 6:
        return 2
    if v >= 5:
        return 1
    return 0


def _r_from_flare_class(cls: Optional[str]) -> Optional[str]:
    """
    Rough R-scale mapping from a flare class string (e.g., C5.0, M1.2, X3.0).
    R1: M1–M5, R2: M5–X1, R3: X1–X10, R4: X10–X20, R5: ≥X20
    """
    if not cls:
        return None
    s = cls.strip().upper()
    if not s:
        return None
    band = s[0]
    try:
        mag = float(s[1:]) if len(s) > 1 else 0.0
    except ValueError:
        mag = 0.0

    if band == "X":
        if mag >= 20:
            return "R5"
        if mag >= 10:
            return "R4"
        return "R3"  # X1–X9.9
    if band == "M":
        if mag >= 5:
            return "R2"
        if mag >= 1:
            return "R1"
    return None


def _fetch_json(url: str, ua: str = "GaiaEyes/space-alerts", timeout: int = 15) -> Optional[Any]:
    try:
        req = Request(url, headers={"User-Agent": ua})
        with urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except Exception:
        return None


def _latest_pfu_10mev_from_goes() -> Optional[Dict[str, Any]]:
    """
    Pull the latest ≥10 MeV proton flux sample from the GOES integral protons feed.
    Returns {"ts": "...", "pfu": float} or None.
    """
    data = _fetch_json(GOES_PROTONS_URL, ua="GaiaEyes/space-protons")
    if not isinstance(data, list):
        return None
    latest = None
    for row in data:
        # SWPC keys are typically: "time_tag", "proton_flux_gt_10_mev", etc.
        pfu = row.get("proton_flux_gt_10_mev")
        ts = row.get("time_tag")
        try:
            val = float(pfu) if pfu is not None else None
        except (TypeError, ValueError):
            val = None
        if val is None or not ts:
            continue
        # walk forward; keep the most recent valid
        latest = {"ts": ts, "pfu": val}
    return latest


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


# X-ray flux time-series endpoint
@router.get("/xray/history")
async def xray_history(conn = Depends(get_db), hours: int = 24):
    """
    Time-series for GOES X-ray flux over the last N hours (default 24),
    derived from ext.xray_flux.

    Returns shape:
      {
        "ok": true,
        "data": {
          "series": {
            "long": [[ts1, flux1], ...],
            "short": [[ts1, flux1], ...]
          }
        }
      }

    Where "long" corresponds to the 0.1–0.8 nm channel and "short" to the
    0.05–0.4 nm channel, when available.
    """
    hours = max(1, min(hours, 72))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours)

    rows: List[Dict[str, Any]] = []
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")
            await cur.execute(
                """
                select ts_utc, energy_band, flux
                from ext.xray_flux
                where ts_utc >= %s
                order by ts_utc asc
                """,
                (window_start,),
            )
            rows = await cur.fetchall() or []
    except Exception as exc:
        return {"ok": False, "data": None, "error": f"xray_history query failed: {exc}"}

    long_series: List[List[Any]] = []
    short_series: List[List[Any]] = []

    for row in rows:
        ts = _iso(row.get("ts_utc"))
        if not ts:
            continue
        flux = row.get("flux")
        if flux is None:
            continue
        try:
            fval = float(flux)
        except (TypeError, ValueError):
            continue

        energy = str(row.get("energy_band") or "").lower()
        if "0.1-0.8" in energy:
            long_series.append([ts, fval])
        elif "0.05-0.4" in energy:
            short_series.append([ts, fval])
        else:
            # Unknown channel; ignore for now.
            continue

    return {
        "ok": True,
        "data": {
            "series": {
                "long": long_series,
                "short": short_series,
            }
        },
        "error": None,
    }


# Magnetosphere endpoint
@router.get("/magnetosphere")
async def magnetosphere(conn = Depends(get_db)):
    """
    Magnetosphere status + 24h r0 series backed by ext.magnetosphere_pulse and marts.magnetosphere_last_24h.

    Returns shape:
      {
        "ok": true,
        "data": {
          "ts": "...",
          "kpis": {...},
          "sw": {...},
          "trend": {"r0": "..."},
          "chart": {"mode": "...", "amp": ...},
          "series": { "r0": [ {"t": "...", "v": 9.0}, ... ] }
        }
      }
    """
    latest: Optional[Dict[str, Any]] = None
    series_rows: List[Dict[str, Any]] = []
    chart_meta: Dict[str, Any] = {"mode": "absolute", "amp": 1.0}

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")
            # Latest magnetosphere pulse
            await cur.execute(
                """
                select ts, n_cm3, v_kms, bz_nt, pdyn_npa, r0_re, symh_est,
                       dbdt_proxy, trend_r0, geo_risk, kpi_bucket, lpp_re, kp_latest
                from ext.magnetosphere_pulse
                order by ts desc
                limit 1
                """
            )
            latest = await cur.fetchone()

            # 24h r0/Kp series for charts
            await cur.execute(
                """
                select ts, r0_re, kp_latest
                from marts.magnetosphere_last_24h
                order by ts asc
                """
            )
            series_rows = await cur.fetchall() or []

    except Exception as exc:
        return {"ok": False, "error": f"magnetosphere query failed: {exc}"}

    if not latest:
        return {"ok": False, "error": "no magnetosphere data available"}

    # Build 24h r0 series
    series_r0: List[Dict[str, Any]] = []
    for row in series_rows:
        t = row.get("ts")
        v = row.get("r0_re")
        if t is None or v is None:
            continue
        try:
            t_str = t.isoformat() if isinstance(t, datetime) else str(t)
            series_r0.append({"t": t_str, "v": float(v)})
        except Exception:
            continue

    # KPIs
    ts = latest.get("ts")
    r0 = latest.get("r0_re")
    geo_risk = latest.get("geo_risk") or _bucket_geo_risk(r0)
    kpi_bucket = latest.get("kpi_bucket") or _bucket_kpi(latest.get("symh_est"))
    dbdt_proxy = latest.get("dbdt_proxy")
    dbdt_tag = _dbdt_tag_from_proxy(dbdt_proxy)
    lpp = latest.get("lpp_re")
    kp_latest = latest.get("kp_latest")

    kpis = {
        "r0_re": None if r0 is None else round(float(r0), 1),
        "geo_risk": geo_risk,
        "storminess": kpi_bucket,
        "dbdt": dbdt_tag,
        "lpp_re": None if lpp is None else round(float(lpp), 1),
        "kp": kp_latest,
    }

    sw = {
        "n_cm3": latest.get("n_cm3"),
        "v_kms": latest.get("v_kms"),
        "bz_nt": latest.get("bz_nt"),
    }

    trend = {"r0": latest.get("trend_r0") or "flat"}

    data = {
        "ts": _iso(ts) or ts,
        "kpis": kpis,
        "sw": sw,
        "trend": trend,
        "chart": chart_meta,
        "series": {
            "r0": series_r0,
        },
    }

    return {"ok": True, "data": data, "error": None}


# --- Unified alerts endpoint ---
@router.get("/alerts")
async def space_alerts(conn = Depends(get_db)):
    """
    Unified live alerts (radiation S-scale, geomagnetic G-scale, solar flare class, radio-blackout R-scale).
    Mirrors the WP plugin sources but keeps graceful fallbacks.
    Returns:
      {
        "ok": true,
        "updated": "...Z",
        "alerts": [ {key, severity, level, message, values}, ... ]
      }
    """
    alerts: List[Dict[str, Any]] = []
    updated = datetime.now(timezone.utc).isoformat()

    # --- Geomagnetic (from ext.space_weather) ---
    kp_now = None
    kp_max24 = None
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("set statement_timeout = 60000")
            # latest kp
            await cur.execute(
                """
                select ts_utc, kp_index
                from ext.space_weather
                where kp_index is not null
                order by ts_utc desc
                limit 1
                """
            )
            row = await cur.fetchone()
            if row:
                kp_now = float(row.get("kp_index"))
            # 24h max
            await cur.execute(
                """
                select max(kp_index) as max_kp
                from ext.space_weather
                where ts_utc >= (now() at time zone 'utc') - interval '24 hours'
                  and kp_index is not null
                """
            )
            rowm = await cur.fetchone()
            if rowm and rowm.get("max_kp") is not None:
                kp_max24 = float(rowm.get("max_kp"))
    except Exception:
        pass

    kp_ref = kp_now if kp_now is not None else kp_max24
    g_now = _g_from_kp(kp_ref)
    if g_now >= 1:
        severity = "warn" if g_now >= 2 else "advisory"
        alerts.append({
            "key": "geomagnetic_g",
            "severity": severity,
            "level": f"G{g_now}",
            "message": f"Geomagnetic activity: G{g_now} (Kp {kp_ref:.1f})",
            "values": {"kp_now": kp_now, "kp_24h_max": kp_max24}
        })

    # --- Radiation (≥10 MeV PFU -> S-scale) ---
    p = _latest_pfu_10mev_from_goes()
    if p and p.get("pfu") is not None:
        S = _s_scale_from_pfu(p["pfu"])
        if S != "S0":
            alerts.append({
                "key": "radiation_s",
                "severity": "warn",
                "level": S,
                "message": f"Solar radiation storm: {S} (≥10 MeV {p['pfu']:.2f} pfu)",
                "values": {"pfu_10mev": p["pfu"], "ts": p.get("ts")}
            })

    # --- Solar flares (GOES XRS) and related radio blackout risk ---
    goes = _goes_flares_summary()
    max_cls = goes.get("max_class")
    if max_cls:
        # Always report the strongest flare class seen in the last 24h
        flare_severity = "warn" if max_cls.startswith("X") else ("advisory" if max_cls.startswith("M") else "info")
        alerts.append({
            "key": "solar_flare",
            "severity": flare_severity,
            "level": max_cls,
            "message": f"Solar flare: {max_cls} in last 24h",
            "values": {"max_24h": max_cls}
        })

        # Derive radio blackout (R-scale) from the flare class
        r = _r_from_flare_class(max_cls)
        if r:
            alerts.append({
                "key": "radio_blackout_r",
                "severity": "watch" if r == "R1" else "advisory",
                "level": r,
                "message": f"Radio blackout risk: {r} (24 h max {max_cls})",
                "values": {"max_24h": max_cls}
            })

    # sort by severity importance
    order = {"warn": 3, "advisory": 2, "watch": 1, "info": 0}
    alerts.sort(key=lambda a: order.get(a["severity"], 0), reverse=True)

    return {"ok": True, "updated": updated, "alerts": alerts}