import os, json, re, hashlib, requests
from .models import Item, Draft

WP_BASE = os.getenv("WP_BASE_URL","").rstrip("/")
WP_USER = os.getenv("WP_USERNAME","")
WP_APP_PW = os.getenv("WP_APP_PASSWORD","")

def _wp_headers():
    from base64 import b64encode
    token = b64encode(f"{WP_USER}:{WP_APP_PW}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def canonical_slug(item: Item)->str:
    base = re.sub(r"[^a-z0-9\- ]","", item.title.lower()).strip()[:80]
    base = re.sub(r"\s+", "-", base)
    h = hashlib.sha1(str(item.url).encode()).hexdigest()[:8]
    return f"gaia-research-{base}-{h}"

def render_wp_html(item: Item, draft: Draft) -> str:
    def sect(s):
        return f"""
<h3>TL;DR</h3><p>{s.tldr}</p>
<h4>What happened</h4><p>{s.what_happened}</p>
<h4>Why it matters</h4><p>{s.why_it_matters}</p>
<h4>Today</h4><p>{s.details_today}</p>
<h4>Next 72h</h4><p>{s.next_72h}</p>
<h4>Plain-language impacts</h4><p>{s.impacts_plain}</p>"""
    return f"""
<p><em>Source:</em> <a href="{item.url}" target="_blank" rel="noopener">Link</a></p>
<div class="ge-tabs">
<h2>Scientific Lens</h2>{sect(draft.scientific)}
<hr/>
<h2>Mystical Lens</h2>{sect(draft.mystical)}
</div>"""

def _wp_search_slug(slug:str):
    url = f"{WP_BASE}/wp-json/wp/v2/posts?slug={slug}"
    r = requests.get(url, headers=_wp_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

def upsert_post(item: Item, draft: Draft):
    slug = canonical_slug(item)
    title = f"[Research] {item.title}"
    content = render_wp_html(item, draft)
    existing = _wp_search_slug(slug)
    payload = {"title": title, "content": content, "status":"publish", "slug": slug}
    if existing:
        post_id = existing[0]["id"]
        url = f"{WP_BASE}/wp-json/wp/v2/posts/{post_id}"
        r = requests.post(url, headers=_wp_headers(), data=json.dumps(payload), timeout=45)
        r.raise_for_status()
        return r.json()
    else:
        url = f"{WP_BASE}/wp-json/wp/v2/posts"
        r = requests.post(url, headers=_wp_headers(), data=json.dumps(payload), timeout=45)
        r.raise_for_status()
        return r.json()