from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from .semantic import SemanticAction, SemanticGuardrails, SemanticPayload, SemanticRenderHints


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _join_labels(values: Sequence[str]) -> str:
    cleaned = [value for value in (_clean_text(item) for item in values) if value]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _confidence_for_window(top_drivers: Sequence[Mapping[str, Any]], likely_domains: Sequence[Mapping[str, Any]]) -> str:
    if top_drivers and likely_domains:
        severity = _clean_text(top_drivers[0].get("severity")).lower()
        if severity in {"high", "strong", "storm", "elevated"}:
            return "high"
        return "moderate"
    if top_drivers or likely_domains:
        return "low"
    return "low"


def build_user_outlook_window_semantic(
    *,
    day: date,
    window_hours: int,
    top_drivers: Sequence[Mapping[str, Any]],
    likely_domains: Sequence[Mapping[str, Any]],
    summary: str,
    support_line: str,
) -> SemanticPayload:
    leading_driver = dict(top_drivers[0]) if top_drivers else {}
    domain_labels = [
        _clean_text(item.get("label") or item.get("key"))
        for item in likely_domains
        if isinstance(item, Mapping)
    ]
    leading_label = _clean_text(leading_driver.get("label") or leading_driver.get("key") or "This signal")
    leading_detail = _clean_text(leading_driver.get("detail"))
    if not summary:
        if leading_detail:
            summary = leading_detail
        elif leading_label:
            summary = f"{leading_label} looks like the main signal worth watching over this window."
        else:
            summary = "No clearer short-range forecast driver stands out from the data available right now."

    domains_summary = ""
    if domain_labels:
        domains_summary = f"{_join_labels(domain_labels[:3])} may be easier to notice over this window."

    actions = []
    if leading_label:
        actions.append(
            SemanticAction(
                key="review_drivers",
                priority=1,
                reason="leading_signal",
                label=f"Open current drivers if you want to compare {leading_label.lower()} with the live state.",
            )
        )
    if support_line:
        actions.append(
            SemanticAction(
                key="support",
                priority=2,
                reason="pacing_support",
                label=support_line,
            )
        )

    confidence = _confidence_for_window(top_drivers, likely_domains)
    return SemanticPayload(
        schema_version="1.0",
        kind="user_outlook_window",
        date=day.isoformat(),
        user_context={"audience": "member", "channel": "app_outlook", "window_hours": window_hours},
        facts={
            "window_hours": window_hours,
            "leading_driver": leading_driver or None,
            "likely_domain_labels": domain_labels,
            "top_driver_count": len(top_drivers),
        },
        interpretation={
            "header_summary": summary,
            "leading_signal_summary": leading_detail or summary,
            "domains_summary": domains_summary or None,
            "support_summary": _clean_text(support_line) or None,
            "empty_state": "No clearer short-range forecast driver stands out from the data available right now.",
        },
        actions={
            "primary": [item.__dict__ for item in actions],
            "secondary": [],
        },
        guardrails=SemanticGuardrails(
            confidence_overall=confidence,
            claim_strength="may_notice" if likely_domains else "observe_only",
            evidence_basis=[
                basis
                for basis in (
                    "forecast_driver_mix" if top_drivers else None,
                    "personal_pattern_history" if likely_domains else None,
                    "current_gauges" if likely_domains else None,
                )
                if basis
            ],
            max_urgency="watch" if confidence == "high" else ("notable" if confidence == "moderate" else "quiet"),
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="short",
            preferred_detail_sections=["overview", "leading_signal", "domains", "support"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )


def build_user_outlook_overview_semantic(
    *,
    day: date,
    available_windows: Sequence[str],
    forecast_data_ready: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any] | None],
) -> SemanticPayload:
    first_window = next((dict(item) for item in windows if isinstance(item, Mapping)), {})
    location_found = bool(forecast_data_ready.get("location_found"))
    if first_window:
        header_summary = _clean_text(first_window.get("summary")) or "A near-future outlook is ready."
    elif not location_found:
        header_summary = "Add location to unlock the local side of your personal outlook."
    else:
        header_summary = "No outlook is ready yet. The forecast layers need a little more data to settle."

    availability_bits: list[str] = []
    if "next_24h" in available_windows:
        availability_bits.append("24h")
    if "next_72h" in available_windows:
        availability_bits.append("72h")
    if "next_7d" in available_windows:
        availability_bits.append("7d")
    availability_summary = (
        f"Ready windows: {', '.join(availability_bits)}"
        if availability_bits
        else "No outlook windows are ready yet."
    )

    empty_state = (
        "No outlook yet. Add your location and give forecast data a little more time."
        if not location_found
        else "No outlook yet. Forecast layers need a little more time to build a useful window."
    )

    return SemanticPayload(
        schema_version="1.0",
        kind="user_outlook_overview",
        date=day.isoformat(),
        user_context={"audience": "member", "channel": "app_outlook"},
        facts={
            "available_windows": list(available_windows),
            "location_found": location_found,
            "window_count": len(list(available_windows)),
        },
        interpretation={
            "header_summary": header_summary,
            "availability_summary": availability_summary,
            "empty_state": empty_state,
            "seven_day_pending": "The 7-day view will appear once the forecast layer is steady enough to support it.",
        },
        actions={
            "primary": [
                SemanticAction(
                    key="review_current_drivers",
                    priority=1,
                    reason="compare_live_state",
                    label="Compare this outlook with the current drivers if you want the live-state view alongside the forecast.",
                ).__dict__
            ],
            "secondary": [],
        },
        guardrails=SemanticGuardrails(
            confidence_overall="moderate" if available_windows else "low",
            claim_strength="may_notice" if available_windows else "observe_only",
            evidence_basis=["forecast_driver_mix"] + (["personal_pattern_history"] if available_windows else []),
            max_urgency="notable" if available_windows else "quiet",
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="short",
            preferred_detail_sections=["overview", "windows", "support"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )
