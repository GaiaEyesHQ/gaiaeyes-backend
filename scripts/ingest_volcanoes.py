#!/usr/bin/env python3
"""
Ingest global volcano activity from the Smithsonian / USGS
Global Volcanism Program Weekly Volcanic Activity Report RSS feed
into ext.global_hazards.

Env:
  GVP_VOLCANO_RSS_URL  (optional) - override the default RSS feed URL
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

Usage:
  python scripts/ingest_volcanoes.py
"""

import os
import sys
import json
import datetime as dt
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Ensure the repo root (parent of this file) is on sys.path so we can import supabase_rest_client
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from supabase_rest_client import supabase_upsert


DEFAULT_GVP_RSS = "https://volcano.si.edu/news/WeeklyVolcanoRSS.xml"  # example; update to actual GVP RSS URL


def fetch_rss(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "GaiaEyes/volcano-ingest"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_gvp_rss(xml_bytes: bytes):
    """
    Parse the GVP Weekly Volcanic Activity RSS feed.

    Each <item> generally has:
      <title>Volcano Name (Country) | Date Range | Summary...</title>
      <link>...</link>
      <description>...</description>
      <pubDate>...</pubDate>
      ...possibly other elements...

    We'll do a light parse to extract:
      - title (string)
      - link (url)
      - description (summary)
      - pubDate (as started_at)
    """
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"[gvp] XML parse error: {e}", file=sys.stderr)
        return items

    # RSS structure: <rss><channel><item>...</item></channel></rss>
    channel = root.find("channel")
    if channel is None:
        return items

    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()

        # Basic pubDate parsing; RFC822 style usually
        started_at = None
        if pub:
            try:
                # Example: "Wed, 26 Nov 2025 23:00:00 +0000"
                started_dt = dt.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
                started_at = started_dt.astimezone(dt.timezone.utc).isoformat()
            except Exception:
                started_at = None

        # Rough location: often volcano name + country in title
        location = ""
        if "(" in title and ")" in title:
            # e.g. "Kirishimayama (Japan) | 23 July-29 July 2025 | ..."
            try:
                before, rest = title.split("(", 1)
                country_part, _ = rest.split(")", 1)
                location = country_part.strip()
            except ValueError:
                pass

        items.append(
            {
                "title": title,
                "url": link,
                "summary": desc,
                "location": location,
                "started_at": started_at,
            }
        )

    return items


def build_hazard_rows(volcano_items):
    """
    Map GVP volcano items into rows for ext.global_hazards.

    We'll set:
      source   = "smithsonian-gvp"
      kind     = "volcano"
      severity = "info" (for now; can be refined based on text)
      title    = item['title']
      location = item['location']
      payload  = full item
      hash     = stable hash key
    """
    rows = []
    for it in volcano_items:
        title = it.get("title") or ""
        if not title:
            continue
        source = "smithsonian-gvp"
        kind = "volcano"
        location = it.get("location") or ""
        started_at = it.get("started_at")
        # Very rough severity inference: look for "Orange", "Red", "Yellow" in text
        severity = "info"
        text_for_sev = (title + " " + (it.get("summary") or "")).lower()
        if " red " in text_for_sev or "red alert" in text_for_sev:
            severity = "red"
        elif " orange " in text_for_sev or "orange alert" in text_for_sev:
            severity = "orange"
        elif " yellow " in text_for_sev or "yellow alert" in text_for_sev:
            severity = "yellow"

        # Build a stable hash so upserts are idempotent
        h = f"{source}|{kind}|{title}|{location}"

        row = {
            "source": source,
            "kind": kind,
            "title": title,
            "location": location,
            "severity": severity,
            "started_at": started_at,
            "payload": it,
            "hash": h,
        }
        rows.append(row)
    return rows


def main():
    rss_url = os.getenv("GVP_VOLCANO_RSS_URL", DEFAULT_GVP_RSS)
    if not rss_url:
        print("[gvp] no RSS URL configured", file=sys.stderr)
        sys.exit(1)

    print(f"[gvp] fetching volcano feed: {rss_url}", flush=True)
    try:
        xml_bytes = fetch_rss(rss_url)
    except (HTTPError, URLError) as e:
        print(f"[gvp] error fetching RSS: {e}", file=sys.stderr)
        sys.exit(1)

    volcano_items = parse_gvp_rss(xml_bytes)
    print(f"[gvp] parsed {len(volcano_items)} volcano report items", flush=True)

    if not volcano_items:
        sys.exit(0)

    rows = build_hazard_rows(volcano_items)
    if not rows:
        print("[gvp] no rows built from volcano items", file=sys.stderr)
        sys.exit(0)

    print(f"[gvp] upserting {len(rows)} rows into ext.global_hazards", flush=True)
    supabase_upsert("ext.global_hazards", rows, on_conflict="hash")


if __name__ == "__main__":
    main()