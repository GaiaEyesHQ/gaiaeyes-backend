#!/usr/bin/env python3
import os, sys, json, pathlib
from datetime import datetime, timedelta, timezone

MEDIA_DIR = os.getenv("MEDIA_DIR", "../gaiaeyes-media")
OUT = os.getenv("OUTPUT_JSON_PATH", f"{MEDIA_DIR}/data/quakes_latest.json")

DAY = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
WEEK = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"

import urllib.request
import urllib.parse

# Supabase/PostgREST env (optional DB upserts)
# Prefer an explicit SUPABASE_REST_URL if provided, otherwise derive from SUPABASE_URL.
REST = os.getenv("SUPABASE_REST_URL", "") or os.getenv("SUPABASE_URL", "")
REST = REST.rstrip("/")
if REST and "/rest/v1" not in REST:
    REST = REST + "/rest/v1"
# Prefer a service role key, fall back to SUPABASE_SERVICE_KEY or anon key if present.
KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.getenv("SUPABASE_SERVICE_KEY", "")
    or os.getenv("SUPABASE_ANON_KEY", "")
)

def rest_upsert(schema: str, table: str, rows: list):
    """Upsert rows into schema.table via PostgREST/Supabase (Prefer: resolution=merge-duplicates)."""
    if not (REST and KEY and rows):
        return False

    # Supabase REST (supabase.co) uses /rest/v1/{table} and Content-Profile to select schema.
    if "supabase.co" in REST:
        url = f"{REST}/{table}"
        headers = {
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        if schema and schema != "public":
            headers["Content-Profile"] = schema
            headers["Accept-Profile"] = schema
    else:
        # Generic PostgREST: schema-qualified table in the path.
        url = f"{REST}/{schema}.{table}"
        headers = {
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }

    data = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(url, headers=headers, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()  # drain
        return True
    except Exception as e:
        print(f"[postgrest] upsert {schema}.{table} failed: {e}", file=sys.stderr)
        return False

def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def pick(feat):
    props = feat.get("properties", {}) or {}
    geom  = feat.get("geometry", {}) or {}
    coords = geom.get("coordinates") or [None, None, None]
    depth_km = None
    lat = lon = None
    try:
        if isinstance(coords, list):
            lon = float(coords[0]) if len(coords) > 0 and coords[0] is not None else None
            lat = float(coords[1]) if len(coords) > 1 and coords[1] is not None else None
            depth_km = float(coords[2]) if len(coords) > 2 and coords[2] is not None else None
    except Exception:
        pass
    tms = props.get("time", 0)
    t = datetime.utcfromtimestamp(tms/1000.0).replace(tzinfo=timezone.utc) if tms else None
    return {
        "usgs_id": feat.get("id"),
        "time_utc": t.isoformat().replace("+00:00","Z") if t else None,
        "mag": props.get("mag"),
        "magType": props.get("magType"),
        "depth_km": depth_km,
        "place": props.get("place"),
        "latitude": lat,
        "longitude": lon,
        "tsunami": props.get("tsunami"),
        "url": props.get("url")
    }

def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=72)

    rows = []
    all_features = []
    # Containers for day totals and buckets (all magnitudes)
    day_features = []
    buckets_day = {"<2.5":0,"2.5–3.9":0,"4.0–4.9":0,"5.0–5.9":0,"6.0–6.9":0,"≥7.0":0}

    for feed in (DAY, WEEK):
        try:
            data = fetch(feed)
            feats = data.get("features", [])
            all_features.extend(feats)
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
    SAMPLE_MAX = int(os.getenv("EQ_SAMPLE_MAX", "300"))
    events_all = events_all[:SAMPLE_MAX]

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

    # --- Optional DB upserts (ext + marts) via PostgREST ---
    try:
        if REST and KEY:
            # Upsert raw events into ext.earthquakes_events (dedup by usgs_id)
            events_rows = []
            for f in all_features:
                ev = pick(f)
                if not ev.get("usgs_id"):
                    continue
                events_rows.append({
                    "usgs_id": ev["usgs_id"],
                    "time_utc": ev["time_utc"],
                    "mag": ev["mag"],
                    "mag_type": ev.get("magType"),
                    "depth_km": ev.get("depth_km"),
                    "place": ev.get("place"),
                    "latitude": ev.get("latitude"),
                    "longitude": ev.get("longitude"),
                    "url": ev.get("url"),
                    "source": "usgs"
                })
            if events_rows:
                rest_upsert("ext", "earthquakes_events", events_rows)

            # Upsert into ext.earthquakes for API consumers (/v1/quakes/events)
            quakes_rows = []
            for f in all_features:
                ev = pick(f)
                if not ev.get("usgs_id") or not ev.get("time_utc"):
                    continue
                quakes_rows.append({
                    "event_id": ev["usgs_id"],
                    "origin_time": ev["time_utc"],
                    "mag": ev["mag"],
                    "depth_km": ev.get("depth_km"),
                    "lat": ev.get("latitude"),
                    "lon": ev.get("longitude"),
                    "place": ev.get("place"),
                    "src": "usgs",
                    "meta": {
                        "url": ev.get("url"),
                        "magType": ev.get("magType"),
                        "tsunami": ev.get("tsunami"),
                    },
                })
            if quakes_rows:
                rest_upsert("ext", "earthquakes", quakes_rows)

            # Upsert day snapshot into ext.earthquakes_day
            day_row = {
                "day": now.date().isoformat(),
                "total_all": total_all,
                "buckets_day": buckets_day
            }
            rest_upsert("ext", "earthquakes_day", [day_row])

            # Compute and upsert daily aggregate into marts.quakes_daily for today
            # Derive all_quakes/m4p/m5p/m6p/m7p from the day_features list
            m4 = m5 = m6 = m7 = 0
            for ff in day_features:
                try:
                    m = float((ff.get("properties") or {}).get("mag"))
                except Exception:
                    m = None
                if m is None: continue
                if m >= 4.0: m4 += 1
                if m >= 5.0: m5 += 1
                if m >= 6.0: m6 += 1
                if m >= 7.0: m7 += 1
            marts_daily = {
                "day": now.date().isoformat(),
                "all_quakes": total_all,
                "m4p": m4,
                "m5p": m5,
                "m6p": m6,
                "m7p": m7
            }
            rest_upsert("marts", "quakes_daily", [marts_daily])
    except Exception as e:
        print(f"[postgrest] upserts skipped: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()