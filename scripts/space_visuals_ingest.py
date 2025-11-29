#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import datetime as dt
import urllib.request
import urllib.parse
import sys

# Ensure the repo root (parent of this file) is on sys.path so we can import ingest_space_visuals
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
from typing import Any, Dict, List, Tuple

import requests

import psycopg
from psycopg.types.json import Json as PsycoJson

# Helioviewer-backed AIA/HMI ingestors (upload directly to Supabase Storage + ext.space_visuals)
from ingest_space_visuals import ingest_aia_304 as hv_ingest_aia_304, ingest_hmi_intensity as hv_ingest_hmi_intensity


# Helper to read env overrides and split by comma
def env_urls(key: str, defaults):
    v = os.getenv(key, "").strip()
    if not v:
        return defaults
    return [u.strip() for u in v.split(",") if u.strip()]

OUT_JSON = os.getenv("OUTPUT_JSON_PATH", "space_live.json")
MEDIA_DIR = os.getenv("MEDIA_DIR", "gaiaeyes-media")
IMG_DIR = os.path.join(MEDIA_DIR, "images", "space")
DATA_DIR = os.path.join(MEDIA_DIR, "data")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

IMAGE_SPECS: Dict[str, Dict[str, Any]] = {
    "aia_primary": {
        "instrument": "SDO AIA 193Å",
        "credit": "NASA/SDO",
        "feature_flags": {"flare_markers": True},
    },
    "ovation_nh": {
        "instrument": "SWPC OVATION Prime",
        "credit": "NOAA/SWPC",
        "feature_flags": {"aurora_probability": True},
    },
    "ovation_sh": {
        "instrument": "SWPC OVATION Prime",
        "credit": "NOAA/SWPC",
        "feature_flags": {"aurora_probability": True},
    },
    "soho_c2": {"instrument": "SOHO LASCO C2", "credit": "ESA & NASA"},
    "lasco_c3": {"instrument": "SOHO LASCO C3", "credit": "ESA & NASA"},
    "ccor1_jpeg": {"instrument": "GOES-16 CCOR", "credit": "NOAA/NASA"},
    "hmi_intensity": {
        "instrument": "SDO HMI Intensitygram",
        "credit": "NASA/SDO",
    },
    "geospace_1d": {"instrument": "SWPC GEOSPACE", "credit": "NOAA/SWPC"},
    "geospace_3h": {"instrument": "SWPC GEOSPACE", "credit": "NOAA/SWPC"},
    "geospace_7d": {"instrument": "SWPC GEOSPACE", "credit": "NOAA/SWPC"},
    "kp_station": {"instrument": "SWPC Station Kp", "credit": "NOAA/SWPC"},
    "a_station": {"instrument": "SWPC Station A", "credit": "NOAA/SWPC"},
    "drap_global": {"instrument": "SWPC DRAP", "credit": "NOAA/SWPC"},
    "drap_n_pole": {"instrument": "SWPC DRAP", "credit": "NOAA/SWPC"},
    "drap_s_pole": {"instrument": "SWPC DRAP", "credit": "NOAA/SWPC"},
    "synoptic_map": {"instrument": "SWPC Synoptic", "credit": "NOAA/SWPC"},
    "swx_overview_small": {"instrument": "SWPC SWx", "credit": "NOAA/SWPC"},
    "ccor1_mp4": {
        "instrument": "GOES-16 CCOR",
        "credit": "NOAA/NASA",
        "asset_type": "video",
    },
}

SERIES_SPECS: Dict[str, Dict[str, Any]] = {
    "goes_xray": {
        "label": "GOES X-ray flux (1–8 Å)",
        "units": "W/m²",
        "color": "#7fc8ff",
        "instrument": "GOES XRS",
        "credit": "NOAA/SWPC",
        "feature_flags": {"flare_markers": True},
    },
    "goes_protons": {
        "label": "GOES proton flux (≥10 MeV)",
        "units": "pfu",
        "color": "#ffd089",
        "instrument": "GOES EPS",
        "credit": "NOAA/SWPC",
        "feature_flags": {"radiation_alerts": True},
    },
    "goes_electrons": {
        "label": "GOES electron flux (>2 MeV)",
        "units": "e⁻ cm⁻² s⁻¹ sr⁻¹",
        "color": "#b0f2ff",
        "instrument": "GOES SEISS",
        "credit": "NOAA/SWPC",
    },
    "aurora_power_north": {
        "label": "Aurora hemispheric power (north)",
        "units": "GW",
        "color": "#5eead4",
        "instrument": "OVATION Prime",
        "credit": "NOAA/SWPC",
        "feature_flags": {"aurora_probability": True},
    },
    "aurora_power_south": {
        "label": "Aurora hemispheric power (south)",
        "units": "GW",
        "color": "#c084fc",
        "instrument": "OVATION Prime",
        "credit": "NOAA/SWPC",
        "feature_flags": {"aurora_probability": True},
    },
}

# Map a logical key/filename to a standardized Supabase Storage relative path
def _map_supabase_dest(key: str, filename: str) -> str:
    k = (key or "").lower()
    # DRAP -> single latest
    if k.startswith("drap_"):
        return "drap/latest.png"
    # Aurora viewlines
    if k == "ovation_nh":
        return "aurora/viewline/tonight-north.png"
    if k == "ovation_sh":
        return "aurora/viewline/tonight-south.png"
    # NASA LASCO/AIA/HMI/CCOR
    if k in ("soho_c2",):
        return "nasa/lasco_c2/latest.jpg"
    if k in ("lasco_c3",):
        return "nasa/lasco_c3/latest.jpg"
    if k == "aia_primary":
        return "nasa/aia_193/latest.jpg"
    if k == "aia_304":
        return "nasa/aia_304/latest.jpg"
    if k == "hmi_intensity":
        return "nasa/hmi_intensity/latest.jpg"
    if k in ("ccor1_jpeg",):
        return "nasa/ccor1/latest.jpg"
    if k in ("ccor1_mp4",):
        return "nasa/ccor1/latest.mp4"
    # Magnetosphere (geospace horizons)
    if k == "geospace_1d":
        return "magnetosphere/geospace/1d.png"
    if k == "geospace_3h":
        return "magnetosphere/geospace/3h.png"
    if k == "geospace_7d":
        return "magnetosphere/geospace/7d.png"
    # Station indices
    if k == "kp_station":
        return "space/kp_station/latest.png"
    if k == "a_station":
        return "space/a_station/latest.png"
    # Synoptic / SWX overview
    if k == "synoptic_map":
        return "nasa/synoptic/latest.jpg"
    if k == "swx_overview_small":
        return "nasa/swx/overview/latest.gif"
    # Fallback: keep the legacy filename shape under images/space only if explicitly needed later
    return f"images/space/{filename}"


def probe_url(url: str, timeout: int = 8) -> bool:
    """Check if a URL responds with an image payload."""

    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and str(r.headers.get("content-type", "")).startswith("image"):
            return True
    except Exception:
        pass

    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and str(r.headers.get("content-type", "")).startswith("image"):
            return True
    except Exception:
        pass

    return False


def probe_and_select(primary_urls: List[str], secondary_urls: List[str]) -> str | None:
    """Return the first URL that responds successfully, preferring the primary list."""

    for url in primary_urls:
        if probe_url(url):
            return url
    for url in secondary_urls:
        if probe_url(url):
            return url
    return None


def select_solar_imagery_sources():
    """Pick the best-available solar imagery sources for AIA 193Å, AIA 304Å, and HMI."""

    # NOAA SUVI replacements (195 Å, 304 Å, and SUVI map)
    aia_primary_urls = ["https://services.swpc.noaa.gov/images/animations/suvi/primary/195/latest.png"]
    aia_primary_fallback = []
    aia_304_primary = ["https://services.swpc.noaa.gov/images/animations/suvi/primary/304/latest.png"]
    aia_304_fallback = []
    hmi_primary = ["https://services.swpc.noaa.gov/images/animations/suvi/primary/map/latest.png"]
    hmi_fallback = []

    return {
        "aia_primary_urls": aia_primary_urls,
        "aia_primary_fallback": aia_primary_fallback,
        "aia_primary_url": probe_and_select(aia_primary_urls, aia_primary_fallback)
        or (aia_primary_urls[0] if aia_primary_urls else None),
        "aia_304_primary": aia_304_primary,
        "aia_304_fallback": aia_304_fallback,
        "aia_304_url": probe_and_select(aia_304_primary, aia_304_fallback)
        or (aia_304_primary[0] if aia_304_primary else None),
        "hmi_primary": hmi_primary,
        "hmi_fallback": hmi_fallback,
        "hmi_img": probe_and_select(hmi_primary, hmi_fallback)
        or (hmi_primary[0] if hmi_primary else None),
    }


def dl(url_or_urls, dest):
    """Download first successful URL into dest. url_or_urls can be str or list[str]."""
    urls = url_or_urls if isinstance(url_or_urls, (list, tuple)) else [url_or_urls]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0 (+https://gaiaeyes.com)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                with open(dest, "wb") as f:
                    f.write(r.read())
            return True
        except Exception as e:
            print(f"[dl] {url} -> {e}")
    return False


def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0 (+https://gaiaeyes.com)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[json] {url} -> {e}")
        return None


def http_get(url, as_json=False, ua="GaiaEyes/1.0 (+https://gaiaeyes.com)"):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        return json.loads(data.decode("utf-8")) if as_json else data
    except Exception as e:
        print(f"[get] {url} -> {e}")
        return None

def latest_from_dir(base_url: str, suffix_filter: str = ".jpg", contains: str = "ccor1"):
    """Scrape a simple directory index and return the latest matching file URL by name sort.
    base_url should end with '/'. We match links containing `contains` and ending with `suffix_filter`.
    """
    html = http_get(base_url, as_json=False)
    if not html:
        return None
    try:
        text = html.decode("utf-8", "ignore") if isinstance(html, (bytes, bytearray)) else str(html)
    except Exception:
        text = str(html)
    import re
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
    cands = [h for h in hrefs if h.lower().endswith(suffix_filter) and contains in h]
    if not cands:
        return None
    cands = sorted(set(cands))
    last = cands[-1]
    if not last.startswith("http"):
        return urllib.parse.urljoin(base_url.rstrip('/') + '/', last)
    return last


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        for fmt in (None, "%Y-%m-%d %H:%M:%S"):
            try:
                if fmt:
                    parsed = dt.datetime.strptime(v, fmt).replace(tzinfo=dt.timezone.utc)
                else:
                    parsed = dt.datetime.fromisoformat(v)
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=dt.timezone.utc)
                return parsed.astimezone(dt.timezone.utc)
            except ValueError:
                continue
    return None


def _isoformat(ts: dt.datetime | None) -> str | None:
    if not ts:
        return None
    return ts.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _float(value: Any) -> float | None:
    try:
        f = float(value)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _classify_xray(value: float) -> str:
    if value <= 0:
        return "—"
    import math

    logv = math.log10(value)
    if logv >= -4:
        cls = "X"
        scale = 1e-4
    elif logv >= -5:
        cls = "M"
        scale = 1e-5
    elif logv >= -6:
        cls = "C"
        scale = 1e-6
    elif logv >= -7:
        cls = "B"
        scale = 1e-7
    else:
        cls = "A"
        scale = 1e-8
    return f"{value/scale:.1f}{cls}"


def _normalize_xrs(rows: Any, limit: int = 720) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        for entry in rows:
            ts = _parse_timestamp(entry.get("time_tag") or entry.get("time") or entry.get("timestamp"))
            short = _float(entry.get("xray_flux_1") or entry.get("short") or entry.get("flux_short")) or 0.0
            longv = _float(entry.get("xray_flux_2") or entry.get("long") or entry.get("flux_long")) or 0.0
            val = max(short, longv)
            if ts is not None and val is not None:
                samples.append({"ts": _isoformat(ts), "value": val, "class": _classify_xray(val)})
    elif isinstance(rows, list):
        start = 0
        if rows and isinstance(rows[0], list):
            header = ",".join(str(x).lower() for x in rows[0])
            if "time" in header or "short" in header:
                start = 1
        for entry in rows[start:]:
            if not isinstance(entry, list) or len(entry) < 3:
                continue
            ts = _parse_timestamp(entry[0])
            short = _float(entry[1]) or 0.0
            longv = _float(entry[2]) or 0.0
            val = max(short, longv)
            if ts is not None and val is not None:
                samples.append({"ts": _isoformat(ts), "value": val, "class": _classify_xray(val)})
    return samples[-limit:]


def _normalize_flux(rows: Any, value_keys: Tuple[str, ...], *, limit: int = 720) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    for entry in rows or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_timestamp(entry.get("time_tag") or entry.get("time") or entry.get("timestamp"))
        val = None
        for key in value_keys:
            val = _float(entry.get(key))
            if val is not None:
                break
        if ts is not None and val is not None:
            point = {"ts": _isoformat(ts), "value": val}
            if entry.get("satellite"):
                point["satellite"] = entry.get("satellite")
            if entry.get("energy"):
                point["energy"] = entry.get("energy")
            samples.append(point)
    return samples[-limit:]


def _normalize_aurora(rows: Any, limit: int = 288) -> Dict[str, List[Dict[str, Any]]]:
    if isinstance(rows, dict):
        for key in ("forecasts", "data"):
            if key in rows and isinstance(rows[key], list):
                rows = rows[key]
                break
    series = {"aurora_power_north": [], "aurora_power_south": []}
    for entry in rows or []:
        if not isinstance(entry, dict):
            continue
        hemi_raw = str(entry.get("hemisphere") or entry.get("Hemisphere") or "north").lower()
        key = "aurora_power_south" if "south" in hemi_raw else "aurora_power_north"
        ts = _parse_timestamp(entry.get("ForecastTime") or entry.get("forecast_time") or entry.get("time") or entry.get("time_tag"))
        power = _float(entry.get("Power") or entry.get("power") or entry.get("hemispheric_power") or entry.get("powerGW"))
        if ts is not None and power is not None:
            series[key].append({"ts": _isoformat(ts), "value": power, "hemisphere": "south" if key.endswith("south") else "north"})
    return {k: v[-limit:] for k, v in series.items() if v}


def _build_supabase_rows(slot_ts: dt.datetime, stamp: str, saved: Dict[str, str], video: Dict[str, str], series_payload: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    assets = dict(saved)
    assets.update(video)
    for key, rel_path in assets.items():
        spec = IMAGE_SPECS.get(key, {})
        meta = dict(spec.get("meta") or {})
        meta.setdefault("capture_stamp", stamp)
        meta.setdefault("relative_path", rel_path)
        rows.append(
            {
                "ts": slot_ts,
                "key": key,
                "asset_type": spec.get("asset_type", "image"),
                "image_path": rel_path,
                "meta": meta,
                "series": None,
                "feature_flags": spec.get("feature_flags") or {},
                "instrument": spec.get("instrument"),
                "credit": spec.get("credit"),
            }
        )
    for key, samples in series_payload.items():
        if not samples:
            continue
        spec = SERIES_SPECS.get(key, {})
        meta = {k: v for k, v in spec.items() if k not in {"feature_flags", "instrument", "credit"}}
        rows.append(
            {
                "ts": slot_ts,
                "key": key,
                "asset_type": "series",
                "image_path": None,
                "meta": meta,
                "series": samples,
                "feature_flags": spec.get("feature_flags") or {},
                "instrument": spec.get("instrument"),
                "credit": spec.get("credit"),
            }
        )
    return rows


def _persist_supabase(rows: List[Dict[str, Any]]):
    if not SUPABASE_DB_URL:
        print("[space_visuals] SUPABASE_DB_URL not set; skipping Supabase upserts")
        return
    if not rows:
        return
    payload = []
    for row in rows:
        item = dict(row)
        for field in ("meta", "series", "feature_flags"):
            if item.get(field) is not None:
                item[field] = PsycoJson(item[field])
        payload.append(item)
    sql = """
        insert into ext.space_visuals (ts, key, asset_type, image_path, meta, series, feature_flags, instrument, credit)
        values (%(ts)s, %(key)s, %(asset_type)s, %(image_path)s, %(meta)s, %(series)s, %(feature_flags)s, %(instrument)s, %(credit)s)
        on conflict (key, asset_type, ts)
        do update set
            image_path = excluded.image_path,
            meta = excluded.meta,
            series = excluded.series,
            feature_flags = excluded.feature_flags,
            instrument = excluded.instrument,
            credit = excluded.credit
    """
    try:
        with psycopg.connect(SUPABASE_DB_URL) as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, payload)
            conn.commit()
        print(f"[space_visuals] upserted {len(rows)} rows into ext.space_visuals")
    except Exception as exc:
        print(f"[space_visuals] Supabase upsert failed: {exc}")


def main():
    # 1) Solar imagery + Solar flares (XRS) + Proton/Electron flux (GOES)
    solar_sources = select_solar_imagery_sources()
    aia_primary_url = solar_sources["aia_primary_url"]
    aia_304_url = solar_sources["aia_304_url"]
    hmi_img = solar_sources["hmi_img"]
    xrs_7d = "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json"
    protons_7d = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json"
    electrons_7d = "https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-7-day.json"

    # 2) Aurora (Ovation) maps (NH/SH)
    ov_nh = "https://services.swpc.noaa.gov/images/aurora-forecast-northern-hemisphere.jpg"
    ov_sh = "https://services.swpc.noaa.gov/images/aurora-forecast-southern-hemisphere.jpg"
    # NOAA deprecated the older forecast URL; use the latest JSON endpoint that stays updated.
    aurora_forecast = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"

    # 3) CME coronagraph imagery (SOHO C2 & LASCO C3)
    soho_c2 = "https://soho.nascom.nasa.gov/data/realtime/c2/1024/latest.jpg"
    lasco_c3 = env_urls("LASCO_C3_URLS", [
        "https://soho.nascom.nasa.gov/data/realtime/c3/1024/latest.jpg"
    ])

    # CCOR-1 directory scrape for latest JPEG, and pick known MP4 names
    ccor_jpegs_dir = "https://services.swpc.noaa.gov/products/ccor1/jpegs/"
    ccor_mp4s_dir  = "https://services.swpc.noaa.gov/products/ccor1/mp4s/"
    ccor1_jpeg_url = latest_from_dir(ccor_jpegs_dir, suffix_filter=".jpg", contains="ccor1")
    ccor1_mp4_url = None
    for name in [os.getenv("CCOR1_MP4_NAME", "ccor1_last_24hrs.mp4"), "ccor1_last_7_days.mp4", "ccor1_last_27_days.mp4"]:
        test = ccor_mp4s_dir.rstrip('/') + '/' + name
        if http_get(test, as_json=False):
            ccor1_mp4_url = test
            break

    # GEOSPACE plots and station indices / DRAP / synoptic / overview
    geospace_1d = "https://services.swpc.noaa.gov/images/geospace/geospace_1_day.png"
    geospace_3h = "https://services.swpc.noaa.gov/images/geospace/geospace_3_hour.png"
    geospace_7d = "https://services.swpc.noaa.gov/images/geospace/geospace_7_day.png"
    kp_station  = "https://services.swpc.noaa.gov/images/station-k-index.png"
    a_station   = "https://services.swpc.noaa.gov/images/station-a-index.png"
    drap_global = "https://services.swpc.noaa.gov/images/drap_global.png"
    drap_npole  = "https://services.swpc.noaa.gov/images/drap_n-pole.png"
    drap_spole  = "https://services.swpc.noaa.gov/images/drap_s-pole.png"
    synoptic_map = "https://services.swpc.noaa.gov/images/synoptic-map.jpg"
    swx_small    = "https://services.swpc.noaa.gov/images/swx-overview-small.gif"

    now_utc = dt.datetime.now(dt.timezone.utc)
    stamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    slot_ts = now_utc.replace(minute=0, second=0, microsecond=0)

    # Also mirror AIA 304 and HMI intensity via Helioviewer into Supabase Storage/ext.space_visuals.
    # These helpers handle upload_bytes/upload_alias/upsert_visual_row themselves, and will keep
    # nasa/aia_304/latest.jpg and nasa/hmi_intensity/latest.jpg fresh even if SDO browse images are stale.
    try:
        hv_ingest_aia_304(now_utc)
    except Exception as e:
        print(f"[space_visuals] Helioviewer ingest AIA 304 failed: {e}")
    try:
        hv_ingest_hmi_intensity(now_utc)
    except Exception as e:
        print(f"[space_visuals] Helioviewer ingest HMI intensity failed: {e}")
    imgs = {
        "aia_primary": (f"aia_primary_{stamp}.png", [aia_primary_url] if aia_primary_url else []),
        "aia_304": (f"aia_304_{stamp}.png", [aia_304_url] if aia_304_url else []),
        "ovation_nh": (f"ovation_nh_{stamp}.jpg", ov_nh),
        "ovation_sh": (f"ovation_sh_{stamp}.jpg", ov_sh),
        "soho_c2": (f"soho_c2_{stamp}.jpg", soho_c2),
        "lasco_c3": (f"lasco_c3_{stamp}.jpg", lasco_c3),
        "ccor1_jpeg": (f"ccor1_{stamp}.jpg", [ccor1_jpeg_url] if ccor1_jpeg_url else []),
        "hmi_intensity": (f"hmi_intensity_{stamp}.png", [hmi_img] if hmi_img else []),
        "geospace_1d": (f"geospace_1d_{stamp}.png", geospace_1d),
        "geospace_3h": (f"geospace_3h_{stamp}.png", geospace_3h),
        "geospace_7d": (f"geospace_7d_{stamp}.png", geospace_7d),
        "kp_station": (f"kp_station_{stamp}.png", kp_station),
        "a_station": (f"a_station_{stamp}.png", a_station),
        "drap_global": (f"drap_global_{stamp}.png", drap_global),
        "drap_n_pole": (f"drap_n_pole_{stamp}.png", drap_npole),
        "drap_s_pole": (f"drap_s_pole_{stamp}.png", drap_spole),
        "synoptic_map": (f"synoptic_map_{stamp}.jpg", synoptic_map),
        "swx_overview_small": (f"swx_overview_small_{stamp}.gif", swx_small)
    }
    saved = {}
    missing = []
    for key, (fn, url) in imgs.items():
        dest = os.path.join(IMG_DIR, fn)
        if dl(url, dest):
            saved[key] = _map_supabase_dest(key, fn)
        else:
            missing.append(key)

    # Download CCOR-1 MP4 video if available
    video = {}
    if ccor1_mp4_url:
        try:
            mp4_name = f"ccor1_{stamp}.mp4"
            mp4_dest = os.path.join(IMG_DIR, mp4_name)
            if dl([ccor1_mp4_url], mp4_dest):
                video["ccor1_mp4"] = _map_supabase_dest("ccor1_mp4", mp4_name)
            else:
                missing.append("ccor1_mp4")
        except Exception as e:
            print("[dl] ccor1 mp4 ->", e)
            missing.append("ccor1_mp4")
    else:
        missing.append("ccor1_mp4")

    # Warn if any legacy images/space paths slipped through
    if any((p or "").startswith("images/space/") for p in list(saved.values()) + list(video.values())):
        print("[space_visuals] WARNING: legacy images/space/ paths present; consider full migration to standardized keys.")

    xrs = fetch_json(xrs_7d) or []
    p7d = fetch_json(protons_7d) or []
    e7d = fetch_json(electrons_7d) or []
    aurora_json = fetch_json(aurora_forecast) or []

    normalized_series: Dict[str, List[Dict[str, Any]]] = {}
    xrs_norm = _normalize_xrs(xrs)
    if xrs_norm:
        normalized_series["goes_xray"] = xrs_norm
    protons_norm = _normalize_flux(p7d, ("integral_protons_10MeV", "flux"))
    if protons_norm:
        normalized_series["goes_protons"] = protons_norm
    electrons_norm = _normalize_flux(e7d, ("integral_electrons_gt_2MeV", "flux"))
    if electrons_norm:
        normalized_series["goes_electrons"] = electrons_norm
    aurora_norm = _normalize_aurora(aurora_json)
    normalized_series.update({k: v for k, v in aurora_norm.items() if v})

    out = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "images": saved,
        "video": video,
        "missing": missing,
        "series": {
            "xrs_7d": xrs,
            "protons_7d": p7d,
            "electrons_7d": e7d,
            "aurora_forecast": aurora_json,
        },
        "notes": "Visuals cached for detail pages. Use with [gaia_space_visuals] or [gaia_space_detail].",
    }

    with open(OUT_JSON if os.path.isabs(OUT_JSON) else os.path.join(MEDIA_DIR, OUT_JSON), "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("[space_visuals] wrote images and space_live.json")

    supabase_rows = _build_supabase_rows(slot_ts, stamp, saved, video, normalized_series)
    _persist_supabase(supabase_rows)


if __name__ == "__main__":
    main()
