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


# AIA 304 (mirror)
def ingest_aia_304(captured_at: dt.datetime):
    src = "https://sdo.gsfc.nasa.gov/assets/img/browse/latest/SDO_AIA_304.jpg"
    r = requests.get(src, timeout=60)
    r.raise_for_status()
    rel = f"nasa/aia_304/aia_304_{_stamp(captured_at)}.jpg"
    public = upload_bytes(rel, r.content, content_type="image/jpeg")
    upload_alias("nasa/aia_304/latest.jpg", public, content_type="image/jpeg")
    upsert_visual_row("aia_304", rel, "SDO/AIA", "aia_304", captured_at)


# Aurora viewline (use your stored URLs if you already fetch them; otherwise just alias)
def alias_aurora_viewline(tonight_url: Optional[str], tomorrow_url: Optional[str], ts: dt.datetime):
    # If your ingest computes/pulls these PNGs elsewhere, re-upload via deterministic rel keys (aurora/viewline/…)
    if tonight_url:
        r = requests.get(tonight_url, timeout=60)
        r.raise_for_status()
        rel = f"aurora/viewline/tonight-north_{_stamp(ts)}.png"
        public = upload_bytes(rel, r.content, content_type="image/png")
        upload_alias("aurora/viewline/tonight-north.png", public, content_type="image/png")
        upsert_visual_row("aurora_viewline_tonight", rel, "NOAA/SWPC OVATION", "ovation", ts)
    if tomorrow_url:
        r = requests.get(tomorrow_url, timeout=60)
        r.raise_for_status()
        rel = f"aurora/viewline/tomorrow-north_{_stamp(ts)}.png"
        public = upload_bytes(rel, r.content, content_type="image/png")
        upload_alias("aurora/viewline/tomorrow-north.png", public, content_type="image/png")
        upsert_visual_row("aurora_viewline_tomorrow", rel, "NOAA/SWPC OVATION", "ovation", ts)


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
    "ingest_drap_now",
    "ingest_lasco_c2",
    "upload_rendered_png",
    "upload_alias",
    "upload_bytes",
    "upsert_visual_row",
]
