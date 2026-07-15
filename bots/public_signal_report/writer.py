from __future__ import annotations

import json
from typing import Any, Mapping

from openai import OpenAI

from services.openai_models import resolve_openai_model


REQUIRED_COPY_KEYS = {
    "headline",
    "quick_read",
    "facebook",
    "instagram",
    "voiceover",
    "section_copy",
}


def writer_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task": "Write the public Gaia Eyes Daily Signal Report from this factual report object.",
        "report_name": "Gaia Eyes Daily Signal Report",
        "required_flow": ["Regional Watch", "Space Watch", "Earth Signal", "Major Events when present"],
        "facts": dict(report),
        "outputs": {
            "headline": "A clear, emotional, factual headline for the day's combined pattern.",
            "quick_read": "Two or three sentences that give the useful rundown first.",
            "facebook": "A readable 250-450 word report with the quick read followed by the required sections.",
            "instagram": "A 60-110 word summary naming only the strongest regional and global signals, ending with 'Full daily report: gaiaeyes.com'.",
            "voiceover": "A natural 45-75 word reel script with no CTA or wellness-tip ending.",
            "section_copy": {
                "regional_watch": "Two to five concise regional paragraphs.",
                "space_watch": "One concise paragraph.",
                "earth_signal": "One concise Schumann/ULF paragraph.",
                "major_events": "Zero to four concise event bullets.",
            },
        },
    }


def generate_platform_copy(
    report: Mapping[str, Any],
    *,
    api_key: str,
    model: str | None = None,
) -> dict[str, Any]:
    if not api_key:
        return {"status": "not_generated", "reason": "OPENAI_API_KEY missing"}
    selected_model = model or resolve_openai_model("public_writer")
    if not selected_model:
        return {"status": "not_generated", "reason": "public writer model missing"}

    system = (
        "You are the Gaia Eyes public Daily Signal Report writer. Use only supplied facts. "
        "Write the report in this exact order: Regional Watch, Space Watch, Earth Signal, then Major Events when present. "
        "Lead with a useful emotional hook and give the rundown before details. Name regions precisely; never broaden one event to a continent or the whole world. "
        "Do not call regional conditions global, widespread, or worldwide unless coverage.public_global_claims_allowed is true. "
        "Regional health language may say 'may', 'can', or 'some people notice' and must stay within each region's supplied health_context. "
        "Earth Signal may also describe possible human effects with 'may', 'can', or 'some people notice'. Do not append a disclaimer, caveat paragraph, or research defense to Earth Signal. "
        "When Space Watch is quiet, frame it as welcome room to recoup while noting that carryover and regional conditions can still matter. "
        "Do not invent active weather, AQI, pollen, hazards, health effects, measurements, locations, or causality. "
        "Major Events is conditional and must not list events absent from the supplied facts. "
        "Facebook may end with 'Full report: gaiaeyes.com' and 'Personalized patterns: gaiaeyes.com/app'. "
        "Voiceover must not include a CTA. No emojis. Return only JSON."
    )
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=selected_model,
            reasoning_effort="low",
            max_completion_tokens=3200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(writer_payload(report), ensure_ascii=False)},
            ],
        )
        text = str(response.choices[0].message.content or "").strip()
        obj = json.loads(text)
        if not isinstance(obj, dict) or not REQUIRED_COPY_KEYS.issubset(obj):
            return {"status": "invalid", "reason": "writer response missing required keys", "raw": obj}
        if not isinstance(obj.get("section_copy"), dict):
            return {"status": "invalid", "reason": "section_copy must be an object", "raw": obj}
        return {"status": "generated", "model": selected_model, **obj}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "model": selected_model}
