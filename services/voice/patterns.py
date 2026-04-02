from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from .semantic import SemanticAction, SemanticGuardrails, SemanticPayload, SemanticRenderHints


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _confidence_level(raw: str) -> str:
    normalized = _clean_text(raw).lower()
    if normalized == "strong":
        return "high"
    if normalized in {"moderate", "emerging"}:
        return "moderate"
    return "low"


def _claim_strength(raw: str) -> str:
    normalized = _clean_text(raw).lower()
    if normalized == "strong":
        return "strong_repeat_pattern"
    if normalized in {"moderate", "emerging"}:
        return "may_notice"
    return "observe_only"


def _value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if value is not None:
                return value
    return None


def _format_last_seen(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.strftime("%b %d, %Y").replace(" 0", " ")
    except Exception:
        return raw


def _lift_text(row: Mapping[str, Any]) -> str:
    relative_lift = float(_value(row, "relative_lift", "relativeLift") or 0.0)
    sample_size = int(_value(row, "sample_size", "sampleSize", "exposed_n", "exposed_days", "exposedDays") or 0)
    lag_hours = int(_value(row, "lag_hours", "lagHours") or 0)
    lag_label = _clean_text(_value(row, "lag_label", "lagLabel")) or (
        "same day" if lag_hours == 0 else f"{lag_hours}h"
    )
    if sample_size > 0 and relative_lift > 0:
        return f"{relative_lift:.1f}x more common when exposed • {sample_size} exposed days • Lag {lag_label}"
    if sample_size > 0:
        return f"{sample_size} exposed days • Lag {lag_label}"
    return f"Lag {lag_label}"


def _baseline_text(row: Mapping[str, Any]) -> str:
    exposed_rate = int(round(float(_value(row, "exposed_rate", "exposedRate") or 0.0) * 100))
    baseline_rate = int(round(float(_value(row, "unexposed_rate", "unexposedRate") or 0.0) * 100))
    last_seen = _format_last_seen(_value(row, "last_seen_at", "lastSeenAt"))
    bits = [f"When exposed: {exposed_rate}%", f"When not exposed: {baseline_rate}%"]
    if last_seen:
        bits.append(f"Last seen: {last_seen}")
    return " • ".join(bits)


def build_pattern_card_semantic(
    *,
    day: date,
    row: Mapping[str, Any],
    used_today: bool,
) -> SemanticPayload:
    confidence = _clean_text(row.get("confidence"))
    signal = _clean_text(row.get("signal"))
    outcome = _clean_text(row.get("outcome"))
    explanation = _clean_text(row.get("explanation"))

    actions = [
        SemanticAction(
            key="track_pattern",
            priority=1,
            reason="pattern_tracking",
            label="Keep logging the same outcome so this pattern can sharpen over time.",
        )
    ]
    if used_today:
        actions.insert(
            0,
            SemanticAction(
                key="compare_today",
                priority=1,
                reason="active_today",
                label="This signal is active today, so compare it with how the day actually feels.",
            ),
        )

    return SemanticPayload(
        schema_version="1.0",
        kind="personal_pattern_card",
        date=day.isoformat(),
        user_context={"audience": "member", "channel": "app_patterns"},
        facts={
            "signal_key": _clean_text(row.get("signal_key")),
            "signal": signal,
            "outcome_key": _clean_text(row.get("outcome_key")),
            "outcome": outcome,
            "confidence": confidence,
            "used_today": used_today,
            "sample_size": int(_value(row, "sample_size", "sampleSize", "exposed_n", "exposed_days", "exposedDays") or 0),
            "lag_hours": int(_value(row, "lag_hours", "lagHours") or 0),
            "relative_lift": float(_value(row, "relative_lift", "relativeLift") or 0.0),
        },
        interpretation={
            "header_summary": explanation,
            "evidence_summary": _lift_text(row),
            "baseline_summary": _baseline_text(row),
            "active_today_summary": (
                f"{signal} is part of today's signal mix, so {outcome.lower()} is worth comparing with your current state."
                if used_today and signal and outcome
                else None
            ),
        },
        actions={
            "primary": [item.__dict__ for item in actions],
            "secondary": [],
        },
        guardrails=SemanticGuardrails(
            confidence_overall=_confidence_level(confidence),
            claim_strength=_claim_strength(confidence),
            evidence_basis=["personal_pattern_history"] + (["current_driver_mix"] if used_today else []),
            max_urgency="watch" if used_today else ("notable" if confidence.lower() in {"strong", "moderate"} else "quiet"),
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="short",
            preferred_detail_sections=["pattern_summary", "evidence", "baseline"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )


def build_patterns_overview_semantic(
    *,
    day: date,
    strongest_count: int,
    emerging_count: int,
    body_count: int,
    used_today_count: int,
    partial: bool,
) -> SemanticPayload:
    if strongest_count > 0:
        header_summary = f"{strongest_count} clearer pattern{'s' if strongest_count != 1 else ''} stand out in your history right now."
    elif emerging_count > 0:
        header_summary = f"{emerging_count} possible repeat{'s are' if emerging_count != 1 else ' is'} taking shape, but none are strong enough to lean on yet."
    else:
        header_summary = "No clear patterns stand out yet. More overlap will make this page more useful."

    if used_today_count > 0:
        header_summary += f" {used_today_count} of those pattern{'s are' if used_today_count != 1 else ' is'} also active in today's signal mix."

    return SemanticPayload(
        schema_version="1.0",
        kind="patterns_overview",
        date=day.isoformat(),
        user_context={"audience": "member", "channel": "app_patterns"},
        facts={
            "strongest_count": strongest_count,
            "emerging_count": emerging_count,
            "body_count": body_count,
            "used_today_count": used_today_count,
            "partial": partial,
        },
        interpretation={
            "header_summary": header_summary,
            "strongest_subtitle": "The clearest repeats in your history so far.",
            "strongest_empty": "No clear patterns yet. Keep logging to help this section fill in.",
            "emerging_subtitle": "Possible repeats that still need more overlap before they feel reliable.",
            "emerging_empty": "Nothing is clearly emerging yet. More overlap will help this section fill in.",
            "emerging_pending": "Loading the rest of your pattern history.",
            "body_subtitle": "Wearable-based patterns appear here when the overlap is strong enough.",
            "body_empty": "No body-signal patterns are standing out yet.",
            "body_pending": "Checking wearable patterns now.",
        },
        actions={
            "primary": [
                SemanticAction(
                    key="keep_logging",
                    priority=1,
                    reason="pattern_tracking",
                    label="Keep logging symptoms and body context so weak patterns can either sharpen or fall away.",
                ).__dict__
            ],
            "secondary": [],
        },
        guardrails=SemanticGuardrails(
            confidence_overall="moderate" if strongest_count > 0 else ("low" if emerging_count > 0 else "low"),
            claim_strength="may_notice" if strongest_count > 0 else "observe_only",
            evidence_basis=["personal_pattern_history"],
            max_urgency="watch" if used_today_count > 0 else ("notable" if strongest_count > 0 else "quiet"),
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="short",
            preferred_detail_sections=["overview", "strongest", "emerging", "body_signals"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )
