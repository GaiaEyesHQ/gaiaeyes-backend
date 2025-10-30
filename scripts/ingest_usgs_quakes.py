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

def pick(feat):
    props = feat.get("properties", {}) or {}
    geom  = feat.get("geometry", {}) or {}
    coords = geom.get("coordinates") or [None, None, None]
    depth_km = None
    try:
        if isinstance(coords, list) and len(coords) >= 3:
            depth_km = float(coords[2])
    except Exception:
        depth_km = None
    tms = props.get("time", 0)
    t = datetime.utcfromtimestamp(tms/1000.0).replace(tzinfo=timezone.utc) if tms else None
    return {
        "mag": props.get("mag"),
        "magType": props.get("magType"),
        "place": props.get("place"),
        "time_utc": t.isoformat().replace("+00:00","Z") if t else None,
        "depth_km": depth_km,
        "tsunami": props.get("tsunami"),
        "url": props.get("url")
    }

def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=72)

    rows = []
    # Containers for day totals and buckets (all magnitudes)
    day_features = []
    buckets_day = {"<2.5":0,"2.5–3.9":0,"4.0–4.9":0,"5.0–5.9":0,"6.0–6.9":0,"≥7.0":0}

    for feed in (DAY, WEEK):
        try:
            data = fetch(feed)
            feats = data.get("features", [])
            if feed == DAY:
                day_features = feats  # keep full set for totals/buckets
                # Build day buckets for all magnitudes (use UTC day feed only)
                for ff in feats:
                    try:
                        m = float((ff.get("properties") or {}).get("mag"))
                    except Exception:
                        m = None
                    if m is None: 
                        continue
                    if m < 2.5:
                        buckets_day["<2.5"] += 1
                    elif m < 4.0:
                        buckets_day["2.5–3.9"] += 1
                    elif m < 5.0:
                        buckets_day["4.0–4.9"] += 1
                    elif m < 6.0:
                        buckets_day["5.0–5.9"] += 1
                    elif m < 7.0:
                        buckets_day["6.0–6.9"] += 1
                    else:
                        buckets_day["≥7.0"] += 1
            # Build the 72h M5+ list (from DAY and WEEK feeds)
            for f in feats:
                p = f.get("properties", {}) or {}
                mag = p.get("mag")
                tms = p.get("time", 0)
                if mag is None or tms == 0:
                    continue
                t = datetime.utcfromtimestamp(tms/1000.0).replace(tzinfo=timezone.utc)
                if t >= cutoff and float(mag) >= 5.0:
                    rows.append(pick(f))
        except Exception as e:
            print(f"[USGS] warn {feed}: {e}", file=sys.stderr)

    # unique by (time, place, mag)
    seen, uniq = set(), []
    for r in rows:
        k = (r["time_utc"], r["place"], r["mag"])
        if k not in seen:
            seen.add(k); uniq.append(r)

    # All-events sample from the DAY feed (all magnitudes, last 24h), sorted by time desc, cap 100
    events_all = []
    for f in day_features:
        pp = (f.get("properties") or {})
        tms = pp.get("time", 0)
        if not tms: continue
        events_all.append(pick(f))
    events_all = [e for e in events_all if e.get("time_utc")]  # keep only parsed
    events_all.sort(key=lambda x: x.get("time_utc",""), reverse=True)
    events_all = events_all[:100]

    total_all = len(day_features)
    total_24h_m5p = sum(1 for f in day_features if ((f.get("properties") or {}).get("mag") or 0) >= 5.0)

    payload = {
        "timestamp_utc": now.replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "events": sorted(uniq, key=lambda x: x["time_utc"], reverse=True)[:10],
        "events_all_sample": events_all,
        "counts": {
            "all": total_all,
            "last_24h_m5p": total_24h_m5p
        },
        "buckets_day": buckets_day,
        "sources": {"usgs_day": DAY, "usgs_week": WEEK}
    }

    p = pathlib.Path(OUT); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",",":"), ensure_ascii=False))
    print(f"[usgs] wrote -> {p}")

if __name__ == "__main__":
    main()