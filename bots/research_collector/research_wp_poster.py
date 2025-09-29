#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Dict, Any
from pathlib import Path

import os, sys, html, re, random, datetime as dt
import json

# --- Markdown sanitizer utilities ---
MD_HEAD_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
MD_ITALIC_RE = re.compile(r"\*(.+?)\*|_(.+?)_")

def strip_markdown_syntax(txt: str) -> str:
    if not isinstance(txt, str):
        return ""
    s = MD_HEAD_RE.sub("", txt)
    s = MD_BOLD_RE.sub(r"\1", s)
    s = MD_ITALIC_RE.sub(lambda m: m.group(1) or (m.group(2) or ""), s)
    s = re.sub(r"^\s*[-•*]\s+", "", s, flags=re.M)
    return s
RELEVANT_RE = re.compile(r"(aurora|geomagnetic|kp\b|solar wind|cme|flare|sunspot|coronal hole|schumann|magnetosphere|ionosphere|hrv|coherence|eeg|emf|0\.1\s*hz|autonomic|vagal)", re.I)
def sb_today_metrics() -> Dict[str, Any] | None:
    url = f"{SUPABASE_REST_URL}/marts.space_weather_daily"
    today = dt.datetime.utcnow().date().isoformat()
    r = session.get(url, params={"select":"day,kp_max,bz_min,sw_speed_avg","day":f"eq.{today}"}, timeout=20)
    if r.status_code != 200:
        return None
    j = r.json() or []
    if j:
        return j[0]
    # fallback to yesterday if today sparse
    y = (dt.datetime.utcnow().date() - dt.timedelta(days=1)).isoformat()
    r2 = session.get(url, params={"select":"day,kp_max,bz_min,sw_speed_avg","day":f"eq.{y}"}, timeout=20)
    if r2.status_code != 200:
        return None
    jj = r2.json() or []
    return jj[0] if jj else None

def _is_relevant_item(a: Dict[str,Any]) -> bool:
    """Basic on-mission filter for roundup display.
    Uses title and any output text to keep only space-weather/frequency/physiology items."""
    title = a.get("title") or ""
    blob = [title]
    for o in a.get("outputs", []):
        if o.get("output_type") in ("summary_short","summary_long"):
            blob.append(o.get("content",""))
    text = "\n".join(blob)
    return bool(RELEVANT_RE.search(text))
import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

# WP creds
WP_BASE_URL     = os.getenv("WP_BASE_URL","").rstrip("/")
WP_USERNAME     = os.getenv("WP_USERNAME","")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD","")
WP_STATUS       = (os.getenv("WP_STATUS","publish") or "publish").lower()
WP_CATEGORY_ID  = os.getenv("WP_CATEGORY_ID","").strip()
WP_TAG_IDS      = os.getenv("WP_TAG_IDS","").strip()

# Optional category by slug and title prefix (allow reusing this poster for multiple lanes)
WP_CATEGORY_SLUG = os.getenv("WP_CATEGORY_SLUG","").strip().lower()
WP_TITLE_PREFIX  = os.getenv("WP_TITLE_PREFIX","").strip()
SUMMARY_MODE     = os.getenv("SUMMARY_MODE","").strip().lower()  # "news" | "evergreen" | ""

# Featured image / media settings
MEDIA_CDN_BASE      = os.getenv("MEDIA_CDN_BASE", "").rstrip("/")
WP_FEATURED_SOURCE  = (os.getenv("WP_FEATURED_SOURCE", "bg").lower())  # 'bg' | 'caption' | 'none'
WP_FEATURED_BG_KIND = os.getenv("WP_FEATURED_BG_KIND", "square").strip().lower()  # 'square' | 'tall' | 'wide'
WP_FEATURED_CREDIT  = os.getenv("WP_FEATURED_CREDIT", "Image: Gaia Eyes backgrounds").strip()
# Optional footer CTA
WP_CTA_HTML         = os.getenv("WP_CTA_HTML", "").strip()
# Token for GitHub tree listing fallback (private media repo)
GITHUB_API_TOKEN    = os.getenv("GITHUB_API_TOKEN", "").strip() or os.getenv("GAIAEYES_MEDIA_TOKEN", "").strip()

# Add a small table of contents by default
WP_ADD_TOC         = (os.getenv("WP_ADD_TOC", "true").lower() in ("1","true","yes"))
WP_LOOKBACK_DAYS  = int(os.getenv("WP_LOOKBACK_DAYS", "3"))

# Gallery injection controls
WP_GALLERY_ENABLE = (os.getenv("WP_GALLERY_ENABLE","1").strip().lower() in ("1","true","yes","on"))
WP_GALLERY_KIND   = os.getenv("WP_GALLERY_KIND","wide").strip().lower()    # 'wide' | 'tall' | 'square'
WP_GALLERY_COUNT  = int(os.getenv("WP_GALLERY_COUNT","3"))

# Supabase
SUPABASE_REST_URL   = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY= os.getenv("SUPABASE_SERVICE_KEY","").strip()

session = requests.Session()
session.headers.update({
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Accept": "application/json"
})

# --- Category slug resolver ---
def wp_resolve_category_id(slug: str) -> str | None:
    if not (WP_BASE_URL and slug):
        return None
    try:
        url = f"{WP_BASE_URL}/wp-json/wp/v2/categories"
        r = session.get(url, params={"slug": slug}, auth=wp_auth(), timeout=30)
        if r.status_code != 200:
            print("[WP] resolve category slug failed:", r.status_code, (r.text or "")[:200])
            return None
        arr = r.json() or []
        if arr and isinstance(arr, list):
            cid = str(arr[0].get("id"))
            print(f"[WP] resolved category '{slug}' -> id {cid}")
            return cid
    except Exception as e:
        print("[WP] resolve category error:", e)
    return None

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

def pick_background_from_cdn(kind: str = "square") -> tuple[str|None, str|None, str|None, str|None, str|None]:
    """Return (owner, repo, sha, path, cdn_url) or (None,... ) on failure."""
    if not MEDIA_CDN_BASE:
        return None, None, None, None, None
    parsed = _parse_jsdelivr_base(MEDIA_CDN_BASE)
    if not parsed: return None, None, None, None, None
    owner, repo, sha = parsed
    files = _list_jsdelivr_paths(owner, repo, sha)
    if not files:
        print("[WP] jsDelivr returned no file listing; falling back to GitHub API")
        files = _list_github_paths(owner, repo, sha)
    if not files:
        print("[WP] No files found via jsDelivr or GitHub")
        return None, None, None, None, None
    cand = [p for p in files if p.startswith(f"/backgrounds/{kind}/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    if not cand and kind != "square":
        cand = [p for p in files if p.startswith("/backgrounds/square/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    if not cand:
        print("[WP] No background candidates found")
        return None, None, None, None, None
    # deterministic daily pick
    dseed = int(dt.datetime.utcnow().strftime("%Y%m%d"))
    random.seed(dseed)
    path = random.choice(cand)
    root = MEDIA_CDN_BASE
    if root.endswith("/images"): root = root[:-7]
    url = f"{root}{path}"
    print(f"[WP] Picked featured background: {url}")
    return owner, repo, sha, path, url

# --- Gallery helpers ---
def pick_backgrounds_from_cdn(kind: str = "wide", count: int = 3) -> list[str]:
    """
    Return a list of CDN URLs for background images of the requested kind.
    Falls back to 'square' if none found. Deterministic daily selection.
    """
    if not MEDIA_CDN_BASE:
        return []
    parsed = _parse_jsdelivr_base(MEDIA_CDN_BASE)
    if not parsed:
        return []
    owner, repo, sha = parsed
    files = _list_jsdelivr_paths(owner, repo, sha)
    if not files:
        files = _list_github_paths(owner, repo, sha)
    if not files:
        return []
    cand = [p for p in files if p.startswith(f"/backgrounds/{kind}/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    if not cand and kind != "square":
        cand = [p for p in files if p.startswith("/backgrounds/square/") and p.lower().endswith((".jpg",".jpeg",".png",".webp"))]
    if not cand:
        return []
    # daily-deterministic shuffle
    dseed = int(dt.datetime.utcnow().strftime("%Y%m%d"))
    random.seed(dseed)
    random.shuffle(cand)
    chosen = cand[:max(0, int(count))]
    root = MEDIA_CDN_BASE
    if root.endswith("/images"):
        root = root[:-7]
    return [f"{root}{p}" for p in chosen]

def inject_gallery_block(html_content: str, urls: list[str]) -> str:
    """Insert a simple gallery of images after the first H2/H3 or at top if none."""
    if not urls:
        return html_content
    gallery_block = "\n".join(
        f'<!-- wp:image {{"id":0,"sizeSlug":"large"}} --><figure class="wp-block-image size-large"><img src="{html.escape(u)}" alt=""/></figure><!-- /wp:image -->'
        for u in urls
    )
    if "</h2>" in html_content:
        return html_content.replace("</h2>", "</h2>\n" + gallery_block, 1)
    if "</h3>" in html_content:
        return html_content.replace("</h3>", "</h3>\n" + gallery_block, 1)
    return gallery_block + "\n" + html_content

def wp_upload_image_from_url(image_url: str, filename_hint="featured.jpg", dl_headers: dict | None = None) -> tuple[int|None, str|None]:
    try:
        resp = session.get(image_url, headers=dl_headers or {}, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print("[WP] download image failed:", e); return None, None
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
        return None, None
    j = r.json() or {}
    return j.get("id"), j.get("source_url") or j.get("guid", {}).get("rendered")

# --- TOC helpers ---

def slugify(txt: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\- ]+", "", txt).strip().lower()
    s = re.sub(r"\s+", "-", s)
    return s[:64] or "section"

def build_toc_and_inject_ids(html_content: str) -> tuple[str, str]:
    """
    Find <h3>...</h3> headings, inject id="..." if missing, and build a UL TOC.
    Returns (modified_html, toc_html).
    """
    headings = []
    # match minimal h3 blocks
    pattern = re.compile(r"<h3(.*?)>(.*?)</h3>", re.IGNORECASE | re.DOTALL)

    def _strip_tags(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s or "").strip()

    def _has_id(attrs: str) -> bool:
        return bool(re.search(r"\bid=\"[^\"]+\"", attrs or ""))

    def repl(m):
        attrs, inner = m.group(1), m.group(2)
        text = _strip_tags(inner)
        if not text:
            return m.group(0)
        slug = slugify(text)
        headings.append((text, slug))
        if _has_id(attrs):
            return m.group(0)
        # inject id into opening tag
        new_open = f"<h3 id=\"{slug}\"{attrs}>"
        return new_open + inner + "</h3>"

    modified = pattern.sub(repl, html_content)
    if not headings:
        return html_content, ""
    items = "\n".join(f'<li><a href="#${{slug}}">{html.escape(text)}</a></li>'.replace("${slug}", slug) for text, slug in headings)
    # Minimal inline CSS for TOC (scoped to .toc) — dark friendly
    toc_style = (
        "<style>"
        ".toc{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.12);border-radius:8px;"
        "padding:12px 14px;margin:12px 0 18px;font-size:0.95rem;line-height:1.35;color:inherit}"
        ".toc strong{display:block;margin-bottom:6px;font-size:0.95rem;letter-spacing:.2px;color:inherit}"
        ".toc ul{list-style:disc;margin:0 0 0 18px;padding:0}"
        ".toc li{margin:4px 0}"
        ".toc a{color:inherit;text-decoration:none;border-bottom:1px dashed rgba(255,255,255,.25)}"
        ".toc a:hover{text-decoration:none;border-bottom-color:rgba(255,255,255,.5)}"
        "</style>"
    )
    toc = f"{toc_style}<div class=\"toc\"><strong>On this page</strong><ul>\n{items}\n</ul></div>"
    return modified, toc

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
    # Exclude already-used items (allow null or false)
    params = {
        "select": "id,source,title,url,published_at",
        "published_at": f"gte.{since}",
        # Exclude already-used items (allow null or false)
        "or": "(roundup_used.is.null,roundup_used.eq.false)",
        "order": "published_at.desc",
        "limit": str(limit)
    }
    r = session.get(url, params=params, timeout=20)
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
    filtered = []
    for a in arts:
        if a.get("outputs"):
            if _is_relevant_item(a):
                filtered.append(a)
    return filtered
def _fmt(v: Any, unit: str = "") -> str:
    try:
        if v is None:
            return "n/a"
        vf = float(v)
        if unit and unit.strip().startswith("nT"):
            return f"{vf:.1f} nT"
        if unit and unit.strip().startswith("km/s"):
            return f"{vf:.0f} km/s"
        return f"{vf:.1f}{unit}"
    except Exception:
        return "n/a"

def render_top_signals(metrics: Dict[str,Any] | None) -> str:
    if not metrics:
        return ""
    kp = _fmt(metrics.get("kp_max"))
    bz = _fmt(metrics.get("bz_min"), "nT")
    sw = _fmt(metrics.get("sw_speed_avg"), "km/s")
    html_parts = [
        "<h2>Top Signals</h2>",
        "<ul>",
        f"<li><strong>Kp (max)</strong>: {kp}</li>",
        f"<li><strong>Bz (min)</strong>: {bz} (more negative = stronger southward)</li>",
        f"<li><strong>Solar wind (avg)</strong>: {sw}</li>",
        "</ul>",
        "<p><em>Gaia Eyes research insight:</em> Lower Kp and easing solar‑wind speed generally indicate reduced geomagnetic disturbance. Observational work often notes HRV rebound as conditions calm, with brief dips near southward Bz swings.</p>",
    ]
    return "\n".join(html_parts)


# --- Quick Facts helper ---
def collect_quick_facts(items: List[Dict[str,Any]], max_facts: int = 6) -> List[str]:
    facts: List[str] = []
    seen = set()
    for a in items:
        for o in a.get("outputs", []):
            if o.get("output_type") == "fact":
                t = (o.get("content") or "").strip()
                if 8 <= len(t) <= 160 and t not in seen:
                    facts.append(t)
                    seen.add(t)
                    if len(facts) >= max_facts:
                        return facts
    return facts

# --- Body formatting helpers ---
TERM_AP_RE = re.compile(r"\bAp\s+index\b", re.IGNORECASE)

def normalize_terms(txt: str) -> str:
    """Project-wide wording fixes (non-destructive)."""
    if not isinstance(txt, str):
        return ""
    # Prefer Kp terminology unless we explicitly detect Ap context (not implemented here)
    return TERM_AP_RE.sub("Kp index", txt)


def format_body_blocks(raw: str) -> list[str]:
    """
    Convert plain text with blank lines and simple bullets into HTML blocks.
    - Recognizes bullets starting with '-', '•', or '*'
    - Keeps paragraphs tidy; preserves single newlines as <br/>
    - Escapes HTML in text content
    Returns a list of HTML strings (<p>...</p> or <ul>...</ul>)
    """
    if not raw:
        return []
    text = strip_markdown_syntax(normalize_terms(raw))
    # Normalize newlines and trim trailing spaces
    text = re.sub(r"\r\n?", "\n", text).strip()
    # Split into blocks on 2+ newlines
    blocks = re.split(r"\n{2,}", text)
    rendered: list[str] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        # bullet detection: at least half of lines start with a bullet marker
        bullet_lines = [ln for ln in lines if re.match(r"^(\-|\*|•)\s+", ln)]
        if bullet_lines and len(bullet_lines) >= max(1, len(lines)//2):
            items = []
            for ln in lines:
                m = re.match(r"^(\-|\*|•)\s+(.*)$", ln)
                if m:
                    items.append(f"<li>{html.escape(m.group(2).strip())}</li>")
                else:
                    # treat as a continuation line for previous bullet
                    if items:
                        items[-1] = items[-1][:-5] + "<br/>" + html.escape(ln) + "</li>"
                    else:
                        items.append(f"<li>{html.escape(ln)}</li>")
            rendered.append("<ul>" + "".join(items) + "</ul>")
        else:
            # Regular paragraph; convert single newlines to <br/>
            para = html.escape(" ".join(lines)).replace("\n", "<br/>")
            rendered.append(f"<p>{para}</p>")
    return rendered

# --- Narrative helpers (less repetitive, more human) ---
BOILER_HEADINGS_RE = re.compile(
    r"^\s*(what happened\??|why (it )?matters\??|what to watch\??|bottom line\??|the takeaway\??)\s*:?\s*$",
    re.IGNORECASE
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

FACT_HEADER_VARIANTS = [
    "Key facts",
    "Quick hits",
    "In brief",
    "Need‑to‑know",
    "Fast facts",
    "Signals at a glance"
]

def strip_boilerplate_headings(text: str) -> str:
    """Remove repetitive section headings like 'What Happened?', keep the content."""
    if not text:
        return ""
    lines = re.split(r"\r?\n", text)
    kept = []
    for ln in lines:
        if BOILER_HEADINGS_RE.match(ln.strip()):
            continue
        kept.append(ln)
    return "\n".join(kept).strip()

def summarize_text(raw: str, max_chars: int = 280) -> str:
    """
    Create a short, human-like summary: take the first 1–2 sentences after stripping boilerplate.
    """
    if not raw:
        return ""
    cleaned = strip_boilerplate_headings(raw)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    parts = SENTENCE_SPLIT_RE.split(cleaned)
    if not parts:
        return cleaned[:max_chars]
    # Take first 1–2 sentences
    lead = parts[0]
    if len(lead) < max_chars * 0.6 and len(parts) > 1:
        lead = (lead + " " + parts[1]).strip()
    return lead[:max_chars].rstrip(" ,;:") + ("…" if len(lead) > max_chars else "")

def pick_fact_header(seed_key: str) -> str:
    """Pick a stable header variant per-article (based on title/url)."""
    h = abs(hash(seed_key)) % len(FACT_HEADER_VARIANTS)
    return FACT_HEADER_VARIANTS[h]

# --- Mark articles as used in roundup ---
def sb_mark_roundup_used(ids: List[str]) -> None:
    if not ids:
        return
    url = f"{SUPABASE_REST_URL}/research_articles"
    for i in ids:
        try:
            r = session.patch(url,
                              params={"id": f"eq.{i}"},
                              json={"roundup_used": True},
                              timeout=20)
            if r.status_code not in (200, 204):
                print("[SB] mark roundup_used failed:", i, r.status_code, (r.text or "")[:160])
        except Exception as e:
            print("[SB] mark roundup_used error:", i, e)

def wp_auth():
    if not (WP_BASE_URL and WP_USERNAME and WP_APP_PASSWORD):
        raise SystemExit("Missing WP_* envs")
    return (WP_USERNAME, WP_APP_PASSWORD)

def wp_create_post(title: str, html_content: str, featured_media: int | None = None) -> dict:
    endpoint = f"{WP_BASE_URL}/wp-json/wp/v2/posts"
    # Resolve category by slug if no numeric id provided
    cat_id = WP_CATEGORY_ID
    if (not cat_id) and WP_CATEGORY_SLUG:
        cat_id = wp_resolve_category_id(WP_CATEGORY_SLUG) or ""
    payload = {"title": title, "content": html_content, "status": WP_STATUS}
    if cat_id:
        try:
            payload["categories"] = [int(cat_id)]
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
    # Header note
    parts = [f"<p><em>Curated highlights from today’s mission‑relevant sources.</em></p>"]
    # Top signals from marts
    try:
        top = render_top_signals(sb_today_metrics())
        if top:
            parts.append(top)
    except Exception as e:
        print("[WP] top signals error:", e)
    # Items (max 7)
    items = items[:7]
    for a in items:
        title = html.escape(a.get("title","(untitled)"))
        url = html.escape(a.get("url","#"))
        parts.append(f'<h3><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>')
        # Prefer long summary, then short
        long = next((o["content"] for o in a.get("outputs",[]) if o.get("output_type")=="summary_long"), "")
        short= next((o["content"] for o in a.get("outputs",[]) if o.get("output_type")=="summary_short"), "")
        body = long or short

        sanitized = strip_markdown_syntax(body or "")
        # 1) Add a concise, human-like lead summary (one short paragraph)
        lead = summarize_text(sanitized)
        if lead:
            parts.append(f"<p><strong>Summary:</strong> {html.escape(lead)}</p>")

        # 2) Render the rest of the body without markdown, minus boilerplate headings
        body_clean = strip_boilerplate_headings(sanitized)
        for chunk in format_body_blocks(body_clean):
            parts.append(chunk)

        # 3) Facts list with varied header (if present)
        facts = [o["content"] for o in a.get("outputs",[]) if o.get("output_type")=="fact"][:4]
        if facts:
            parts.append(f"<h4>{html.escape(pick_fact_header(title + url))}</h4>")
            parts.append("<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>")
    # Quick Facts footer (research-only, for overlays/social reuse)
    qf = collect_quick_facts(items)
    if qf:
        parts.append("<h3>Quick Facts</h3>")
        parts.append("<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in qf) + "</ul>")
    # Final normalization pass for terminology (e.g., Ap -> Kp)
    final_html = "\n".join(parts)
    final_html = normalize_terms(final_html)
    return final_html

def read_summary_files() -> tuple[str|None, str|None]:
    """
    Try to read pre-rendered title/body from either research_lane/_summary.* (preferred)
    or local folder if present. Returns (title, html) or (None, None) if not found.
    """
    candidates = [
        (HERE.parent / "research_lane" / "_summary_title.txt", HERE.parent / "research_lane" / "_summary.html"),
        (HERE / "_summary_title.txt", HERE / "_summary.html"),
    ]
    for t, h in candidates:
        try:
            if t.exists() and h.exists():
                title = t.read_text(encoding="utf-8").strip()
                body  = h.read_text(encoding="utf-8")
                if title and body:
                    print(f"[WP] found pre-rendered summary at {h}")
                    return title, body
        except Exception as e:
            print("[WP] read summary files error:", e)
    return None, None

def main():
    # Preflight auth/URL so failures are obvious
    wp_verify_credentials(WP_BASE_URL, wp_auth())

    # If in NEWS mode (or summary files exist), read the pre-rendered summary and post it
    use_summary = SUMMARY_MODE == "news"
    sum_title, sum_html = read_summary_files()
    if sum_title and sum_html:
        use_summary = True

    if use_summary:
        # Title prefix support
        title = (WP_TITLE_PREFIX + " " + sum_title).strip() if WP_TITLE_PREFIX else sum_title
        html_content = sum_html
        items = []
    else:
        items = sb_recent_summaries(days=WP_LOOKBACK_DAYS, limit=8)
        print(f"[WP] roundup candidates after relevance filter: {len(items)}")
        if not items:
            print("No recent research items.")
            return
        today = dt.datetime.utcnow().strftime("%b %d, %Y")
        base_title = f"Gaia Eyes Research Roundup — {today}"
        title = (WP_TITLE_PREFIX + " " + base_title).strip() if WP_TITLE_PREFIX else base_title
        html_content = roundup_html(items)

    featured_id = None
    featured_src_url = None  # WP media source_url
    owner = repo = sha = path = None
    cdn_url = None

    if WP_FEATURED_SOURCE == "bg":
        owner, repo, sha, path, cdn_url = pick_background_from_cdn(WP_FEATURED_BG_KIND)
    elif WP_FEATURED_SOURCE == "caption":
        # no caption image in roundup; keep None
        pass

    # Try to upload featured image if we have a CDN URL
    if cdn_url:
        print(f"[WP] Using featured URL: {cdn_url}")
        # First attempt: jsDelivr CDN
        fid, fsrc = wp_upload_image_from_url(cdn_url)
        if not fid and owner and repo and path is not None:
            # Fallback: GitHub raw (private repo case) with token
            raw_url = None
            if sha:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{sha}{path}"
            else:
                # default branch fallback
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main{path}"
            print(f"[WP] jsDelivr download failed; trying raw GitHub: {raw_url}")
            headers = {}
            if GITHUB_API_TOKEN:
                headers["Authorization"] = f"Bearer {GITHUB_API_TOKEN}"
            fid, fsrc = wp_upload_image_from_url(raw_url, dl_headers=headers)
        featured_id, featured_src_url = fid, fsrc
        if featured_id:
            print(f"[WP] Featured image uploaded, id={featured_id}")
        else:
            print("[WP] Featured upload failed; will inline external hero if available")

    # Hero image handling: if featured upload succeeded, **do not** inline the hero to avoid duplicates.
    # If featured upload failed, inline the external hero so we still have a visible header image.
    hero_url = featured_src_url or cdn_url
    if featured_id:
        # Featured image present — keep page clean and just add credit line (no inline duplicate)
        if WP_FEATURED_CREDIT:
            html_content = f"<p><em>{html.escape(WP_FEATURED_CREDIT)}</em></p>\n" + html_content
    elif hero_url:
        # No featured media — inline hero so the post still has a visible header image
        html_content = f'<p><img src="{html.escape(hero_url)}" alt="Featured image" style="max-width:100%;height:auto;"/></p>\n' + html_content
        if WP_FEATURED_CREDIT:
            html_content = f"<p><em>{html.escape(WP_FEATURED_CREDIT)}</em></p>\n" + html_content

    # Gallery injection disabled by default for research posts
    # if WP_GALLERY_ENABLE:
    #     gallery_urls = pick_backgrounds_from_cdn(WP_GALLERY_KIND, WP_GALLERY_COUNT)
    #     if hero_url:
    #         gallery_urls = [u for u in gallery_urls if u != hero_url]
    #     html_content = inject_gallery_block(html_content, gallery_urls)

    # Optional TOC: build from H3 headings and inject anchor IDs
    if WP_ADD_TOC and SUMMARY_MODE != "news":
        html_content, toc_html = build_toc_and_inject_ids(html_content)
        if toc_html:
            html_content = toc_html + "\n" + html_content

    # Optional CTA footer
    if WP_CTA_HTML:
        html_content = html_content + "\n" + WP_CTA_HTML

    created = wp_create_post(title, html_content, featured_media=featured_id)
    try:
        used_ids = [a.get("id") for a in items if a.get("id")]
        sb_mark_roundup_used(used_ids)
    except Exception as e:
        print("[SB] roundup_used post-mark failed:", e)
    link = created.get("link") if isinstance(created, dict) else None
    status = created.get("status") if isinstance(created, dict) else None
    print("WP research post created:", link or "(no JSON link)", "status:", status or created.get("status_code"))

if __name__=="__main__":
    main()
