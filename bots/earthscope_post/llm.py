import os, json
from typing import Any, Dict, List, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

class LLMFailure(Exception):
    pass

# ---------------- helpers ----------------

def _round1(x: Optional[float]) -> Optional[float]:
    try:
        if x is None:
            return None
        return round(float(x), 1)
    except Exception:
        return None

def _clip(s: str, max_len: int) -> str:
    if not isinstance(s, str):
        return s
    s = s.strip()
    return s if len(s) <= max_len else s[: max_len - 1].rstrip() + "…"

def _dedupe_hashtags(h: str, min_ct=6, max_ct=10) -> str:
    if not isinstance(h, str):
        return h
    seen = set()
    out = []
    for tok in h.replace(",", " ").split():
        if not tok.startswith("#"):
            continue
        t = tok.strip()
        tl = t.lower()
        if tl not in seen and len(t) > 1:
            seen.add(tl)
            out.append(t)
    if len(out) < min_ct:
        pads = ["#GaiaEyes", "#DailyEarthscope", "#SpaceWeather", "#KpIndex", "#HeartCoherence", "#Grounding"]
        for p in pads:
            if p.lower() not in seen:
                out.append(p)
                seen.add(p.lower())
                if len(out) >= min_ct:
                    break
    return " ".join(out[:max_ct])

def _metrics_from_payload(metrics_json: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    sw = (metrics_json or {}).get("space_weather") or {}
    kp = _round1(sw.get("kp_max"))
    bz = _round1(sw.get("bz_min"))
    wind = _round1(sw.get("sw_speed_avg"))
    day_iso = (metrics_json or {}).get("day") or ""
    return kp, bz, wind, day_iso

def _deterministic_markdown(day_iso: str,
                            kp: Optional[float],
                            bz: Optional[float],
                            wind: Optional[float]) -> Tuple[str, str, str, str, Dict[str, Any]]:
    # Headline & caption
    if kp is not None and kp >= 5:
        headline = "Storm Energy with Pockets of Clarity"
    elif kp is not None and kp >= 3:
        headline = "Elevated Field • Steady Focus"
    else:
        headline = "Calm Field • Clear Focus"
    title = f"Daily Earthscope — {headline} ({day_iso})"

    parts = []
    if kp is not None:   parts.append(f"Kp {kp:.1f}")
    if bz is not None:   parts.append(f"Bz {bz:.1f} nT")
    if wind is not None: parts.append(f"solar wind {wind:.1f} km/s")
    metrics_line = ", ".join(parts) if parts else "quiet field"

    caption = (
        f"Earthscope — {metrics_line}. "
        "Tune into steady breath and simple grounding to align with today’s rhythm. "
        "Hydrate, move gently, and keep screens softer tonight."
    )
    caption = _clip(caption, 600)

    # Effects
    mood = "Calmer baseline with occasional ripples." if (kp is None or kp < 4) else "Heightened sensitivity; balance stimulation with recovery."
    energy = "Smooth focus window; good for structured tasks." if (kp is None or kp < 4) else "Surges and dips; plan buffers and short breaks."
    heart = "Favorable for HRV coherence; use slow, even breathing." if (kp is None or kp < 4) else "HRV may fluctuate; double down on heart-focused breath."
    neuro = "Nervous system steady—pair with nature contact." if (kp is None or kp < 4) else "Extra grounding helps counter restlessness."

    tips = [
        "4–6 breathing (inhale 4s, exhale 6s) for 5–10 minutes.",
        "Ground outdoors briefly (barefoot if safe) to settle your system.",
        "Hydrate with intention; add minerals if needed.",
        "Ease evening screens; favor soft, warm light for sleep.",
    ]

    body_md = f"""# Daily Earthscope • {day_iso}

## How This May Affect You
- **Mood:** {mood}
- **Energy:** {energy}
- **Heart:** {heart}
- **Nervous System:** {neuro}

## Self-Care Playbook
- {tips[0]}
- {tips[1]}
- {tips[2]}
- {tips[3]}
"""

    hashtags = _dedupe_hashtags("#GaiaEyes #DailyEarthscope #SpaceWeather #AuroraWatch #KpIndex #HeartCoherence #Grounding #Breathwork #Wellness")
    # Keep an empty sources_json so DB insert stays simple; content won’t show a Sources section.
    sources_json: Dict[str, Any] = {}
    return title, caption, body_md, hashtags, sources_json

# ---------------- main LLM path ----------------

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def _call_llm(prompt: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Gaia Eyes’ Daily Earthscope writer. "
                    "Write credible, readable, human-sounding daily forecasts that blend space weather with wellness. "
                    "Never invent numbers or events. If a numeric field is missing, omit it. "
                    "Round numbers to 1 decimal. Avoid placeholders."
                ),
            },
            {"role": "user", "content": json.dumps(prompt)},
        ],
    )
    return json.loads(resp.choices[0].message.content)

def generate_daily_earthscope(
    metrics_json: Dict[str, Any],
    donki_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # Round metrics before sending to the model
    kp, bz, wind, day_iso = _metrics_from_payload(metrics_json)
    if "space_weather" in (metrics_json or {}):
        if kp is not None:   metrics_json["space_weather"]["kp_max"] = kp
        if bz is not None:   metrics_json["space_weather"]["bz_min"] = bz
        if wind is not None: metrics_json["space_weather"]["sw_speed_avg"] = wind

    # LLM prompt without Trending/Sources
    prompt = {
        "task": "Render a Gaia Eyes 'Daily Earthscope' post with effects and self-care only.",
        "format": "Return strict JSON with keys: title, caption, body_markdown, hashtags.",
        "voice": "calm, clear, credible, lightly poetic and humorous, never alarmist",
        "length_hints": {"caption_min_chars": 220, "caption_max_chars": 600, "hashtags_min": 6, "hashtags_max": 10},
        "sections_required": [
            "How This May Affect You (Mood, Energy, Heart, Nervous System)",
            "Self-Care Playbook (3–6 concise bullets, actionable)"
        ],
        "data": {
            "metrics_json": metrics_json
        },
        "output_rules": [
            "Title must be informative and human.",
            "Caption must be 220–600 characters with 6–10 distinct hashtags.",
            "Body must be Markdown with H2 headings.",
            "Include inline metrics when available: Kp (kp_max), Bz (bz_min) nT, solar wind (sw_speed_avg) km/s; 1 decimal.",
            "Tie Self-Care tips to today's conditions."
        ],
    }

    try:
        obj = _call_llm(prompt)
        for k in ["title", "caption", "body_markdown", "hashtags"]:
            if k not in obj or not isinstance(obj[k], str) or not obj[k].strip():
                raise LLMFailure(f"Missing/invalid field: {k}")

        obj["caption"]  = _clip(obj["caption"], 600)
        obj["hashtags"] = _dedupe_hashtags(obj["hashtags"])
        # Provide empty sources_json so main.py can still insert the column
        obj["sources_json"] = {}
        return obj

    except Exception:
        # Rich deterministic fallback
        title, caption, body_md, hashtags, sources_json = _deterministic_markdown(
            day_iso=day_iso, kp=kp, bz=bz, wind=wind
        )
        return {
            "title": title,
            "caption": caption,
            "body_markdown": body_md,
            "hashtags": hashtags,
            "sources_json": sources_json,  # empty {}
        }
