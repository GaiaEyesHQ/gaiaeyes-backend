#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, json, time
from pathlib import Path
from typing import Dict, Any, List
import requests
from dotenv import load_dotenv

def _to_text(v, max_len: int | None = None) -> str:
    """Coerce arbitrary JSON values (str/list/dict/number) into a clean string.
    - dict: prefer 'text' then 'content', else JSON-dump
    - list: join items coerced to text with spaces
    - str: strip and clip
    """
    try:
        if isinstance(v, str):
            s = v
        elif isinstance(v, list):
            s = " ".join([_to_text(x) for x in v if x is not None])
        elif isinstance(v, dict):
            s = v.get("text") or v.get("content") or json.dumps(v, ensure_ascii=False)
        elif v is None:
            s = ""
        else:
            s = str(v)
        s = s.strip()
        if max_len and len(s) > max_len:
            s = s[: max_len - 1].rstrip() + "…"
        return s
    except Exception:
        return ""

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
    headers = dict(session.headers)
    headers["Prefer"] = "return=representation"
    r = session.post(url, json=rows, timeout=TIMEOUT, headers=headers)
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

def call_openai_chat(messages: List[Dict[str,str]], max_tokens=800, temperature=0.3) -> str:
    import openai
    openai.api_key = OPENAI_API_KEY
    resp = openai.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()

def call_openai_json(system: str, user: str, max_tokens=900, temperature=0.2) -> Dict[str, Any]:
    """Ask the model to return strict JSON; fall back to best-effort parse."""
    import json as _json
    sys_msg = {"role":"system","content":system}
    usr_msg = {"role":"user","content":user}
    txt = call_openai_chat([sys_msg, usr_msg], max_tokens=max_tokens, temperature=temperature)
    try:
        return _json.loads(txt)
    except Exception:
        # try to locate a JSON object in the text
        s = txt.find('{'); e = txt.rfind('}')
        if s != -1 and e != -1 and e > s:
            try:
                return _json.loads(txt[s:e+1])
            except Exception:
                pass
        raise

def craft_prompts_json(article: Dict[str,Any]) -> Dict[str,str]:
    title = article.get("title","(untitled)")
    url   = article.get("url","")
    raw   = (article.get("summary_raw") or "").strip()
    body  = (article.get("content_raw") or "").strip()

    system = (
        "You are an assistant for Gaia Eyes. Write concise, credible research outputs about space weather and electromagnetic phenomena. "
        "No speculation and no medical claims. Do NOT include advice, tips, or self‑care. "
        "If a source does not discuss human physiology, do not infer or mention mood/HRV/EEG/nervous system. "
        "Write in a plain scientific newsroom style. No markdown headings, no ###, no bullets, no emojis."
    )

    user = f"""
ARTICLE_TITLE: {title}
ARTICLE_URL: {url}
SUMMARY_RAW: {raw}
CONTENT_RAW: {body}

Produce STRICT JSON with keys:
- summary_short: string (<=600 chars). One sentence with the concrete update (numbers when present) + 3–5 research hashtags inline. No advice. No emojis.
- summary_long: string (2–4 short paragraphs, plain text). Cover only what the article reports: instruments, models, metrics, timings. Do not use markdown headings or bullets. Only discuss human physiology if the article itself discusses it explicitly; otherwise omit.
- facts: array of 1–3 short strings (40–140 chars), each a single objective statement suitable for an overlay; no hashtags/emojis/advice.
- credibility: "high"|"medium"|"low" based on the source and specificity.
- topics: array subset of ["space_weather","geomagnetic","schumann","hrv","eeg","emf","ionosphere","magnetosphere","sleep","nervous_system"].

Rules:
- Pull concrete data points (Kp, Bz, solar wind speed, forecast windows) only if present. Do NOT fabricate.
- No markdown syntax (no ###, **, *, -). Plain sentences only.
- If the article is off‑mission, set credibility="low" and topics=[].
Return ONLY the JSON object.
"""
    return {"system": system, "user": user}

def main():
    arts = sb_select_new(limit=12)
    if not arts:
        print("No new research articles.")
        return

    outs=[]
    processed=[]
    for a in arts:
        # Build JSON prompt and call model
        p = craft_prompts_json(a)
        try:
            j = call_openai_json(p["system"], p["user"], max_tokens=1000, temperature=0.2)
        except Exception as e:
            # Fallback: try legacy 3-call mode using summary_raw only
            print("[AI] JSON parse error; falling back:", e)
            legacy = {
                "short": f"{a.get('title','')} — {a.get('summary_raw','')[:420]}",
                "long": a.get('summary_raw','')[:1200],
                "facts": []
            }
            j = {
                "summary_short": legacy["short"][:600],
                "summary_long": legacy["long"],
                "facts": legacy["facts"],
                "credibility": "medium",
                "topics": []
            }

        # prepare outputs
        article_id = a["id"]
        short = _to_text(j.get("summary_short"), max_len=600)
        long  = _to_text(j.get("summary_long"))
        facts_raw = j.get("facts") or []
        facts = []
        for f in facts_raw:
            t = _to_text(f)
            if 8 <= len(t) <= 140:
                facts.append(t)

        outs.append({"article_id": article_id, "output_type":"summary_short", "content": short[:600], "model": MODEL})
        outs.append({"article_id": article_id, "output_type":"summary_long",  "content": long,        "model": MODEL})
        for fact in facts:
            outs.append({"article_id": article_id, "output_type":"fact", "content": fact, "model": MODEL})

        processed.append(article_id)

    sb_insert_outputs(outs)
    sb_mark_processed(processed)
    print("Done summarizing.")

if __name__=="__main__":
    main()
