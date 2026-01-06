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

import logging

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

 # module logger (library-friendly; handlers configured by caller)
logger = logging.getLogger("space_visuals_ingest")



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
    try:
        with connect(DB_URL) as conn, conn.cursor() as cur:
            logger.debug(
                "[db] insert ext.space_visuals key=%s rel_path=%s instrument=%s credit=%s captured_at=%s flags=%s",
                key,
                rel_path,
                instrument,
                credit,
                _stamp(captured_at),
                flags,
            )
            cur.execute(
                """
                insert into ext.space_visuals (ts, key, asset_type, image_path, meta, feature_flags, instrument, credit)
                values (now(), %s, 'image', %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (key, rel_path, json.dumps(meta), json.dumps(flags), instrument, credit),
            )
            conn.commit()
            logger.info("[db] committed ext.space_visuals row key=%s", key)
    except Exception:
        logger.exception("[db] upsert_visual_row failed key=%s rel_path=%s", key, rel_path)
        raise


# DRAP (mirror)
def ingest_drap_now(captured_at: dt.datetime):
    src = "https://services.swpc.noaa.gov/images/d-rap/global.png"
    logger.info("[ingest] DRAP (now) src=%s", src)
    try:
        r = requests.get(src, timeout=60)
        logger.debug("[http] GET %s -> %s bytes=%s", src, getattr(r, "status_code", "?"), len(r.content) if hasattr(r, "content") else "NA")
        r.raise_for_status()
        rel = f"drap/drap_{_stamp(captured_at)}.png"
        public = upload_bytes(rel, r.content, content_type="image/png")
        upload_alias("drap/latest.png", public, content_type="image/png")
        upsert_visual_row("drap", rel, "NOAA/SWPC", "drap", captured_at)
        logger.info("[ingest] DRAP uploaded %s and aliased to drap/latest.png", rel)
    except Exception:
        logger.exception("[ingest] DRAP ingest failed")
        raise


# LASCO C2 (mirror)
def ingest_lasco_c2(captured_at: dt.datetime):
    src = "https://soho.nascom.nasa.gov/data/LATEST/images/c2/latest.jpg"
    logger.info("[ingest] LASCO C2 src=%s", src)
    try:
        r = requests.get(src, timeout=60)
        logger.debug("[http] GET %s -> %s bytes=%s", src, getattr(r, "status_code", "?"), len(r.content) if hasattr(r, "content") else "NA")
        r.raise_for_status()
        rel = f"nasa/lasco_c2/lasco_c2_{_stamp(captured_at)}.jpg"
        public = upload_bytes(rel, r.content, content_type="image/jpeg")
        upload_alias("nasa/lasco_c2/latest.jpg", public, content_type="image/jpeg")
        upsert_visual_row("lasco_c2", rel, "SOHO/LASCO", "lasco_c2", captured_at)
        logger.info("[ingest] LASCO C2 uploaded %s and aliased to nasa/lasco_c2/latest.jpg", rel)
    except Exception:
        logger.exception("[ingest] LASCO C2 ingest failed")
        raise


# AIA 304 (via Helioviewer screenshot)
def ingest_aia_304(captured_at: dt.datetime):
    """
    Fetch a recent AIA 304 Å full-disc image via the Helioviewer API and mirror it into Supabase.

    We use the v2 takeScreenshot endpoint with sourceId=13 (SDO/AIA 304) and request a 1024x1024 PNG.
    """
    logger.info("[ingest] AIA 304 via Helioviewer")
    date_str = captured_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "date": date_str,
        "imageScale": 2.0,
        "layers": "[13,1,100]",
        "x0": 0,
        "y0": 0,
        "width": 1024,
        "height": 1024,
        "display": "true",
    }

    img_bytes = None
    content_type = "image/png"
    try:
        logger.debug("[http] GET %s params=%s", HELIOVIEWER_API, params)
        hv_resp = requests.get(HELIOVIEWER_API, params=params, timeout=60)
        logger.debug("[http] Helioviewer -> %s ct=%s bytes=%s", hv_resp.status_code, hv_resp.headers.get("Content-Type"), len(hv_resp.content))
        hv_resp.raise_for_status()
        img_bytes = hv_resp.content
        content_type = "image/png"
    except Exception as e:
        logger.warning("[aia_304] Helioviewer failed: %s; trying SDO fallback", e)
        try:
            fallback_src = "https://sdo.gsfc.nasa.gov/assets/img/browse/latest/SDO_AIA_304.jpg"
            fr = requests.get(fallback_src, timeout=60)
            logger.debug("[http] GET %s -> %s bytes=%s", fallback_src, getattr(fr, "status_code", "?"), len(fr.content) if hasattr(fr, "content") else "NA")
            fr.raise_for_status()
            img_bytes = fr.content
            content_type = "image/jpeg"
        except Exception:
            logger.exception("[aia_304] Fallback SDO fetch failed")
            raise

    if not img_bytes:
        raise RuntimeError("Failed to fetch AIA 304 image from Helioviewer and fallback source")

    rel = f"nasa/aia_304/aia_304_{_stamp(captured_at)}.png"
    public = upload_bytes(rel, img_bytes, content_type=content_type)
    latest_alias = "nasa/aia_304/latest.jpg"
    upload_alias(latest_alias, public, content_type=content_type)
    upsert_visual_row("aia_304", latest_alias, "SDO/AIA (via Helioviewer)", "aia_304", captured_at)
    logger.info("[ingest] AIA 304 aliased to %s (stored=%s)", latest_alias, rel)


# HMI Intensity (continuum) via Helioviewer screenshot
def ingest_hmi_intensity(captured_at: dt.datetime):
    """
    Fetch a recent HMI continuum (intensitygram) full-disc image via the Helioviewer API
    and mirror it into Supabase.

    We use the v2 takeScreenshot endpoint with sourceId=18 (SDO/HMI Int) and request a 1024x1024 PNG.
    """
    logger.info("[ingest] HMI Intensity via Helioviewer")
    date_str = captured_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "date": date_str,
        "imageScale": 2.0,
        "layers": "[18,1,100]",
        "x0": 0,
        "y0": 0,
        "width": 1024,
        "height": 1024,
        "display": "true",
    }

    img_bytes = None
    content_type = "image/png"
    try:
        logger.debug("[http] GET %s params=%s", HELIOVIEWER_API, params)
        hv_resp = requests.get(HELIOVIEWER_API, params=params, timeout=60)
        logger.debug("[http] Helioviewer -> %s ct=%s bytes=%s", hv_resp.status_code, hv_resp.headers.get("Content-Type"), len(hv_resp.content))
        hv_resp.raise_for_status()
        img_bytes = hv_resp.content
        content_type = "image/png"
    except Exception as e:
        logger.warning("[hmi_intensity] Helioviewer failed: %s; trying SDO fallback", e)
        try:
            fallback_src = "https://sdo.gsfc.nasa.gov/assets/img/browse/latest/SDO_HMIIC.jpg"
            fr = requests.get(fallback_src, timeout=60)
            logger.debug("[http] GET %s -> %s bytes=%s", fallback_src, getattr(fr, "status_code", "?"), len(fr.content) if hasattr(fr, "content") else "NA")
            fr.raise_for_status()
            img_bytes = fr.content
            content_type = "image/jpeg"
        except Exception:
            logger.exception("[hmi_intensity] Fallback SDO fetch failed")
            raise

    if not img_bytes:
        raise RuntimeError("Failed to fetch HMI intensity image from Helioviewer and fallback source")

    rel = f"nasa/hmi_intensity/hmi_intensity_{_stamp(captured_at)}.png"
    public = upload_bytes(rel, img_bytes, content_type=content_type)
    latest_alias = "nasa/hmi_intensity/latest.jpg"
    upload_alias(latest_alias, public, content_type=content_type)
    upsert_visual_row("hmi_intensity", latest_alias, "SDO/HMI (via Helioviewer)", "hmi_intensity", captured_at)
    logger.info("[ingest] HMI intensity aliased to %s (stored=%s)", latest_alias, rel)


# Aurora static viewline forecast images (tonight/tomorrow)
def ingest_aurora_viewline_static(captured_at: dt.datetime):
    """
    Fetch the SWPC experimental 'static viewline' forecast images for tonight and tomorrow
    and mirror them into Supabase Storage with deterministic aliases the site/app expect.
    """
    logger.info("[ingest] aurora viewline static (tonight/tomorrow)")
    # Tonight
    try:
        rt = requests.get(AURORA_TONIGHT_URL, timeout=60)
        logger.debug("[http] GET %s -> %s bytes=%s", AURORA_TONIGHT_URL, rt.status_code, len(rt.content))
        rt.raise_for_status()
        rel_t = f"aurora/viewline/tonight_{_stamp(captured_at)}.png"
        pub_t = upload_bytes(rel_t, rt.content, content_type="image/png")
        upload_alias("aurora/viewline/tonight.png", pub_t, content_type="image/png")
        upsert_visual_row("aurora_viewline_tonight", rel_t, "NOAA/SWPC OVATION", "ovation", captured_at)
        logger.info("[ingest] aurora tonight aliased to aurora/viewline/tonight.png (source=%s)", AURORA_TONIGHT_URL)
    except Exception:
        logger.exception("[ingest] aurora tonight fetch/alias failed (url=%s)", AURORA_TONIGHT_URL)

    # Tomorrow
    try:
        rtm = requests.get(AURORA_TOMORROW_URL, timeout=60)
        logger.debug("[http] GET %s -> %s bytes=%s", AURORA_TOMORROW_URL, rtm.status_code, len(rtm.content))
        rtm.raise_for_status()
        rel_tm = f"aurora/viewline/tomorrow_{_stamp(captured_at)}.png"
        pub_tm = upload_bytes(rel_tm, rtm.content, content_type="image/png")
        upload_alias("aurora/viewline/tomorrow.png", pub_tm, content_type="image/png")
        upsert_visual_row("aurora_viewline_tomorrow", rel_tm, "NOAA/SWPC OVATION", "ovation", captured_at)
        logger.info("[ingest] aurora tomorrow aliased to aurora/viewline/tomorrow.png (source=%s)", AURORA_TOMORROW_URL)
    except Exception:
        logger.exception("[ingest] aurora tomorrow fetch/alias failed (url=%s)", AURORA_TOMORROW_URL)


# Aurora viewline (use your stored URLs if you already fetch them; otherwise just alias)
def alias_aurora_viewline(tonight_url: Optional[str], tomorrow_url: Optional[str], ts: dt.datetime):
    """
    Mirror provided 'tonight'/'tomorrow' viewline PNGs into Supabase Storage.

    Produces deterministic aliases:
      - aurora/viewline/tonight.png
      - aurora/viewline/tomorrow.png
    """
    logger.info("[alias] aurora viewline provided URLs (tonight=%s, tomorrow=%s)", bool(tonight_url), bool(tomorrow_url))
    if tonight_url:
        try:
            r = requests.get(tonight_url, timeout=60)
            logger.debug("[http] GET %s -> %s bytes=%s", tonight_url, r.status_code, len(r.content))
            r.raise_for_status()
            rel_t = f"aurora/viewline/tonight_{_stamp(ts)}.png"
            pub_t = upload_bytes(rel_t, r.content, content_type="image/png")
            upload_alias("aurora/viewline/tonight.png", pub_t, content_type="image/png")
            upsert_visual_row("aurora_viewline_tonight", rel_t, "NOAA/SWPC OVATION", "ovation", ts)
            logger.info("[alias] aurora tonight -> %s", rel_t)
        except Exception:
            logger.exception("[alias] aurora tonight alias failed (url=%s)", tonight_url)
    else:
        logger.debug("[alias] aurora tonight url missing: skip")

    if tomorrow_url:
        try:
            r = requests.get(tomorrow_url, timeout=60)
            logger.debug("[http] GET %s -> %s bytes=%s", tomorrow_url, r.status_code, len(r.content))
            r.raise_for_status()
            rel_tm = f"aurora/viewline/tomorrow_{_stamp(ts)}.png"
            pub_tm = upload_bytes(rel_tm, r.content, content_type="image/png")
            upload_alias("aurora/viewline/tomorrow.png", pub_tm, content_type="image/png")
            upsert_visual_row("aurora_viewline_tomorrow", rel_tm, "NOAA/SWPC OVATION", "ovation", ts)
            logger.info("[alias] aurora tomorrow -> %s", rel_tm)
        except Exception:
            logger.exception("[alias] aurora tomorrow alias failed (url=%s)", tomorrow_url)
    else:
        logger.debug("[alias] aurora tomorrow url missing: skip")


# Optionally mirror nowcast images for north/south poles from environment URLs
def ingest_aurora_nowcast_from_env(captured_at: dt.datetime):
    """
    Optionally mirror nowcast images for north/south poles into Supabase Storage,
    but alias them using the existing "viewline" hemisphere names expected by the app:

      - aurora/viewline/tonight-north.png  (from AURORA_NOWCAST_NORTH_URL)
      - aurora/viewline/tonight-south.png  (from AURORA_NOWCAST_SOUTH_URL)
    """
    north_url = os.getenv("AURORA_NOWCAST_NORTH_URL", "").strip()
    south_url = os.getenv("AURORA_NOWCAST_SOUTH_URL", "").strip()
    logger.info("[ingest] aurora nowcast env (north=%s, south=%s)", bool(north_url), bool(south_url))

    def _fetch_and_alias(src_url: str, hemi: str):
        if not src_url:
            logger.debug("[ingest] nowcast %s: url missing: skip", hemi)
            return
        r = requests.get(src_url, timeout=60)
        logger.debug("[http] GET %s -> %s bytes=%s", src_url, r.status_code, len(r.content))
        r.raise_for_status()
        rel = f"aurora/viewline/tonight-{hemi}_{_stamp(captured_at)}.png"
        pub = upload_bytes(rel, r.content, content_type="image/png")
        upload_alias(f"aurora/viewline/tonight-{hemi}.png", pub, content_type="image/png")
        upsert_visual_row(f"aurora_nowcast_{hemi}", rel, "NOAA/SWPC OVATION", "ovation", captured_at)
        logger.info("[ingest] aurora nowcast %s aliased to aurora/viewline/tonight-%s.png", hemi, hemi)

    try:
        _fetch_and_alias(north_url, "north")
    except Exception:
        logger.exception("[ingest] aurora nowcast north failed")

    try:
        _fetch_and_alias(south_url, "south")
    except Exception:
        logger.exception("[ingest] aurora nowcast south failed")


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
    logger.debug("[upload] rendered key=%s bytes=%s dest=%s", key, buf.getbuffer().nbytes, rel)
    public = upload_bytes(rel, buf.getvalue(), content_type="image/png")
    upload_alias(f"{subfolder}/{key}_latest.png", public, content_type="image/png")
    upsert_visual_row(key, rel, credit, instrument, captured_at)
    logger.info("[upload] rendered png aliased to %s_latest.png", key)



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

# --- simple CLI entrypoint so GitHub Actions can call specific ingesters ---
def _run_cli():
    import argparse

    parser = argparse.ArgumentParser(description="Ingest aurora viewline images into Supabase Storage")
    parser.add_argument(
        "--viewline-static",
        action="store_true",
        help="Fetch & alias experimental 'tonight.png' and 'tomorrow.png' into aurora/viewline/",
    )
    parser.add_argument(
        "--nowcast-env",
        action="store_true",
        help="Fetch & alias 'tonight-north.png' and 'tonight-south.png' from AURORA_NOWCAST_{NORTH,SOUTH}_URL env vars",
    )
    args = parser.parse_args()

    ts = dt.datetime.utcnow()

    if args.viewline_static:
        try:
            ingest_aurora_viewline_static(ts)
            logger.info("[cli] viewline_static: done")
        except Exception:
            logger.exception("[cli] viewline_static: failed")

    if args.nowcast_env:
        try:
            ingest_aurora_nowcast_from_env(ts)
            logger.info("[cli] nowcast_env: done")
        except Exception:
            logger.exception("[cli] nowcast_env: failed")


if __name__ == "__main__":
    _run_cli()
