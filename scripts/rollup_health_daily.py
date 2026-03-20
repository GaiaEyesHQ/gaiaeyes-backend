#!/usr/bin/env python3
"""
Refresh gaia.daily_summary for the last N days across users.

This script delegates to gaia.refresh_daily_summary_user(...) so the SQL
function remains the single source of truth for daily HealthKit normalization.

ENV:
  SUPABASE_DB_URL  (required)
  DAYS_BACK        (default 7)                 # how many days to recompute
  USER_TZ          (default 'America/Chicago') # day bucketing timezone
"""

import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import asyncpg

def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr); sys.exit(2)
    return v

DB = env("SUPABASE_DB_URL", required=True)
DAYS_BACK = int(env("DAYS_BACK", "7"))
USER_TZ = env("USER_TZ", "America/Chicago")

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        local_day = datetime.now(ZoneInfo(USER_TZ)).date()
        user_rows = await conn.fetch(
            """
            select distinct user_id
            from gaia.samples
            where start_time >= now() - ($1::int + 180) * interval '1 day'
            order by user_id
            """,
            DAYS_BACK,
        )
        refreshed = 0
        for row in user_rows:
            user_id = row["user_id"]
            if user_id is None:
                continue
            await conn.execute(
                "select gaia.refresh_daily_summary_user($1::uuid, $2::date, $3::text, $4::int)",
                user_id,
                local_day,
                USER_TZ,
                DAYS_BACK,
            )
            refreshed += 1
        print(
            f"Refreshed gaia.daily_summary for {refreshed} user(s) "
            f"through {local_day.isoformat()} (tz={USER_TZ}, days_back={DAYS_BACK})"
        )
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
