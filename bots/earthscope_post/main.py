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

# --------------- Trending fetcher ---------------

def _scrape_title_desc(url: str, timeout: int = 15) -> Optional[Dict[str, str]]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "gaia-ops/earthscope-bot"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.string.strip() if soup.title and soup.title.string else url)
        desc = ""
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            desc = og["content"].strip()
        if not desc:
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"):
                desc = md["content"].strip()
        if desc and len(desc) > 240:
            desc = desc[:237].rstrip() + "…"
        return {"title": title, "url": url, "summary": desc or "Latest update from this source."}
    except Exception:
        return None

def fetch_trending_articles(max_items: int = 3) -> List[Dict[str, str]]:
    """
    Fetch 2–3 current references (title+summary+link) from canonical sources.
    Override with env vars if desired.
    """
    candidate_urls = [
        os.environ.get("TREND_SOLARHAM", "https://www.solarham.com/"),
        os.environ.get("TREND_SPACEWEATHER", "https://www.spaceweather.com/"),
        os.environ.get("TREND_NASA", "https://science.nasa.gov/heliophysics/"),
        os.environ.get("TREND_HEARTMATH", "https://www.heartmath.org/gci/gcms/live-data/"),
    ]
    items: List[Dict[str, str]] = []
    for url in candidate_urls:
        item = _scrape_title_desc(url)
        if item:
            items.append(item)
        if len(items) >= max_items:
            break
    return items

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
    trending = fetch_trending_articles(max_items=3)

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
        conflict_clause = "on conflict on constraint ux_daily_posts_global"
    else:
        conflict_clause = "on conflict on constraint ux_daily_posts_per_user"

    sql = f"""
insert into content.daily_posts (
  day, user_id, platform, title, caption, body_markdown, hashtags, metrics_json, sources_json
) values (
  $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb
)
{conflict_clause}
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