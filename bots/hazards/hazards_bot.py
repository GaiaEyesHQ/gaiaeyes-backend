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

import requests
from dateutil import parser as dtparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.append(SCRIPT_DIR)

from wp_client import WPClient  # noqa: E402

UTC = timezone.utc

DB_PATH = os.path.join(SCRIPT_DIR, "hazards.sqlite")

USGS_URLS = {
    "M5_week": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/5.0_week.geojson",
}
GDACS_EVENTLIST = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/JSON"


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


def setup_wp() -> WPClient:
    base = os.environ.get("WP_BASE_URL", "").strip()
    user = os.environ.get("WP_USERNAME", "").strip()
    app = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and app):
        raise RuntimeError("Missing WP_BASE_URL / WP_USERNAME / WP_APP_PASSWORD")
    return WPClient(base, user, app)


def ensure_taxonomy(wp: WPClient) -> Dict[str, int]:
    return {
        "Hazards Digest": wp.ensure_category("Hazards Digest", "hazards-digest"),
        "Earthquake": wp.ensure_category("Earthquake"),
        "Cyclone": wp.ensure_category("Cyclone"),
        "Volcano/Ash": wp.ensure_category("Volcano/Ash", "volcano-ash"),
    }


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


def fetch_usgs() -> List[dict]:
    response = requests.get(USGS_URLS["M5_week"], timeout=15)
    response.raise_for_status()
    geojson = response.json()
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
    response = requests.get(GDACS_EVENTLIST, timeout=20)
    response.raise_for_status()
    data = response.json()
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
        event_type = (properties.get("eventtype") or "").lower()
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
        hazard_type = {
            "eq": "quake",
            "tc": "cyclone",
            "vo": "ash",
        }.get(event_type, "other")
        title_base = f"{(alert or '').upper()} {event_type.upper()}"
        payload = {
            "source": "gdacs",
            "id": event_id,
            "ts": iso(timestamp),
            "type": hazard_type,
            "severity": severity,
            "title": f"{title_base} — {name}" if name else title_base,
            "body": f"GDACS {event_type.upper()} alert: {name or 'Unnamed'}",
            "lat": lat,
            "lon": lon,
            "links": [properties.get("link")] if properties.get("link") else [],
            "gdacs_color": alert,
        }
        if event_type == "eq":
            payload["mag"] = properties.get("magnitude")
        if event_type == "tc":
            payload["stormname"] = name
        results.append(payload)
    return results


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
    return f"⚠️ {severity.upper()} — Hazard Update"


def compose_body(item: dict) -> str:
    lines = ["<p><em>Times are UTC. Links go to source pages/maps.</em></p>", "<ul>"]
    if item.get("type") == "quake":
        if item.get("mag") is not None:
            lines.append(f"<li><strong>Magnitude:</strong> M{item['mag']:.1f}</li>")
        if item.get("title"):
            lines.append(f"<li><strong>Summary:</strong> {item['title']}</li>")
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
    if item.get("type") == "quake":
        base.append(categories["Earthquake"])
    elif item.get("type") == "cyclone":
        base.append(categories["Cyclone"])
    elif item.get("type") == "ash":
        base.append(categories["Volcano/Ash"])
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
    wp = setup_wp()
    categories = ensure_taxonomy(wp)

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
        items.extend(fetch_vaac())
    except Exception as exc:  # pragma: no cover - network handling
        print("[warn] VAAC fetch failed:", exc, file=sys.stderr)

    if not items:
        print("[info] No items fetched.")
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

        if item.get("severity") in ("red", "orange"):
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
    if current_time.hour in (0, 12) and current_time.minute <= 14:
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

    snapshot = {"generated_at": iso(now_utc()), "items": items_window(hours=48)}
    out_dir = os.path.join(SCRIPT_DIR, "out")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2)


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "run":
        run_once()
        return
    print("usage: hazards_bot.py run", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
