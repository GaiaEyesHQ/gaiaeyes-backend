from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional, Sequence

from .profiles import VoiceProfile
from .semantic import SemanticGuardrails, SemanticPayload, SemanticRenderHints


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _confidence_from_pattern_status(pattern_status: str, severity: str) -> str:
    normalized_status = _clean_text(pattern_status).lower()
    if normalized_status == "strong":
        return "high"
    if normalized_status == "moderate":
        return "moderate"
    normalized_severity = _clean_text(severity).lower()
    if normalized_severity in {"high", "watch", "elevated"}:
        return "moderate"
    return "low"


def build_driver_summary_semantic(
    *,
    day: date,
    raw_top_drivers: Sequence[Mapping[str, Any]],
    primary_driver: Optional[Mapping[str, Any]],
    supporting_drivers: Sequence[Mapping[str, Any]],
    today_personal_themes: Sequence[Mapping[str, Any]],
    override_note: str = "",
) -> SemanticPayload:
    primary_driver = dict(primary_driver or {})
    supporting_driver_rows = [dict(item) for item in supporting_drivers if isinstance(item, Mapping)]
    theme_rows = [dict(item) for item in today_personal_themes if isinstance(item, Mapping)]

    confidence = _confidence_from_pattern_status(
        _clean_text(primary_driver.get("confidence")),
        _clean_text(primary_driver.get("severity")),
    )
    claim_strength = "may_notice" if confidence in {"moderate", "high"} else "observe_only"

    return SemanticPayload(
        schema_version="1.0",
        kind="driver_summary",
        date=day.isoformat(),
        facts={
            "raw_top_drivers": [dict(item) for item in raw_top_drivers if isinstance(item, Mapping)],
        },
        interpretation={
            "primary_driver": primary_driver or None,
            "supporting_drivers": supporting_driver_rows,
            "body_themes": theme_rows,
            "override_note": override_note or None,
        },
        actions={"primary": [], "secondary": []},
        guardrails=SemanticGuardrails(
            confidence_overall=confidence,
            claim_strength=claim_strength,
            evidence_basis=[
                basis
                for basis in (
                    "personal_pattern_history" if primary_driver.get("active_pattern_refs") else None,
                    "current_driver_mix" if raw_top_drivers else None,
                )
                if basis
            ],
            max_urgency="watch" if confidence in {"moderate", "high"} else "notable",
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="short",
            preferred_detail_sections=["what_is_active", "what_you_may_notice"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )


def render_driver_daily_brief(
    payload: SemanticPayload,
    *,
    voice_profile: Optional[VoiceProfile] = None,
) -> str:
    _ = voice_profile or VoiceProfile.app_summary_default()
    interpretation = payload.interpretation or {}
    override_note = _clean_text(interpretation.get("override_note"))
    if override_note:
        return override_note

    primary_driver = interpretation.get("primary_driver") if isinstance(interpretation.get("primary_driver"), Mapping) else {}
    supporting_drivers = [
        item for item in (interpretation.get("supporting_drivers") or []) if isinstance(item, Mapping)
    ]
    if not primary_driver:
        return ""

    label = _clean_text(primary_driver.get("label") or primary_driver.get("key") or "This signal")
    primary_short = _clean_text(primary_driver.get("personal_reason_short"))
    normalized_label = label.lower()
    if normalized_label in {"current symptoms", "symptoms logged"}:
        daily_brief = "Right now, your current symptoms look most relevant for you."
        if primary_short:
            daily_brief += f" {primary_short}"
    elif primary_short:
        daily_brief = f"Right now, {label.lower()} looks most relevant for you. {primary_short}"
    else:
        daily_brief = f"Right now, {label.lower()} looks like the clearest current driver in your mix."

    if supporting_drivers:
        support_label = _clean_text(supporting_drivers[0].get("label") or supporting_drivers[0].get("key"))
        if support_label:
            daily_brief += f" {support_label} is also in the mix."
    return daily_brief


def build_driver_reason_semantic(
    *,
    day: date,
    row: Mapping[str, Any],
) -> SemanticPayload:
    pattern_status = _clean_text(row.get("pattern_status"))
    severity = _clean_text(row.get("severity"))
    confidence = _confidence_from_pattern_status(pattern_status, severity)

    return SemanticPayload(
        schema_version="1.0",
        kind="driver_reason",
        date=day.isoformat(),
        facts={
            "driver": {
                "key": _clean_text(row.get("key")),
                "label": _clean_text(row.get("label")),
                "state": _clean_text(row.get("state")),
                "state_label": _clean_text(row.get("state_label")),
                "severity": severity,
                "reading": _clean_text(row.get("reading")),
                "category": _clean_text(row.get("category")),
            },
            "current_symptoms": list(row.get("current_symptoms") or []),
            "historical_symptoms": list(row.get("historical_symptoms") or []),
        },
        interpretation={
            "role": _clean_text(row.get("role")),
            "seed_short_reason": _clean_text(row.get("short_reason")),
            "seed_personal_reason": _clean_text(row.get("personal_reason")),
            "pattern_summary": _clean_text(row.get("pattern_summary")),
            "outlook_summary": _clean_text(row.get("outlook_summary")),
            "pattern_status": pattern_status,
        },
        actions={"primary": [], "secondary": []},
        guardrails=SemanticGuardrails(
            confidence_overall=confidence,
            claim_strength="may_notice" if confidence in {"moderate", "high"} else "observe_only",
            evidence_basis=[
                basis
                for basis in (
                    "pattern_history" if pattern_status in {"strong", "moderate", "emerging"} else None,
                    "current_driver_state",
                )
                if basis
            ],
            max_urgency="watch" if severity in {"high", "watch", "elevated"} else "notable",
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="short",
            preferred_detail_sections=["what_is_active", "what_you_may_notice", "what_may_help"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )


def render_driver_reason(
    payload: SemanticPayload,
    *,
    variant: str = "full",
    voice_profile: Optional[VoiceProfile] = None,
) -> str:
    _ = voice_profile or VoiceProfile.app_summary_default()
    interpretation = payload.interpretation or {}
    driver = payload.facts.get("driver") if isinstance(payload.facts, Mapping) else {}
    label = _clean_text((driver or {}).get("label") or (driver or {}).get("key") or "Driver")

    if variant == "short":
        seed = _clean_text(interpretation.get("seed_short_reason"))
        if seed:
            return seed
        state = _clean_text((driver or {}).get("state_label") or (driver or {}).get("state"))
        return f"{label} is {state.lower()} right now." if state else f"{label} is active right now."

    seed = _clean_text(interpretation.get("seed_personal_reason"))
    if seed:
        return seed
    state = _clean_text((driver or {}).get("state_label") or (driver or {}).get("state"))
    if state:
        return f"{label} is {state.lower()} right now, but no stronger personal pattern is leading with it yet."
    return f"{label} is active right now, but no stronger personal pattern is leading with it yet."
