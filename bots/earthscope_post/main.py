import os, asyncio, json
from datetime import datetime, timedelta, timezone, date as Date
from typing import Any, Dict, List, Optional
from decimal import Decimal

import asyncpg
import requests
from bs4 import BeautifulSoup

from llm import generate_daily_earthscope, LLMFailure

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]

# ---------------- JSON helpers ----------------

def _to_jsonable(obj: Any) -> Any:
    """Recursively convert Decimal/Date/Datetime to JSON-safe types."""
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Date):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj

# ---------------- DB helpers ----------------

async def fetch_all(conn, q: str, *args):
    rows = await conn.fetch(q, *args)
    return [dict(r) for r in rows]

async def fetch_one(conn, q: str, *args):
    row = await conn.fetchrow(q, *args)
    return dict(row) if row else None

async def get_best_day(conn) -> Date:
    """
    UTC fallback: today; if missing/sparse (row_count < 50) then yesterday; else abort.
    Returns a Python date object (not string).
    """
    today = datetime.now(timezone.utc).date()
    yday  = today - timedelta(days=1)
    q = """select day, row_count
           from marts.space_weather_daily
           where day in ($1, $2)"""
    rows = await fetch_all(conn, q, today, yday)  # bind as dates
    by_day = {r["day"]: (r.get("row_count") or 0) for r in rows}  # r["day"] is date
    if by_day.get(today, 0) >= 50:
        return today
    if by_day.get(yday, 0) >= 50:
        return yday
    raise SystemExit("no data for today/yesterday")

# --------------- Trending fetcher (improved) ---------------
# --------------- Trending fetcher (news-first, de-genericized) ---------------
import re
import feedparser
from urllib.parse import urlparse

NON_NEWS_PATTERNS = [
    re.compile(r"fundraiser", re.I),
    re.compile(r"donate", re.I),
    re.compile(r"sign[\s-]?up", re.I),
    re.compile(r"newsletter", re.I),
    re.compile(r"privacy\s*policy", re.I),
    re.compile(r"cookie", re.I),
    re.compile(r"terms\s*of\s*use", re.I),
    re.compile(r"about\s+us", re.I),
]
GENERIC_PATTERNS = [
    re.compile(r"news and information", re.I),
    re.compile(r"latest update", re.I),
    re.compile(r"studies the sun", re.I),
    re.compile(r"dynamic influence", re.I),
]

def _is_non_news(text: str) -> bool:
    if not text: return True
    for pat in NON_NEWS_PATTERNS:
        if pat.search(text):
            return True
    return False

def _is_generic(text: str) -> bool:
    if not text: return True
    for pat in GENERIC_PATTERNS:
        if pat.search(text):
            return True
    # Toss very short blurbs
    if len(text.strip()) < 40:
        return True
    return False

def _mk_summary_from_metrics(metrics_json: Dict[str, Any]) -> str:
    sw = (metrics_json or {}).get("space_weather") or {}
    parts = []
    if sw.get("kp_max") is not None: parts.append(f"Kp {float(sw['kp_max']):.1f}")
    if sw.get("bz_min") is not None: parts.append(f"Bz {float(sw['bz_min']):.1f} nT")
    if sw.get("sw_speed_avg") is not None: parts.append(f"solar wind {float(sw['sw_speed_avg']):.1f} km/s")
    if parts:
        return f"Today’s context: {', '.join(parts)}. See this article for details and expert charts."
    return "Today’s context: quiet to unsettled field. See this article for updates."

def _clean_feed_item(title: str, link: str, summary: str, metrics_json: Dict[str, Any]) -> Optional[Dict[str,str]]:
    # Basic noise filters
    if not link or _is_non_news(title or "") or _is_non_news(summary or ""):
        return None
    # Tidy up whitespace
    title = (title or "").strip()
    summary = (summary or "").strip()
    # Strip HTML tags that sometimes appear in RSS summaries
    summary = re.sub(r"<[^>]+>", "", summary)
    # Force a concrete summary if generic
    if _is_generic(summary):
        summary = _mk_summary_from_metrics(metrics_json)
    # Clip long blurbs
    if len(summary) > 280:
        summary = summary[:277].rstrip() + "…"
    return {"title": title or link, "url": link, "summary": summary}

def _fetch_rss(url: str, metrics_json: Dict[str, Any], cap: int = 2) -> List[Dict[str,str]]:
    items = []
    try:
        feed = feedparser.parse(url)
        for e in feed.entries[:5]:  # look at a few, filter below
            title = getattr(e, "title", "") or ""
            link = getattr(e, "link", "") or ""
            # prefer content/summary detail
            summary = getattr(e, "summary", "") or ""
            if hasattr(e, "content") and e.content:
                # sometimes content[0].value has the body
                body = e.content[0].value or ""
                if len(body) > len(summary):
                    summary = body
            cleaned = _clean_feed_item(title, link, summary, metrics_json)
            if cleaned:
                items.append(cleaned)
            if len(items) >= cap:
                break
    except Exception:
        pass
    return items

def _scrape_html_summary(url: str, metrics_json: Dict[str, Any], timeout: int = 15) -> Optional[Dict[str,str]]:
    """Fallback: scrape a page and try to pull the first real paragraph, filtering junk."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "gaia-ops/earthscope-bot"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Skip very generic pages entirely
        if _is_non_news(soup.get_text(" ", strip=True)[:400]):
            return None
        # Aim for news-ish content blocks
        p = soup.select("article p, main p, .content p, p")
        text = ""
        for node in p[:10]:
            txt = node.get_text(" ", strip=True)
            if txt and not _is_non_news(txt) and len(txt) > 60:
                text = txt
                break
        if not text:
            # fallback to meta desc
            og = soup.find("meta", attrs={"property": "og:description"})
            if og and og.get("content"): text = og["content"].strip()
        if not text:
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"): text = md["content"].strip()
        if not text:
            text = _mk_summary_from_metrics(metrics_json)

        title = (soup.title.string.strip() if soup.title and soup.title.string else url)
        if len(text) > 280: text = text[:277].rstrip() + "…"
        # Final generic check
        if _is_generic(text):
            text = _mk_summary_from_metrics(metrics_json)
        return {"title": title, "url": url, "summary": text}
    except Exception:
        return None

def fetch_trending_articles(max_items: int = 3, metrics_json: Dict[str, Any] = None) -> List[Dict[str, str]]:
    """
    Strategy order:
      1) If TREND_URLS is set (comma-separated articles), fetch exactly those (HTML summarize) in order.
      2) Otherwise, use curated RSS feeds to get actual stories, then (if needed) fill from HTML.
    """
    metrics_json = metrics_json or {}
    chosen: List[Dict[str,str]] = []

    # 1) Exact article override (high priority)
    env_list = os.environ.get("TREND_URLS", "").strip()
    if env_list:
        for raw in [u.strip() for u in env_list.split(",") if u.strip()]:
            it = _scrape_html_summary(raw, metrics_json)
            if it: chosen.append(it)
            if len(chosen) >= max_items: return chosen

    # 2) Curated feeds (news-first)
    # SpaceWeatherLive (news); NASA Heliophysics blog; LiveScience space tag
    feeds = [
        os.environ.get("TREND_FEED_1", "https://www.spaceweatherlive.com/en/news.rss"),
        os.environ.get("TREND_FEED_2", "https://science.nasa.gov/heliophysics/feed/"),
        os.environ.get("TREND_FEED_3", "https://www.livescience.com/space/rss.xml"),
    ]
    for f in feeds:
        for item in _fetch_rss(f, metrics_json, cap=2):
            chosen.append(item)
            if len(chosen) >= max_items:
                return chosen

    # 3) Fallback HTML summaries of home pages (filtered)
    fallbacks = [
        "https://www.spaceweather.com/",
        "https://www.solarham.com/",
        "https://science.nasa.gov/heliophysics/",
        "https://www.heartmath.org/gci/gcms/live-data/",
    ]
    for url in fallbacks:
        it = _scrape_html_summary(url, metrics_json)
        if it:
            chosen.append(it)
        if len(chosen) >= max_items:
            break

    return chosen[:max_items]
# ---------------- Main run ----------------

async def run():
    platform = os.environ.get("PLATFORM", "instagram").strip()
    user_id_env  = os.environ.get("USER_ID", "").strip()
    user_id  = user_id_env or None   # empty => None (global)
    dry_run  = os.environ.get("DRY_RUN", "false").lower() == "true"

    conn = await asyncpg.connect(SUPABASE_DB_URL)

    # Best day (as date)
    day: Date = await get_best_day(conn)

    # Space weather for that date
    sw = await fetch_one(conn, "select * from marts.space_weather_daily where day=$1", day)
    if not sw:
        await conn.close()
        raise SystemExit("no space weather row")

    # DONKI events for the day
    events = await fetch_all(conn, """
        select event_type, start_time, class
        from ext.donki_event
        where date(start_time) = $1
        order by start_time asc
    """, day)

    # metrics_json exactly as contract (day stringified only for JSON)
    day_iso = day.isoformat()
    metrics_json: Dict[str, Any] = {
        "day": day_iso,
        "space_weather": {
            "kp_max": sw.get("kp_max"),
            "bz_min": sw.get("bz_min"),
            "sw_speed_avg": sw.get("sw_speed_avg"),
            "flares_count": sw.get("flares_count"),
            "cmes_count": sw.get("cmes_count"),
        }
    }
    metrics_json = _to_jsonable(metrics_json)  # Decimal → float etc.

    # Trending references (2–3)
    trending = fetch_trending_articles(max_items=3, metrics_json=metrics_json)

    # LLM render (rich sections + hashtags + sources)
    try:
        llm = generate_daily_earthscope(metrics_json, events, trending)
        title        = llm["title"].strip()
        caption      = llm["caption"].strip()
        body_md      = llm["body_markdown"].strip()
        hashtags     = llm["hashtags"].strip()
        sources_json = llm["sources_json"]
    except Exception as e:
        # Minimal deterministic fallback
        kp, bz, wind = sw.get("kp_max"), sw.get("bz_min"), sw.get("sw_speed_avg")
        title   = f"Daily Earthscope • {day_iso}"
        caption = (f"Earthscope — Kp {kp if kp is not None else 'n/a'}, "
                   f"Bz {bz if bz is not None else 'n/a'} nT, "
                   f"solar wind {wind if wind is not None else 'n/a'} km/s. "
                   "Ground, breathe, hydrate. #GaiaEyes #DailyEarthscope #SpaceWeather")
        body_md = f"""# Daily Earthscope • {day_iso}

## Trending Space Weather Highlights
- See SolarHam, SpaceWeather, NASA, HeartMath for the latest reports.

## How This May Affect You
- Mood & Energy: calm, centered
- Heart & Nervous System: coherent rhythms

## Self-Care Playbook
- hydrate
- 4/6 breathing
- ground outdoors

**Sources:** SolarHam · SpaceWeather · NASA · HeartMath
"""
        hashtags = "#GaiaEyes #DailyEarthscope #SpaceWeather #HeartCoherence"
        sources_json = {
            "datasets": ["marts.space_weather_daily", "ext.donki_event"],
            "references": [
                "https://www.solarham.com/",
                "https://www.spaceweather.com/",
                "https://www.nasa.gov/",
                "https://www.heartmath.org/gci/gcms/live-data/"
            ],
            "note": f"LLM fallback used due to error: {type(e).__name__}"
        }

    # Upsert row (bind day as DATE)
    row = {
        "day": day,                              # DATE → DB
        "user_id": user_id,                      # null for global, UUID for user-specific
        "platform": platform,
        "title": title,
        "caption": caption,
        "body_markdown": body_md,
        "hashtags": hashtags,
        "metrics_json": json.dumps(metrics_json, ensure_ascii=False),
        "sources_json": json.dumps(_to_jsonable(sources_json), ensure_ascii=False),
    }

    if dry_run:
        preview = {**row, "day": day_iso}  # show string date in logs
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        await conn.close()
        return

    # ---- Choose conflict target based on whether user_id is NULL or not ----
    if user_id is None:
        # Match your partial unique index: (day, platform) WHERE user_id IS NULL
        sql = """
insert into content.daily_posts (
  day, user_id, platform, title, caption, body_markdown, hashtags, metrics_json, sources_json
) values (
  $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb
)
on conflict (day, platform) where (user_id is null)
do update set
  title         = excluded.title,
  caption       = excluded.caption,
  body_markdown = excluded.body_markdown,
  hashtags      = excluded.hashtags,
  metrics_json  = excluded.metrics_json,
  sources_json  = excluded.sources_json,
  updated_at    = now();
"""
    else:
        # Match your partial unique index: (day, platform, user_id) WHERE user_id IS NOT NULL
        sql = """
insert into content.daily_posts (
  day, user_id, platform, title, caption, body_markdown, hashtags, metrics_json, sources_json
) values (
  $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb
)
on conflict (day, platform, user_id) where (user_id is not null)
do update set
  title         = excluded.title,
  caption       = excluded.caption,
  body_markdown = excluded.body_markdown,
  hashtags      = excluded.hashtags,
  metrics_json  = excluded.metrics_json,
  sources_json  = excluded.sources_json,
  updated_at    = now();
"""

    await conn.execute(sql,
        row["day"], row["user_id"], row["platform"], row["title"],
        row["caption"], row["body_markdown"], row["hashtags"],
        row["metrics_json"], row["sources_json"])

    await conn.close()
    print(f"Upserted Daily Earthscope for {day_iso} → platform={platform} (user_id={'null' if user_id is None else user_id})")

if __name__ == "__main__":
    asyncio.run(run())
