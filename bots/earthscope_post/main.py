import os, asyncio, json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import requests
from bs4 import BeautifulSoup

from llm import generate_daily_earthscope, LLMFailure

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]

# ---------- DB helpers ----------

async def fetch_all(conn, q, *args):
    rows = await conn.fetch(q, *args)
    return [dict(r) for r in rows]

async def fetch_one(conn, q, *args):
    row = await conn.fetchrow(q, *args)
    return dict(row) if row else None

async def get_best_day(conn) -> str:
    today = datetime.now(timezone.utc).date()
    yday  = today - timedelta(days=1)
    q = """select day, row_count from marts.space_weather_daily where day in ($1,$2)"""
    rows = await fetch_all(conn, q, str(today), str(yday))
    rows_map = {r["day"]: (r.get("row_count") or 0) for r in rows}
    if rows_map.get(str(today), 0) >= 50:
        return str(today)
    if rows_map.get(str(yday), 0) >= 50:
        return str(yday)
    raise SystemExit("no data for today/yesterday")

# ---------- Trending fetcher (simple) ----------

def _scrape_title_desc(url: str, timeout: int = 15) -> Optional[Dict[str, str]]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "gaia-ops/earthscope-bot"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.string.strip() if soup.title and soup.title.string else url)
        # prefer og:description, then meta[name=description]
        desc = ""
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"): desc = og["content"].strip()
        if not desc:
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"): desc = md["content"].strip()
        if desc and len(desc) > 240:
            desc = desc[:237].rstrip() + "…"
        return {"title": title, "url": url, "summary": desc or "Latest update from this source."}
    except Exception:
        return None

def fetch_trending_articles(max_items: int = 3) -> List[Dict[str, str]]:
    """Fetch 2–3 current references and short summaries from canonical sources."""
    candidate_urls = [
        os.environ.get("TREND_SOLARHAM", "https://www.solarham.com/"),
        os.environ.get("TREND_SPACEWEATHER", "https://www.spaceweather.com/"),
        os.environ.get("TREND_NASA", "https://www.nasa.gov/solar-system/sun/"),
        os.environ.get("TREND_HEARTMATH", "https://www.heartmath.org/gci/gcms/live-data/"),
    ]
    items: List[Dict[str, str]] = []
    for url in candidate_urls:
        item = _scrape_title_desc(url)
        if item: items.append(item)
        if len(items) >= max_items: break
    return items

# ---------- Main run ----------

async def run():
    platform = os.environ.get("PLATFORM","instagram")
    user_id  = os.environ.get("USER_ID") or None
    dry_run  = os.environ.get("DRY_RUN","false").lower() == "true"

    conn = await asyncpg.connect(SUPABASE_DB_URL)

    day = await get_best_day(conn)
    sw = await fetch_one(conn, "select * from marts.space_weather_daily where day=$1", day)
    if not sw:
        raise SystemExit("no space weather row")

    events = await fetch_all(conn, """
        select event_type, start_time, class
        from ext.donki_event
        where date(start_time) = $1
        order by start_time asc
    """, day)

    # Build metrics_json exactly per contract
    metrics_json: Dict[str, Any] = {
        "day": day,
        "space_weather": {
            "kp_max": sw.get("kp_max"),
            "bz_min": sw.get("bz_min"),
            "sw_speed_avg": sw.get("sw_speed_avg"),
            "flares_count": sw.get("flares_count"),
            "cmes_count": sw.get("cmes_count"),
        }
    }
    # (optional) If you later join health features, add "health" here.

    # Trending references (2–3 items with title+summary+link)
    trending = fetch_trending_articles(max_items=3)

    # LLM render
    try:
        llm = generate_daily_earthscope(metrics_json, events, trending)
        title        = llm["title"].strip()
        caption      = llm["caption"].strip()
        body_md      = llm["body_markdown"].strip()
        hashtags     = llm["hashtags"].strip()
        sources_json = llm["sources_json"]
    except Exception as e:
        # Minimal fallback (deterministic)
        kp = sw.get("kp_max"); bz = sw.get("bz_min"); wind = sw.get("sw_speed_avg")
        title   = f"Daily Earthscope • {day}"
        caption = (f"Earthscope — Kp {kp if kp is not None else 'n/a'}, "
                   f"Bz {bz if bz is not None else 'n/a'} nT, "
                   f"solar wind {wind if wind is not None else 'n/a'} km/s. "
                   "Ground, breathe, hydrate. #GaiaEyes #DailyEarthscope #SpaceWeather")
        body_md = f"""# Daily Earthscope • {day}

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

    row = {
        "day": day,
        "user_id": user_id,    # null for global
        "platform": platform,
        "title": title,
        "caption": caption,
        "body_markdown": body_md,
        "hashtags": hashtags,
        "metrics_json": json.dumps(metrics_json),
        "sources_json": json.dumps(sources_json),
    }

    if dry_run:
        print(json.dumps(row, indent=2, ensure_ascii=False))
        await conn.close()
        return

    # Upsert (idempotent) aligned with your unique index using coalesce(user_id, ZERO_UUID)
    await conn.execute("""
    insert into content.daily_posts
      (day,user_id,platform,title,caption,body_markdown,hashtags,metrics_json,sources_json)
    values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb)
    on conflict (day, coalesce(user_id, $10::uuid), platform)
    do update set
      title=$4, caption=$5, body_markdown=$6, hashtags=$7,
      metrics_json=$8::jsonb, sources_json=$9::jsonb, updated_at=now();
    """,
    row["day"], row["user_id"], row["platform"], row["title"],
    row["caption"], row["body_markdown"], row["hashtags"],
    row["metrics_json"], row["sources_json"], ZERO_UUID)

    await conn.close()
    print(f"Upserted Daily Earthscope for {day} → platform={platform}")

if __name__ == "__main__":
    asyncio.run(run())