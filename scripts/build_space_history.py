#!/usr/bin/env python3
import os
import json
import datetime as dt
import urllib.request
import urllib.parse

REST = os.getenv("SUPABASE_REST_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
OUT = os.getenv("OUTPUT_JSON_PATH", "space_history.json")
DAYS = int(os.getenv("HISTORY_DAYS", "365"))
TABLE = os.getenv("SW_DAILY_TABLE", "marts.space_weather_daily")
FIELDS = os.getenv("SW_DAILY_FIELDS", "day,kp_max_24h,bz_min,sw_speed_avg")


def query_since(start_iso: str):
    if not (REST and KEY):
        return []
    url = f"{REST}/{TABLE}?" + urllib.parse.urlencode({
        "select": FIELDS,
        "order": "day.asc",
        "day": "gte." + start_iso,
    })
    req = urllib.request.Request(
        url, headers={"apikey": KEY, "Authorization": "Bearer " + KEY}
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    since = (dt.datetime.utcnow().date() - dt.timedelta(days=DAYS - 1)).isoformat()
    rows = query_since(since)
    kp, bz, sw = [], [], []
    for r in rows:
        d = r.get("day")
        if not d:
            continue
        if r.get("kp_max_24h") is not None:
            kp.append([d, float(r["kp_max_24h"])])
        if r.get("bz_min") is not None:
            bz.append([d, float(r["bz_min"])])
        if r.get("sw_speed_avg") is not None:
            sw.append([d, float(r["sw_speed_avg"])])
    out = {
        "timestamp_utc": dt.datetime.utcnow()
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "series": {
            "kp_daily_max": kp,
            "bz_daily_min": bz,
            "sw_daily_avg": sw,
        },
    }
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("[space_history] wrote ->", OUT)


if __name__ == "__main__":
    main()
