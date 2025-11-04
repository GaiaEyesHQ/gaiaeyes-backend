#!/usr/bin/env python3
"""
Trigger the nightly refresh of symptom marts in Supabase.

ENV:
  SUPABASE_DB_URL (required) -- direct or pooler connection string
"""

import asyncio
import os
import sys

import asyncpg


def env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        print(f"Missing required env var: {key}", file=sys.stderr)
        sys.exit(2)
    return value


SQL = "select marts.refresh_symptom_marts();"


async def main() -> None:
    dsn = env("SUPABASE_DB_URL")
    conn = await asyncpg.connect(dsn=dsn, statement_cache_size=0)
    try:
        await conn.execute(SQL)
        print("✅ marts.refresh_symptom_marts() completed")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
