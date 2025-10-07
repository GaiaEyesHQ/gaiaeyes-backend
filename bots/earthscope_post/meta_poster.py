#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meta Poster (Facebook/Instagram) — Standalone
---------------------------------------------
Posts Gaia Eyes daily content to FB/IG using the Graph API.

Two modes:
  1) post-square  — posts the square caption card with caption+hashtags
  2) post-carousel — posts a 3-image carousel (stats, affects, playbook)

Reads caption/hashtags from Supabase `content.daily_posts` (platform=default),
resolves image URLs from your media repo (jsDelivr by default), and publishes.

.env expected (same folder or parent):
  SUPABASE_REST_URL=https://<proj>.supabase.co/rest/v1
  SUPABASE_SERVICE_KEY=...
  SUPABASE_ANON_KEY=...               # optional
  SUPABASE_USER_ID=...                # optional, if you filter by user
  MEDIA_CDN_BASE=https://cdn.jsdelivr.net/gh/gennwu/gaiaeyes-media/images

  FB_PAGE_ID=...
  FB_ACCESS_TOKEN=...                 # page access token (with required scopes)
  IG_USER_ID=...

Usage:
  python meta_poster.py post-square  --date 2025-09-10
  python meta_poster.py post-carousel --date 2025-09-10

Add --dry-run to print what would post without publishing.
"""

import os
import sys
import json
import logging
import argparse
import datetime as dt
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, List, Dict
import time
import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

SUPABASE_REST_URL   = os.getenv("SUPABASE_REST_URL", "").rstrip("/")
SB_KEY              = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
SB_USER_ID          = os.getenv("SUPABASE_USER_ID")
MEDIA_CDN_BASE      = os.getenv("MEDIA_CDN_BASE", "https://cdn.jsdelivr.net/gh/gennwu/gaiaeyes-media/images").rstrip("/")

FB_PAGE_ID          = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN     = os.getenv("FB_ACCESS_TOKEN")
IG_USER_ID          = os.getenv("IG_USER_ID")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.7, status_forcelist=[429,500,502,503,504])
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

# ---------------- Supabase ----------------

def _sb_headers(schema: str = "content") -> Dict[str,str]:
    if not SB_KEY:
        raise RuntimeError("Missing Supabase key in env")
    h = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Accept": "application/json"}
    if schema and schema != "public":
        h["Accept-Profile"] = schema
    return h

def sb_select_daily_post(day: dt.date, platform: str = "default") -> Optional[dict]:
    if not SUPABASE_REST_URL:
        return None
    url = f"{SUPABASE_REST_URL}/daily_posts"
    params = {"day": f"eq.{day.isoformat()}", "platform": f"eq.{platform}",
              "select": "day,platform,caption,hashtags,body_markdown,metrics_json"}
    r = session.get(url, headers=_sb_headers("content"), params=params, timeout=20)
    if r.status_code != 200:
        logging.error("Supabase posts fetch failed: %s %s", r.status_code, r.text[:200])
        return None
    data = r.json()
    return data[0] if data else None

def sb_select_latest_post(platform: str = "default") -> Optional[dict]:
    if not SUPABASE_REST_URL:
        return None
    url = f"{SUPABASE_REST_URL}/daily_posts"
    params = {
        "platform": f"eq.{platform}",
        "select": "day,platform,caption,hashtags,body_markdown,metrics_json",
        "order": "day.desc",
        "limit": "1",
    }
    r = session.get(url, headers=_sb_headers("content"), params=params, timeout=20)
    if r.status_code != 200:
        logging.error("Supabase latest posts fetch failed: %s %s", r.status_code, r.text[:200])
        return None
    data = r.json()
    return data[0] if data else None

# ---------------- Meta (Graph API) ---------------

def _require_meta():
    missing = [k for k in ("FB_PAGE_ID","FB_ACCESS_TOKEN","IG_USER_ID") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing env for Meta posting: {', '.join(missing)}")

# -- Facebook Photo Post --

def fb_post_photo(image_url: str, caption: str, dry_run: bool=False) -> dict:
    _require_meta()
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    payload = {"url": image_url, "caption": caption, "access_token": FB_ACCESS_TOKEN}
    if dry_run:
        logging.info("[DRY] FB photo %s", json.dumps(payload)[:200])
        return {"dry": True}
    r = session.post(url, data=payload, timeout=30)
    try:
        return r.json()
    finally:
        if r.status_code != 200:
            logging.error("FB post failed: %s %s", r.status_code, r.text[:200])

# -- Instagram Carousel (3 images) --

def ig_post_carousel(image_urls: List[str], caption: str, dry_run: bool=False) -> dict:
    _require_meta()
    # Step 1: create child containers
    children = []
    for url in image_urls:
        data = {"image_url": url, "is_carousel_item": "true", "access_token": FB_ACCESS_TOKEN}
        if dry_run:
            logging.info("[DRY] IG child %s", url)
            children.append("DRY_CHILD")
            continue
        r = session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media", data=data, timeout=30)
        j = r.json()
        if r.status_code != 200 or "id" not in j:
            logging.error("IG child failed: %s %s", r.status_code, r.text[:200])
            raise RuntimeError("IG child create failed")
        children.append(j["id"])

    # Step 2: create carousel container
    data = {"media_type": "CAROUSEL", "children": ",".join(children),
            "caption": caption, "access_token": FB_ACCESS_TOKEN}
    if dry_run:
        logging.info("[DRY] IG carousel container %s", json.dumps(data)[:200])
        return {"dry": True}
    r = session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media", data=data, timeout=30)
    j = r.json()
    if r.status_code != 200 or "id" not in j:
        logging.error("IG container failed: %s %s", r.status_code, r.text[:200])
        raise RuntimeError("IG carousel container failed")
    creation_id = j["id"]

    # Step 3: publish
    r = session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
                     data={"creation_id": creation_id, "access_token": FB_ACCESS_TOKEN}, timeout=30)
    if r.status_code != 200:
        logging.error("IG publish failed: %s %s", r.status_code, r.text[:200])
    return r.json()

# --------------- Helpers -----------------

def today_utc() -> dt.date:
    return dt.datetime.utcnow().date()

def today_in_tz() -> dt.date:
    tz = os.getenv("GAIA_TIMEZONE", "America/Chicago")
    try:
        return dt.datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return dt.datetime.utcnow().date()

def build_square_caption(post: dict) -> str:
    caption = (post.get("caption") or "").strip()
    hashtags = (post.get("hashtags") or "").strip()
    if hashtags:
        return caption + "\n\n" + hashtags
    return caption

def derive_caption_and_hashtags(post: dict) -> (str, str):
    """Return (caption, hashtags) preferring structured sections from metrics_json or JSON caption."""
    cap = (post.get("caption") or "").strip()
    tags = (post.get("hashtags") or "").strip()
    # 1) If caption looks like a JSON blob with sections, parse it
    if cap.startswith("{") and '"sections"' in cap:
        try:
            j = json.loads(cap)
            sec = j.get("sections") or {}
            if isinstance(sec, dict) and sec.get("caption"):
                cap = sec["caption"].strip()
            # metrics-level hashtags not expected here, keep existing tags
        except Exception:
            pass
    # 2) Prefer sections from metrics_json when available
    try:
        metrics = post.get("metrics_json")
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        if isinstance(metrics, dict):
            sec = metrics.get("sections") or {}
            if isinstance(sec, dict):
                cap2 = sec.get("caption")
                if cap2: cap = str(cap2).strip()
                # Optionally allow hashtags from metrics if present later
    except Exception:
        pass
    # 3) Build final caption block with hashtags at the end
    if tags:
        return cap + "\n\n" + tags, tags
    return cap, tags

# meta_poster.py

# 1) ensure you still import os, etc. (no need for time now)

def default_image_urls() -> Dict[str,str]:
    base = MEDIA_CDN_BASE.rstrip("/")
    return {
        "square": f"{base}/daily_caption.jpg",
        "stats":  f"{base}/daily_stats.jpg",
        "affects":f"{base}/daily_affects.jpg",
        "play":   f"{base}/daily_playbook.jpg",
    }
# --------------- CLI -----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["post-square", "post-carousel"], help="What to publish")
    ap.add_argument("--date", default=today_in_tz().isoformat(), help="YYYY-MM-DD (defaults to GAIA_TIMEZONE today)")
    ap.add_argument("--platform", default="default", help="daily_posts.platform (default)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = dt.date.fromisoformat(args.date)
    post = sb_select_daily_post(day, platform=args.platform)
    if not post:
        logging.warning("No content.daily_posts found for day=%s platform=%s; trying latest", day, args.platform)
        post = sb_select_latest_post(platform=args.platform)
        if not post:
            logging.error("No content.daily_posts available to post (date or latest)")
            sys.exit(2)
        else:
            try:
                day = dt.date.fromisoformat(post.get("day")) if isinstance(post.get("day"), str) else day
            except Exception:
                pass

    logging.info("Post day=%s platform=%s caption[0:80]=%s", day, args.platform, (post.get("caption") or "")[:80])

    urls = default_image_urls()

    if args.cmd == "post-square":
        caption, _ = derive_caption_and_hashtags(post)
        resp_fb = fb_post_photo(urls["square"], caption, dry_run=args.dry_run)
        logging.info("FB resp: %s", resp_fb)
        # For IG, you can optionally re-post the same square as a photo post:
        # (uncomment to enable)
        ig_photo = session.post(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
            data={"image_url": urls["square"], "caption": caption, "access_token": FB_ACCESS_TOKEN},
            timeout=30
        ).json()
        if not args.dry_run and "id" in ig_photo:
            session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
                         data={"creation_id": ig_photo["id"], "access_token": FB_ACCESS_TOKEN}, timeout=30)
        return

    if args.cmd == "post-carousel":
        caption, _ = derive_caption_and_hashtags(post)  # reuse long caption/hashtags if desired
        image_urls = [urls["stats"], urls["affects"], urls["play"]]
        resp_ig = ig_post_carousel(image_urls, caption, dry_run=args.dry_run)
        logging.info("IG resp: %s", resp_ig)
        return

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Post failed")
        sys.exit(1)
