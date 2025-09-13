#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, hashlib, datetime as dt
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import feedparser
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

SUPABASE_REST_URL   = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY= os.getenv("SUPABASE_SERVICE_KEY","").strip()
GAIA_TIMEZONE       = os.getenv("GAIA_TIMEZONE","America/Chicago")

# after existing imports / dotenv loads
HTTP_USER_AGENT = os.getenv(
    "HTTP_USER_AGENT",
    "GaiaEyesBot/1.0 (+https://gaiaeyes.com; gaiaeyes7.83@gmail.com)"
)

session = requests.Session()
session.headers.update({
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "User-Agent": HTTP_USER_AGENT,
    "Accept": "application/json, application/xml;q=0.9, */*;q=0.8"
})
TIMEOUT=20

def sb_upsert_articles(rows: List[Dict[str,Any]]):
    if not rows:
        return
    url = f"{SUPABASE_REST_URL}/research_articles"
    # upsert on url_hash
    for r in rows:
        r["url_hash"] = r.get("url_hash") or sha256(r["url"])
    resp = session.post(url, json=rows, timeout=TIMEOUT, params={"on_conflict":"url_hash"})
    if resp.status_code not in (200,201,204):
        print("[SB] upsert articles failed:", resp.status_code, resp.text[:200])
    else:
        print(f"[SB] upserted {len(rows)} article(s)")

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def parse_rss(feed_url: str, source_id: str, tags: List[str]) -> List[Dict[str,Any]]:
    d = feedparser.parse(feed_url)
    out=[]
    for e in d.entries:
        title = e.get("title","").strip()
        link  = e.get("link","").strip()
        if not (title and link): continue
        pub = None
        if e.get("published_parsed"):
            pub = dt.datetime(*e.published_parsed[:6], tzinfo=dt.timezone.utc).isoformat()
        summary = (e.get("summary") or e.get("description") or "").strip()
        out.append({
            "source": source_id, "source_type":"rss",
            "title": title, "url": link,
            "published_at": pub,
            "summary_raw": summary,
            "tags": tags
        })
    return out

def parse_usgs_quake(url: str, source_id: str, tags: List[str]) -> List[Dict[str,Any]]:
    r = session.get(url, timeout=TIMEOUT); r.raise_for_status()
    j = r.json()
    out=[]
    for feat in j.get("features", []):
        props = feat.get("properties", {})
        title = props.get("title","").strip() or "USGS Event"
        link  = props.get("url","").strip() or props.get("detail","").strip()
        tms   = props.get("time")
        pub   = dt.datetime.utcfromtimestamp(tms/1000).replace(tzinfo=dt.timezone.utc).isoformat() if tms else None
        out.append({
            "source": source_id, "source_type":"api",
            "title": title, "url": link,
            "published_at": pub,
            "summary_raw": f"Magnitude {props.get('mag')} at {props.get('place')}",
            "tags": tags
        })
    return out

def parse_swpc_alerts(url: str, source_id: str, tags: list) -> list:
    r = session.get(url, timeout=TIMEOUT); r.raise_for_status()
    data = r.json()  # list of lists or list of dicts depending on endpoint
    out = []
    # alerts.json (list of dicts with keys like issue_datetime, alert_type, message)
    # If endpoint returns a list of lists (table form), adjust accordingly.
    if isinstance(data, list) and data and isinstance(data[0], dict):
        for row in data:
            title = row.get("alert_type") or row.get("message") or "SWPC Alert"
            link  = row.get("link") or "https://www.swpc.noaa.gov/"
            pub   = row.get("issue_datetime") or row.get("time_issued") or None
            out.append({
                "source": source_id, "source_type": "api",
                "title": title.strip()[:240], "url": link,
                "published_at": pub,
                "summary_raw": (row.get("message") or "").strip(),
                "tags": tags
            })
    else:
        # be resilient if table-like
        for row in data[1:]:
            title = f"SWPC Alert: {row[2]}" if len(row) > 2 else "SWPC Alert"
            pub   = row[0] if len(row) > 0 else None
            link  = "https://www.swpc.noaa.gov/"
            out.append({
                "source": source_id, "source_type":"api",
                "title": title.strip()[:240],
                "url": link, "published_at": pub,
                "summary_raw": " ".join(map(str, row))[:500],
                "tags": tags
            })
    return out

def parse_swpc_kp(url: str, source_id: str, tags: list) -> list:
    r = session.get(url, timeout=TIMEOUT); r.raise_for_status()
    data = r.json()  # [header, row, row...]
    out = []
    if isinstance(data, list) and len(data) > 1 and isinstance(data[0], list):
        hdr = [h.lower() for h in data[0]]
        # try to find kp column
        kp_idx = None
        for i, h in enumerate(hdr):
            if "kp" in h:
                kp_idx = i; break
        # pick last row
        last = data[-1]
        kp_val = last[kp_idx] if kp_idx is not None and len(last) > kp_idx else None
        timestamp = last[0] if last else None
        title = f"Kp update: {kp_val}"
        out.append({
            "source": source_id, "source_type":"api",
            "title": title, "url": url,
            "published_at": timestamp,
            "summary_raw": f"Latest NOAA Planetary K index: {kp_val}",
            "tags": tags
        })
    return out

def parse_nws_alerts(url: str, source_id: str, tags: list) -> list:
    # api.weather.gov requires a UA (already set). Parse active alerts.
    r = session.get(url, timeout=TIMEOUT); r.raise_for_status()
    j = r.json()
    out = []
    for feat in (j.get("features") or []):
        props = feat.get("properties", {})
        headline = props.get("headline") or props.get("event") or "NWS Alert"
        link = props.get("url") or props.get("alert_link") or "https://api.weather.gov/alerts"
        pub  = props.get("sent") or props.get("onset") or props.get("effective")
        desc = props.get("description") or ""
        out.append({
            "source": source_id, "source_type":"api",
            "title": headline.strip()[:240],
            "url": link, "published_at": pub,
            "summary_raw": desc.strip()[:1000],
            "tags": tags
        })
    return out

def load_sources() -> Dict[str,Any]:
    import yaml
    with open(HERE / "sources.yaml","r",encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main():
    src=load_sources()
    to_upsert=[]
    for ent in src.get("rss", []):
        print("[RSS]", ent["id"], ent["url"])
        try:
            to_upsert += parse_rss(ent["url"], ent["id"], ent.get("tags",[]))
        except Exception as e:
            print("[ERR rss]", ent["id"], e)

    for ent in src.get("api", []):
        print("[API]", ent["id"], ent["url"])
        try:
            parser = ent.get("parser")
            if parser == "usgs_quake":
                to_upsert += parse_usgs_quake(ent["url"], ent["id"], ent.get("tags",[]))
            elif parser == "swpc_alerts":
                to_upsert += parse_swpc_alerts(ent["url"], ent["id"], ent.get("tags",[]))
            elif parser == "swpc_kp":
                to_upsert += parse_swpc_kp(ent["url"], ent["id"], ent.get("tags",[]))
            elif parser == "nws_alerts":
                to_upsert += parse_nws_alerts(ent["url"], ent["id"], ent.get("tags",[]))
            else:
            # Generic catch-all
                r = session.get(ent["url"], timeout=TIMEOUT); r.raise_for_status()
                j = r.json()
                title = j.get("title") or ent["id"]
                to_upsert += [{
                    "source": ent["id"], "source_type":"api",
                    "title": f"{title}",
                    "url": ent["url"], "tags": ent.get("tags",[])
                }]
        except Exception as e:
            print("[ERR api]", ent["id"], e)

    # stamp url_hash and upsert
    for r in to_upsert:
        r["url_hash"] = sha256(r["url"] + r["title"])
    sb_upsert_articles(to_upsert)

if __name__=="__main__":
    main()
