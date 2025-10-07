#!/usr/bin/env python3
import os, sys, json, pathlib
from datetime import datetime, timedelta, timezone

MEDIA_DIR = os.getenv("MEDIA_DIR", "../gaiaeyes-media")
OUT = os.getenv("OUTPUT_JSON_PATH", f"{MEDIA_DIR}/data/quakes_latest.json")

DAY = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
WEEK = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"

import urllib.request

def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def pick(props):
    return {
        "mag": props.get("mag"),
        "place": props.get("place"),
        "time_utc": datetime.utcfromtimestamp(props.get("time",0)/1000.0).replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z"),
        "tsunami": props.get("tsunami"),
        "url": props.get("url")
    }

def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=72)

    rows = []
    for feed in (DAY, WEEK):
        try:
            data = fetch(feed)
            for f in data.get("features", []):
                p = f.get("properties", {}) or {}
                mag = p.get("mag")
                tms = p.get("time", 0)
                if mag is None or tms == 0: 
                    continue
                t = datetime.utcfromtimestamp(tms/1000.0).replace(tzinfo=timezone.utc)
                if t >= cutoff and mag >= 5.0:
                    rows.append(pick(p))
        except Exception as e:
            print(f"[USGS] warn {feed}: {e}", file=sys.stderr)

    # unique by (time, place, mag)
    seen, uniq = set(), []
    for r in rows:
        k = (r["time_utc"], r["place"], r["mag"])
        if k not in seen:
            seen.add(k); uniq.append(r)

    payload = {
        "timestamp_utc": now.replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "events": sorted(uniq, key=lambda x: x["time_utc"], reverse=True)[:10],
        "sources": {"usgs_day": DAY, "usgs_week": WEEK}
    }

    p = pathlib.Path(OUT); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",",":"), ensure_ascii=False))
    print(f"[usgs] wrote -> {p}")

if __name__ == "__main__":
    main()