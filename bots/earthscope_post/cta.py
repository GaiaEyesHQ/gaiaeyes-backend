from __future__ import annotations

import hashlib
from typing import Any, Mapping


CTA_VARIANTS = [
    {
        "key": "solar-heart",
        "card": "Could solar activity affect your heart? Gaia Eyes checks your wearable patterns.",
        "caption": (
            "Want to know if solar activity affects your heart? Gaia Eyes compares wearable data "
            "with Earth and space signals to help find your patterns."
        ),
    },
    {
        "key": "mood-environment",
        "card": "Mood off for no clear reason? Gaia Eyes tracks signals around your day.",
        "caption": (
            "Mood off for no obvious reason? Gaia Eyes tracks symptoms, wearable data, and "
            "environmental signals so you can see what may be influencing your day."
        ),
    },
    {
        "key": "headache-forecast",
        "card": "Headaches or sinus pressure flaring? Gaia Eyes helps forecast your week.",
        "caption": (
            "Headaches or sinus pressure flaring? Environmental factors can play a role. Gaia Eyes "
            "helps compare symptoms with your surroundings and forecast the week ahead."
        ),
    },
    {
        "key": "provider-stats",
        "card": "Tired of being dismissed? Turn symptom patterns into stats you can share.",
        "caption": (
            "Tired of being dismissed about your symptoms? Gaia Eyes helps turn health patterns "
            "into concrete stats you can share with your provider."
        ),
    },
    {
        "key": "moon-cycles",
        "card": "Feel the moon sometimes? Gaia Eyes checks wearable and moon-cycle patterns.",
        "caption": (
            "Feel like howling at the moon sometimes? Gaia Eyes looks for patterns between "
            "wearable data, symptoms, and moon cycles."
        ),
    },
    {
        "key": "frequency-sensitive",
        "card": "Sensitive to Schumann or ULF signals? Gaia Eyes helps you find out.",
        "caption": (
            "Frequencies may affect heart and mental-health patterns. Gaia Eyes helps you find "
            "out if you are sensitive to Schumann resonance or ULF frequencies."
        ),
    },
    {
        "key": "complete-picture",
        "card": "One place for wearables, symptoms, conditions, triggers, and forecasts.",
        "caption": (
            "Got several health apps and none explain why you feel the way you do? Gaia Eyes "
            "combines wearable data, symptoms, medical conditions, and environmental signals "
            "to show your triggers, patterns, and what may be coming."
        ),
    },
]


def select_earthscope_cta(seed: Any) -> Mapping[str, str]:
    seed_text = str(seed or "").strip() or "earthscope"
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(CTA_VARIANTS)
    return CTA_VARIANTS[index]


def append_caption_cta(caption: str, *, seed: Any = "") -> str:
    text = (caption or "").strip()
    cta = select_earthscope_cta(seed).get("caption", "").strip()
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
