from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Mapping

from openai import OpenAI

from services.openai_models import resolve_openai_model


REQUIRED_COPY_KEYS = {
    "headline",
    "quick_read",
    "facebook",
    "instagram",
    "voiceover",
    "reel_story",
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
                "reel_story": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["hook", "where", "drivers", "effects", "summary"],
                    "properties": {
                        "hook": {"type": "string"},
                        "where": {"type": "string"},
                        "drivers": {"type": "string"},
                        "effects": {"type": "string"},
                        "summary": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["regional", "space", "earth", "major_event"],
                            "properties": {
                                "regional": {"type": "string"},
                                "space": {"type": "string"},
                                "earth": {"type": "string"},
                                "major_event": {"type": "string"},
                            },
                        },
                    },
                },
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
        "edition": report.get("edition"),
        "geographic_scope": report.get("geographic_scope"),
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
        "task": f"Write the public {report.get('public_name') or 'Gaia Eyes Health Snapshot'} from this factual report object.",
        "report_name": report.get("public_name") or "Gaia Eyes Health Snapshot",
        "geographic_scope": report.get("geographic_scope") or "global",
        "required_flow": ["Regional Watch", "Space Watch", "Earth Signal", "Major Events when present"],
        "audience_and_voice": {
            "reader": "A general adult reader with no science or weather background.",
            "voice": "Warm, clear, conversational, and useful; like a trusted daily health-and-environment update.",
            "short_form_rule": "Reel slides, Instagram, and voiceover must state what is happening in everyday language and sound natural when spoken aloud, without substituting new abstract terms for source jargon.",
            "detail_rule": "The longer Facebook report may name relevant measurements after first explaining what they mean in plain English.",
        },
        "facts": _writer_facts(report),
        "outputs": {
            "headline": "A plain-English emotional or body-first hook, no more than 12 words.",
            "quick_read": "Two or three sentences that give the useful rundown first.",
            "facebook": "A readable 200-450 word report with the quick read followed by the required sections. Explain the public meaning before naming technical measurements.",
            "instagram": "A conversational summary of 60-110 words, naming only the strongest in-scope regional, space, and Earth conditions in everyday language and ending with 'Full daily report: gaiaeyes.com'.",
            "voiceover": "A natural 55-75 word spoken reel script for a general audience. Open with an emotional or body-first hook, translate technical evidence into everyday language, and do not end with a CTA or wellness tip.",
            "reel_story": {
                "hook": "Slide 1: a concrete, human body-first question, no more than 8 words.",
                "where": "Slide 2: one natural complete sentence naming the strongest one to three in-scope regions. Do not mention sampling, anchors, coverage, or signals.",
                "drivers": "Slide 3: one natural complete sentence stating the actual environmental conditions behind the day, such as heat, humidity, storms, pressure changes, smoke, or poor air. Use the condition itself, not an abstract synonym such as push, factor, or influence.",
                "effects": "Slide 4: one warm, direct complete sentence naming only supported things some people may notice.",
                "summary": {
                    "regional": "Slide 5 Regional row: one everyday-language complete sentence of 4-12 words.",
                    "space": "Slide 5 Space row: one everyday-language complete sentence of 4-12 words. Describe the practical pace of space weather, not readings or metrics.",
                    "earth": "Slide 5 Earth row: one everyday-language complete sentence of 4-12 words. Give the simple public takeaway about Earth's background signals; omit acronyms, raw values, and specialist classifier words.",
                    "major_event": "Slide 5 optional Major Event row: one complete sentence of up to 12 words, or an empty string when none is supplied.",
                },
            },
            "section_copy": {
                "regional_watch": "Two to five concise regional paragraphs.",
                "space_watch": "One concise paragraph.",
                "earth_signal": "One concise Schumann/ULF paragraph.",
                "major_events": "Zero to four concise event bullets.",
            },
        },
    }


def _copy_validation_errors(copy: Mapping[str, Any], report: Mapping[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    ranges = {
        "facebook": (200, 450),
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
    reel_story = copy.get("reel_story") if isinstance(copy.get("reel_story"), Mapping) else {}
    slide_ranges = {
        "hook": (1, 8),
        "where": (3, 24),
        "drivers": (3, 24),
        "effects": (3, 24),
    }
    normalized_slides: list[tuple[str, str]] = []
    for key, (minimum, maximum) in slide_ranges.items():
        text = str(reel_story.get(key) or "").strip()
        count = len(text.split())
        if not minimum <= count <= maximum:
            errors.append(f"reel_story.{key} must be {minimum}-{maximum} words; received {count}")
        if key != "hook" and text and text[-1] not in ".?!":
            errors.append(f"reel_story.{key} must be a complete sentence ending in punctuation")
        normalized = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
        normalized_slides.append((key, " ".join(normalized.split())))
    summary = reel_story.get("summary") if isinstance(reel_story.get("summary"), Mapping) else {}
    for key in ("regional", "space", "earth"):
        text = str(summary.get(key) or "").strip()
        count = len(text.split())
        if not 4 <= count <= 12:
            errors.append(f"reel_story.summary.{key} must be 4-12 words; received {count}")
        if text and text[-1] not in ".?!":
            errors.append(f"reel_story.summary.{key} must be a complete sentence ending in punctuation")
        if ";" in text or "(" in text or ")" in text:
            errors.append(f"reel_story.summary.{key} must use plain prose without semicolons or parentheses")
        normalized = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
        normalized_slides.append((f"summary.{key}", " ".join(normalized.split())))
    major_event_text = str(summary.get("major_event") or "").strip()
    if len(major_event_text.split()) > 12:
        errors.append("reel_story.summary.major_event must be no more than 12 words")
    if major_event_text and major_event_text[-1] not in ".?!":
        errors.append("reel_story.summary.major_event must be a complete sentence ending in punctuation")
    for index, (left_key, left) in enumerate(normalized_slides):
        for right_key, right in normalized_slides[index + 1 :]:
            if left and right and SequenceMatcher(None, left, right).ratio() >= 0.8:
                errors.append(f"reel_story.{left_key} and reel_story.{right_key} are near-duplicates")
    major_events = report.get("major_events") if isinstance(report, Mapping) else {}
    event_items = major_events.get("items") if isinstance(major_events, Mapping) else None
    if event_items == []:
        public_fields = [
            str(copy.get(key) or "")
            for key in ("quick_read", "facebook", "instagram", "voiceover")
        ]
        public_fields.extend(str(reel_story.get(key) or "") for key in slide_ranges)
        public_fields.extend(str(summary.get(key) or "") for key in ("regional", "space", "earth", "major_event"))
        if any("major event" in text.lower() for text in public_fields):
            errors.append("copy must omit Major Events when no qualifying events are supplied")
        if major_event_text:
            errors.append("reel_story.summary.major_event must be empty when no qualifying event is supplied")
    factual_text = "\n".join(
        [str(copy.get(key) or "") for key in ("quick_read", "facebook", "instagram", "voiceover")]
        + [str(reel_story.get(key) or "") for key in slide_ranges]
        + [str(summary.get(key) or "") for key in ("regional", "space", "earth", "major_event")]
    )
    earth_signal = report.get("earth_signal") if isinstance(report, Mapping) else {}
    if isinstance(earth_signal, Mapping) and earth_signal.get("ulf_usable") is not True:
        if re.search(r"\bulf\b[^.!?\n]*\bclassified\b", factual_text, flags=re.IGNORECASE):
            errors.append("copy must not call ULF classified when no usable ULF class is supplied")
    if re.search(r"\blow-strength\b", factual_text, flags=re.IGNORECASE):
        errors.append("copy must describe supplied low space activity in plain language")
    if re.search(r"\b(?:active|quiet|variable)\s+(?:diffuse|coherent)\s+ulf\b", factual_text, flags=re.IGNORECASE):
        errors.append("copy must translate ULF classifiers into grammatical public prose")
    earth_summary = str(summary.get("earth") or "")
    if re.search(r"\bschumann\s+is\b", earth_summary, flags=re.IGNORECASE):
        errors.append("reel_story.summary.earth must describe measured Schumann frequencies, not Schumann as a score")
    sentences = re.split(r"(?<=[.!?])\s+|\n+", factual_text.lower())
    unsupported_comparisons = {
        "schumann": ("expected", "normal", "typical", "aligned", "tracked", "steady", "stable"),
        "ulf": ("modest", "weak", "strong", "unusual"),
        "solar wind": ("modest", "weak", "strong", "normal", "typical", "steady", "stable"),
    }
    for subject, descriptors in unsupported_comparisons.items():
        subject_pattern = re.compile(rf"\b{re.escape(subject)}\b")
        descriptor_patterns = [re.compile(rf"\b{re.escape(descriptor)}\w*\b") for descriptor in descriptors]
        if any(
            subject_pattern.search(sentence)
            and any(pattern.search(sentence) for pattern in descriptor_patterns)
            for sentence in sentences
        ):
            errors.append(f"copy gives {subject} an unsupported qualitative comparison")
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
        "You are the Gaia Eyes public Health Snapshot writer. Use only supplied facts and stay inside the supplied geographic_scope. "
        "Write for a general adult reader with no science, space-weather, or meteorology background. The voice should feel warm, clear, conversational, and human, like a trusted daily health-and-environment update. "
        "Do not sound like a dashboard, lab report, data analyst, forecast discussion, or internal note. Prefer familiar words and short spoken sentences. "
        "Reel slides, Instagram, and voiceover are short-form public copy: translate the evidence into what an ordinary person can understand without exposing collection or processing language. "
        "In short-form copy, avoid terms such as sampled, anchors, coverage, supported drivers, current readings, harmonics, context class, ULF, Kp, Bz, low-frequency, and diffuse. Do not merely delete technical terms or invent abstract synonyms such as push, factor, or influence; state the actual condition or simple public takeaway naturally. "
        "The longer Facebook report and detailed section_copy may name relevant technical measurements, including Schumann frequencies or ULF, after first explaining their plain-English meaning. "
        "Write the report in this exact order: Regional Watch, Space Watch, Earth Signal, then Major Events when present. "
        "The headline and voiceover must open with a natural emotional or body-first hook, not a list of conditions, metrics, or regions. Avoid vague metaphors. "
        "Facebook must also open with the emotional or body-first hook before its quick rundown. "
        "Do not say readings explain why someone feels a certain way; say supplied conditions may be part of what they notice. "
        "Give the rundown before details. Name regions precisely; never broaden one event to a continent or the whole world. In detailed report copy, say conditions were observed across a region rather than reported by the region. "
        "Do not call regional conditions global, widespread, or worldwide unless coverage.public_global_claims_allowed is true. "
        "Regional health language may say 'may', 'can', or 'some people notice' and must stay within each region's supplied health_context. "
        "Choose only the most relevant one or two supplied health effects per regional paragraph; do not reproduce symptom lists. "
        "Earth Signal may describe possible human effects with 'may', 'can', or 'some people notice' only when its supplied measurement is marked usable and earth_signal includes an explicit health_context. Without that list, describe only the measured field pattern. If ULF is unusable, do not interpret its class, numbers, or human effects. "
        "Schumann harmonic values are frequency measurements, not an activity or intensity score. State measured frequencies only. Do not call them expected, normal, typical, aligned, tracked, steady, stable, elevated, active, calm, or unusual unless comparative evidence is explicitly supplied. "
        "For ULF, use a supplied context_class verbatim. Do not characterize raw intensity, coherence, or persistence values as modest, elevated, strong, weak, or unusual unless comparative thresholds are supplied. "
        "For solar wind, use supplied measurements and signal_strength only. Do not call it modest, strong, weak, normal, typical, steady, or stable without supplied comparative evidence. "
        "Say space weather is low, moderate, or high as supplied; never write low-strength. If ULF is unusable, say it is unavailable and never call it classified. If ULF is usable, name its supplied context_class whenever saying it is classified. "
        "In detailed report copy, translate supplied ULF classifiers into natural prose, such as 'an active pattern spread across the measured frequencies'; never stack bare internal labels such as 'Active diffuse ULF'. Explain Earth measurements concretely without mystical heartbeat, energy, or beneath-our-feet metaphors. "
        "In the reel summary Earth row, translate available Schumann and ULF evidence into a simple description of Earth's background signals. A natural construction is 'Earth's background signals were active and spread out.' Do not use the words Schumann, ULF, low-frequency, or diffuse there, and never write 'Schumann is' followed by a value or state. "
        "Do not append a disclaimer, caveat paragraph, or research defense to Earth Signal. "
        "Use recovery or recoup language only when space_watch.recovery_frame is true. When it is false, describe current versus daily activity without a recovery claim. "
        "When Earth measurements are unavailable, state that once in plain English without exposing internal confidence-threshold language. "
        "Distinguish daily space peaks from current readings. Do not mention a CME catalog count as an active impact unless Earth-directed or impact evidence is supplied. "
        "Use reader-friendly metric names rather than source field identifiers. Do not invent active weather, AQI, pollen, hazards, health effects, measurements, locations, or causality. "
        "Major Events is conditional and must not list events absent from the supplied facts. "
        "The five reel_story slides must be complete, distinct thoughts. Never split one sentence across slides or repeat the same statement with one changed word. Slide 5 uses separate complete Regional, Space, and Earth rows, plus Major Event only when supplied; do not compress those rows into classifier fragments. "
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
            errors = _copy_validation_errors(obj, report)
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
                "model": selected_model,
                "validation_errors": errors,
                "raw": obj,
            }
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "model": selected_model}
