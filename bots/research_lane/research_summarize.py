#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, time
from pathlib import Path
from typing import Dict, Any, List
import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")

SUPABASE_REST_URL    = os.getenv("SUPABASE_REST_URL","").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY","").strip()
OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY","").strip()
MODEL                = os.getenv("GAIA_OPENAI_MODEL","gpt-4o-mini")

session = requests.Session()
session.headers.update({
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Accept": "application/json"
})
TIMEOUT=25

def sb_select_new(limit=10) -> List[Dict[str,Any]]:
    url = f"{SUPABASE_REST_URL}/research_articles"
    params = {
        "select":"id,source,title,url,summary_raw,content_raw,published_at,tags",
        "status":"eq.new",
        "order":"published_at.desc",
        "limit": str(limit)
    }
    r = session.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json() or []

def sb_insert_outputs(rows: List[Dict[str,Any]]):
    if not rows: return
    url = f"{SUPABASE_REST_URL}/article_outputs"
    r = session.post(url, json=rows, timeout=TIMEOUT)
    if r.status_code not in (200,201,204):
        print("[SB] insert outputs failed:", r.status_code, r.text[:200])
    else:
        print(f"[SB] inserted {len(rows)} outputs")

def sb_mark_processed(ids: List[str]):
    for i in ids:
        url = f"{SUPABASE_REST_URL}/research_articles"
        r = session.patch(url, json={"status":"processed"}, params={"id":f"eq.{i}"}, timeout=TIMEOUT)
        if r.status_code not in (200,204):
            print("[SB] mark processed failed:", i, r.status_code, r.text[:120])

def call_openai(prompt: str, max_tokens=500, temperature=0.6) -> str:
    import openai
    openai.api_key = OPENAI_API_KEY
    resp = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role":"user","content":prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()

def craft_prompts(article: Dict[str,Any]) -> Dict[str,str]:
    title = article["title"]
    url   = article["url"]
    raw   = article.get("summary_raw") or ""
    body  = article.get("content_raw") or ""

    base = f"""
Title: {title}
URL: {url}

Context (may be brief): {raw}

Write in clear, accessible language for the Gaia Eyes audience (space weather, Schumann, HRV/EEG/nervous system).
"""

    short_p = base + """
Task: Write a short social caption (<= 600 chars). Start with a hook. Mention the key event briefly and note a possible human impact (mood/energy/heart/nervous system). Include 3–5 relevant hashtags at the end.
"""

    long_p = base + """
Task: Write a concise blog-ready summary with 3 sections and short bullets:
1) What Happened
2) Why It Matters (links to mood/energy/heart/nervous system; be measured; no medical claims)
3) What To Watch (1–3 practical notes or how to follow updates)

Keep it ~150–250 words total.
"""

    fact_p = base + """
Task: Extract 1–2 short 'Did you know?' style facts (max 140 chars each) that can be used as image overlays. Return each fact on a new line with no numbering.
"""

    return {"short": short_p, "long": long_p, "fact": fact_p}

def main():
    arts = sb_select_new(limit=12)
    if not arts:
        print("No new research articles.")
        return

    outs=[]
    processed=[]
    for a in arts:
        prompts = craft_prompts(a)
        try:
            short = call_openai(prompts["short"], max_tokens=350)
            long  = call_openai(prompts["long"],  max_tokens=500)
            facts = call_openai(prompts["fact"],  max_tokens=120)
        except Exception as e:
            print("[AI] error:", e)
            continue

        # prepare outputs
        article_id = a["id"]
        outs.append({"article_id": article_id, "output_type":"summary_short", "content": short, "model": MODEL})
        outs.append({"article_id": article_id, "output_type":"summary_long",  "content": long,  "model": MODEL})
        for line in (facts or "").splitlines():
            fact = line.strip(" -•\t")
            if 8 <= len(fact) <= 140:
                outs.append({"article_id": article_id, "output_type":"fact", "content": fact, "model": MODEL})

        processed.append(article_id)

    sb_insert_outputs(outs)
    sb_mark_processed(processed)
    print("Done summarizing.")

if __name__=="__main__":
    main()
