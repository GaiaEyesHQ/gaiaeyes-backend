import os, json
from typing import Any, Dict, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

class LLMFailure(Exception):
    pass

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
    system = (
        "You are Gaia Eyes’ Daily Earthscope writer. "
        "Write concise, credible, human-sounding daily forecasts based on provided data. "
        "Never invent numbers. If a number is null, omit it or say 'data pending'. "
        "Friendly, grounded tone; never fear-monger."
    )

    default_sources = {
        "datasets": ["marts.space_weather_daily", "ext.donki_event"],
        "references": [
            "https://www.solarham.com/",
            "https://www.spaceweather.com/",
            "https://www.nasa.gov/",
            "https://www.heartmath.org/gci/gcms/live-data/"
        ]
    }

    prompt = {
        "task": "Render a Gaia Eyes 'Daily Earthscope' post with sections.",
        "format": "Return strict JSON with keys: title, caption, body_markdown, hashtags, sources_json.",
        "brand": {"name": "Gaia Eyes", "palette": "aurora blues/greens"},
        "voice": "calm, clear, credible, lightly poetic, never alarmist",
        "audience": "general public",
        "length_hints": {"caption_max_chars": 600},
        "sections_required": [
            "Trending Space Weather Highlights",
            "How This May Affect You (Mood, Energy, Heart, Nervous System)",
            "Self-Care Playbook (3–6 short bullets)",
            "Sources (SolarHam, SpaceWeather, NASA, HeartMath)"
        ],
        "data": {
            "metrics_json": metrics_json,
            "donki_events": donki_events,
            "trending": trending
        },
        "output_rules": [
            "Use the provided numbers and trending items; do not fabricate.",
            "If a number is null/missing, omit or say 'data pending'.",
            "Body must be valid Markdown with clear H2 headings.",
            "Include the trending items as bullets with Markdown links and 1–2 sentence summaries.",
            "Caption must include 4–10 viral-friendly hashtags.",
            "Keep a human feel; short, readable sentences; no jargon."
        ],
        "sources_json": default_sources
    }

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.3,
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

    for k in ["title", "caption", "body_markdown", "hashtags"]:
        if k not in obj or not isinstance(obj[k], str) or not obj[k].strip():
            raise LLMFailure(f"Missing/invalid field: {k}")

    sj = obj.get("sources_json") or {}
    if "datasets" not in sj or "references" not in sj:
        sj = default_sources
    obj["sources_json"] = sj

    return obj