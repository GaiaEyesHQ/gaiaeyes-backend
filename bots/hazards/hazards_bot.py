#!/usr/bin/env python3
"""Global hazards bot: fetch, dedupe, and post updates to WordPress."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import feedparser
import requests
from dateutil import parser as dtparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.append(SCRIPT_DIR)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from bots.hazards.wp_client import WPClient  # noqa: E402
from scripts.supabase_rest_client import supabase_upsert  # noqa: E402

UTC = timezone.utc

DB_PATH = os.path.join(SCRIPT_DIR, "hazards.sqlite")

# Optional local/remote media quakes feed (GaiaEyes media repo)
MEDIA_QUAKES_CANDIDATE_PATHS = [
    os.path.join(os.environ.get("GITHUB_WORKSPACE", ""), "gaiaeyes-media", "data", "quakes_latest.json"),
    os.path.join(SCRIPT_DIR, "..", "..", "gaiaeyes-media", "data", "quakes_latest.json"),
    os.path.join(os.getcwd(), "gaiaeyes-media", "data", "quakes_latest.json"),
]
MEDIA_QUAKES_RAW_URL = "https://raw.githubusercontent.com/GaiaEyesHQ/gaiaeyes-media/main/data/quakes_latest.json"
# Optional override URL for media quakes (set in ENV to force a specific URL)
MEDIA_QUAKES_URL = os.environ.get("MEDIA_QUAKES_URL", "").strip()
def load_json_file(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None

# Candidate endpoints (providers sometimes rotate or rate-limit)
USGS_ENDPOINTS = [
    # User-preferred: only significant events
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_hour.geojson",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson",
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson",
    # Fallback (48h window via FDSN)
    "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude=5&starttime={start}",
]
GDACS_ENDPOINTS = [
    # User-preferred: last 100 latest events
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/latest",
    # Fallbacks
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/JSON",
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/Json",
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/json",
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist",
]
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"


# Helper to try multiple endpoints with fallback and friendly User-Agent
def fetch_json_any(urls: List[str], *, params: Optional[dict]=None, timeout: int=20) -> Optional[dict]:
    headers = {
        "Accept": "application/json, application/*+json",
        "User-Agent": "GaiaEyes-HazardsBot/1.0 (+https://gaiaeyes.com)"
    }
    last_exc = None
    for raw in urls:
        url = raw
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 404 or resp.status_code == 403:
                last_exc = Exception(f"{resp.status_code} for {url}")
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_exc = e
            continue
    if last_exc:
        raise last_exc
    return None


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha1(value: str) -> str:
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    degrees_to_radians = math.pi / 180
    dlat = (lat2 - lat1) * degrees_to_radians
    dlon = (lon2 - lon1) * degrees_to_radians
    a = (
        0.5
        - math.cos(dlat) / 2
        + math.cos(lat1 * degrees_to_radians)
        * math.cos(lat2 * degrees_to_radians)
        * (1 - math.cos(dlon))
        / 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def db_init() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
    CREATE TABLE IF NOT EXISTS seen (
      source TEXT NOT NULL,
      src_id TEXT NOT NULL,
      hash TEXT NOT NULL,
      first_seen TEXT NOT NULL,
      last_seen TEXT NOT NULL,
      wp_post_id INTEGER,
      PRIMARY KEY (source, src_id)
    );
    """
    )
    con.execute(
        """
    CREATE TABLE IF NOT EXISTS items (
      key TEXT PRIMARY KEY,
      payload TEXT NOT NULL,
      ts TEXT NOT NULL,
      type TEXT NOT NULL,
      severity TEXT NOT NULL,
      lat REAL,
      lon REAL
    );
    """
    )
    con.commit()
    con.close()


def cache_upsert_seen(source: str, src_id: str, content_hash: str) -> tuple[bool, Optional[int]]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "SELECT hash, wp_post_id FROM seen WHERE source=? AND src_id=?",
        (source, src_id),
    )
    row = cur.fetchone()
    now = iso(now_utc())
    if row:
        old_hash, wp_post_id = row
        if old_hash == content_hash:
            cur.execute(
                "UPDATE seen SET last_seen=? WHERE source=? AND src_id=?",
                (now, source, src_id),
            )
            con.commit()
            con.close()
            return False, wp_post_id
        cur.execute(
            "UPDATE seen SET hash=?, last_seen=? WHERE source=? AND src_id=?",
            (content_hash, now, source, src_id),
        )
        con.commit()
        con.close()
        return True, wp_post_id
    cur.execute(
        "INSERT INTO seen(source, src_id, hash, first_seen, last_seen) VALUES(?,?,?,?,?)",
        (source, src_id, content_hash, now, now),
    )
    con.commit()
    con.close()
    return True, None


def cache_set_wp_id(source: str, src_id: str, post_id: int) -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "UPDATE seen SET wp_post_id=? WHERE source=? AND src_id=?",
        (post_id, source, src_id),
    )
    con.commit()
    con.close()


def items_put(
    key: str,
    payload: dict,
    ts: str,
    type_: str,
    severity: str,
    lat: Optional[float],
    lon: Optional[float],
) -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT OR REPLACE INTO items(key, payload, ts, type, severity, lat, lon) VALUES(?,?,?,?,?,?,?)",
        (key, json.dumps(payload), ts, type_, severity, lat, lon),
    )
    con.commit()
    con.close()


def items_window(hours: int = 12) -> List[dict]:
    cutoff = iso(now_utc() - timedelta(hours=hours))
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "SELECT payload FROM items WHERE ts >= ? ORDER BY ts ASC",
        (cutoff,),
    )
    rows = cur.fetchall()
    con.close()
    return [json.loads(row[0]) for row in rows]


def ensure_taxonomy(wp: WPClient) -> Dict[str, int]:
    try:
        return {
            "Hazards Digest": wp.ensure_category("Hazards Digest", "hazards-digest"),
            "Global Hazards": wp.ensure_category("Global Hazards", "global-hazards"),
            "Alerts": wp.ensure_category("Alerts", "alerts"),
            "Earthquake": wp.ensure_category("Earthquake"),
            "Cyclone": wp.ensure_category("Cyclone"),
            "Volcano/Ash": wp.ensure_category("Volcano/Ash", "volcano-ash"),
            "Flood": wp.ensure_category("Flood"),
            "Wildfire": wp.ensure_category("Wildfire"),
            "Drought": wp.ensure_category("Drought"),
            "Storm": wp.ensure_category("Storm"),
            "Landslide": wp.ensure_category("Landslide"),
        }
    except Exception as e:  # pragma: no cover - network/auth handling
        raise RuntimeError(f"Failed to ensure categories via WP REST: {e}")


def severity_quake_usgs(mag: float) -> str:
    if mag >= 7.5:
        return "red"
    if mag >= 7.0:
        return "orange"
    if mag >= 6.0:
        return "yellow"
    return "info"


def severity_from_gdacs_color(color: str) -> str:
    normalized = (color or "").lower()
    if normalized == "red":
        return "red"
    if normalized == "orange":
        return "orange"
    if normalized == "yellow":
        return "yellow"
    return "info"


def hazard_type_from_text(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ["earthquake"]):
        return "quake"
    if any(w in t for w in ["tropical cyclone", "hurricane", "typhoon", "cyclone"]):
        return "cyclone"
    if any(w in t for w in ["volcano", "volcanic", "ash"]):
        return "ash"
    if any(w in t for w in ["flood", "inundation", "flash flood"]):
        return "flood"
    if any(w in t for w in ["wildfire", "forest fire", "bushfire"]):
        return "wildfire"
    if any(w in t for w in ["drought"]):
        return "drought"
    if any(w in t for w in ["landslide", "mudslide"]):
        return "landslide"
    if any(w in t for w in ["storm", "severe storm", "windstorm", "gust"]):
        return "storm"
    return "other"


def severity_from_text(text: str) -> str:
    t = (text or "").lower()
    if "red" in t:
        return "red"
    if "orange" in t:
        return "orange"
    if "yellow" in t:
        return "yellow"
    if "green" in t:
        return "info"
    return "info"


def fetch_usgs() -> List[dict]:
    # try USGS GeoJSON summary feeds first; fallback to FDSN query for the last 48h
    start_iso = (now_utc() - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S")
    geojson = None
    try:
        geojson = fetch_json_any(USGS_ENDPOINTS[:2], timeout=20)
    except Exception:
        # fallback to FDSN query form
        geojson = fetch_json_any([USGS_ENDPOINTS[2].format(start=start_iso)], timeout=25)
    if not geojson:
        return []
    items: List[dict] = []
    for feature in geojson.get("features", []):
        properties = feature.get("properties", {}) or {}
        geometry = feature.get("geometry", {}) or {}
        coordinates = geometry.get("coordinates", [None, None])
        lon, lat = coordinates[0], coordinates[1]
        magnitude = properties.get("mag")
        time_ms = properties.get("time")
        if time_ms is None:
            continue
        timestamp = datetime.fromtimestamp(time_ms / 1000.0, tz=UTC)
        if timestamp < now_utc() - timedelta(hours=48):
            continue
        src_id = str(
            properties.get("code")
            or properties.get("ids")
            or properties.get("id")
            or properties.get("title")
        )
        title = properties.get("title") or (
            f"M{magnitude:.1f} Earthquake" if magnitude is not None else "Earthquake"
        )
        url = properties.get("url")
        severity = severity_quake_usgs(magnitude or 0.0)
        payload = {
            "source": "usgs",
            "id": src_id,
            "ts": iso(timestamp),
            "type": "quake",
            "severity": severity,
            "title": title,
            "body": properties.get("place") or "",
            "mag": magnitude,
            "lat": lat,
            "lon": lon,
            "links": [url] if url else [],
        }
        items.append(payload)
    return items


def fetch_gdacs() -> List[dict]:
    """
    Prefer the official GDACS RSS (includes floods, wildfires, droughts, etc.)
    and fall back to the JSON event list if RSS parsing fails.
    """
    # --- Try RSS first ---
    try:
        headers = {
            "User-Agent": "GaiaEyes-HazardsBot/1.0 (+https://gaiaeyes.com)",
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        }
        resp = requests.get(GDACS_RSS_URL, headers=headers, timeout=25)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)

        results: List[dict] = []
        now_cut = now_utc() - timedelta(hours=48)

        for entry in parsed.entries:
            title = entry.get("title") or ""
            link = entry.get("link")
            summary = entry.get("summary") or entry.get("description") or ""
            published = entry.get("published") or entry.get("updated") or ""
            try:
                ts = dtparse.parse(published).astimezone(UTC) if published else now_utc()
            except Exception:
                ts = now_utc()
            if ts < now_cut:
                continue

            raw_txt = f"{title}\n{summary}"
            hazard = hazard_type_from_text(raw_txt)
            sev = severity_from_text(raw_txt)

            # Light location heuristic from title ("… in <place>")
            loc = None
            lowered = title.lower()
            if " in " in lowered:
                loc = title[lowered.index(" in ") + 4 :].strip()

            src_id = entry.get("id") or link or sha1(f"{title}|{published}")

            # The 'details' are the RSS summary/description HTML snippet
            results.append(
                {
                    "source": "gdacs",
                    "id": src_id,
                    "ts": iso(ts),
                    "type": hazard,
                    "severity": sev,
                    "title": title,
                    "body": (summary[:4000] if isinstance(summary, str) else ""),
                    "details": (summary if isinstance(summary, str) else ""),
                    "lat": None,
                    "lon": None,
                    "links": [link] if link else [],
                    "location": loc,
                }
            )
        if results:
            return results
    except Exception as e:
        print("[warn] GDACS RSS fetch failed, falling back to JSON:", e, file=sys.stderr)

    # --- Fallback: the JSON endpoints (existing behavior) ---
    data = fetch_json_any(GDACS_ENDPOINTS, timeout=25)
    if not data:
        return []
    results: List[dict] = []
    for event in data.get("features", []):
        properties = event.get("properties", {}) or {}
        geometry = event.get("geometry", {}) or {}
        coordinates = geometry.get("coordinates", [None, None])
        lon, lat = coordinates[0], coordinates[1]
        event_id = str(
            properties.get("eventid")
            or properties.get("identifier")
            or properties.get("eventid")
        )
        event_type_val = (properties.get("eventtype") or "").lower()
        name = (
            properties.get("eventname")
            or properties.get("title")
            or properties.get("eventname")
        )
        alert = properties.get("alertlevel") or ""
        startdate = (
            properties.get("fromdate")
            or properties.get("alertdate")
            or properties.get("publicationdate")
            or properties.get("fromdate")
        )
        try:
            timestamp = dtparse.parse(startdate).astimezone(UTC)
        except Exception:
            timestamp = now_utc()
        if timestamp < now_utc() - timedelta(hours=48):
            continue

        severity = severity_from_gdacs_color(alert)
        hazard_map = {
            "eq": "quake",
            "tc": "cyclone",
            "vo": "ash",
            "fl": "flood",
            "wf": "wildfire",
            "dr": "drought",
            "ls": "landslide",
            "st": "storm",
        }
        hazard_type = hazard_map.get(event_type_val, "other")
        title_base = f"{(alert or '').upper()} {event_type_val.upper() or 'EVENT'}"
        details = properties.get("description") or properties.get("text") or ""

        results.append(
            {
                "source": "gdacs",
                "id": event_id,
                "ts": iso(timestamp),
                "type": hazard_type,
                "severity": severity,
                "title": f"{title_base} — {name}" if name else title_base,
                "body": (details[:4000] if isinstance(details, str) else f"GDACS {event_type_val.upper()} alert"),
                "details": details,
                "lat": lat,
                "lon": lon,
                "links": [properties.get("link")] if properties.get("link") else [],
                "gdacs_color": alert,
                "location": properties.get("country") or properties.get("eventname"),
            }
        )
    return results


def fetch_media_quakes() -> List[dict]:
    """
    Pull quakes from the gaiaeyes-media repo's data/quakes_latest.json.
    Accept flexible schemas:
      - USGS-like: {"features":[{properties:{mag,time,title,place,code,id,url}, geometry:{coordinates:[lon,lat]}}]}
      - Flat list: [{"mag":..,"time" or "ts":..,"lat":..,"lon":..,"id":..,"title"/"place":..,"url":..}]
      - Wrapped list: {"items":[ ... as above ... ]}
    """
    data = None
    # ENV override: try explicit URL first if provided
    if MEDIA_QUAKES_URL:
        try:
            data = fetch_json_any([MEDIA_QUAKES_URL], timeout=15)
        except Exception:
            data = None
    # Try local file candidates
    if data is None:
        for p in MEDIA_QUAKES_CANDIDATE_PATHS:
            if p and os.path.isfile(p):
                data = load_json_file(p)
                if data:
                    break
    # Fallback to raw GitHub
    if data is None:
        try:
            data = fetch_json_any([MEDIA_QUAKES_RAW_URL], timeout=15)
        except Exception:
            data = None
    if not data:
        return []

    items: List[dict] = []
    now_cut = now_utc() - timedelta(hours=48)

    # Case 1: USGS-like features
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        for f in data["features"]:
            props = f.get("properties", {}) or {}
            geom = f.get("geometry", {}) or {}
            coords = geom.get("coordinates", [None, None])
            lon, lat = coords[0], coords[1]
            mag = props.get("mag")
            t = props.get("time")
            ts = None
            if isinstance(t, (int, float)):
                ts = datetime.fromtimestamp(float(t) / 1000.0, tz=UTC)
            elif isinstance(t, str):
                try:
                    ts = dtparse.parse(t).astimezone(UTC)
                except Exception:
                    ts = None
            if ts is None or ts < now_cut:
                continue
            src_id = str(props.get("code") or props.get("id") or f.get("id") or props.get("title") or f"{lat},{lon},{iso(ts)}")
            title = props.get("title") or props.get("place") or "Earthquake"
            url = props.get("url")
            sev = severity_quake_usgs(float(mag) if isinstance(mag, (int, float)) else 0.0)
            items.append({
                "source": "media",
                "id": src_id,
                "ts": iso(ts),
                "type": "quake",
                "severity": sev,
                "title": title,
                "body": props.get("place") or "",
                "mag": mag,
                "lat": lat,
                "lon": lon,
                "links": [url] if url else [],
            })
        print(f"[info] media quakes parsed: {len(items)}", file=sys.stderr)
        return items

    # Case 2: Wrapped list under "items" (generic)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        data_list = data["items"]
    # Case 3: Wrapped list under "events" (media schema)
    elif isinstance(data, dict) and isinstance(data.get("events"), list):
        data_list = data["events"]
    # Case 4: Already a list
    elif isinstance(data, list):
        data_list = data
    else:
        return []

    for q in data_list:
        if not isinstance(q, dict):
            continue
        mag = q.get("mag") or q.get("magnitude")
        # time can be ISO string, unix ms, or present under ts
        ts_val = q.get("time") or q.get("ts") or q.get("time_utc")
        ts = None
        if isinstance(ts_val, (int, float)):
            # heuristics: treat large values as ms
            ts = datetime.fromtimestamp(float(ts_val) / (1000.0 if float(ts_val) > 10_000_000_000 else 1.0), tz=UTC)
        elif isinstance(ts_val, str):
            try:
                ts = dtparse.parse(ts_val).astimezone(UTC)
            except Exception:
                ts = None
        if ts is None or ts < now_cut:
            continue
        lat = q.get("lat") or q.get("latitude")
        lon = q.get("lon") or q.get("longitude")
        src_id = str(q.get("id") or q.get("code") or q.get("usgs_id") or f"{lat},{lon},{iso(ts)}")
        title = q.get("title") or q.get("place") or "Earthquake"
        url = q.get("url")
        sev = severity_quake_usgs(float(mag) if isinstance(mag, (int, float)) else 0.0)
        items.append({
            "source": "media",
            "id": src_id,
            "ts": iso(ts),
            "type": "quake",
            "severity": sev,
            "title": title,
            "body": q.get("place") or "",
            "mag": mag,
            "lat": lat,
            "lon": lon,
            "links": [url] if url else [],
        })
    print(f"[info] media quakes parsed: {len(items)}", file=sys.stderr)
    return items


def fetch_vaac() -> List[dict]:
    return []


def maybe_same_quake(a: dict, b: dict) -> bool:
    if a.get("type") != "quake" or b.get("type") != "quake":
        return False
    try:
        time_a = dtparse.parse(a["ts"])
        time_b = dtparse.parse(b["ts"])
    except Exception:
        return False
    if abs((time_a - time_b).total_seconds()) > 10 * 60:
        return False
    if (
        a.get("lat") is None
        or b.get("lat") is None
        or a.get("lon") is None
        or b.get("lon") is None
    ):
        return False
    dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
    if dist > 50:
        return False
    mag_a = float(a.get("mag") or 0.0)
    mag_b = float(b.get("mag") or 0.0)
    return abs(mag_a - mag_b) <= 0.2


def dedupe(items: List[dict]) -> List[dict]:
    deduped: List[dict] = []
    for item in items:
        if any(maybe_same_quake(item, existing) for existing in deduped):
            continue
        deduped.append(item)
    return deduped


def compose_title(item: dict) -> str:
    item_type = item.get("type")
    severity = item.get("severity", "info")
    if item_type == "quake":
        magnitude = item.get("mag")
        if isinstance(magnitude, (int, float)):
            return f"⚠️ {severity.upper()} — M{magnitude:.1f} Earthquake — {item.get('title')}"
        return f"⚠️ {severity.upper()} — Earthquake — {item.get('title')}"
    if item_type == "cyclone":
        name = item.get("stormname") or ""
        return f"⚠️ {severity.upper()} — Cyclone {name}".strip()
    if item_type == "ash":
        return f"⚠️ {severity.upper()} — Volcanic Ash Advisory"
    return f"⚠️ {severity.upper()} — {item_type.capitalize() if item_type else 'Hazard'} — {item.get('title')}"


def compose_body(item: dict) -> str:
    lines = ["<p><em>Times are UTC. Links go to source pages/maps.</em></p>", "<ul>"]
    if item.get("type") == "quake":
        if item.get("mag") is not None:
            lines.append(f"<li><strong>Magnitude:</strong> M{item['mag']:.1f}</li>")
        if item.get("title"):
            lines.append(f"<li><strong>Summary:</strong> {item['title']}</li>")
    details = item.get("details")
    if details:
        lines.append(f"<li><strong>Details:</strong> {details}</li>")
    if item.get("lat") is not None and item.get("lon") is not None:
        lines.append(f"<li><strong>Location:</strong> {item['lat']:.2f}, {item['lon']:.2f}</li>")
    lines.append(f"<li><strong>Time:</strong> {item['ts']}</li>")
    if item.get("links"):
        links_html = " | ".join(
            f'<a href="{url}" target="_blank" rel="noopener">Source</a>' for url in item["links"]
        )
        lines.append(f"<li><strong>Links:</strong> {links_html}</li>")
    lines.append("</ul>")
    return "\n".join(lines)


def compose_digest(items: List[dict], window_hours: int) -> tuple[str, str, List[str]]:
    if not items:
        title = (
            f"🌍 Global Hazards Digest — {now_utc().strftime('%Y-%m-%d %H:%M UTC')}"
            " (No significant events)"
        )
        return title, "<p>No notable items in the last period.</p>", []
    now_time = now_utc()
    ampm = "AM" if now_time.hour < 12 else "PM"
    title = f"🌍 Global Hazards Digest — {now_time.strftime('%Y-%m-%d')} {ampm}"
    sections = {"quake": [], "cyclone": [], "ash": [], "other": []}
    for item in items:
        key = item.get("type") if item.get("type") in sections else "other"
        bullet = (
            f"<li><strong>{item.get('severity', 'info').upper()}</strong> — {item.get('title','(no title)')}"
            f" — {item['ts']}</li>"
        )
        sections[key].append(bullet)
    html_parts = ["<p><em>Times are UTC. Quick-look digest of the last 12 hours.</em></p>"]
    for key, label in [
        ("quake", "Earthquakes"),
        ("cyclone", "Cyclones/Severe"),
        ("ash", "Volcano/Ash"),
        ("other", "Other"),
    ]:
        if sections[key]:
            html_parts.append(f"<h3>{label}</h3><ul>")
            html_parts.extend(sections[key])
            html_parts.append("</ul>")
    tags = sorted({item.get("severity", "info") for item in items})
    return title, "\n".join(html_parts), tags


def slugify_instant(item: dict) -> str:
    timestamp = dtparse.parse(item["ts"])
    stamp = timestamp.strftime("%Y%m%d-%H%M")
    key = f"{item['type']}-{item['source']}-{item['id']}".lower().replace(" ", "-")
    return f"{stamp}-{key}"


def instant_categories(categories: Dict[str, int], item: dict) -> List[int]:
    base: List[int] = []
    t = item.get("type")
    if t == "quake":
        base.append(categories["Earthquake"])
    elif t == "cyclone":
        base.append(categories["Cyclone"])
    elif t == "ash":
        base.append(categories["Volcano/Ash"])
    elif t == "flood":
        base.append(categories["Flood"])
    elif t == "wildfire":
        base.append(categories["Wildfire"])
    elif t == "drought":
        base.append(categories["Drought"])
    elif t == "storm":
        base.append(categories["Storm"])
    elif t == "landslide":
        base.append(categories["Landslide"])
    return base


def instant_tags(wp: WPClient, item: dict) -> List[int]:
    tags: List[int] = [wp.ensure_tag(item.get("severity", "info"))]
    if item.get("type") == "quake" and item.get("mag") is not None:
        tags.append(wp.ensure_tag(f"M{item['mag']:.1f}"))
    if item.get("type") == "cyclone" and item.get("stormname"):
        tags.append(wp.ensure_tag(item["stormname"]))
    return tags


def run_once() -> None:
    db_init()
    wp: Optional[WPClient] = None
    categories: Dict[str, int] = {}
    skip_wp = os.environ.get("HAZARDS_SKIP_WP", "1").lower() in ("1", "true", "yes")
    if skip_wp:
        print("[info] HAZARDS_SKIP_WP enabled; skipping WP posts.", file=sys.stderr)
    else:
        try:
            wp = WPClient()
            categories = ensure_taxonomy(wp)
        except Exception as exc:  # pragma: no cover - network/auth handling
            print("[warn] WP taxonomy setup failed; skipping WP posts:", exc, file=sys.stderr)
            wp = None
            categories = {}

    items: List[dict] = []
    try:
        items.extend(fetch_usgs())
    except Exception as exc:  # pragma: no cover - network handling
        print("[warn] USGS fetch failed:", exc, file=sys.stderr)
    try:
        items.extend(fetch_gdacs())
    except Exception as exc:  # pragma: no cover - network handling
        print("[warn] GDACS fetch failed:", exc, file=sys.stderr)
    try:
        media_items = fetch_media_quakes()
        if media_items:
            print(f"[info] media quakes added: {len(media_items)}", file=sys.stderr)
            items.extend(media_items)
    except Exception as exc:  # pragma: no cover - best-effort local/remote media
        print("[warn] Media quakes fetch failed:", exc, file=sys.stderr)
    try:
        items.extend(fetch_vaac())
    except Exception as exc:  # pragma: no cover - network handling
        print("[warn] VAAC fetch failed:", exc, file=sys.stderr)

    if not items:
        print("[info] No items fetched (all upstream candidates returned no data or 4xx).")
        return

    items = dedupe(items)

    for item in items:
        src_id = item["id"]
        source = item["source"]
        compact = json.dumps(
            {key: item[key] for key in sorted(item.keys()) if key not in ("links",)},
            sort_keys=True,
        )
        content_hash = sha1(compact)
        _changed, _last_wp = cache_upsert_seen(source, src_id, content_hash)
        items_put(
            f"{source}:{src_id}",
            item,
            item["ts"],
            item["type"],
            item["severity"],
            item.get("lat"),
            item.get("lon"),
        )

        if wp and categories and item.get("severity") in ("red", "orange"):
            slug = slugify_instant(item)
            title = compose_title(item)
            body = compose_body(item)
            categories_list = instant_categories(categories, item)
            tags_list = instant_tags(wp, item)

            try:
                post = wp.upsert_post(
                    slug=slug,
                    title=title,
                    content=body,
                    categories=categories_list,
                    tags=tags_list,
                )
                cache_set_wp_id(source, src_id, int(post["id"]))
                print(f"[post] Instant upsert ok: {post['id']} {slug}")
            except Exception as exc:  # pragma: no cover - network handling
                print("[error] Instant post failed:", exc, file=sys.stderr)

    current_time = now_utc()
    window_hours = 12
    if wp and categories and current_time.hour in (0, 12) and current_time.minute <= 14:
        recent_items = items_window(hours=window_hours)
        title, html, tag_names = compose_digest(recent_items, window_hours)
        slug = (
            f"hazards-digest-{current_time.strftime('%Y%m%d')}"
            f"-{'am' if current_time.hour < 12 else 'pm'}"
        )
        tag_ids: List[int] = []
        for name in tag_names:
            try:
                tag_ids.append(wp.ensure_tag(name))
            except Exception:  # pragma: no cover - tag ensure best effort
                pass
        try:
            post = wp.upsert_post(
                slug=slug,
                title=title,
                content=html,
                categories=[categories["Hazards Digest"]],
                tags=tag_ids,
            )
            print(f"[post] Digest upsert ok: {post['id']} {slug}")
        except Exception as exc:  # pragma: no cover - network handling
            print("[error] Digest post failed:", exc, file=sys.stderr)

    items = items_window(hours=48)
    snapshot = {"generated_at": iso(now_utc()), "items": items}
    out_dir = os.path.join(SCRIPT_DIR, "out")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)

    rows = []
    for it in items:
        src = it.get("source")
        kind = it.get("kind") or it.get("type")
        title = it.get("title")
        if not title:
            continue
        loc = it.get("location") or it.get("region")
        sev = it.get("severity") or it.get("magnitude")

        # started_at / ended_at can be null for now unless you have clear timestamps
        h = f"{src}|{kind}|{title}|{it.get('id') or it.get('slug') or ''}"

        rows.append(
            {
                "source": src,
                "kind": kind,
                "title": title,
                "location": loc,
                "severity": sev,
                "details": it.get("details"),
                "payload": it,
                "hash": h,
            }
        )

    supabase_upsert("ext.global_hazards", rows, on_conflict="hash")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "run":
        run_once()
        return
    print("usage: hazards_bot.py run", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
