import json
from .models import Draft, Sections, Item

SYS = "You write concise, trustworthy news for Gaia Eyes. Use verified facts; avoid speculation."

def _fallback(item: Item) -> Draft:
    base = Sections(
        tldr=item.title,
        what_happened=item.summary[:240],
        why_it_matters="Relevant to space weather / human systems; tracking follow-ups.",
        details_today="",
        next_72h="Monitor Kp/Bz and solar wind for changes.",
        impacts_plain="Navigation/GNSS and wellness impacts minimal unless Kp rises quickly."
    )
    return Draft(scientific=base, mystical=base, tags=["GaiaEyes","EarthScope"])

def llm_call(_prompt: dict) -> str:
    """
    Placeholder. Wire to your LLM if you want; must return JSON string matching Draft schema.
    Returning '{}' forces the safe fallback.
    """
    return "{}"

def rewrite_dual(item: Item) -> Draft:
    prompt = {
      "system": SYS,
      "user": f"""
Title: {item.title}
Source: {item.source}
URL: {item.url}
Summary: {item.summary}
Topics: {', '.join(item.topics)}
Return STRICT JSON with keys: scientific, mystical, tags.
Each section has: tldr, what_happened, why_it_matters, details_today, next_72h, impacts_plain.
"""}
    for _ in range(2):
        try:
            txt = llm_call(prompt)
            payload = json.loads(txt)
            sci = Sections(**payload["scientific"])
            mys = Sections(**payload["mystical"])
            return Draft(scientific=sci, mystical=mys, tags=payload.get("tags", []))
        except Exception:
            continue
    return _fallback(item)