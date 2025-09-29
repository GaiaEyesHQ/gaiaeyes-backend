#!/usr/bin/env python3
import os, sys, datetime as dt
from pathlib import Path

# Reuse the SWPC/USGS parsers you already have in research_collector
sys.path.append(str(Path(__file__).resolve().parents[1] / "research_collector"))
from research_collector import (
    parse_swpc_alerts, parse_swpc_kp, parse_swpc_geomag_3day_txt,
    parse_swpc_rtsw_plasma1d, parse_swpc_rtsw_mag1d, parse_swpc_ovation_latest,
    normalize_url, session, TIMEOUT, _year_tag
)

NEWS_LOOKBACK_DAYS = int(os.getenv("NEWS_LOOKBACK_DAYS","3"))
NEWS_MIN_ITEMS     = int(os.getenv("NEWS_MIN_ITEMS","5"))
NEWS_CATEGORY_SLUG = os.getenv("NEWS_CATEGORY_SLUG","space-news")
NEWS_TITLE_PREFIX  = os.getenv("NEWS_TITLE_PREFIX","Space Weather Daily: ")
NEWS_EXCLUDE_KEYWORDS = [k.strip().lower() for k in os.getenv("NEWS_EXCLUDE_KEYWORDS","").split(",") if k.strip()]
HTTP_USER_AGENT    = os.getenv("HTTP_USER_AGENT","GaiaEyesBot/1.0 (+https://gaiaeyes.com)")
GAIA_TZ            = os.getenv("GAIA_TIMEZONE","America/Chicago")

def _now_iso():
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()

def _fresh(ts_iso: str|None) -> bool:
    if not ts_iso: return True
    try:
        ts = dt.datetime.fromisoformat(ts_iso.replace("Z","+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - ts).days <= NEWS_LOOKBACK_DAYS
    except Exception:
        return True

def _filter_excludes(items):
    if not NEWS_EXCLUDE_KEYWORDS: return items
    out=[]
    for r in items:
        blob = (r.get("title","") + " " + r.get("summary_raw","")).lower()
        if any(k in blob for k in NEWS_EXCLUDE_KEYWORDS):
            continue
        out.append(r)
    return out

def collect():
    items=[]
    # SWPC JSON/TXT endpoints (authoritative + structured)
    items += parse_swpc_alerts("https://services.swpc.noaa.gov/products/alerts.json", "swpc-alerts-json", ["SWPC","alerts"])
    items += parse_swpc_kp("https://services.swpc.noaa.gov/products/summary/planetary-k-index-3-day.json", "swpc-kp-3day", ["SWPC","kp"])
    items += parse_swpc_rtsw_plasma1d("https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json", "swpc-rtsw-plasma1d", ["SWPC","DSCOVR"])
    items += parse_swpc_rtsw_mag1d("https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json", "swpc-rtsw-mag1d", ["SWPC","DSCOVR"])
    items += parse_swpc_ovation_latest("https://services.swpc.noaa.gov/json/ovation_aurora_latest.json", "swpc-ovation-latest", ["SWPC","OVATION"])
    items += parse_swpc_geomag_3day_txt("https://www.swpc.noaa.gov/ftpdir/forecasts/3-day_forecast.txt", "swpc-geomag-3day", ["SWPC","forecast"])

    # Freshness gate (strict) + optional excludes
    items = [r for r in items if _fresh(r.get("published_at"))]
    items = _filter_excludes(items)

    # If underfilled, we still post—but summarizer will be terse
    return items

def main():
    items = collect()
    print(f"[NEWS] collected {len(items)} fresh items")
    # Hand off to the summarizer/poster (reuse existing pipeline)
    os.environ["SUMMARY_MODE"] = "news"
    os.environ["WP_CATEGORY_SLUG"] = NEWS_CATEGORY_SLUG
    os.environ["WP_TITLE_PREFIX"]  = NEWS_TITLE_PREFIX
    # Write a temporary JSON for the summarizer to consume (keeps your current interfaces simple)
    import json, tempfile
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
        json.dump({"items": items}, f)
        tmp = f.name
    os.environ["COLLECTED_NEWS_PATH"] = tmp
    # Run your existing summarizer + poster
    # Expectation: research_summarize.py reads COLLECTED_NEWS_PATH when SUMMARY_MODE=news
    #              research_wp_poster.py then posts the produced HTML under WP_CATEGORY_SLUG
    os.system(f"{sys.executable} {Path(__file__).resolve().parents[1] / 'research_collector' / 'research_summarize.py'}")
    os.system(f"{sys.executable} {Path(__file__).resolve().parents[1] / 'research_collector' / 'research_wp_poster.py'}")

if __name__ == "__main__":
    main()