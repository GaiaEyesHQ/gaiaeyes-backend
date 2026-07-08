from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence


CTA_VARIANTS = [
    {
        "key": "solar-heart",
        "themes": ("solar", "active", "cme"),
        "card": "Could solar activity affect your heart? Gaia Eyes checks your wearable patterns.",
        "caption": (
            "Want to know if solar activity affects your heart? Gaia Eyes compares wearable data "
            "with Earth and space signals."
        ),
    },
    {
        "key": "mood-environment",
        "themes": ("general", "mood", "calm"),
        "card": "Mood off for no clear reason? Gaia Eyes tracks signals around your day.",
        "caption": (
            "Mood off for no obvious reason? Gaia Eyes tracks symptoms, wearable data, and "
            "environmental signals together."
        ),
    },
    {
        "key": "headache-forecast",
        "themes": ("symptom", "forecast", "active"),
        "card": "Headaches or sinus pressure flaring? Gaia Eyes helps forecast your week.",
        "caption": (
            "Headaches or sinus pressure flaring? Gaia Eyes helps compare symptoms with "
            "environmental factors and the week ahead."
        ),
    },
    {
        "key": "provider-stats",
        "themes": ("general", "symptom"),
        "card": "Tired of being dismissed? Turn symptom patterns into stats you can share.",
        "caption": (
            "Tired of being dismissed? Gaia Eyes turns symptom patterns into stats you can "
            "share with your provider."
        ),
    },
    {
        "key": "moon-cycles",
        "themes": ("moon",),
        "card": "Feel the moon sometimes? Gaia Eyes checks wearable and moon-cycle patterns.",
        "caption": (
            "Feel the moon sometimes? Gaia Eyes checks for patterns between symptoms, "
            "wearable data, and moon cycles."
        ),
    },
    {
        "key": "frequency-sensitive",
        "themes": ("schumann", "ulf", "frequency"),
        "card": "Feeling sensitive to background signals? Gaia Eyes helps find your environmental triggers and patterns.",
        "caption": (
            "Feeling sensitive to background signals? Gaia Eyes compares sleep, heart patterns, "
            "mood, symptoms, and environmental changes."
        ),
    },
    {
        "key": "complete-picture",
        "themes": ("general", "calm", "forecast"),
        "card": "One place for wearables, symptoms, conditions, triggers, and forecasts.",
        "caption": (
            "Gaia Eyes brings wearables, symptoms, conditions, environmental signals, "
            "triggers, patterns, and forecasts into one place."
        ),
    },
]


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _context_themes(context: Mapping[str, Any] | None) -> Sequence[str]:
    if not isinstance(context, Mapping):
        return ("general",)
    tone = str(context.get("tone") or "").lower()
    bands = context.get("bands") if isinstance(context.get("bands"), Mapping) else {}
    kp_band = str(bands.get("kp") or "").lower()
    kp = _safe_float(context.get("kp_max_24h") or context.get("kp_max") or context.get("kp_current"))
    cmes = _safe_float(context.get("cmes_24h") or context.get("cmes_count"))
    flares = _safe_float(context.get("flares_24h") or context.get("flares_count"))
    schumann = _safe_float(
        context.get("schumann_value_hz")
        or context.get("sch_any_fundamental_avg_hz")
        or context.get("sch_fundamental_avg_hz")
        or context.get("sch_cumiana_fundamental_avg_hz")
    )
    if schumann is not None and (schumann >= 7.6 or tone == "schumann"):
        return ("schumann", "frequency")
    if (cmes is not None and cmes > 0) or (flares is not None and flares > 0):
        return ("solar", "cme")
    if tone in {"stormy", "unsettled"} or kp_band in {"active", "storm", "severe", "unsettled"} or (kp is not None and kp >= 3):
        return ("active", "symptom")
    if tone in {"calm", "neutral"} or kp_band in {"quiet", "calm"} or (kp is not None and kp < 3):
        return ("calm", "general")
    return ("general",)


def select_earthscope_cta(seed: Any, *, context: Mapping[str, Any] | None = None) -> Mapping[str, str]:
    seed_text = str(seed or "").strip() or "earthscope"
    themes = set(_context_themes(context))
    options = [
        item for item in CTA_VARIANTS
        if themes.intersection(set(item.get("themes") or ()))
    ] or CTA_VARIANTS
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(options)
    return options[index]


def append_caption_cta(caption: str, *, seed: Any = "", context: Mapping[str, Any] | None = None) -> str:
    text = (caption or "").strip()
    cta = select_earthscope_cta(seed, context=context).get("caption", "").strip()
    if not cta:
        return text
    lower = text.lower()
    if any(
        marker in lower
        for marker in (
            "gaia eyes compares wearable data",
            "gaia eyes tracks symptoms",
            "gaia eyes helps compare symptoms",
            "gaia eyes helps turn health patterns",
            "gaia eyes looks for patterns",
            "gaia eyes helps you find out",
            "gaia eyes combines wearable data",
        )
    ):
        return text
    return f"{text}\n\n{cta}" if text else cta
