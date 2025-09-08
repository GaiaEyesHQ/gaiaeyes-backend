import os, asyncio, json
from datetime import datetime, timedelta, timezone, date as Date
from typing import Any, Dict, List, Optional
from decimal import Decimal

import asyncpg

from llm import generate_daily_earthscope

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

    # If you keep DONKI later, you can still fetch here; it's unused now.
    events: List[Dict[str, Any]] = []

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

    # LLM render (effects + self-care only; no trending, no sources section)
    llm = generate_daily_earthscope(
        metrics_json=metrics_json,
        donki_events=events
    )
    title        = llm["title"].strip()
    caption      = llm["caption"].strip()
    body_md      = llm["body_markdown"].strip()
    hashtags     = llm["hashtags"].strip()
    sources_json = llm.get("sources_json") or {}  # remains empty by design

    row = {
        "day": day,
        "user_id": user_id,
        "platform": platform,
        "title": title,
        "caption": caption,
        "body_markdown": body_md,
        "hashtags": hashtags,
        "metrics_json": json.dumps(metrics_json, ensure_ascii=False),
        "sources_json": json.dumps(sources_json, ensure_ascii=False),  # '{}'::jsonb
    }

    if dry_run:
        preview = {**row, "day": day_iso}
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        await conn.close()
        return

    # Upsert based on your partial unique indexes (global vs per-user)
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
