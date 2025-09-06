import os, json, math
from typing import Any, Dict, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI

# Model can be overridden via env
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

class LLMFailure(Exception):
    pass

def _clip(s: str, max_len: int) -> str:
    if not isinstance(s, str):
        return s
    s = s.strip()
    return s if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"

def _dedupe_hashtags(h: str) -> str:
    if not isinstance(h, str):
        return h
    seen = set()
    out = []
    for tok in h.replace(",", " ").split():
        if not tok.startswith("#"):
            continue
        t = tok.strip()
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(t)
    # keep 6–10 max
    if len(out) < 6:
        return " ".join(out)
    return " ".join(out[:10])

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def generate_daily_earthscope(
    metrics_json: Dict[str, Any],
    donki_events: List[Dict[str, Any]],
    trending: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Returns dict with keys:
      - title (str)
      - caption (str)
      - body_markdown (str)
      - hashtags (str)
      - sources_json (dict: {datasets:[], references:[]})
    """

    # Canonical sources (shown at bottom of post)
    default_sources = {
        "datasets": ["marts.space_weather_daily", "ext.donki_event"],
        "references": [
            "https://www.solarham.com/",
            "https://www.spaceweather.com/",
            "https://www.nasa.gov/",
            "https://www.heartmath.org/gci/gcms/live-data/"
        ]
    }

    # Tight system guidance to ensure quality and avoid one-word/placeholder output
    system = (
        "You are Gaia Eyes’ Daily Earthscope writer. "
        "Write credible, readable, human-sounding daily forecasts that blend space-weather with wellness. "
        "Never invent numbers or events. If a numeric field is missing, omit it (do not write placeholders). "
        "Use a friendly, grounded tone; never fear-monger; avoid jargon. "
        "Round any long numeric values to 1 decimal (e.g., Kp 2.7, Bz -5.1 nT, wind 430.4 km/s). "
        "Avoid generic filler like 'latest update from this source' — always summarize concrete info from the provided items."
    )

    # Richer prompt with explicit structural and quality constraints
    prompt = {
        "task": "Render a Gaia Eyes 'Daily Earthscope' post with sections and linked trending articles.",
        "format": "Return strict JSON with keys: title, caption, body_markdown, hashtags, sources_json.",
        "brand": {"name": "Gaia Eyes"},
        "voice": "calm, clear, credible, lightly poetic, never alarmist",
        "audience": "general public",
        "length_hints": {
            "caption_min_chars": 220,
            "caption_max_chars": 600,
            "hashtags_min": 6,
            "hashtags_max": 10
        },
        "sections_required": [
            "Trending Space Weather Highlights (linked bullets with 1–2 sentence summaries)",
            "How This May Affect You (Mood, Energy, Heart, Nervous System)",
            "Self-Care Playbook (3–6 concise bullets, actionable)",
            "Sources (the four canonical sites below)"
        ],
        "data": {
            # metrics_json contains numbers from marts.space_weather_daily; use them inline (rounded).
            "metrics_json": metrics_json,
            # donki_events: include up to 3 notable items (type/class/time) in Trending if present.
            "donki_events": donki_events,
            # trending: list of {title,url,summary}; include 2–3 as markdown links with 1–2 sentence summaries.
            "trending": trending
        },
        "output_rules": [
            # Title
            "Title must be informative and human, e.g., 'Daily Earthscope — Calm Field & Clear Focus' or 'Daily Earthscope — Storm Watch & Coherent Breath'.",
            # Caption
            "Caption must be 220–600 characters, human, not generic; include a clear hook, a takeaway, and a gentle CTA.",
            "Caption must include 6–10 distinct hashtags (mix niche + broader).",
            # Body
            "Body must be valid Markdown with H2 headings (##).",
            "In 'Trending' use markdown bullets with [Title](url) followed by a 1–2 sentence summary. No placeholders.",
            "Include inline metrics when available: Kp (kp_max), Bz (bz_min) with 'nT', solar wind (sw_speed_avg) with 'km/s'. Round to 1 decimal.",
            "If DONKI events exist, include up to 3 notable items with type and class (e.g., M1.2) as part of Trending.",
            "In 'How This May Affect You', write 1–2 short bullets per domain (Mood, Energy, Heart, Nervous System). Avoid one-word replies.",
            "In 'Self-Care Playbook', include 3–6 concise, practical tips tied to today's conditions.",
            # Sources JSON
            "Return sources_json that includes the canonical references below. You may add any used article URLs under a 'trending' array."
        ],
        "sources_json": default_sources
    }

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.2,  # tighter for consistency
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(prompt)}
        ],
    )

    try:
        obj = json.loads(resp.choices[0].message.content)
    except Exception as e:
        raise LLMFailure(f"Failed to parse JSON response: {e}")

    # Basic validation
    for k in ["title", "caption", "body_markdown", "hashtags"]:
        if k not in obj or not isinstance(obj[k], str) or not obj[k].strip():
            raise LLMFailure(f"Missing/invalid field: {k}")

    # Post-process: clip caption length to max, dedupe hashtags, clip hashtags string if absurdly long
    cap_max = int(prompt["length_hints"]["caption_max_chars"])
    obj["caption"] = _clip(obj["caption"], cap_max)

    obj["hashtags"] = _dedupe_hashtags(obj["hashtags"])

    # Ensure sources_json exists and optionally add trending links we passed in
    sj = obj.get("sources_json") or {}
    if "datasets" not in sj or "references" not in sj:
        sj = default_sources
    # If caller provided trending items, surface them under sources_json.trending for easy querying
    if isinstance(trending, list) and trending:
        # Keep only title/url/summary fields; drop empties
        clean_trending = []
        for t in trending:
            title = (t.get("title") or "").strip()
            url = (t.get("url") or "").strip()
            summary = (t.get("summary") or "").strip()
            if url:
                clean_trending.append({"title": title or url, "url": url, "summary": summary})
        if clean_trending:
            sj = {**sj, "trending": clean_trending}

    obj["sources_json"] = sj
    return obj
