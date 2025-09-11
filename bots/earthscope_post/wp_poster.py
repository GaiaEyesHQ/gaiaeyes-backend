#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, datetime as dt
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")  # also load repo root if needed

# --- WordPress credentials (Application Password) ---
WP_BASE_URL   = os.getenv("WP_BASE_URL", "").rstrip("/")   # e.g. https://yourdomain.com
WP_USERNAME   = os.getenv("WP_USERNAME", "")
WP_APP_PASS   = os.getenv("WP_APP_PASSWORD", "")           # 24-char app password
WP_CATEGORY_ID= os.getenv("WP_CATEGORY_ID", "")            # optional numeric category id
WP_TAGS       = os.getenv("WP_TAGS", "gaia eyes, space weather").split(",")

# --- Supabase (to fetch daily post content) ---
SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY","").strip()
GAIA_TIMEZONE = os.getenv("GAIA_TIMEZONE","America/Chicago")

# --- Media CDN (jsDelivr with commit SHA or your CDN) ---
MEDIA_CDN_BASE = os.getenv("MEDIA_CDN_BASE","").rstrip("/")

def today_in_tz(tz: str) -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return dt.datetime.utcnow().date()

def sb_headers(schema="content") -> Dict[str,str]:
    h = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Accept":"application/json"}
    if schema and schema != "public":
        h["Accept-Profile"] = schema
    return h

def fetch_daily_post(day: dt.date, platform="default") -> Optional[dict]:
    if not (SUPABASE_REST_URL and SUPABASE_SERVICE_KEY):
        return None
    url = f"{SUPABASE_REST_URL}/daily_posts"
    params = {
        "select":"day,platform,title,caption,body_markdown,hashtags,metrics_json",
        "day": f"eq.{day.isoformat()}",
        "platform": f"eq.{platform}",
        "limit": "1"
    }
    r = requests.get(url, headers=sb_headers("content"), params=params, timeout=20)
    if r.status_code != 200: return None
    data = r.json()
    if data: return data[0]
    # fallback to latest
    r = requests.get(url, headers=sb_headers("content"),
                     params={"select":"day,platform,title,caption,body_markdown,hashtags,metrics_json",
                             "platform": f"eq.{platform}", "order":"day.desc", "limit":"1"}, timeout=20)
    if r.status_code != 200: return None
    data = r.json()
    return data[0] if data else None

def html_escape(s: str) -> str:
    import html
    return html.escape(s, quote=True)

def md_to_html(md: str) -> str:
    """
    Minimal markdown-to-HTML for our sections.
    """
    if not md: return ""
    # headers **Title:** → <h3>Title</h3>
    out = []
    for line in md.splitlines():
        t = line.strip()
        if not t:
            out.append("<br/>")
            continue
        # bullets starting with •
        if t.startswith("• "):
            out.append(f"<li>{html_escape(t[2:])}</li>")
            continue
        # headings like "Space Weather Snapshot —" or bold "How This Affects You:"
        if t.endswith(":") and not t.startswith("•"):
            out.append(f"<h3>{html_escape(t[:-1])}</h3>")
            continue
        out.append(f"<p>{html_escape(t)}</p>")
    # wrap loose <li> into <ul>
    html_join = "\n".join(out)
    html_join = html_join.replace("\n<li>","<ul>\n<li>",1) if "<li>" in html_join else html_join
    if "<li>" in html_join and not html_join.rstrip().endswith("</ul>"):
        html_join = html_join + "\n</ul>"
    return html_join

def build_post_html(post: dict) -> str:
    day = post.get("day")
    title = post.get("title") or "GAIA EYES • Daily Earthscope"
    caption = (post.get("caption") or "").strip()
    body_md = (post.get("body_markdown") or "").strip()
    hashtags = (post.get("hashtags") or "").strip()

    # Build hero image (square) and links to tall cards
    square = f"{MEDIA_CDN_BASE}/daily_caption.jpg" if MEDIA_CDN_BASE else ""
    stats  = f"{MEDIA_CDN_BASE}/daily_stats.jpg" if MEDIA_CDN_BASE else ""
    affects= f"{MEDIA_CDN_BASE}/daily_affects.jpg" if MEDIA_CDN_BASE else ""
    play   = f"{MEDIA_CDN_BASE}/daily_playbook.jpg" if MEDIA_CDN_BASE else ""

    parts = []
    if square:
        parts.append(f'<p><img src="{html_escape(square)}" alt="Gaia Eyes Daily Earthscope" style="max-width:100%;height:auto;"/></p>')

    # Caption paragraph
    if caption:
        parts.append(f"<p>{html_escape(caption)}</p>")

    # Convert markdown sections to HTML
    if body_md:
        parts.append(md_to_html(body_md))

    # Links to tall cards
    links = []
    if stats:   links.append(f'<a href="{html_escape(stats)}">Today’s Metrics</a>')
    if affects: links.append(f'<a href="{html_escape(affects)}">How This Affects You</a>')
    if play:    links.append(f'<a href="{html_escape(play)}">Self-Care Playbook</a>')
    if links:
        parts.append("<p>" + " • ".join(links) + "</p>")

    if hashtags:
        parts.append(f"<p><em>{html_escape(hashtags)}</em></p>")

    return "\n".join(parts)

def wp_auth() -> tuple[str,str]:
    if not (WP_BASE_URL and WP_USERNAME and WP_APP_PASS):
        raise SystemExit("Missing WP_BASE_URL / WP_USERNAME / WP_APP_PASSWORD")
    return WP_USERNAME, WP_APP_PASS

def wp_upload_image(image_url: str) -> Optional[int]:
    """
    Download image by URL and upload to WP media. Returns media ID or None.
    """
    try:
        r = requests.get(image_url, timeout=30)
        r.raise_for_status()
    except Exception:
        return None
    filename = os.path.basename(image_url.split("?")[0]) or "gaiaeyes.jpg"
    media_endpoint = f"{WP_BASE_URL}/wp-json/wp/v2/media"
    files = {"file": (filename, r.content, "image/jpeg")}
    auth = wp_auth()
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    resp = requests.post(media_endpoint, auth=auth, files=files, headers=headers, timeout=40)
    if resp.status_code not in (200,201):
        return None
    media = resp.json()
    return media.get("id")

def wp_create_post(title: str, html: str, featured_media: Optional[int]=None) -> dict:
    endpoint = f"{WP_BASE_URL}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": html,
        "status": "publish",
    }
    if WP_CATEGORY_ID:
        try: payload["categories"] = [int(WP_CATEGORY_ID)]
        except: pass
    if WP_TAGS:
        # you can pre-create tags and map names to IDs if you prefer; for now attach names as plaintext in content
        pass
    if featured_media:
        payload["featured_media"] = int(featured_media)

    resp = requests.post(endpoint, auth=wp_auth(), json=payload, timeout=40)
    resp.raise_for_status()
    return resp.json()

def main():
    day = today_in_tz(GAIA_TIMEZONE)
    post = fetch_daily_post(day) or fetch_daily_post(today_in_tz("UTC"))  # fallback
    if not post:
        print("No daily post found in Supabase.")
        sys.exit(0)

    # Title for WordPress
    title_date = dt.datetime.strptime(post["day"], "%Y-%m-%d").strftime("%b %d, %Y")
    title = f"GAIA EYES • Daily Earthscope — {title_date}"

    html = build_post_html(post)

    # Option A: hotlink caption card (no upload)
    featured_id = None

    # Option B: upload square and set as featured image (uncomment to enable)
    # if MEDIA_CDN_BASE:
    #     img_id = wp_upload_image(f"{MEDIA_CDN_BASE}/daily_caption.jpg")
    #     if img_id: featured_id = img_id

    created = wp_create_post(title, html, featured_media=featured_id)
    print("WP post created:", created.get("link"))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
