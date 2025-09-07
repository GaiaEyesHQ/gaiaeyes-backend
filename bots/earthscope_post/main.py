import os, asyncio, json, re
from datetime import datetime, timedelta, timezone, date as Date
from typing import Any, Dict, List, Optional
from decimal import Decimal

import asyncpg
import requests
import feedparser
from bs4 import BeautifulSoup

from llm import generate_daily_earthscope, LLMFailure

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]

# ---------------- JSON helpers ----------------

def _to_jsonable(obj: Any) -> Any:
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
    today = datetime.now(timezone.utc).date()
    yday  = today - timedelta(days=1)
    q = """select day, row_count
           from marts.space_weather_daily
           where day in ($1, $2)"""
    rows = await fetch_all(conn, q, today, yday)
    by_day = {r["day"]: (r.get("row_count") or 0) for r in rows}
    if by_day.get(today, 0) >= 50:
        return today
    if by_day.get(yday, 0) >= 50:
        return yday
    raise SystemExit("no data for today/yesterday")

# ---------------- News candidate fetcher (LLM will pick) ----------------

SPACE_KEYWORDS = [
    "aurora","geomagnetic","kp "," kp","solar wind","cme","coronal","flare","sunspot",
    "noaa","swpc","helio","imf","magnetosphere","schumann","resonance","storm"
]
KW_RE = re.compile("|".join(SPACE_KEYWORDS), re.I)

def _is_space_related(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    return bool(KW_RE.search(text))

def _clip(s: str, n: int = 280) -> str:
    s = (s or "").strip()
    if len(s) <= n: return s
    return s[:n-1].rstrip() + "…"

def fetch_news_candidates(max_total: int = 20) -> List[Dict[str, str]]:
    feeds = [
        os.environ.get("TREND_FEED_1", "https://www.spaceweatherlive.com/en/news.rss"),
        os.environ.get("TREND_FEED_2", "https://science.nasa.gov/heliophysics/feed/"),
        os.environ.get("TREND_FEED_3", "https://www.swpc.noaa.gov/content/news-and-events"),
        os.environ.get("TREND_FEED_4", "https://science.nasa.gov/feed/"),
    ]
    out: List[Dict[str, str]] = []
    seen = set()

    # Manual pins take precedence
    pins = [u.strip() for u in os.environ.get("TREND_URLS", "").split(",") if u.strip()]
    for u in pins:
        if u not in seen:
            out.append({"source": "manual", "title": "", "url": u, "summary": ""})
            seen.add(u)
            if len(out) >= max_total:
                return out

    for url in feeds:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:10]:
                title = getattr(e, "title", "") or ""
                link  = getattr(e, "link", "") or ""
                summary = getattr(e, "summary", "") or ""
                if not link or link in seen:
                    continue
                seen.add(link)
                summary = _clip(re.sub(r"<[^>]+>", "", summary))
                # keep broader NASA feed items, LLM will filter; still keep few
                if "nasa.gov" in url or "spaceweatherlive" in url or _is_space_related(title, summary):
                    out.append({"source": url, "title": title.strip(), "url": link.strip(), "summary": summary})
                if len(out) >= max_total:
                    return out
        except Exception:
            continue
    return out[:max_total]

# ---------------- Main run ----------------

async def run():
    platform = os.environ.get("PLATFORM", "instagram").strip()
    user_id_env  = os.environ.get("USER_ID", "").strip()
    user_id  = user_id_env or None
    dry_run  = os.environ.get("DRY_RUN", "false").lower() == "true"

    conn = await asyncpg.connect(SUPABASE_DB_URL)

    day: Date = await get_best_day(conn)

    sw = await fetch_one(conn, "select * from marts.space_weather_daily where day=$1", day)
    if not sw:
        await conn.close()
        raise SystemExit("no space weather row")

    events = await fetch_all(conn, """
        select event_type, start_time, class
        from ext.donki_event
        where date(start_time) = $1
        order by start_time asc
    """, day)

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
    metrics_json = _to_jsonable(metrics_json)

    # NEW: get a basket of 10–20 news items and let the LLM choose
    news_candidates = fetch_news_candidates(max_total=20)

    # LLM render (rich sections + hashtags + sources)
    try:
        llm = generate_daily_earthscope(
            metrics_json=metrics_json,
            donki_events=events,
            news_candidates=news_candidates  # << key change
        )
        title        = llm["title"].strip()
        caption      = llm["caption"].strip()
        body_md      = llm["body_markdown"].strip()
        hashtags     = llm["hashtags"].strip()
        sources_json = llm["sources_json"]
    except Exception as e:
        # Deterministic fallback (from llm.py handles rich structure now)
        raise

    row = {
        "day": day,
        "user_id": user_id,
        "platform": platform,
        "title": title,
        "caption": caption,
        "body_markdown": body_md,
        "hashtags": hashtags,
        "metrics_json": json.dumps(metrics_json, ensure_ascii=False),
        "sources_json": json.dumps(_to_jsonable(sources_json), ensure_ascii=False),
    }

    if dry_run:
        preview = {**row, "day": day_iso}
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        await conn.close()
        return

    # Choose conflict target based on user_id NULL/not NULL (partial unique indexes)
    if user_id is None:
        sql = """
insert into content.daily_posts
  (day, user_id, platform, title, caption, body_markdown, hashtags, metrics_json, sources_json)
values
  ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
on conflict (day, platform) where (user_id is null)
do update set
  title = excluded.title,
  caption = excluded.caption,
  body_markdown = excluded.body_markdown,
  hashtags = excluded.hashtags,
  metrics_json = excluded.metrics_json,
  sources_json = excluded.sources_json,
  updated_at = now();
"""
    else:
        sql = """
insert into content.daily_posts
  (day, user_id, platform, title, caption, body_markdown, hashtags, metrics_json, sources_json)
values
  ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
on conflict (day, platform, user_id) where (user_id is not null)
do update set
  title = excluded.title,
  caption = excluded.caption,
  body_markdown = excluded.body_markdown,
  hashtags = excluded.hashtags,
  metrics_json = excluded.metrics_json,
  sources_json = excluded.sources_json,
  updated_at = now();
"""

    await conn.execute(sql,
        row["day"], row["user_id"], row["platform"], row["title"],
        row["caption"], row["body_markdown"], row["hashtags"],
        row["metrics_json"], row["sources_json"])

    await conn.close()
    print(f"Upserted Daily Earthscope for {day_iso} → platform={platform} (user_id={'null' if user_id is None else user_id})")

if __name__ == "__main__":
    asyncio.run(run())
