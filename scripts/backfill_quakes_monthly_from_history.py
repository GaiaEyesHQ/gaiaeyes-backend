#!/usr/bin/env python3
"""
One-time backfill of marts.quakes_monthly from quakes_history.json.

Usage:
  - Ensure quakes_history.json exists (e.g. run ingest_usgs_history.py first)
  - Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars
  - Run: python scripts/backfill_quakes_monthly_from_history.py

Env:
  HISTORY_JSON_PATH=/path/to/quakes_history.json
  SUPABASE_URL=https://<project>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=...
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from urllib.error import HTTPError, URLError


HISTORY_JSON_PATH = os.getenv("HISTORY_JSON_PATH", "quakes_history.json")

# Supabase REST base and key
REST = os.getenv("SUPABASE_REST_URL", "") or os.getenv("SUPABASE_URL", "")
REST = REST.rstrip("/")
if REST and "/rest/v1" not in REST:
    REST = REST + "/rest/v1"

KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.getenv("SUPABASE_SERVICE_KEY", "")
    or os.getenv("SUPABASE_ANON_KEY", "")
)


def rest_upsert(schema: str, table: str, rows: list[dict]) -> bool:
    """Upsert rows into schema.table via Supabase/PostgREST."""
    if not (REST and KEY and rows):
        print("[backfill] REST/KEY/rows missing; aborting upsert", file=sys.stderr)
        return False

    # Supabase: /rest/v1/{table}, schema via Content-Profile
    if "supabase.co" in REST:
        url = f"{REST}/{table}"
        headers = {
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        if schema and schema != "public":
            headers["Content-Profile"] = schema
            headers["Accept-Profile"] = schema
    else:
        url = f"{REST}/{schema}.{table}"
        headers = {
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    data = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(url, headers=headers, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return True
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        print(f"[backfill] upsert {schema}.{table} failed: HTTP {e.code}: {body}", file=sys.stderr)
        return False
    except URLError as e:
        print(f"[backfill] upsert {schema}.{table} failed: URL error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[backfill] upsert {schema}.{table} failed: {e}", file=sys.stderr)
        return False


def build_rows_from_history(history: dict) -> list[dict]:
    """
    Convert quakes_history.json['monthly'] into rows for marts.quakes_monthly.

    Expected monthly entries:
      { "month": "YYYY-MM", "all": N, "m4p": ..., "m5p": ..., "m6p": ..., "m7p": ... }
    """
    monthly = history.get("monthly") or []
    rows_map: dict[str, dict] = {}

    for row in monthly:
        mk = row.get("month")
        if not mk:
            continue
        # Normalize to first of month so it fits a date column
        month_date = f"{mk}-01"  # 'YYYY-MM-01'
        rows_map[mk] = {
            "month": month_date,
            "all_quakes": int(row.get("all", 0)),
            "m4p": int(row.get("m4p", 0)),
            "m5p": int(row.get("m5p", 0)),
            "m6p": int(row.get("m6p", 0)),
            "m7p": int(row.get("m7p", 0)),
        }

    return list(rows_map.values())


def main():
    if not os.path.exists(HISTORY_JSON_PATH):
        print(f"[backfill] history JSON not found at {HISTORY_JSON_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(HISTORY_JSON_PATH, "r", encoding="utf-8") as f:
        history = json.load(f)

    rows = build_rows_from_history(history)
    if not rows:
        print("[backfill] no monthly rows found in history JSON", file=sys.stderr)
        sys.exit(1)

    print(f"[backfill] prepared {len(rows)} monthly rows for marts.quakes_monthly")
    ok = rest_upsert("marts", "quakes_monthly", rows)
    if not ok:
        print("[backfill] upsert failed", file=sys.stderr)
        sys.exit(1)

    print("[backfill] upsert into marts.quakes_monthly complete")


if __name__ == "__main__":
    main()