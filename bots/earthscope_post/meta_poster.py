
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meta Poster (Facebook/Instagram)
Posts Gaia Eyes daily content to FB/IG using the Graph API.

Commands:
  post-square   – posts the square caption card with caption+hashtags
  post-carousel – posts a 3-image carousel (stats, affects, playbook)

Reads caption/hashtags from Supabase content.daily_posts (platform=default),
prefers metrics_json.sections.caption over plain caption, and resolves image URLs
from your media repo (jsDelivr-style CDN by default).
"""
import os, sys, json, logging, argparse, datetime as dt
from typing import Optional, List, Dict
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

# --------- Env / Config ----------
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

# --------- Supabase helpers ----------
def _sb_headers(schema: str = "content") -> Dict[str,str]:
  if not SB_KEY:
    raise RuntimeError("Missing Supabase key in env")
  h = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Accept": "application/json",
  }
  if schema and schema != "public":
    h["Accept-Profile"] = schema
  return h

def sb_select_daily_post(day: dt.date, platform: str = "default") -> Optional[dict]:
  if not SUPABASE_REST_URL:
    return None
  url = f"{SUPABASE_REST_URL}/daily_posts"
  params = {
    "day": f"eq.{day.isoformat()}",
    "platform": f"eq.{platform}",
    "select": "day,platform,caption,hashtags,body_markdown,metrics_json"
  }
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

# --------- Meta (Graph API) ----------
def _require_meta():
  missing = [k for k in ("FB_PAGE_ID","FB_ACCESS_TOKEN","IG_USER_ID") if not os.getenv(k)]
  if missing:
    raise RuntimeError(f"Missing env for Meta posting: {', '.join(missing)}")

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

# --------- Helpers ----------
def today_in_tz() -> dt.date:
  tz = os.getenv("GAIA_TIMEZONE", "America/Chicago")
  try:
    return dt.datetime.now(ZoneInfo(tz)).date()
  except Exception:
    return dt.datetime.utcnow().date()

def default_image_urls() -> Dict[str,str]:
  base = MEDIA_CDN_BASE.rstrip("/")
  return {
    "square": f"{base}/daily_caption.jpg",
    "stats":  f"{base}/daily_stats.jpg",
    "affects":f"{base}/daily_affects.jpg",
    "play":   f"{base}/daily_playbook.jpg",
  }

def derive_caption_and_hashtags(post: dict) -> (str, str):
  """Return (caption, hashtags) preferring structured sections from metrics_json; fallback to plain fields."""
  cap = (post.get("caption") or "").strip()
  tags = (post.get("hashtags") or "").strip()

  # 1) Prefer sections from metrics_json when available
  try:
    metrics = post.get("metrics_json")
    if isinstance(metrics, str):
      metrics = json.loads(metrics)
    if isinstance(metrics, dict):
      sec = metrics.get("sections") or {}
      if isinstance(sec, dict):
        cap2 = sec.get("caption")
        if cap2 and str(cap2).strip():
          cap = str(cap2).strip()
  except Exception:
    pass

  # 2) If the (fallback) caption looks like a JSON blob with "sections", parse it
  if cap.startswith("{") and '"sections"' in cap:
    try:
      j = json.loads(cap)
      sec = j.get("sections") or {}
      if isinstance(sec, dict) and sec.get("caption"):
        cap = sec["caption"].strip()
    except Exception:
      pass

  # 3) Append hashtags
  if tags:
    return cap + "\n\n" + tags, tags
  return cap, tags

# --------- CLI ----------
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
    logging.info("Derived caption (len=%d): %s", len(caption), caption[:160])
    resp_fb = fb_post_photo(urls["square"], caption, dry_run=args.dry_run)
    logging.info("FB resp: %s", resp_fb)
    # Optional: also post the square to IG as a single image
    if not args.dry_run:
      data = {"image_url": urls["square"], "caption": caption, "access_token": FB_ACCESS_TOKEN}
      r = session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media", data=data, timeout=30).json()
      if "id" in r:
        session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
                     data={"creation_id": r["id"], "access_token": FB_ACCESS_TOKEN}, timeout=30)
    return

  if args.cmd == "post-carousel":
    caption, _ = derive_caption_and_hashtags(post)  # reuse same caption/hashtags
    logging.info("Derived caption (len=%d): %s", len(caption), caption[:160])
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
