#!/usr/bin/env python3
"""
Build quakes_history.json from USGS events API.
Outputs daily (UTC) and monthly totals (all mags + M4+/M5+/M6+/M7+) and chart series.
Env:
  OUTPUT_JSON_PATH=/path/to/gaiaeyes-media/data/quakes_history.json
"""
import os, sys, json, urllib.request, urllib.parse, datetime as dt
from collections import defaultdict, Counter

DAYS = int(os.getenv("HISTORY_DAYS", "365"))
MONTHS = int(os.getenv("HISTORY_MONTHS", "24"))

USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"

def fetch_usgs(start_date: str, end_date: str):
    """Fetch all results between start_date and end_date using pagination."""
    all_features = []
    offset = 1
    limit = 20000
    while True:
        params = dict(
            format="geojson",
            starttime=start_date,
            endtime=end_date,
            minmagnitude="0",
            orderby="time-asc",
            limit=str(limit),
            offset=str(offset)
        )
        url = USGS_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        feats = data.get("features", [])
        if not feats:
            break
        all_features.extend(feats)
        if len(feats) < limit:
            break
        offset += limit
    return {"type":"FeatureCollection","features":all_features}

def iso_date(d: dt.date) -> str:
    return d.isoformat()

def month_key(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"

def bucket_mag(m: float) -> str:
    if m < 4.0: return "<4.0"
    if m < 5.0: return "4.0–4.9"
    if m < 6.0: return "5.0–5.9"
    if m < 7.0: return "6.0–6.9"
    return "≥7.0"

def build():
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=DAYS-1)
    # Split into ~30-day chunks to avoid USGS 400s
    chunks = []
    cur = start
    while cur <= today:
        nxt = min(cur + dt.timedelta(days=30), today)
        chunks.append((cur, nxt))
        cur = nxt + dt.timedelta(days=1)

    daily = defaultdict(lambda: {"all":0,"m4p":0,"m5p":0,"m6p":0,"m7p":0})
    monthly = defaultdict(lambda: {"all":0,"m4p":0,"m5p":0,"m6p":0,"m7p":0})

    total_events = 0
    for s,e in chunks:
        data = fetch_usgs(iso_date(s), iso_date(e))
        feats = data.get("features", [])
        total_events += len(feats)
        for f in feats:
            props = f.get("properties", {}) or {}
            mag = props.get("mag")
            time_ms = props.get("time")  # epoch ms
            if time_ms is None: continue
            try:
                m = float(mag) if mag is not None else None
            except Exception:
                m = None
            t = dt.datetime.utcfromtimestamp(time_ms/1000.0)
            dkey = t.date()
            mkey = month_key(dkey)
            # increment all
            daily[dkey]["all"] += 1
            monthly[mkey]["all"] += 1
            if m is not None:
                if m >= 4.0:
                    daily[dkey]["m4p"] += 1
                    monthly[mkey]["m4p"] += 1
                if m >= 5.0:
                    daily[dkey]["m5p"] += 1
                    monthly[mkey]["m5p"] += 1
                if m >= 6.0:
                    daily[dkey]["m6p"] += 1
                    monthly[mkey]["m6p"] += 1
                if m >= 7.0:
                    daily[dkey]["m7p"] += 1
                    monthly[mkey]["m7p"] += 1

    # Order and clamp ranges
    dd = []
    dcur = start
    for _ in range(DAYS):
        row = daily[dcur]
        dd.append({"date": iso_date(dcur), **row})
        dcur += dt.timedelta(days=1)

    # Monthly last N months (build from month keys present)
    # Ensure the last MONTHS months
    mon_list = []
    mcur = month_key(today.replace(day=1))
    # Build a set of all months in daily window
    months_set = {month_key(start + dt.timedelta(days=i)) for i in range(DAYS)}
    # Sort months
    months_sorted = sorted(list(months_set))[-MONTHS:]
    for mk in months_sorted:
        row = monthly[mk]
        mon_list.append({"month": mk, **row})

    series = {
        "m5p_daily":  [[row["date"], row["m5p"]] for row in dd],
        "m6p_daily":  [[row["date"], row["m6p"]] for row in dd],
        "all_daily":  [[row["date"], row["all"]] for row in dd],
        "m5p_monthly":[[row["month"], row["m5p"]] for row in mon_list],
        "m6p_monthly":[[row["month"], row["m6p"]] for row in mon_list],
    }

    out = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "window": {"days": DAYS},
        "daily": dd,
        "monthly": mon_list,
        "series": series,
        "meta": {
            "source": "USGS",
            "note": "Daily counts are UTC day bins. 'm5p' = M5.0 and above."
        }
    }
    return out

def main():
    out = build()
    path = os.getenv("OUTPUT_JSON_PATH", "quakes_history.json")
    dirpath = os.path.dirname(path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    raw = json.dumps(out, ensure_ascii=False, separators=(",",":"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"[quakes_history] wrote -> {path}")

if __name__ == "__main__":
    main()