#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meta Poster (Facebook/Instagram)
Posts Gaia Eyes daily content to FB/IG using the Graph API.

Commands:
  post-square   – posts the square caption card with caption+hashtags
  post-carousel – posts a 3-image carousel (stats, affects, playbook)
  post-carousel-fb – posts the 3-image set to Facebook as a multi-image feed post

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
MEDIA_CDN_BASE      = os.getenv("MEDIA_CDN_BASE", "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/images").rstrip("/")

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
def _require_meta(require_ig: bool = False):
  """Ensure required Meta env vars exist. If require_ig=True, also require IG_USER_ID."""
  missing = []
  if not FB_PAGE_ID:
    missing.append("FB_PAGE_ID")
  if not FB_ACCESS_TOKEN:
    missing.append("FB_ACCESS_TOKEN")
  if require_ig and not IG_USER_ID:
    missing.append("IG_USER_ID")
  if missing:
    raise RuntimeError(f"Missing env for Meta posting: {', '.join(missing)}")

def _ig_wait_finished(container_id: str, timeout_sec: int = 90, interval_sec: int = 3) -> bool:
  """Poll IG container until status_code == FINISHED or timeout."""
  import time
  deadline = time.time() + timeout_sec
  url = f"https://graph.facebook.com/v19.0/{container_id}"
  params = {"fields": "status_code", "access_token": FB_ACCESS_TOKEN}
  last = ""
  while time.time() < deadline:
    r = session.get(url, params=params, timeout=15)
    try:
      j = r.json()
    except Exception:
      j = {}
    status = (j or {}).get("status_code") or ""
    if status and status != last:
      logging.info("IG container %s status: %s", container_id, status)
      last = status
    if status == "FINISHED":
      return True
    if status in ("ERROR", "EXPIRED"):
      logging.error("IG container %s terminal status: %s", container_id, status)
      return False
    time.sleep(interval_sec)
  logging.error("IG container %s not ready after %ss", container_id, timeout_sec)
  return False

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


def fb_post_multi_image(image_urls: List[str], caption: str, dry_run: bool=False) -> dict:
  """
  Publish a multi-image feed post to a Facebook Page.
  Implementation:
    1) Stage each image via /{page-id}/photos with published=false to get media FBIDs.
    2) Create a single /{page-id}/feed post with attached_media[]= {"media_fbid": "..."} for each.
  """
  _require_meta()  # IG not required for FB
  # 1) Stage images
  media_ids: List[str] = []
  for url in image_urls:
    payload = {"url": url, "published": "false", "access_token": FB_ACCESS_TOKEN}
    if dry_run:
      logging.info("[DRY] FB stage photo %s", url)
      media_ids.append("DRY_MEDIA_FBid")
      continue
    r = session.post(f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos", data=payload, timeout=30)
    try:
      j = r.json()
    except Exception:
      j = {}
    if r.status_code != 200 or "id" not in j:
      logging.error("FB stage failed for %s: %s %s", url, r.status_code, (r.text or "")[:200])
      raise RuntimeError("FB stage photo failed")
    media_ids.append(j["id"])

  # 2) Publish feed post with attached_media
  if dry_run:
    logging.info("[DRY] FB multi-image feed message len=%d media_ids=%s", len(caption or ""), media_ids)
    return {"dry": True, "attached_media": media_ids}

  data = {"message": caption or "", "access_token": FB_ACCESS_TOKEN}
  for i, mid in enumerate(media_ids):
    data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

  r = session.post(f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/feed", data=data, timeout=30)
  try:
    return r.json()
  finally:
    if r.status_code != 200:
      logging.error("FB multi-image post failed: %s %s", r.status_code, (r.text or "")[:200])

def ig_post_carousel(image_urls: List[str], caption: str, dry_run: bool=False) -> dict:
  _require_meta(require_ig=True)
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

  if not dry_run:
    if not _ig_wait_finished(creation_id, timeout_sec=90, interval_sec=3):
      return {"error": {"message": "Container not ready", "id": creation_id}}

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
  """Return (caption, hashtags) preferring metrics_json.sections.caption; fallback to plain fields or JSON in caption/body."""
  cap = (post.get("caption") or "")
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
          cap = str(cap2)
  except Exception:
    pass

  # 2) If caption is still a JSON blob, parse once or twice
  def _try_parse_sections(s: str) -> Optional[str]:
    try:
      obj = json.loads(s.lstrip())
      # double-encoded string case
      if isinstance(obj, str) and obj.strip().startswith("{"):
        obj = json.loads(obj)
      if isinstance(obj, dict):
        sec = obj.get("sections") or {}
        if isinstance(sec, dict) and sec.get("caption"):
          return str(sec["caption"])
    except Exception:
      return None
    return None

  cap = cap.strip()
  if cap.startswith("{") and '"sections"' in cap:
    parsed = _try_parse_sections(cap)
    if parsed:
      cap = parsed

  # 3) Fallback: check body_markdown for JSON sections if present
  if (not cap) or (cap.startswith("{") and '"sections"' in cap):
    body = (post.get("body_markdown") or "").strip()
    if body.startswith("{") and '"sections"' in body:
      parsed = _try_parse_sections(body)
      if parsed:
        cap = parsed

  cap = cap.strip()
  if tags:
    return cap + "\n\n" + tags, tags
  return cap, tags

# --------- CLI ----------
def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("cmd", choices=["post-square", "post-carousel", "post-carousel-fb"], help="What to publish")
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
        cid = r["id"]
        if _ig_wait_finished(cid, timeout_sec=90, interval_sec=3):
          session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
                       data={"creation_id": cid, "access_token": FB_ACCESS_TOKEN}, timeout=30)
        else:
          logging.error("IG single-photo container not ready; skipping publish.")
    return

  if args.cmd == "post-carousel":
    caption, _ = derive_caption_and_hashtags(post)  # reuse same caption/hashtags
    logging.info("Derived caption (len=%d): %s", len(caption), caption[:160])
    image_urls = [urls["stats"], urls["affects"], urls["play"]]
    resp_ig = ig_post_carousel(image_urls, caption, dry_run=args.dry_run)
    logging.info("IG resp: %s", resp_ig)
    return

  if args.cmd == "post-carousel-fb":
    caption, _ = derive_caption_and_hashtags(post)
    logging.info("Derived caption (len=%d): %s", len(caption), caption[:160])
    image_urls = [urls["stats"], urls["affects"], urls["play"]]
    resp_fb = fb_post_multi_image(image_urls, caption, dry_run=args.dry_run)
    logging.info("FB resp: %s", resp_fb)
    return

if __name__ == "__main__":
  try:
    main()
  except Exception:
    logging.exception("Post failed")
    sys.exit(1)
