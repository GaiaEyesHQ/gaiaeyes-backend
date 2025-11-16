#!/usr/bin/env python3
"""Download Cumiana VLF/Schumann imagery and upsert into ext.space_visuals."""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Sequence, Tuple
import urllib.parse
import urllib.request

import psycopg
from psycopg.types.json import Json as PsycoJson

USER_AGENT = os.getenv("CUMIANA_VISUALS_UA", "GaiaEyes/1.0 (+https://gaiaeyes.com)")
HTTP_TIMEOUT = int(os.getenv("CUMIANA_VISUALS_TIMEOUT", "30"))
MEDIA_DIR = os.getenv("MEDIA_DIR", "gaiaeyes-media")
CUMIANA_DIR = os.path.join(MEDIA_DIR, "images", "cumiana")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
os.makedirs(CUMIANA_DIR, exist_ok=True)


@dataclass
class CumianaVisual:
    slug: str
    url: str
    label: str
    page_url: str = "http://www.vlf.it/cumiana/"
    feature_flags: Dict[str, bool] = None

    def __post_init__(self):
        if self.feature_flags is None:
            self.feature_flags = {"schumann_visual": True}


CUMIANA_VISUALS: Sequence[CumianaVisual] = (
    CumianaVisual(slug="evlf", url="http://www.vlf.it/cumiana/last_E-VLF.jpg", label="Cumiana E-VLF spectrum"),
    CumianaVisual(slug="geomar", url="http://www.vlf.it/cumiana/last-geomar.jpg", label="Cumiana GeoMag"),
    CumianaVisual(slug="marconi", url="http://www.vlf.it/cumiana/last-marconi-multistrip-slow.jpg", label="Cumiana Marconi multistrip"),
    CumianaVisual(slug="geophone", url="http://www.vlf.it/cumiana/last-geophone-multistrip-slow.jpg", label="Cumiana geophone multistrip"),
    CumianaVisual(slug="plotted", url="http://www.vlf.it/cumiana/last-plotted.jpg", label="Cumiana plotted telemetry"),
)


def _parse_last_modified(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "visual"


def _download_visual(url: str, slug: str) -> Optional[Tuple[str, str, Optional[dt.datetime]]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = resp.read()
            lm_dt = _parse_last_modified(resp.headers.get("Last-Modified"))
            parsed = urllib.parse.urlparse(url)
            fname = os.path.basename(parsed.path) or f"{slug}.jpg"
            stem, ext = os.path.splitext(fname)
            safe_stem = _slugify(stem)
            stamp = (lm_dt or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%S")
            local_name = f"{slug}_{safe_stem}_{stamp}{ext or '.jpg'}"
            dest_path = os.path.join(CUMIANA_DIR, local_name)
            with open(dest_path, "wb") as fh:
                fh.write(data)
            rel_path = os.path.relpath(dest_path, MEDIA_DIR).replace("\\", "/")
            return url, rel_path, lm_dt
    except Exception as exc:
        print(f"[cumiana_visuals] download {url} -> {exc}")
        return None


def _persist_supabase(rows: List[Dict[str, object]]):
    if not rows:
        return
    if not SUPABASE_DB_URL:
        print("[cumiana_visuals] SUPABASE_DB_URL not set; skipping Supabase upsert")
        return
    payload: List[Dict[str, object]] = []
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
        print(f"[cumiana_visuals] upserted {len(rows)} rows")
    except Exception as exc:
        print(f"[cumiana_visuals] Supabase upsert failed: {exc}")


def main():
    rows: List[Dict[str, object]] = []
    for visual in CUMIANA_VISUALS:
        download = _download_visual(visual.url, visual.slug)
        if not download:
            continue
        source_url, rel_path, lm_dt = download
        ts_source = lm_dt or dt.datetime.now(dt.timezone.utc)
        ts = ts_source.replace(minute=0, second=0, microsecond=0)
        rows.append(
            {
                "ts": ts,
                "key": f"cumiana_{visual.slug}",
                "asset_type": "image",
                "image_path": rel_path,
                "meta": {
                    "page_url": visual.page_url,
                    "label": visual.label,
                    "source_url": source_url,
                },
                "series": None,
                "feature_flags": visual.feature_flags,
                "instrument": "Cumiana VLF Observatory",
                "credit": "VLF.it",
            }
        )
    if not rows:
        print("[cumiana_visuals] no assets were ingested")
        return
    print(f"[cumiana_visuals] prepared {len(rows)} assets")
    _persist_supabase(rows)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
