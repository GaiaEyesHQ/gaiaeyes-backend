#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, time, html, re
import datetime as dt
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
from urllib.parse import urlparse
import urllib.parse as _uparse

import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

# -------- WordPress / Posting controls --------
WP_BASE_URL     = os.getenv("WP_BASE_URL","").rstrip("/")
WP_USERNAME     = os.getenv("WP_USERNAME","")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD","")
WP_STATUS       = (os.getenv("WP_STATUS","draft") or "draft").lower()  # "draft" or "publish"
WP_CATEGORY_ID  = os.getenv("WP_CATEGORY_ID","").strip()
WP_TAG_IDS      = os.getenv("WP_TAG_IDS","").strip()  # e.g., "12,34,56"
WP_INLINE_IMAGES= (os.getenv("WP_INLINE_IMAGES","true").lower() in ("1","true","yes"))
WP_UPLOAD_INLINE= (os.getenv("WP_UPLOAD_INLINE","false").lower() in ("1","true","yes"))
WP_CTA_HTML     = os.getenv("WP_CTA_HTML","").strip()  # optional HTML appended at bottom

WP_FEATURED_SOURCE = (os.getenv("WP_FEATURED_SOURCE", "bg").lower())  # bg | caption | none
WP_FEATURED_CREDIT = os.getenv("WP_FEATURED_CREDIT", "Credit: ESA/Hubble").strip()
WP_ADD_TOC        = (os.getenv("WP_ADD_TOC", "false").lower() in ("1","true","yes"))
WP_INCLUDE_BODY  = (os.getenv("WP_INCLUDE_BODY", "false").lower() in ("1","true","yes"))
WP_FEATURED_BG_KIND = os.getenv("WP_FEATURED_BG_KIND", "square").strip().lower()  # square|tall|wide

WP_ALT_USERNAME = os.getenv("WP_ALT_USERNAME", "").strip()
_SELECTED_AUTH: Optional[tuple[str,str]] = None

# -------- Supabase --------
SUPABASE_REST_URL   = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY= os.getenv("SUPABASE_SERVICE_KEY","").strip()
GAIA_TIMEZONE       = os.getenv("GAIA_TIMEZONE","America/Chicago")

# -------- Media (CDN) --------
MEDIA_CDN_BASE  = os.getenv("MEDIA_CDN_BASE","").rstrip("/")
UTM_QUERY       = os.getenv("UTM_QUERY","").strip()  # e.g. ?utm_source=wp...

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.7, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

def today_in_tz(tz: str) -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return dt.datetime.utcnow().date()

def fetch_esa_featured_url() -> Optional[str]:
    """ESA source disabled — using backgrounds from media repo."""
    print("[WP] ESA featured source disabled; using MEDIA_CDN_BASE backgrounds.")
    return None

JSDELIVR_RE = re.compile(r"cdn\.jsdelivr\.net/gh/([^/]+)/([^/@]+)(?:@([^/]+))?")

def _parse_jsdelivr_base(base: str) -> Optional[tuple[str,str,str]]:
    """Extract (owner, repo, sha) from MEDIA_CDN_BASE like
       https://cdn.jsdelivr.net/gh/OWNER/REPO@SHA/images (sha optional)"""
    try:
        m = JSDELIVR_RE.search(base)
        if not m:
            print(f"[WP] MEDIA_CDN_BASE not parseable for jsDelivr: {base}")
            return None
        owner, repo, sha = m.group(1), m.group(2), (m.group(3) or "")
        if sha:
            print(f"[WP] MEDIA_CDN_BASE parsed: owner={owner} repo={repo} sha={sha}")
        else:
            print(f"[WP] MEDIA_CDN_BASE parsed (no @sha): owner={owner} repo={repo}")
        return owner, repo, sha
    except Exception as e:
        print("[WP] MEDIA_CDN_BASE parse error:", e)
        return None

def _list_jsdelivr_paths(owner: str, repo: str, sha: str) -> List[str]:
    """Return list of file paths in the repo@sha using jsDelivr data API."""
    try:
        if sha:
            url = f"https://data.jsdelivr.com/v1/package/gh/{owner}/{repo}@{sha}"
        else:
            url = f"https://data.jsdelivr.com/v1/package/gh/{owner}/{repo}"
        r = session.get(url, timeout=25)
        r.raise_for_status()
        j = r.json()
        out = []
        def walk(files, prefix=""):
            for f in files:
                name = f.get("name")
                if not name:
                    continue
                path = f"{prefix}/{name}"
                if f.get("type") == "file":
                    out.append(path)
                elif f.get("type") == "directory":
                    walk(f.get("files", []), path)
        walk(j.get("files", []), "")
        print(f"[WP] jsDelivr listed {len(out)} paths")
        return out
    except Exception as e:
        print("[WP] jsDelivr list error:", e)
        return []

def pick_background_from_cdn(kind: str = "square") -> Optional[str]:
    """Pick a background image URL from backgrounds/{kind} using MEDIA_CDN_BASE root."""
    if not MEDIA_CDN_BASE:
        return None
    parsed = _parse_jsdelivr_base(MEDIA_CDN_BASE)
    if not parsed:
        print("[WP] MEDIA_CDN_BASE not parseable for jsDelivr")
        return None
    owner, repo, sha = parsed
    files = _list_jsdelivr_paths(owner, repo, sha)
    if not files:
        print("[WP] jsDelivr returned no file listing")
        return None
    # Collect image paths under backgrounds/kind
    cand = [p for p in files if p.startswith(f"/backgrounds/{kind}/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    if not cand and kind != "square":
        cand = [p for p in files if p.startswith("/backgrounds/square/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    print(f"[WP] Background candidates for kind='{kind}': {len(cand)}")
    if not cand:
        return None
    # Deterministic daily pick
    try:
        from zoneinfo import ZoneInfo
        dseed = int(dt.datetime.now(ZoneInfo(GAIA_TIMEZONE)).strftime("%Y%m%d"))
    except Exception:
        dseed = int(dt.datetime.utcnow().strftime("%Y%m%d"))
    random.seed(dseed)
    path = random.choice(cand)
    # Build full CDN URL: derive repo root from MEDIA_CDN_BASE (strip trailing /images)
    root = MEDIA_CDN_BASE
    if root.endswith("/images"):
        root = root[:-7]
    url = f"{root}{path}"
    print(f"[WP] Picked featured background: {url}")
    return url

# ---------------- Supabase helpers ----------------
def sb_headers(schema: str = "content") -> Dict[str,str]:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/json"
    }
    if schema and schema != "public":
        h["Accept-Profile"] = schema
    return h

def fetch_daily_post(day: dt.date, platform="default") -> Optional[dict]:
    if not (SUPABASE_REST_URL and SUPABASE_SERVICE_KEY):
        return None
    url = f"{SUPABASE_REST_URL}/daily_posts"
    params = {
        "select": ",".join([
            "day","platform","title","caption","body_markdown","hashtags","metrics_json"
        ]),
        "day": f"eq.{day.isoformat()}",
        "platform": f"eq.{platform}",
        "limit": "1"
    }
    r = session.get(url, headers=sb_headers("content"), params=params, timeout=25)
    if r.status_code != 200:
        print("[SB] posts fetch failed:", r.status_code, r.text[:200])
        return None
    data = r.json()
    if data: return data[0]

    # fallback to latest
    r = session.get(url, headers=sb_headers("content"),
                    params={"select":"day,platform,title,caption,body_markdown,hashtags,metrics_json",
                            "platform": f"eq.{platform}", "order":"day.desc", "limit":"1"},
                    timeout=25)
    if r.status_code != 200:
        print("[SB] latest posts fetch failed:", r.status_code, r.text[:200])
        return None
    data = r.json()
    return data[0] if data else None

# ---------------- WordPress helpers ----------------
def wp_auth() -> tuple[str,str]:
    global _SELECTED_AUTH
    if _SELECTED_AUTH:
        return _SELECTED_AUTH
    user = (WP_USERNAME or "").strip()
    pwd  = (WP_APP_PASSWORD or "").strip()
    if not (WP_BASE_URL and user and pwd):
        raise SystemExit("Missing WP_BASE_URL / WP_USERNAME / WP_APP_PASSWORD")
    return user, pwd

def wp_verify_credentials():
    global _SELECTED_AUTH
    # Try primary
    u, p = wp_auth()
    url = f"{WP_BASE_URL}/wp-json/wp/v2/users/me"
    resp = session.get(url, auth=(u, p), timeout=20)
    if resp.status_code == 200:
        _SELECTED_AUTH = (u, p)
        return
    # If invalid_username and alt provided, try alternate username
    body = resp.text[:300]
    if resp.status_code == 401 and WP_ALT_USERNAME:
        altu = WP_ALT_USERNAME.strip()
        resp2 = session.get(url, auth=(altu, p), timeout=20)
        if resp2.status_code == 200:
            _SELECTED_AUTH = (altu, p)
            return
        print("[WP] Auth failed (alt username):", resp2.status_code, resp2.text[:300])
        resp2.raise_for_status()
    print("[WP] Auth failed:", resp.status_code, body)
    resp.raise_for_status()

def wp_upload_image_from_url(image_url: str, filename_hint="gaiaeyes.jpg") -> Optional[int]:
    try:
        r = session.get(image_url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print("[WP] download image failed:", e)
        return None
    filename = os.path.basename(image_url.split("?")[0]) or filename_hint
    media_endpoint = f"{WP_BASE_URL}/wp-json/wp/v2/media"
    mime = "image/jpeg"
    lower = filename.lower()
    if lower.endswith(".png"): mime = "image/png"
    elif lower.endswith(".webp"): mime = "image/webp"
    files = {"file": (filename, r.content, mime)}
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    resp = session.post(media_endpoint, auth=wp_auth(), files=files, headers=headers, timeout=45)
    if resp.status_code not in (200,201):
        print("[WP] media upload failed:", resp.status_code, resp.text[:200])
        return None
    media = resp.json()
    return media.get("id")

def wp_create_post(title: str, html_content: str, featured_media: Optional[int] = None) -> dict:
    endpoint = f"{WP_BASE_URL}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": html_content,
        "status": WP_STATUS,  # draft or publish
    }
    if WP_CATEGORY_ID:
        try: payload["categories"] = [int(WP_CATEGORY_ID)]
        except: pass
    if WP_TAG_IDS:
        try:
            ids = [int(x.strip()) for x in WP_TAG_IDS.split(",") if x.strip().isdigit()]
            if ids: payload["tags"] = ids
        except: pass
    if featured_media:
        payload["featured_media"] = int(featured_media)

    # one retry on transient failures
    for attempt in (1,2):
        resp = session.post(endpoint, auth=wp_auth(), json=payload, timeout=45)
        if resp.status_code in (200,201):
            return resp.json()
        if resp.status_code in (429,500,502,503,504) and attempt == 1:
            time.sleep(3)
            continue
        print("[WP] create post failed:", resp.status_code, resp.text[:300])
        resp.raise_for_status()

# ---------------- HTML formatting ----------------
def slugify(txt: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\- ]+","", txt).strip().lower()
    s = s.replace(" ","-")
    return s[:64] or "section"

def p(s: str) -> str:
    return f"<p>{html.escape(s)}</p>"

def bullet_ul(lines: List[str]) -> str:
    items = "\n".join(f"<li>{html.escape(x)}</li>" for x in lines if x.strip())
    return f"<ul>\n{items}\n</ul>"

def build_toc_from_md(md: str) -> str:
    if not md or not WP_ADD_TOC:
        return ""
    heads = []
    for line in md.splitlines():
        t = line.strip()
        if t and t.endswith(":") and not t.startswith("•"):
            head = t[:-1].strip(" *")
            heads.append(head)
    if not heads:
        return ""
    items = "\n".join(f'<li><a href="#{slugify(h)}">{html.escape(h)}</a></li>' for h in heads)
    return f"<div class=\"toc\"><strong>On this page</strong><ul>\n{items}\n</ul></div>"

def md_to_clean_html(md: str) -> str:
    """
    Minimal markdown-to-HTML for our sections:
    - Headings → <h3 id="...">
    - Bullets → <ul>
    - Plain lines → <p>
    """
    if not md: return ""
    out = []
    buf_bullets = []
    def flush_bullets():
        nonlocal buf_bullets
        if buf_bullets:
            out.append(bullet_ul(buf_bullets)); buf_bullets = []

    for line in md.splitlines():
        t = line.strip()
        if not t:
            flush_bullets()
            continue
        # Bullet lines start with "• "
        if t.startswith("• "):
            buf_bullets.append(t[2:].strip())
            continue
        # Heading lines end with ":" and aren't bullets
        if t.endswith(":") and not t.startswith("•"):
            flush_bullets()
            head = t[:-1].strip(" *")  # remove trailing colon/bold
            out.append(f'<h3 id="{slugify(head)}">{html.escape(head)}</h3>')
            continue
        # Default paragraph
        flush_bullets()
        out.append(p(t))
    flush_bullets()
    return "\n".join(out)

def build_title(day_iso: str) -> str:
    try:
        d = dt.datetime.strptime(day_iso, "%Y-%m-%d")
    except Exception:
        return "GAIA EYES • Daily Earthscope"
    return f"GAIA EYES • Daily Earthscope — {d.strftime('%b %d, %Y')}"

def metrics_alt_text(metrics_json: Any) -> str:
    try:
        m = metrics_json if isinstance(metrics_json, dict) else json.loads(metrics_json or "{}")
    except Exception:
        m = {}
    pieces = []
    if m.get("kp_max_24h") is not None:
        pieces.append(f"Kp max {m['kp_max_24h']}")
    if m.get("solar_wind_kms") is not None:
        pieces.append(f"SW {round(float(m['solar_wind_kms']))} km/s")
    if m.get("schumann_value_hz") is not None:
        pieces.append(f"Schumann {round(float(m['schumann_value_hz']),2)} Hz")
    if m.get("flares_24h") is not None:
        pieces.append(f"Flares {int(m['flares_24h'])}")
    if m.get("cmes_24h") is not None:
        pieces.append(f"CMEs {int(m['cmes_24h'])}")
    return "Gaia Eyes daily — " + ", ".join(pieces) if pieces else "Gaia Eyes daily"

def build_post_html(post: dict, inline_images: bool, upload_inline: bool) -> (str, Optional[int]):
    """
    Returns (html, featured_media_id). Featured image is always uploaded from the square card.
    Inline tall images are hotlinked by default; can be uploaded if upload_inline=True.
    """
    title = post.get("title") or "GAIA EYES • Daily Earthscope"
    caption = (post.get("caption") or "").strip()
    body_md = (post.get("body_markdown") or "").strip()
    hashtags = (post.get("hashtags") or "").strip()
    metrics = post.get("metrics_json")

    # derive URLs
    base = MEDIA_CDN_BASE.rstrip("/")
    q = UTM_QUERY or ""
    square_url  = f"{base}/daily_caption.jpg{q}" if base else ""
    stats_url   = f"{base}/daily_stats.jpg{q}" if base else ""
    affects_url = f"{base}/daily_affects.jpg{q}" if base else ""
    play_url    = f"{base}/daily_playbook.jpg{q}" if base else ""

    featured_id = None
    featured_url = None
    if WP_FEATURED_SOURCE == "bg":
        featured_url = pick_background_from_cdn(WP_FEATURED_BG_KIND)
    elif WP_FEATURED_SOURCE == "caption":
        featured_url = square_url
    # else: none
    if featured_url:
        print(f"[WP] Using featured URL: {featured_url}")
        featured_id = wp_upload_image_from_url(featured_url, filename_hint="featured.jpg")
        if featured_id:
            print(f"[WP] Featured image uploaded, id={featured_id}")
        else:
            print("[WP] Featured image upload skipped/failed — will inline featured at top")

    parts = []
    # If featured upload failed but we have a URL, inline it at the top as a visible hero
    if featured_id is None and featured_url:
        parts.append(f'<p><img src="{html.escape(featured_url)}" alt="Featured image" style="max-width:100%;height:auto;"/></p>')
    # Credit line for optional bg credit
    if WP_FEATURED_SOURCE == "bg":
        credit = WP_FEATURED_CREDIT or "Image: Gaia Eyes backgrounds"
        parts.append(f"<p><em>{html.escape(credit)}</em></p>")
    # Optional TOC
    toc_html = build_toc_from_md(body_md)
    if toc_html:
        parts.append(toc_html)

    # Caption paragraph
    if caption:
        parts.append(p(caption))

    # Body markdown → clean HTML (only if enabled)
    if WP_INCLUDE_BODY and body_md:
        parts.append(md_to_clean_html(body_md))

    # Inline tall images (gallery-like)
    if inline_images:
        figures = []
        if stats_url:
            figures.append(f'<figure><img src="{html.escape(stats_url)}" alt="{html.escape(metrics_alt_text(metrics))}" style="max-width:100%;height:auto;"/><figcaption>Today’s Metrics</figcaption></figure>')
        if affects_url:
            figures.append(f'<figure><img src="{html.escape(affects_url)}" alt="How This Affects You" style="max-width:100%;height:auto;"/><figcaption>How This Affects You</figcaption></figure>')
        if play_url:
            figures.append(f'<figure><img src="{html.escape(play_url)}" alt="Self-Care Playbook" style="max-width:100%;height:auto;"/><figcaption>Self-Care Playbook</figcaption></figure>')
        if figures:
            parts.append("<hr/>" + "\n".join(figures))

    # CTA at the end (optional)
    if WP_CTA_HTML:
        parts.append(WP_CTA_HTML)

    # Hashtags (light)
    if hashtags:
        parts.append(f"<p><em>{html.escape(hashtags)}</em></p>")

    return ("\n".join(parts)), featured_id

def main():
    # Preflight auth
    wp_verify_credentials()

    # Pull today's post (tz-aware, fallback to UTC)
    day = today_in_tz(GAIA_TIMEZONE)
    post = fetch_daily_post(day) or fetch_daily_post(today_in_tz("UTC"))
    if not post:
        print("No daily post found in Supabase.")
        sys.exit(0)

    title = build_title(post.get("day") or day.isoformat())
    html_content, featured_id = build_post_html(
        post,
        inline_images=WP_INLINE_IMAGES,
        upload_inline=WP_UPLOAD_INLINE
    )

    created = wp_create_post(title, html_content, featured_media=featured_id)
    print("WP post created:", created.get("link"), "status:", created.get("status"))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
