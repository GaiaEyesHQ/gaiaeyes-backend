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
import re

GENERIC_PATTERNS = [
    re.compile(r"latest update from this source", re.I),
    re.compile(r"news and information", re.I),
    re.compile(r"studies (the )?sun", re.I),
    re.compile(r"dynamic influence across our .+ solar system", re.I),
]

def _first_text(nodes, max_len=420):
    """Pick the first meaningful text from a list of nodes; trim nicely."""
    for n in nodes or []:
        txt = (n.get_text(" ", strip=True) or "").strip()
        if txt and len(txt) > 40:  # avoid tiny labels
            return txt[: max_len - 1].rstrip() + ("…" if len(txt) >= max_len else "")
    return ""

def _summarize_from_dom(url: str, html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else url)

    # Prefer page H1, then first meaningful paragraph; many sites structure this way
    h1 = soup.find("h1")
    h1_text = (h1.get_text(" ", strip=True) if h1 else "").strip()

    # Prefer news-like containers if present (site-specific tweaks)
    # SpaceWeather.com: grab the center column first paragraph(s)
    p_candidates = []
    if "spaceweather.com" in url:
        # grab first few <p> elements on page
        p_candidates = soup.select("p")
    elif "solarham.com" in url:
        # SolarHam often has <td> text; fallback to paragraphs anyway
        p_candidates = soup.select("p, td")
    else:
        p_candidates = soup.select("article p, main p, .content p, p")

    lead = _first_text(p_candidates)

    # Fallback to meta descriptions if needed
    if not lead:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            lead = og["content"].strip()
    if not lead:
        md = soup.find("meta", attrs={"name": "description"})
        if md and md.get("content"):
            lead = md["content"].strip()

    if not lead:
        lead = "Key update from this source."

    return {"title": (h1_text or title), "summary": lead}

def _summarize_url(url: str, timeout: int = 20) -> Optional[Dict[str, str]]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "gaia-ops/earthscope-bot"})
        r.raise_for_status()
        info = _summarize_from_dom(url, r.text)
        return {"title": info["title"] or url, "url": url, "summary": info["summary"]}
    except Exception:
        return None

def _looks_generic(text: str) -> bool:
    if not text: return True
    for pat in GENERIC_PATTERNS:
        if pat.search(text):
            return True
    return False

def _enrich_if_generic(item: Dict[str, str], metrics_json: Dict[str, Any]) -> Dict[str, str]:
    """
    If the scraped summary is generic, rewrite a concise summary using current Kp/Bz/wind.
    This guarantees we never pass fluff into the LLM.
    """
    s = (item.get("summary") or "").strip()
    if s and not _looks_generic(s):
        return item

    sw = (metrics_json or {}).get("space_weather") or {}
    kp = sw.get("kp_max")
    bz = sw.get("bz_min")
    wind = sw.get("sw_speed_avg")

    parts = []
    if kp is not None: parts.append(f"Kp {kp:.1f}")
    if bz is not None: parts.append(f"Bz {bz:.1f} nT")
    if wind is not None: parts.append(f"solar wind {wind:.1f} km/s")
    metrics_line = ", ".join(parts) if parts else "quiet geomagnetic background"

    item["summary"] = f"Today’s context: {metrics_line}. See this source for current charts and expert commentary."
    return item

def fetch_trending_articles(max_items: int = 3, metrics_json: Dict[str, Any] = None) -> List[Dict[str, str]]:
    """
    Strategy:
      1) If TREND_URLS env is set (comma-separated), fetch those.
      2) Else try a curated set (SpaceWeather.com, NASA Heliophysics blog hub, SolarHam, HeartMath live).
      3) Summarize via DOM (h1 + first paragraph). If generic, enrich summary with Kp/Bz/wind.
    """
    env_list = os.environ.get("TREND_URLS", "").strip()
    if env_list:
        candidate_urls = [u.strip() for u in env_list.split(",") if u.strip()]
    else:
        candidate_urls = [
            "https://www.spaceweather.com/",
            "https://science.nasa.gov/heliophysics/solar-activity/",  # NASA heliophysics activity hub
            "https://www.solarham.com/",                               # may be on hiatus; keep as context
            "https://www.heartmath.org/gci/gcms/live-data/",
        ]

    items: List[Dict[str, str]] = []
    for url in candidate_urls:
        it = _summarize_url(url)
        if it:
            it = _enrich_if_generic(it, metrics_json or {})
            items.append(it)
        if len(items) >= max_items:
            break

    # Always return 2–3 items max for brevity
    return items[:max_items]
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
