#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, html, re, random, datetime as dt
from pathlib import Path
from typing import List, Dict, Any
import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

# WP creds
WP_BASE_URL     = os.getenv("WP_BASE_URL","").rstrip("/")
WP_USERNAME     = os.getenv("WP_USERNAME","")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD","")
WP_STATUS       = (os.getenv("WP_STATUS","draft") or "draft").lower()
WP_CATEGORY_ID  = os.getenv("WP_CATEGORY_ID","").strip()
WP_TAG_IDS      = os.getenv("WP_TAG_IDS","").strip()

# Featured image / media settings
MEDIA_CDN_BASE      = os.getenv("MEDIA_CDN_BASE", "").rstrip("/")
WP_FEATURED_SOURCE  = (os.getenv("WP_FEATURED_SOURCE", "bg").lower())  # 'bg' | 'caption' | 'none'
WP_FEATURED_BG_KIND = os.getenv("WP_FEATURED_BG_KIND", "square").strip().lower()  # 'square' | 'tall' | 'wide'
WP_FEATURED_CREDIT  = os.getenv("WP_FEATURED_CREDIT", "Image: Gaia Eyes backgrounds").strip()
# Optional footer CTA
WP_CTA_HTML         = os.getenv("WP_CTA_HTML", "").strip()
# Token for GitHub tree listing fallback (private media repo)
GITHUB_API_TOKEN    = os.getenv("GITHUB_API_TOKEN", "").strip() or os.getenv("GAIAEYES_MEDIA_TOKEN", "").strip()

# Supabase
SUPABASE_REST_URL   = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY= os.getenv("SUPABASE_SERVICE_KEY","").strip()

session = requests.Session()
session.headers.update({
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Accept": "application/json"
})

# --- Media listing helpers (backgrounds) ---
JSDELIVR_RE = re.compile(r"cdn\.jsdelivr\.net/gh/([^/]+)/([^/@]+)(?:@([^/]+))?")

def _parse_jsdelivr_base(base: str):
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

def _list_jsdelivr_paths(owner: str, repo: str, sha: str):
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
                name = f.get("name");
                if not name: continue
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

def _list_github_paths(owner: str, repo: str, sha: str):
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if GITHUB_API_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_API_TOKEN}"
        if sha:
            url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}?recursive=1"
        else:
            url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/heads/main?recursive=1"
        r = session.get(url, headers=headers, timeout=25)
        r.raise_for_status()
        j = r.json(); out=[]
        for node in j.get("tree", []):
            if node.get("type") == "blob":
                out.append("/" + node.get("path",""))
        print(f"[WP] GitHub listed {len(out)} paths")
        return out
    except Exception as e:
        print("[WP] GitHub list error:", e); return []

def pick_background_from_cdn(kind: str = "square") -> str | None:
    if not MEDIA_CDN_BASE:
        return None
    parsed = _parse_jsdelivr_base(MEDIA_CDN_BASE)
    if not parsed: return None
    owner, repo, sha = parsed
    files = _list_jsdelivr_paths(owner, repo, sha)
    if not files:
        print("[WP] jsDelivr returned no file listing; falling back to GitHub API")
        files = _list_github_paths(owner, repo, sha)
    if not files:
        print("[WP] No files found via jsDelivr or GitHub")
        return None
    cand = [p for p in files if p.startswith(f"/backgrounds/{kind}/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    if not cand and kind != "square":
        cand = [p for p in files if p.startswith("/backgrounds/square/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    if not cand:
        print("[WP] No background candidates found")
        return None
    # deterministic daily pick
    dseed = int(dt.datetime.utcnow().strftime("%Y%m%d"))
    random.seed(dseed)
    path = random.choice(cand)
    root = MEDIA_CDN_BASE
    if root.endswith("/images"): root = root[:-7]
    url = f"{root}{path}"
    print(f"[WP] Picked featured background: {url}")
    return url

def wp_upload_image_from_url(image_url: str, filename_hint="featured.jpg") -> int | None:
    try:
        resp = session.get(image_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print("[WP] download image failed:", e); return None
    filename = os.path.basename(image_url.split("?")[0]) or filename_hint
    mime = "image/jpeg"
    lower = filename.lower()
    if lower.endswith(".png"): mime = "image/png"
    elif lower.endswith(".webp"): mime = "image/webp"
    media_endpoint = f"{WP_BASE_URL}/wp-json/wp/v2/media"
    files = {"file": (filename, resp.content, mime)}
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    r = session.post(media_endpoint, auth=wp_auth(), files=files, headers=headers, timeout=45)
    if r.status_code not in (200,201):
        print("[WP] media upload failed:", r.status_code, (r.text or "")[:200])
        return None
    return (r.json() or {}).get("id")

# --- WordPress helpers / diagnostics ---
def wp_verify_credentials(base_url: str, auth: tuple[str, str]) -> None:
    url = f"{base_url}/wp-json/wp/v2/users/me"
    r = session.get(url, auth=auth, timeout=30)
    ct = r.headers.get("content-type", "")
    print(f"[WP] /users/me status={r.status_code} ct={ct}")
    if r.status_code != 200:
        print("[WP] body:", (r.text or "")[:300])
        r.raise_for_status()

def sb_recent_summaries(days=1, limit=8) -> List[Dict[str,Any]]:
    url = f"{SUPABASE_REST_URL}/research_articles"
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
    # join-like via outputs: fetch articles, then get outputs per article
    r = session.get(url, params={
        "select":"id,source,title,url,published_at",
        "published_at": f"gte.{since}",
        "order":"published_at.desc",
        "limit": str(limit)
    }, timeout=20)
    r.raise_for_status()
    arts = r.json() or []
    # fetch outputs per article
    out_url = f"{SUPABASE_REST_URL}/article_outputs"
    for a in arts:
        rr = session.get(out_url, params={
            "select":"output_type,content",
            "article_id": f"eq.{a['id']}"
        }, timeout=20)
        rr.raise_for_status()
        a["outputs"] = rr.json() or []
    return arts

def wp_auth():
    if not (WP_BASE_URL and WP_USERNAME and WP_APP_PASSWORD):
        raise SystemExit("Missing WP_* envs")
    return (WP_USERNAME, WP_APP_PASSWORD)

def wp_create_post(title: str, html_content: str, featured_media: int | None = None) -> dict:
    endpoint = f"{WP_BASE_URL}/wp-json/wp/v2/posts"
    payload = {"title": title, "content": html_content, "status": WP_STATUS}
    if WP_CATEGORY_ID:
        try:
            payload["categories"] = [int(WP_CATEGORY_ID)]
        except:
            pass
    if WP_TAG_IDS:
        try:
            ids = [int(x.strip()) for x in WP_TAG_IDS.split(",") if x.strip().isdigit()]
            if ids:
                payload["tags"] = ids
        except:
            pass
    if featured_media:
        payload["featured_media"] = int(featured_media)

    print(f"[WP] POST {endpoint}")
    r = session.post(endpoint, auth=wp_auth(), json=payload, timeout=45)
    ct = r.headers.get("content-type", "")
    print(f"[WP] create status={r.status_code} ct={ct}")

    try:
        r.raise_for_status()
    except Exception:
        print("[WP] body:", (r.text or "")[:400])
        raise

    try:
        return r.json()
    except Exception:
        print("[WP] non-JSON response body:", (r.text or "")[:400])
        return {"status_code": r.status_code, "text": r.text}

def roundup_html(items: List[Dict[str,Any]]) -> str:
    parts = [f"<p><em>Curated highlights from today’s sources.</em></p>"]
    for a in items:
        parts.append(f'<h3><a href="{html.escape(a["url"])}" target="_blank" rel="noopener">{html.escape(a["title"])}</a></h3>')
        shorts = [o["content"] for o in a["outputs"] if o["output_type"]=="summary_short"]
        longs  = [o["content"] for o in a["outputs"] if o["output_type"]=="summary_long"]
        if shorts:
            parts.append(f"<p>{html.escape(shorts[0])}</p>")
        if longs:
            # lightly format into paragraphs
            for para in longs[0].split("\n\n"):
                parts.append(f"<p>{html.escape(para.strip())}</p>")
        facts = [o["content"] for o in a["outputs"] if o["output_type"]=="fact"][:2]
        if facts:
            parts.append("<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>")
    return "\n".join(parts)

def main():
    items = sb_recent_summaries(days=1, limit=8)
    if not items:
        print("No recent research items.")
        return

    # Preflight auth/URL so failures are obvious
    wp_verify_credentials(WP_BASE_URL, wp_auth())

    today = dt.datetime.utcnow().strftime("%b %d, %Y")
    title = f"Gaia Eyes Research Roundup — {today}"
    html_content = roundup_html(items)

    # Featured image from media backgrounds (or caption/none)
    featured_id = None
    featured_url = None
    if WP_FEATURED_SOURCE == "bg":
        featured_url = pick_background_from_cdn(WP_FEATURED_BG_KIND)
    elif WP_FEATURED_SOURCE == "caption":
        # no caption image in roundup; keep None
        pass

    if featured_url:
        print(f"[WP] Using featured URL: {featured_url}")
        featured_id = wp_upload_image_from_url(featured_url)
        if featured_id:
            print(f"[WP] Featured image uploaded, id={featured_id}")
            # add credit line at top of post for transparency
            if WP_FEATURED_CREDIT:
                html_content = f"<p><em>{html.escape(WP_FEATURED_CREDIT)}</em></p>\n" + html_content
        else:
            print("[WP] Featured upload failed; inlining hero at top")
            html_content = f'<p><img src="{html.escape(featured_url)}" alt="Featured image" style="max-width:100%;height:auto;"/></p>\n' + html_content

    # Optional CTA footer
    if WP_CTA_HTML:
        html_content = html_content + "\n" + WP_CTA_HTML

    created = wp_create_post(title, html_content, featured_media=featured_id)
    link = created.get("link") if isinstance(created, dict) else None
    status = created.get("status") if isinstance(created, dict) else None
    print("WP research post created:", link or "(no JSON link)", "status:", status or created.get("status_code"))

if __name__=="__main__":
    main()
