#!/usr/bin/env python3
"""Supabase ingestion helpers for deterministic space visuals uploads."""

from __future__ import annotations

import datetime as dt
import io
import json
import os
from typing import Optional

import requests
from PIL import Image
from psycopg import connect

from app.utils.supabase_storage import _public_url, upload_alias, upload_bytes

DB_URL = os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")
HELIOVIEWER_API = os.getenv("HELIOVIEWER_API_URL", "https://api.helioviewer.org/v2/takeScreenshot/")

# SWPC static viewline forecast images (configurable via env)
AURORA_TONIGHT_URL = os.getenv(
    "AURORA_TONIGHT_URL",
    "https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/tonights_static_viewline_forecast.png",
)
AURORA_TOMORROW_URL = os.getenv(
    "AURORA_TOMORROW_URL",
    "https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/tomorrow_nights_static_viewline_forecast.png",
)


def _stamp(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def upsert_visual_row(
    key: str,
    rel_path: str,
    credit: str,
    instrument: str,
    captured_at: dt.datetime,
    feature_flags: Optional[dict] | None = None,
    meta_extra: Optional[dict] | None = None,
):
    meta = {"capture_stamp": _stamp(captured_at), "relative_path": rel_path, "title": key}
    if meta_extra:
        meta.update(meta_extra)
    flags = feature_flags or {}
    with connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
          insert into ext.space_visuals (ts, key, asset_type, image_path, meta, feature_flags, instrument, credit)
          values (now(), %s, 'image', %s, %s::jsonb, %s::jsonb, %s, %s)
        """,
            (key, rel_path, json.dumps(meta), json.dumps(flags), instrument, credit),
        )
        conn.commit()


# DRAP (mirror)
def ingest_drap_now(captured_at: dt.datetime):
    src = "https://services.swpc.noaa.gov/images/d-rap/global_d-rap_latest.png"
    r = requests.get(src, timeout=60)
    r.raise_for_status()
    rel = f"drap/drap_{_stamp(captured_at)}.png"
    public = upload_bytes(rel, r.content, content_type="image/png")
    upload_alias("drap/latest.png", public, content_type="image/png")
    upsert_visual_row("drap", rel, "NOAA/SWPC", "drap", captured_at)


# LASCO C2 (mirror)
def ingest_lasco_c2(captured_at: dt.datetime):
    src = "https://soho.nascom.nasa.gov/data/LATEST/images/c2/latest.jpg"
    r = requests.get(src, timeout=60)
    r.raise_for_status()
    rel = f"nasa/lasco_c2/lasco_c2_{_stamp(captured_at)}.jpg"
    public = upload_bytes(rel, r.content, content_type="image/jpeg")
    upload_alias("nasa/lasco_c2/latest.jpg", public, content_type="image/jpeg")
    upsert_visual_row("lasco_c2", rel, "SOHO/LASCO", "lasco_c2", captured_at)


# AIA 304 (via Helioviewer screenshot)
def ingest_aia_304(captured_at: dt.datetime):
    """
    Fetch a recent AIA 304 Å full-disc image via the Helioviewer API and mirror it into Supabase.

    We use the v2 takeScreenshot endpoint with sourceId=13 (SDO/AIA 304) and request a 1024x1024 PNG.
    """
    # Build request parameters for Helioviewer
    date_str = captured_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "date": date_str,
        "imageScale": 2.0,
        # Single-layer: [sourceId, opacity, visibilityFlag]; 13 = AIA 304
        "layers": "[13,1,100]",
        # Centered full disc
        "x0": 0,
        "y0": 0,
        "width": 1024,
        "height": 1024,
        # Return PNG bytes directly
        "display": "true",
    }

    # Try Helioviewer first
    img_bytes = None
    try:
        hv_resp = requests.get(HELIOVIEWER_API, params=params, timeout=60)
        hv_resp.raise_for_status()
        img_bytes = hv_resp.content
        content_type = "image/png"
    except Exception:
        # Fallback: attempt legacy SDO browse image (may be stale if SDO web is down)
        try:
            fallback_src = "https://sdo.gsfc.nasa.gov/assets/img/browse/latest/SDO_AIA_304.jpg"
            r = requests.get(fallback_src, timeout=60)
            r.raise_for_status()
            img_bytes = r.content
            content_type = "image/jpeg"
        except Exception:
            raise

    if not img_bytes:
        raise RuntimeError("Failed to fetch AIA 304 image from Helioviewer and fallback source")

    rel = f"nasa/aia_304/aia_304_{_stamp(captured_at)}.png"
    public = upload_bytes(rel, img_bytes, content_type=content_type)
    # Alias for "latest" solar disc; keep .jpg name for compatibility with existing image_path rows
    latest_alias = "nasa/aia_304/latest.jpg"
    upload_alias(latest_alias, public, content_type=content_type)
    upsert_visual_row("aia_304", latest_alias, "SDO/AIA (via Helioviewer)", "aia_304", captured_at)


# HMI Intensity (continuum) via Helioviewer screenshot
def ingest_hmi_intensity(captured_at: dt.datetime):
    """
    Fetch a recent HMI continuum (intensitygram) full-disc image via the Helioviewer API
    and mirror it into Supabase.

    We use the v2 takeScreenshot endpoint with sourceId=18 (SDO/HMI Int) and request a 1024x1024 PNG.
    """
    date_str = captured_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "date": date_str,
        "imageScale": 2.0,
        # Single-layer: [sourceId, opacity, visibilityFlag]; 18 = HMI Int (continuum)
        "layers": "[18,1,100]",
        "x0": 0,
        "y0": 0,
        "width": 1024,
        "height": 1024,
        "display": "true",
    }

    img_bytes = None
    try:
        hv_resp = requests.get(HELIOVIEWER_API, params=params, timeout=60)
        hv_resp.raise_for_status()
        img_bytes = hv_resp.content
        content_type = "image/png"
    except Exception:
        # Fallback: attempt legacy HMI intensity image from SDO (may be stale if SDO web is down)
        try:
            fallback_src = "https://sdo.gsfc.nasa.gov/assets/img/browse/latest/SDO_HMIIC.jpg"
            r = requests.get(fallback_src, timeout=60)
            r.raise_for_status()
            img_bytes = r.content
            content_type = "image/jpeg"
        except Exception:
            raise

    if not img_bytes:
        raise RuntimeError("Failed to fetch HMI intensity image from Helioviewer and fallback source")

    rel = f"nasa/hmi_intensity/hmi_intensity_{_stamp(captured_at)}.png"
    public = upload_bytes(rel, img_bytes, content_type=content_type)
    # Alias for "latest" HMI intensity; keep .jpg name for compatibility
    latest_alias = "nasa/hmi_intensity/latest.jpg"
    upload_alias(latest_alias, public, content_type=content_type)
    upsert_visual_row("hmi_intensity", latest_alias, "SDO/HMI (via Helioviewer)", "hmi_intensity", captured_at)


# Aurora static viewline forecast images (tonight/tomorrow)
def ingest_aurora_viewline_static(captured_at: dt.datetime):
    """
    Fetch the SWPC experimental 'static viewline' forecast images for tonight and tomorrow
    and mirror them into Supabase Storage with deterministic aliases the site/app expect.
    """
    # Tonight
    try:
        rt = requests.get(AURORA_TONIGHT_URL, timeout=60)
        rt.raise_for_status()
        rel_t = f"aurora/viewline/tonight_{_stamp(captured_at)}.png"
        pub_t = upload_bytes(rel_t, rt.content, content_type="image/png")
        upload_alias("aurora/viewline/tonight.png", pub_t, content_type="image/png")
        upsert_visual_row("aurora_viewline_tonight", rel_t, "NOAA/SWPC OVATION", "ovation", captured_at)
    except Exception:
        # Don't crash the whole job if SWPC has a brief outage
        pass

    # Tomorrow
    try:
        rtm = requests.get(AURORA_TOMORROW_URL, timeout=60)
        rtm.raise_for_status()
        rel_tm = f"aurora/viewline/tomorrow_{_stamp(captured_at)}.png"
        pub_tm = upload_bytes(rel_tm, rtm.content, content_type="image/png")
        upload_alias("aurora/viewline/tomorrow.png", pub_tm, content_type="image/png")
        upsert_visual_row("aurora_viewline_tomorrow", rel_tm, "NOAA/SWPC OVATION", "ovation", captured_at)
    except Exception:
        pass


# Aurora viewline (use your stored URLs if you already fetch them; otherwise just alias)
def alias_aurora_viewline(tonight_url: Optional[str], tomorrow_url: Optional[str], ts: dt.datetime):
    """
    Mirror provided 'tonight'/'tomorrow' viewline PNGs into Supabase Storage.

    Produces deterministic aliases:
      - aurora/viewline/tonight.png
      - aurora/viewline/tomorrow.png

    and keeps versioned history objects:
      - aurora/viewline/tonight_<stamp>.png
      - aurora/viewline/tomorrow_<stamp>.png
    """
    if tonight_url:
        r = requests.get(tonight_url, timeout=60)
        r.raise_for_status()
        rel_t = f"aurora/viewline/tonight_{_stamp(ts)}.png"
        pub_t = upload_bytes(rel_t, r.content, content_type="image/png")
        upload_alias("aurora/viewline/tonight.png", pub_t, content_type="image/png")
        upsert_visual_row("aurora_viewline_tonight", rel_t, "NOAA/SWPC OVATION", "ovation", ts)

    if tomorrow_url:
        r = requests.get(tomorrow_url, timeout=60)
        r.raise_for_status()
        rel_tm = f"aurora/viewline/tomorrow_{_stamp(ts)}.png"
        pub_tm = upload_bytes(rel_tm, r.content, content_type="image/png")
        upload_alias("aurora/viewline/tomorrow.png", pub_tm, content_type="image/png")
        upsert_visual_row("aurora_viewline_tomorrow", rel_tm, "NOAA/SWPC OVATION", "ovation", ts)


# Optionally mirror nowcast images for north/south poles from environment URLs
def ingest_aurora_nowcast_from_env(captured_at: dt.datetime):
    """
    Optionally mirror nowcast images for north/south poles into Supabase Storage
    under canonical aliases nowcast-north.png / nowcast-south.png if URLs are provided
    via environment variables:
      - AURORA_NOWCAST_NORTH_URL
      - AURORA_NOWCAST_SOUTH_URL
    """
    north_url = os.getenv("AURORA_NOWCAST_NORTH_URL", "").strip()
    south_url = os.getenv("AURORA_NOWCAST_SOUTH_URL", "").strip()

    def _fetch_and_alias(src_url: str, hemi: str):
        if not src_url:
            return
        r = requests.get(src_url, timeout=60)
        r.raise_for_status()
        rel = f"aurora/nowcast/nowcast-{hemi}_{_stamp(captured_at)}.png"
        pub = upload_bytes(rel, r.content, content_type="image/png")
        upload_alias(f"aurora/nowcast/nowcast-{hemi}.png", pub, content_type="image/png")
        upsert_visual_row(f"aurora_nowcast_{hemi}", rel, "NOAA/SWPC OVATION", "ovation", captured_at)

    try:
        _fetch_and_alias(north_url, "north")
    except Exception:
        pass
    try:
        _fetch_and_alias(south_url, "south")
    except Exception:
        pass


# (Optional) If you render a custom PNG (e.g., "a_station") via PIL:
def upload_rendered_png(
    img: Image.Image,
    key: str,
    captured_at: dt.datetime,
    subfolder: str,
    credit: str,
    instrument: str,
):
    rel = f"{subfolder}/{key}_{_stamp(captured_at)}.png"
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    public = upload_bytes(rel, buf.getvalue(), content_type="image/png")
    upload_alias(f"{subfolder}/{key}_latest.png", public, content_type="image/png")
    upsert_visual_row(key, rel, credit, instrument, captured_at)


__all__ = [
    "_public_url",
    "alias_aurora_viewline",
    "ingest_aia_304",
    "ingest_hmi_intensity",
    "ingest_drap_now",
    "ingest_lasco_c2",
    "upload_rendered_png",
    "upload_alias",
    "upload_bytes",
    "upsert_visual_row",
    "ingest_aurora_viewline_static",
    "ingest_aurora_nowcast_from_env",
]
