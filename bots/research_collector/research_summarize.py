#!/usr/bin/env python3
import os, sys, datetime as dt, json, html
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent

# --- Modes / Env ---
SUMMARY_MODE       = os.getenv("SUMMARY_MODE", "evergreen").strip().lower()   # "news" | "evergreen"
WP_TITLE_PREFIX    = os.getenv("WP_TITLE_PREFIX", "").strip()
WP_CATEGORY_SLUG   = os.getenv("WP_CATEGORY_SLUG", "").strip().lower()
AUTO_POST          = (os.getenv("AUTO_POST", "1").strip().lower() in ("1","true","yes","on"))

# News lane envs
NEWS_LOOKBACK_DAYS = int(os.getenv("NEWS_LOOKBACK_DAYS","3"))
NEWS_MIN_ITEMS     = int(os.getenv("NEWS_MIN_ITEMS","5"))
NEWS_EXCLUDE_KEYWORDS = [k.strip().lower() for k in os.getenv("NEWS_EXCLUDE_KEYWORDS","").split(",") if k.strip()]

# Evergreen lane envs
SUPABASE_REST_URL  = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY","").strip()
EVG_FETCH_LIMIT    = int(os.getenv("EVG_FETCH_LIMIT","7"))

# HTTP
HTTP_USER_AGENT    = os.getenv("HTTP_USER_AGENT","GaiaEyesBot/1.0 (+https://gaiaeyes.com)")
session = requests.Session()
if SUPABASE_SERVICE_KEY:
    session.headers.update({
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "User-Agent": HTTP_USER_AGENT,
        "Accept": "application/json",
    })
else:
    session.headers.update({"User-Agent": HTTP_USER_AGENT})

# --- Import parsers from research_collector for NEWS lane ---
sys.path.append(str(HERE))
from research_collector import (
    parse_swpc_alerts, parse_swpc_kp, parse_swpc_geomag_3day_txt,
    parse_swpc_rtsw_plasma1d, parse_swpc_rtsw_mag1d, parse_swpc_ovation_latest,
)

# --- Helpers ---
def now_date_str():
    return dt.datetime.utcnow().strftime("%b %d, %Y")

def write_outputs(title: str, html_body: str):
    (HERE / "_summary_title.txt").write_text(title, encoding="utf-8")
    (HERE / "_summary.html").write_text(html_body, encoding="utf-8")
    print("[SUMMARY] wrote:", HERE / "_summary_title.txt", "and", HERE / "_summary.html")

def shorten(s: str, n: int = 240) -> str:
    s = " ".join((s or "").split())
    return (s[: n-1] + "…") if len(s) > n else s

# --- NEWS lane ---
def _fresh(ts_iso: str|None) -> bool:
    if not ts_iso: 
        return True
    try:
        ts = dt.datetime.fromisoformat(ts_iso.replace("Z","+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - ts).days <= NEWS_LOOKBACK_DAYS
    except Exception:
        return True

def _filter_excludes(items):
    if not NEWS_EXCLUDE_KEYWORDS: return items
    out=[]
    for r in items:
        blob = ((r.get("title") or "") + " " + (r.get("summary_raw") or "")).lower()
        if any(k in blob for k in NEWS_EXCLUDE_KEYWORDS):
            continue
        out.append(r)
    return out

def collect_news_items():
    items=[]
    # SWPC JSON/TXT endpoints (authoritative)
    items += parse_swpc_alerts("https://services.swpc.noaa.gov/products/alerts.json", "swpc-alerts-json", ["SWPC","alerts"])
    items += parse_swpc_kp("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json", "swpc-kp-3day", ["SWPC","kp"])
    items += parse_swpc_rtsw_plasma1d("https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json", "swpc-rtsw-plasma1d", ["SWPC","DSCOVR"])
    items += parse_swpc_rtsw_mag1d("https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json", "swpc-rtsw-mag1d", ["SWPC","DSCOVR"])
    items += parse_swpc_ovation_latest("https://services.swpc.noaa.gov/json/ovation_aurora_latest.json", "swpc-ovation-latest", ["SWPC","OVATION"])
    items += parse_swpc_geomag_3day_txt("https://services.swpc.noaa.gov/text/3-day-forecast.txt", "swpc-geomag-3day", ["SWPC","forecast"])
    # Freshness + excludes
    items = [r for r in items if _fresh(r.get("published_at"))]
    items = _filter_excludes(items)
    return items

def build_news_summary(items):
    # Lead
    lead_bits = []
    if any("kp" in (r.get("title","").lower()) for r in items):
        lead_bits.append("Kp forecasts updated; minor to moderate geomagnetic activity possible.")
    if any(("plasma" in (r.get("title","").lower())) or ("solar wind" in (r.get("summary_raw","").lower())) for r in items):
        lead_bits.append("Solar wind conditions refreshed via DSCOVR (speed, density, temperature).")
    if any("alert" in (r.get("title","").lower()) for r in items):
        lead_bits.append("New SWPC alerts/notifications issued.")
    if not lead_bits:
        lead_bits.append("Here’s today’s space weather in plain language.")
    lead = " ".join(lead_bits[:2])
    # Bullets
    bullets=[]
    for r in items:
        src = (r.get("source") or "SWPC").upper()
        t   = r.get("title") or "(untitled)"
        u   = r.get("url") or ""
        raw = r.get("summary_raw") or ""
        line = f"<strong>{html.escape(src)}:</strong> "
        line += f"<a href=\"{html.escape(u)}\" target=\"_blank\" rel=\"noopener\">{html.escape(shorten(t, 120))}</a>"
        if raw:
            line += f" — {html.escape(shorten(raw, 200))}"
        bullets.append(f"<li>{line}</li>")
    body = []
    body.append(f"<p><em>{html.escape(lead)}</em></p>")
    body.append("<ul>" + "\n".join(bullets) + "</ul>")
    title_out = (WP_TITLE_PREFIX + " " + now_date_str()).strip() if WP_TITLE_PREFIX else now_date_str()
    return title_out, "\n".join(body)

# --- EVERGREEN lane ---
def fetch_recent_research(limit=None):
    if limit is None:
        limit = EVG_FETCH_LIMIT
    if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
        return []
    try:
        resp = session.get(f"{SUPABASE_REST_URL}/research_articles",
                           params={
                             "select":"title,url,summary_raw,published_at,source",
                             "order":"published_at.desc",
                             "limit": str(limit)
                           }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print("[EVG] fetch error:", e)
        return []

def build_evergreen_summary(items):
    if not items:
        return (WP_TITLE_PREFIX + " " + now_date_str()).strip() if WP_TITLE_PREFIX else now_date_str(), "<p>No research items available.</p>"
    base_title = items[0].get("title") or "Research Spotlight"
    title_out = (WP_TITLE_PREFIX + " " + base_title).strip() if WP_TITLE_PREFIX else base_title
    body=[]
    lead = "This daily research spotlight collects notable articles on space weather, geomagnetism, Schumann resonance, and human‑physiology links."
    body.append(f"<p><em>{html.escape(lead)}</em></p>")
    body.append("<h3>Highlights</h3>")
    bl=[]
    for r in items[:5]:
        t = r.get("title") or "(untitled)"
        u = r.get("url") or "#"
        bl.append(f"<li><a href=\"{html.escape(u)}\" target=\"_blank\" rel=\"noopener\">{html.escape(shorten(t,140))}</a></li>")
    body.append("<ul>" + "\n".join(bl) + "</ul>")
    for r in items[:5]:
        t = r.get("title") or "(untitled)"
        u = r.get("url") or "#"
        s = " ".join((r.get("summary_raw") or "").split())
        if s:
            body.append(f"<p><strong><a href=\"{html.escape(u)}\" target=\"_blank\" rel=\"noopener\">{html.escape(t)}</a></strong> — {html.escape(s)}</p>")
    return title_out, "\n".join(body)

def main():
    print(f"[SUMMARY] mode={SUMMARY_MODE}")
    if SUMMARY_MODE == "news":
        items = collect_news_items()
        print(f"[NEWS] collected {len(items)} fresh items")
        title, body = build_news_summary(items)
    else:
        items = fetch_recent_research()
        print(f"[EVG] fetched {len(items)} research rows")
        title, body = build_evergreen_summary(items)

    # Write summary files for the poster
    write_outputs(title, body)

    # Optionally post immediately using the shared poster
    if AUTO_POST:
        poster = HERE / "research_wp_poster.py"
        if poster.exists():
            # Ensure poster sees the same mode/category/prefix
            os.environ["SUMMARY_MODE"] = SUMMARY_MODE
            os.environ["WP_CATEGORY_SLUG"] = WP_CATEGORY_SLUG
            os.environ["WP_TITLE_PREFIX"]  = WP_TITLE_PREFIX
            rc = os.system(f"{sys.executable} {poster}")
            print("[POSTER] exit code:", rc)
        else:
            print("[POSTER] research_wp_poster.py not found; skipping auto-post.")

if __name__ == "__main__":
    main()