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

session = requests.Session()
session.headers.update({
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Accept": "application/json"
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
            if ent.get("parser") == "usgs_quake":
                to_upsert += parse_usgs_quake(ent["url"], ent["id"], ent.get("tags",[]))
            else:
                # generic: store URL + title if present
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
