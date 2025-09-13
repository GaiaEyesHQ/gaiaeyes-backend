#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, html, datetime as dt
from pathlib import Path
from typing import List, Dict, Any
import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

# WP creds
WP_BASE_URL     = os.getenv("WP_BASE_URL","").rstrip("/")
WP_USERNAME     = os.getenv("WP_USERNAME","")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD","")
WP_STATUS       = (os.getenv("WP_STATUS","draft") or "draft").lower()
WP_CATEGORY_ID  = os.getenv("WP_CATEGORY_ID","").strip()
WP_TAG_IDS      = os.getenv("WP_TAG_IDS","").strip()

# Supabase
SUPABASE_REST_URL   = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY= os.getenv("SUPABASE_SERVICE_KEY","").strip()

session = requests.Session()
session.headers.update({
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Accept": "application/json"
})

def sb_recent_summaries(days=1, limit=8) -> List[Dict[str,Any]]:
    url = f"{SUPABASE_REST_URL}/research_articles"
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat() + "Z"
    # join-like via outputs: fetch articles, then get outputs per article
    r = session.get(url, params={
        "select":"id,source,title,url,published_at",
        "published_at": f"gte.{since}",
        "order":"published_at.desc",
        "limit": str(limit)
    }, timeout=20)
    r.raise_for_status()
    arts = r.json() or []
    # fetch outputs per article
    out_url = f"{SUPABASE_REST_URL}/article_outputs"
    for a in arts:
        rr = session.get(out_url, params={
            "select":"output_type,content",
            "article_id": f"eq.{a['id']}"
        }, timeout=20)
        rr.raise_for_status()
        a["outputs"] = rr.json() or []
    return arts

def wp_auth():
    if not (WP_BASE_URL and WP_USERNAME and WP_APP_PASSWORD):
        raise SystemExit("Missing WP_* envs")
    return (WP_USERNAME, WP_APP_PASSWORD)

def wp_create_post(title: str, html_content: str) -> dict:
    payload = {"title":title, "content":html_content, "status":WP_STATUS}
    if WP_CATEGORY_ID:
        try: payload["categories"] = [int(WP_CATEGORY_ID)]
        except: pass
    if WP_TAG_IDS:
        try:
            ids = [int(x.strip()) for x in WP_TAG_IDS.split(",") if x.strip().isdigit()]
            if ids: payload["tags"] = ids
        except: pass
    r = session.post(f"{WP_BASE_URL}/wp-json/wp/v2/posts", auth=wp_auth(), json=payload, timeout=40)
    r.raise_for_status()
    return r.json()

def roundup_html(items: List[Dict[str,Any]]) -> str:
    parts = [f"<p><em>Curated highlights from today’s sources.</em></p>"]
    for a in items:
        parts.append(f'<h3><a href="{html.escape(a["url"])}" target="_blank" rel="noopener">{html.escape(a["title"])}</a></h3>')
        shorts = [o["content"] for o in a["outputs"] if o["output_type"]=="summary_short"]
        longs  = [o["content"] for o in a["outputs"] if o["output_type"]=="summary_long"]
        if shorts:
            parts.append(f"<p>{html.escape(shorts[0])}</p>")
        if longs:
            # lightly format into paragraphs
            for para in longs[0].split("\n\n"):
                parts.append(f"<p>{html.escape(para.strip())}</p>")
        facts = [o["content"] for o in a["outputs"] if o["output_type"]=="fact"][:2]
        if facts:
            parts.append("<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>")
    return "\n".join(parts)

def main():
    items = sb_recent_summaries(days=1, limit=8)
    if not items:
        print("No recent research items.")
        return
    today = dt.datetime.utcnow().strftime("%b %d, %Y")
    title = f"Gaia Eyes Research Roundup — {today}"
    html = roundup_html(items)
    created = wp_create_post(title, html)
    print("WP research post created:", created.get("link"), "status:", created.get("status"))

if __name__=="__main__":
    main()
