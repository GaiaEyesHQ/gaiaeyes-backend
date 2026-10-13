#!/usr/bin/env python3
"""
Build compare_series.json for overlay charts comparing quakes and space-weather.
"""

import datetime as dt
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.history_json import load_json, validate_history, validate_quakes_history, SPACE_DAILY


def main():
    media_dir = os.getenv("MEDIA_DIR", "gaiaeyes-media")
    out_path = os.getenv(
        "OUTPUT_JSON_PATH", os.path.join(media_dir, "data", "compare_series.json")
    )

    qh = load_json(os.path.join(media_dir, "data", "quakes_history.json"))
    sh = load_json(os.path.join(media_dir, "data", "space_history.json"))
    validate_quakes_history(qh)
    validate_history(sh, "space_history.json", SPACE_DAILY)

    qser = (qh.get("series") or {})
    sser = (sh.get("series") or {})

    series = {}
    series["all_daily"] = qser.get("all_daily", [])
    series["m4p_daily"] = qser.get("m4p_daily", [])
    series["m5p_daily"] = qser.get("m5p_daily", [])
    series["m6p_daily"] = qser.get("m6p_daily", [])
    series["m5p_monthly"] = qser.get("m5p_monthly", [])
    series["m6p_monthly"] = qser.get("m6p_monthly", [])
    series["kp_daily_max"] = sser.get("kp_daily_max", [])
    series["bz_daily_min"] = sser.get("bz_daily_min", [])
    series["sw_daily_avg"] = sser.get("sw_daily_avg", [])

    labels = {
        "all_daily": "Quakes (all, daily)",
        "m4p_daily": "Quakes M4+ (daily)",
        "m5p_daily": "Quakes M5+ (daily)",
        "m6p_daily": "Quakes M6+ (daily)",
        "m5p_monthly": "Quakes M5+ (monthly)",
        "m6p_monthly": "Quakes M6+ (monthly)",
        "kp_daily_max": "Kp (daily max)",
        "bz_daily_min": "Bz (daily min, nT)",
        "sw_daily_avg": "Solar wind (daily avg, km/s)",
    }

    out = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "series": series,
        "labels": labels,
        "meta": {
            "note": "Dates UTC. Use lag to explore timing; correlation is exploratory, not causal."
        },
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("[compare_series] wrote ->", out_path)
    newest = max(day for day, count in qser["all_daily"] if count > 0)
    print(f"[compare_series] quake_source_timestamp_utc={qh['timestamp_utc']} "
          f"newest_quake_day={newest}")


if __name__ == "__main__":
    main()
