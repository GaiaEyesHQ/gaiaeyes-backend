#!/usr/bin/env python3
"""
Build compare_series.json for overlay charts: quakes vs space-weather.
Guaranteed series: m5p_daily from quakes_history.json.
Optional: kp_daily_max, bz_daily_min, sw_daily_avg, flares, cme if sources exist later.

Env:
  MEDIA_DIR=/path/to/gaiaeyes-media
  OUTPUT_JSON_PATH=.../gaiaeyes-media/data/compare_series.json
"""
import os, sys, json, datetime as dt

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def main():
    media_dir = os.getenv("MEDIA_DIR", "gaiaeyes-media")
    out_path = os.getenv("OUTPUT_JSON_PATH", os.path.join(media_dir, "data", "compare_series.json"))

    qh = load_json(os.path.join(media_dir, "data", "quakes_history.json")) or {}
    # Placeholder for future series sources:
    # sh = load_json(os.path.join(media_dir, "data", "space_history.json")) or {}
    # fc = load_json(os.path.join(media_dir, "data", "flares_history.json")) or {}

    series = {}

    # Quakes M5+ daily (always available once quakes_history is populated)
    m5p_daily = (qh.get("series") or {}).get("m5p_daily") or []
    series["m5p_daily"] = m5p_daily

    # Hooks for future when you add space history:
    # series["kp_daily_max"] = sh.get("series", {}).get("kp_daily_max", [])
    # series["bz_daily_min"] = sh.get("series", {}).get("bz_daily_min", [])
    # series["sw_daily_avg"] = sh.get("series", {}).get("sw_daily_avg", [])
    # series["cme_daily_cnt"] = fc.get("series", {}).get("cme_daily_cnt", [])
    # series["flares_m_count"] = fc.get("series", {}).get("flares_m_count", [])

    out = {
        "timestamp_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "series": series,
        "meta": {
            "note": "Dates UTC. m5p_daily present by default. Space-weather series can be added as they become available."
        }
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",",":")))
    print(f"[compare_series] wrote -> {out_path}")

if __name__ == "__main__":
    main()