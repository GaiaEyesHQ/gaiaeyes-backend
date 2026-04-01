from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from .semantic import SemanticAction, SemanticGuardrails, SemanticPayload, SemanticRenderHints


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_text(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _join_labels(labels: Sequence[str]) -> str:
    values = [item for item in labels if item]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _header_summary(
    *,
    active_labels: Sequence[str],
    contributing_driver_labels: Sequence[str],
    pattern_texts: Sequence[str],
    worse_count: int,
) -> str:
    if not active_labels:
        return "Nothing looks active right now. Log anything new here if it starts."

    active_count = len(active_labels)
    summary = f"{active_count} symptom{' is' if active_count == 1 else 's are'} active right now."
    if worse_count > 0:
        summary += " At least one looks worse and is worth another check-in."
    elif contributing_driver_labels:
        summary += f" {_join_labels(contributing_driver_labels[:2])} look closest to this window."
    elif pattern_texts:
        summary += " Your log also has a repeat pattern worth watching here."
    else:
        summary += " Keep the active list current as things shift."
    return summary


def _active_summary(
    *,
    active_labels: Sequence[str],
    worse_count: int,
    improving_count: int,
    follow_up_enabled: bool,
) -> str:
    if not active_labels:
        return "No symptoms are active right now."

    preview_labels = list(active_labels)[:2]
    label_preview = _join_labels(preview_labels)
    label_subject = label_preview or "The active symptoms"
    subject_plural = len(preview_labels) != 1
    if worse_count > 0:
        verb = "need" if subject_plural else "needs"
        pronoun = "they are" if subject_plural else "it is"
        summary = f"{label_subject} {verb} a fresh update if {pronoun} still ramping up."
    elif improving_count > 0:
        verb = "may be" if subject_plural else "may be"
        summary = f"{label_subject} {verb} settling, so it helps to mark what is improving."
    else:
        verb = "are" if subject_plural else "is"
        summary = f"{label_subject} {verb} the main {'items' if subject_plural else 'item'} to keep updated right now."

    if follow_up_enabled:
        summary += " Follow-up check-ins can keep that timeline current."
    return summary


def _follow_up_summary(*, active_count: int, follow_up_enabled: bool, push_enabled: bool) -> str:
    if follow_up_enabled and push_enabled:
        return "Follow-up reminders are on, so you can mark symptoms as ongoing, improving, worse, or resolved."
    if follow_up_enabled:
        return "Follow-up check-ins are on here. Turn on push if you want nudges outside this screen."
    if active_count > 0:
        return "Optional follow-up check-ins can help keep these symptom updates current."
    return "Follow-up check-ins stay available when you want reminders after a symptom is logged."


def build_current_symptoms_semantic(
    *,
    day: date,
    window_hours: int,
    summary: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    contributing_drivers: Sequence[Mapping[str, Any]],
    pattern_context: Sequence[Mapping[str, Any]],
    follow_up_settings: Mapping[str, Any],
) -> SemanticPayload:
    active_labels = _unique_text(item.get("label") for item in items if isinstance(item, Mapping))
    contributing_driver_labels = _unique_text(
        item.get("label") or item.get("key")
        for item in contributing_drivers
        if isinstance(item, Mapping)
    )
    pattern_texts = _unique_text(
        item.get("text") or item.get("outcome") or item.get("signal")
        for item in pattern_context
        if isinstance(item, Mapping)
    )

    active_count = int(summary.get("active_count") or 0)
    improving_count = int(summary.get("improving_count") or 0)
    worse_count = int(summary.get("worse_count") or 0)
    follow_up_enabled = bool(follow_up_settings.get("enabled") or follow_up_settings.get("notification_family_enabled"))
    push_enabled = bool(follow_up_settings.get("push_enabled"))

    confidence = "low"
    if active_count > 0 and (contributing_driver_labels or pattern_texts):
        confidence = "moderate"
    if active_count > 1 and contributing_driver_labels and pattern_texts:
        confidence = "high"

    actions: list[SemanticAction] = []
    if active_count > 0:
        actions.append(
            SemanticAction(
                key="update_states",
                priority=1,
                reason="current_tracking",
                label="Update a symptom when it becomes ongoing, improving, worse, or resolved",
            )
        )
    else:
        actions.append(
            SemanticAction(
                key="log_next_symptom",
                priority=1,
                reason="capture_new_signal",
                label="Log anything new here when it starts so pattern context can build",
            )
        )
    actions.append(
        SemanticAction(
            key="follow_up",
            priority=2,
            reason="follow_up" if follow_up_enabled else "optional_follow_up",
            label=_follow_up_summary(
                active_count=active_count,
                follow_up_enabled=follow_up_enabled,
                push_enabled=push_enabled,
            ),
        )
    )

    return SemanticPayload(
        schema_version="1.0",
        kind="current_symptoms_snapshot",
        date=day.isoformat(),
        user_context={
            "audience": "member",
            "channel": "app_detail",
            "window_hours": window_hours,
        },
        facts={
            "active_count": active_count,
            "active_labels": active_labels,
            "contributing_driver_labels": contributing_driver_labels,
            "pattern_texts": pattern_texts,
            "follow_up_enabled": follow_up_enabled,
        },
        interpretation={
            "header_summary": _header_summary(
                active_labels=active_labels,
                contributing_driver_labels=contributing_driver_labels,
                pattern_texts=pattern_texts,
                worse_count=worse_count,
            ),
            "active_summary": _active_summary(
                active_labels=active_labels,
                worse_count=worse_count,
                improving_count=improving_count,
                follow_up_enabled=follow_up_enabled,
            ),
            "empty_state": "Nothing is active right now. Log anything new here so future patterns have something to compare.",
            "contributing_empty": "No nearby drivers are standing out around this symptom window yet.",
            "pattern_empty": "No strong repeat pattern is attached yet. Keep logging changes so this section can sharpen.",
            "follow_up_summary": _follow_up_summary(
                active_count=active_count,
                follow_up_enabled=follow_up_enabled,
                push_enabled=push_enabled,
            ),
        },
        actions={
            "primary": [item.__dict__ for item in actions],
            "secondary": [],
        },
        guardrails=SemanticGuardrails(
            confidence_overall=confidence,
            claim_strength="may_notice" if pattern_texts or contributing_driver_labels else "observe_only",
            evidence_basis=[
                basis
                for basis in (
                    "current_symptom_window" if active_count else None,
                    "current_driver_mix" if contributing_driver_labels else None,
                    "personal_pattern_history" if pattern_texts else None,
                    "symptom_follow_up" if follow_up_enabled else None,
                )
                if basis
            ],
            max_urgency="watch" if worse_count > 0 else ("notable" if active_count > 0 else "quiet"),
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="short",
            preferred_detail_sections=["active_now", "contributing_signals", "patterns", "follow_up"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )
