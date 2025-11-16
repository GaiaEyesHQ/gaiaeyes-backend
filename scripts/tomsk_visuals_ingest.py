#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import os
import re
import sys

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple
import urllib.parse
import urllib.request

import psycopg
from psycopg.types.json import Json as PsycoJson

USER_AGENT = os.getenv("TOMSK_VISUALS_UA", "GaiaEyes/1.0 (+https://gaiaeyes.com)")
HTTP_TIMEOUT = int(os.getenv("TOMSK_VISUALS_TIMEOUT", "30"))
MEDIA_DIR = os.getenv("MEDIA_DIR", "gaiaeyes-media")
TOMSK_DIR = os.path.join(MEDIA_DIR, "images", "tomsk")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
os.makedirs(TOMSK_DIR, exist_ok=True)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

@dataclass
class TomskPage:
    slug: str
    url: str
    label: str
    feature_flags: Dict[str, bool]

TOMSK_PAGES: Sequence[TomskPage] = (
    TomskPage(
        slug="sos70_page_47",
        url="https://sos70.ru/?page_id=47",
        label="SOS70 Tomsk Schumann visuals (page 47)",
        feature_flags={"schumann_visual": True},
    ),
    TomskPage(
        slug="sos70_page_48",
        url="https://sos70.ru/?page_id=48",
        label="SOS70 Tomsk Schumann visuals (page 48)",
        feature_flags={"schumann_visual": True},
    ),
    TomskPage(
        slug="sos70_home",
        url="https://sos70.ru",
        label="SOS70 Tomsk Schumann visuals (homepage)",
        feature_flags={"schumann_visual": True},
    ),
    TomskPage(
        slug="sos70_page_52",
        url="https://sos70.ru/?page_id=52",
        label="SOS70 Tomsk Schumann visuals (page 52)",
        feature_flags={"schumann_visual": True},
    ),
)


def _http_get(url: str) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:
        print(f"[tomsk_visuals] {url} -> {exc}")
        return None


def _looks_like_image(url: Optional[str]) -> bool:
    if not url:
        return False
    q = url.split("?", 1)[0].lower()
    return any(q.endswith(ext) for ext in IMAGE_EXTS)


class _ImageHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        attrs_map = {k.lower(): v for k, v in attrs}
        if tag.lower() == "img":
            self._collect_from_img(attrs_map)
        elif tag.lower() == "a":
            href = attrs_map.get("href")
            if _looks_like_image(href):
                self.candidates.append(href)

    def _collect_from_img(self, attrs: Dict[str, str]):
        keys = [
            "data-full-url",
            "data-large-file",
            "data-orig-file",
            "data-src",
            "data-lazy-src",
            "src",
        ]
        for key in keys:
            val = attrs.get(key)
            if val:
                self.candidates.append(val)
        srcset = attrs.get("srcset")
        if srcset:
            parsed = _largest_from_srcset(srcset)
            if parsed:
                self.candidates.append(parsed)


def _largest_from_srcset(srcset: str) -> Optional[str]:
    best_url = None
    best_width = -1
    for chunk in srcset.split(","):
        part = chunk.strip()
        if not part:
            continue
        if " " in part:
            url, width = part.rsplit(" ", 1)
        else:
            url, width = part, "0"
        url = url.strip()
        width_val = 0
        try:
            width_val = int(width.strip().rstrip("w"))
        except Exception:
            width_val = 0
        if url and width_val >= best_width:
            best_url = url
            best_width = width_val
    return best_url


def _normalize_image_url(url: str, base_url: str) -> Optional[str]:
    if not url:
        return None
    url = url.strip().strip('"').strip("'")
    if not url or url.startswith("data:"):
        return None
    if url.startswith("//"):
        url = "https:" + url
    absolute = urllib.parse.urljoin(base_url, url)
    absolute = absolute.split("?", 1)[0]
    parsed = urllib.parse.urlparse(absolute)
    path = re.sub(r"-\d+x\d+(?=\.[A-Za-z0-9]+$)", "", parsed.path)
    normalized = parsed._replace(path=path)
    return urllib.parse.urlunparse(normalized)


def _candidate_urls(raw_url: str, base_url: str) -> List[str]:
    guesses = []
    normalized = _normalize_image_url(raw_url, base_url)
    raw_abs = urllib.parse.urljoin(base_url, raw_url)
    for cand in (normalized, raw_abs):
        if cand and _looks_like_image(cand):
            guesses.append(cand)
    # keep order but drop duplicates
    seen = set()
    unique = []
    for cand in guesses:
        if cand not in seen:
            unique.append(cand)
            seen.add(cand)
    return unique


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


def _download_with_meta(urls: Sequence[str], dest_dir: str, prefix: str) -> Optional[Tuple[str, str, Optional[dt.datetime]]]:
    os.makedirs(dest_dir, exist_ok=True)
    for cand in urls:
        try:
            req = urllib.request.Request(cand, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                data = resp.read()
                lm_dt = _parse_last_modified(resp.headers.get("Last-Modified"))
                fname = os.path.basename(urllib.parse.urlparse(cand).path)
                if not fname:
                    fname = "tomsk_visual.jpg"
                stem, ext = os.path.splitext(fname)
                safe_stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "tomsk"
                stamp = (lm_dt or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%S")
                local_name = f"{prefix}_{safe_stem}_{stamp}{ext or '.jpg'}"
                dest_path = os.path.join(dest_dir, local_name)
                with open(dest_path, "wb") as fh:
                    fh.write(data)
                rel_path = os.path.relpath(dest_path, MEDIA_DIR).replace("\\", "/")
                return cand, rel_path, lm_dt
        except Exception as exc:
            print(f"[tomsk_visuals] download {cand} -> {exc}")
    return None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "visual"


def _persist_supabase(rows: List[Dict[str, object]]):
    if not rows:
        return
    if not SUPABASE_DB_URL:
        print("[tomsk_visuals] SUPABASE_DB_URL not set; skipping Supabase upsert")
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
        print(f"[tomsk_visuals] upserted {len(rows)} rows")
    except Exception as exc:
        print(f"[tomsk_visuals] Supabase upsert failed: {exc}")


def _collect_page_images(page: TomskPage) -> List[Tuple[str, str, Optional[dt.datetime]]]:
    body = _http_get(page.url)
    if not body:
        print(f"[tomsk_visuals] unable to fetch {page.url}")
        return []
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError:
        decoded = body.decode("cp1251", errors="ignore")
    parser = _ImageHTMLParser()
    parser.feed(decoded)
    assets: List[Tuple[str, str, Optional[dt.datetime]]] = []
    seen_sources = set()
    for raw in parser.candidates:
        urls = _candidate_urls(raw, page.url)
        if not urls:
            continue
        download = _download_with_meta(urls, TOMSK_DIR, page.slug)
        if not download:
            continue
        source_url, rel_path, lm_dt = download
        if source_url in seen_sources:
            continue
        seen_sources.add(source_url)
        assets.append((source_url, rel_path, lm_dt))
    return assets


def main():
    rows: List[Dict[str, object]] = []
    for page in TOMSK_PAGES:
        page_assets = _collect_page_images(page)
        if not page_assets:
            continue
        for source_url, rel_path, lm_dt in page_assets:
            parsed = urllib.parse.urlparse(source_url)
            stem = os.path.splitext(os.path.basename(parsed.path))[0]
            slug = _slugify(f"{page.slug}-{stem}")
            ts = (lm_dt or dt.datetime.now(dt.timezone.utc)).replace(minute=0, second=0, microsecond=0)
            rows.append(
                {
                    "ts": ts,
                    "key": f"tomsk_{slug}",
                    "asset_type": "image",
                    "image_path": rel_path,
                    "meta": {
                        "page_url": page.url,
                        "label": page.label,
                        "source_url": source_url,
                    },
                    "series": None,
                    "feature_flags": page.feature_flags,
                    "instrument": "Tomsk SR Observatory",
                    "credit": "SOS70.ru",
                }
            )
    if not rows:
        print("[tomsk_visuals] no assets were ingested")
        return
    print(f"[tomsk_visuals] prepared {len(rows)} assets")
    _persist_supabase(rows)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
