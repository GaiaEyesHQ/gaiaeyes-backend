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

COPY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "gaia_eyes_daily_signal_copy",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(REQUIRED_COPY_KEYS),
            "properties": {
                "headline": {"type": "string"},
                "quick_read": {"type": "string"},
                "facebook": {"type": "string"},
                "instagram": {"type": "string"},
                "voiceover": {"type": "string"},
                "section_copy": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["regional_watch", "space_watch", "earth_signal", "major_events"],
                    "properties": {
                        "regional_watch": {"type": "string"},
                        "space_watch": {"type": "string"},
                        "earth_signal": {"type": "string"},
                        "major_events": {"type": "string"},
                    },
                },
            },
        },
    },
}


def _writer_facts(report: Mapping[str, Any]) -> dict[str, Any]:
    space = report.get("space_watch") if isinstance(report.get("space_watch"), Mapping) else {}
    space_metrics = space.get("metrics") if isinstance(space.get("metrics"), Mapping) else {}
    source_row = space.get("source_row") if isinstance(space.get("source_row"), Mapping) else {}
    earth = report.get("earth_signal") if isinstance(report.get("earth_signal"), Mapping) else {}
    schumann = earth.get("schumann") if isinstance(earth.get("schumann"), Mapping) else {}
    ulf = earth.get("ulf") if isinstance(earth.get("ulf"), Mapping) else {}
    schumann_values = {
        key: schumann.get(key)
        for key in ("f0", "f1", "f2", "f3", "f4", "f5", "combined_f1")
        if schumann.get(key) is not None
    }
    ulf_usable = earth.get("ulf_usable") is True

    return {
        "day": report.get("day"),
        "coverage": report.get("coverage"),
        "regional_watch": report.get("regional_watch"),
        "space_watch": {
            "signal_strength": space.get("signal_strength"),
            "recovery_frame": space.get("recovery_frame"),
            "daily_metrics": {
                "daily_kp_peak": space_metrics.get("kp_max"),
                "daily_bz_low_nt": space_metrics.get("bz_min"),
                "daily_solar_wind_average_kms": space_metrics.get("solar_wind_kms"),
                "cme_catalog_entries": space_metrics.get("cmes_count"),
            },
            "current_metrics": {
                "current_kp": source_row.get("kp_now"),
                "current_bz_nt": source_row.get("bz_now"),
                "current_solar_wind_kms": source_row.get("sw_speed_now_kms") or source_row.get("sw_speed_now"),
                "current_solar_wind_density_cm3": source_row.get("sw_density_now_cm3"),
            },
            "cme_note": "A catalog count alone does not establish current or Earth-directed impact.",
        },
        "earth_signal": {
            "schumann_available": bool(schumann_values),
            "schumann_values": schumann_values,
            "ulf_usable": ulf_usable,
            "ulf": (
                {
                    "context_class": ulf.get("context_class"),
                    "confidence_score": ulf.get("confidence_score"),
                    "regional_intensity": ulf.get("regional_intensity"),
                    "regional_coherence": ulf.get("regional_coherence"),
                    "regional_persistence": ulf.get("regional_persistence"),
                    "stations_used": ulf.get("stations_used"),
                }
                if ulf_usable
                else None
            ),
            "unavailable_reason": (
                "ULF did not meet the public confidence threshold. Do not interpret its class, measurements, or possible effects."
                if not ulf_usable
                else None
            ),
        },
        "major_events": report.get("major_events"),
    }


def writer_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task": "Write the public Gaia Eyes Daily Signal Report from this factual report object.",
        "report_name": "Gaia Eyes Daily Signal Report",
        "required_flow": ["Regional Watch", "Space Watch", "Earth Signal", "Major Events when present"],
        "facts": _writer_facts(report),
        "outputs": {
            "headline": "A plain-English emotional or body-first hook, no more than 12 words.",
            "quick_read": "Two or three sentences that give the useful rundown first.",
            "facebook": "A readable 250-450 word report with the quick read followed by the required sections.",
            "instagram": "A summary of at least 60 and no more than 110 words, naming only the strongest regional and global signals and ending with 'Full daily report: gaiaeyes.com'.",
            "voiceover": "A natural 55-75 word reel script that opens with an emotional or body-first hook and has no CTA or wellness-tip ending.",
            "section_copy": {
                "regional_watch": "Two to five concise regional paragraphs.",
                "space_watch": "One concise paragraph.",
                "earth_signal": "One concise Schumann/ULF paragraph.",
                "major_events": "Zero to four concise event bullets.",
            },
        },
    }


def _copy_validation_errors(copy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    ranges = {
        "facebook": (250, 450),
        "instagram": (60, 110),
        "voiceover": (55, 75),
    }
    for key, (minimum, maximum) in ranges.items():
        count = len(str(copy.get(key) or "").split())
        if not minimum <= count <= maximum:
            errors.append(f"{key} must be {minimum}-{maximum} words; received {count}")
    headline_count = len(str(copy.get("headline") or "").split())
    if not 1 <= headline_count <= 12:
        errors.append(f"headline must be 1-12 words; received {headline_count}")
    return errors


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
        "The headline and voiceover must open with a natural emotional or body-first hook, not a list of conditions, metrics, or regions. Avoid vague metaphors. "
        "Facebook must also open with the emotional or body-first hook before its quick rundown. "
        "Do not say readings explain why someone feels a certain way; say supplied conditions may be part of what they notice. "
        "Give the rundown before details. Name regions precisely; never broaden one event to a continent or the whole world. Say conditions were sampled or detected, not reported by a region. "
        "Do not call regional conditions global, widespread, or worldwide unless coverage.public_global_claims_allowed is true. "
        "Regional health language may say 'may', 'can', or 'some people notice' and must stay within each region's supplied health_context. "
        "Choose only the most relevant one or two supplied health effects per regional paragraph; do not reproduce symptom lists. "
        "Earth Signal may describe possible human effects with 'may', 'can', or 'some people notice' only when its supplied measurement is marked usable and earth_signal includes an explicit health_context. Without that list, describe only the measured field pattern. If ULF is unusable, do not interpret its class, numbers, or human effects. "
        "Schumann harmonic values are frequency measurements, not an activity or intensity score. Do not call them steady, elevated, active, calm, or unusual unless comparative evidence is explicitly supplied. "
        "Do not append a disclaimer, caveat paragraph, or research defense to Earth Signal. "
        "Use recovery or recoup language only when space_watch.recovery_frame is true. When it is false, describe current versus daily activity without a recovery claim. "
        "When Earth measurements are unavailable, state that once in plain English without exposing internal confidence-threshold language. "
        "Distinguish daily space peaks from current readings. Do not mention a CME catalog count as an active impact unless Earth-directed or impact evidence is supplied. "
        "Use reader-friendly metric names rather than source field identifiers. Do not invent active weather, AQI, pollen, hazards, health effects, measurements, locations, or causality. "
        "Major Events is conditional and must not list events absent from the supplied facts. "
        "Facebook may end with 'Full report: gaiaeyes.com' and 'Personalized patterns: gaiaeyes.com/app'. "
        "Voiceover must end on the factual rundown, with no CTA, advice, wellness tip, reflection prompt, or filler sign-off. No emojis. Return only JSON."
    )
    try:
        client = OpenAI(api_key=api_key)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(writer_payload(report), ensure_ascii=False)},
        ]
        for attempt in range(2):
            response = client.chat.completions.create(
                model=selected_model,
                reasoning_effort="low",
                max_completion_tokens=3200,
                response_format=COPY_RESPONSE_FORMAT,
                messages=messages,
            )
            text = str(response.choices[0].message.content or "").strip()
            obj = json.loads(text)
            if not isinstance(obj, dict) or not REQUIRED_COPY_KEYS.issubset(obj):
                return {"status": "invalid", "reason": "writer response missing required keys", "raw": obj}
            if not isinstance(obj.get("section_copy"), dict):
                return {"status": "invalid", "reason": "section_copy must be an object", "raw": obj}
            errors = _copy_validation_errors(obj)
            if not errors:
                return {"status": "generated", "model": selected_model, "writer_attempts": attempt + 1, **obj}
            if attempt == 0:
                messages.extend(
                    [
                        {"role": "assistant", "content": text},
                        {
                            "role": "user",
                            "content": (
                                "Rewrite the complete JSON draft to address these review failures: "
                                + "; ".join(errors)
                                + ". Preserve the supplied facts and schema. Use plain public language; do not expose internal terms such as confidence thresholds, usability decisions, or recovery-frame instructions."
                            ),
                        },
                    ]
                )
                continue
            return {
                "status": "invalid",
                "reason": "writer copy failed editorial validation",
                "validation_errors": errors,
                "raw": obj,
            }
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "model": selected_model}
