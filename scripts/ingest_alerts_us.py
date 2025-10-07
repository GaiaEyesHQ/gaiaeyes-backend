#!/usr/bin/env python3
import os, sys, json, pathlib
from datetime import datetime, timezone
import urllib.request

MEDIA_DIR = os.getenv("MEDIA_DIR", "../gaiaeyes-media")
OUT = os.getenv("OUTPUT_JSON_PATH", f"{MEDIA_DIR}/data/alerts_us_latest.json")

# NWS API (alerts active)
NWS = "https://api.weather.gov/alerts/active"  # returns GeoJSON

TYPES = {"Severe Thunderstorm Warning","Tornado Warning","Flood Warning","Flash Flood Warning",
         "Severe Thunderstorm Watch","Tornado Watch","Flood Advisory","Flash Flood Watch"}

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent":"gaiaeyes.com"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    now = datetime.now(timezone.utc)
    data = {}
    try:
        data = fetch(NWS)
    except Exception as e:
        print(f"[NWS] fetch failed: {e}", file=sys.stderr)

    rows = []
    for f in data.get("features", []):
        p = f.get("properties", {}) or {}
        ev = (p.get("event") or "").strip()
        if ev not in TYPES: 
            continue
        area = p.get("areaDesc") or ""
        onset = p.get("onset") or p.get("effective")
        ends  = p.get("ends") or p.get("expires")
        rows.append({
            "event": ev,
            "headline": p.get("headline") or ev,
            "area": area,
            "onset_utc": onset,
            "ends_utc": ends,
            "severity": (p.get("severity") or "").lower(),
            "certainty": (p.get("certainty") or "").lower(),
            "urgency": (p.get("urgency") or "").lower(),
            "nws_url": p.get("id")
        })

    payload = {
        "timestamp_utc": now.replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "alerts": rows[:20],
        "sources": {"nws_active": NWS}
    }

    p = pathlib.Path(OUT); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",",":"), ensure_ascii=False))
    print(f"[nws] wrote -> {p}")

if __name__ == "__main__":
    main()