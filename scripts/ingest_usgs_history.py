#!/usr/bin/env python3
"""
Build quakes_history.json from USGS events API.
Outputs daily (UTC) and monthly totals (all mags + M4+/M5+/M6+/M7+) and chart series.
Env:
  OUTPUT_JSON_PATH=/path/to/gaiaeyes-media/data/quakes_history.json
"""
import os, sys, json, urllib.request, urllib.parse, datetime as dt
import errno
import gzip
import http.client
import socket
import ssl
import time
import urllib.error
import zlib
from collections import defaultdict, Counter

DAYS = int(os.getenv("HISTORY_DAYS", "365"))
MONTHS = int(os.getenv("HISTORY_MONTHS", "24"))

USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
USGS_PAGE_SIZE = 5000
USGS_MAX_ATTEMPTS = 4
USGS_TIMEOUT_SECONDS = 60
USGS_RETRY_BACKOFF_SECONDS = 2
USGS_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _retryable_usgs_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in USGS_RETRYABLE_STATUS
    if isinstance(exc, urllib.error.URLError):
        return _retryable_usgs_error(exc.reason)
    if isinstance(exc, socket.gaierror):
        return exc.errno == socket.EAI_AGAIN
    return isinstance(exc, (http.client.IncompleteRead, EOFError, gzip.BadGzipFile,
                            zlib.error, TimeoutError,
                            ConnectionError, ssl.SSLEOFError)) or (
        isinstance(exc, OSError) and exc.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH}
    )


def _fetch_usgs_page(req, offset, start_date, end_date):
    for attempt in range(1, USGS_MAX_ATTEMPTS + 1):
        bytes_read = 0
        try:
            # Accept a page only after the full read. Each retry opens a fresh
            # response for the same query, without advancing the offset.
            with urllib.request.urlopen(req, timeout=USGS_TIMEOUT_SECONDS) as response:
                if response.status == 204:
                    return {"features": []}  # USGS's default no-data response.
                encoding = ",".join(response.headers.get_all("Content-Encoding", [])).strip().lower()
                if encoding not in {"", "identity", "gzip"}:
                    raise ValueError("Unsupported USGS content encoding")
                raw = response.read()
                bytes_read = len(raw)
                if encoding == "gzip":
                    if not raw:
                        raise EOFError("Empty USGS gzip body")
                    # Validate the complete gzip stream (including its trailer)
                    # before accepting JSON or advancing this page's offset.
                    raw = gzip.decompress(raw)
        except (http.client.IncompleteRead, OSError, EOFError, zlib.error, ValueError) as exc:
            if isinstance(exc, http.client.IncompleteRead):
                bytes_read = len(exc.partial)
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            retry = _retryable_usgs_error(exc) and attempt < USGS_MAX_ATTEMPTS
            delay = USGS_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1)
            failure = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
            action = f"retrying in {delay}s" if retry else "aborting"
            # Log only our query context and counts, never response bodies,
            # headers, full URLs, or exception messages.
            print(f"[quakes_history] USGS start={start_date!r} end={end_date!r} "
                  f"limit={USGS_PAGE_SIZE} offset={offset} attempt={attempt}/{USGS_MAX_ATTEMPTS} "
                  f"bytes_read={bytes_read} failed ({failure}); {action}", file=sys.stderr)
            if not retry:
                raise
            time.sleep(delay)
        else:
            # Invalid JSON/UTF-8 is not a transient transport failure.
            return json.loads(raw.decode("utf-8"))

def fetch_usgs(start_date: str, end_date: str):
    """Fetch all results between start_date and end_date using pagination."""
    all_features = []
    seen_ids = set()
    offset = 1
    limit = USGS_PAGE_SIZE
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
        req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0", "Accept-Encoding":"gzip"})
        data = _fetch_usgs_page(req, offset, start_date, end_date)
        feats = data.get("features", [])
        if not feats:
            break
        for feature in feats:
            event_id = feature.get("id")
            if event_id is not None:
                if event_id in seen_ids:
                    continue
                seen_ids.add(event_id)
            all_features.append(feature)
        # Advance/terminate by the raw page size, not the number of unique IDs.
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
    cutoff = dt.datetime.now(dt.timezone.utc)
    today = cutoff.date()
    start = today - dt.timedelta(days=DAYS-1)
    # Query contiguous UTC windows through the captured run time, including the
    # partial current day. USGS includes both query endpoints; below we count
    # each window as [start, end) so shared-boundary events are counted once.
    chunks = []
    cur = dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc)
    while cur < cutoff:
        nxt = min(cur + dt.timedelta(days=30), cutoff)
        chunks.append((cur, nxt))
        cur = nxt

    daily = defaultdict(lambda: {"all":0,"m4p":0,"m5p":0,"m6p":0,"m7p":0})
    monthly = defaultdict(lambda: {"all":0,"m4p":0,"m5p":0,"m6p":0,"m7p":0})

    total_events = 0
    for s,e in chunks:
        data = fetch_usgs(s.isoformat(), e.isoformat())
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
            t = dt.datetime.fromtimestamp(time_ms/1000.0, tz=dt.timezone.utc)
            if not s <= t < e:
                continue
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
            "note": ("Daily counts are UTC day bins. 'm5p' = M5.0 and above. "
                     "Current UTC day/month is partial; events before "
                     f"{cutoff.isoformat().replace('+00:00', 'Z')} are included.")
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
    try:
        main()
    except (http.client.IncompleteRead, OSError, EOFError, zlib.error, ValueError) as exc:
        # Expected download/decode failures must not reintroduce upstream
        # exception text (including body prefixes) through a CLI traceback.
        print(f"[quakes_history] failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
