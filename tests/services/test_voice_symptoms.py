import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.voice.symptoms import build_current_symptoms_semantic


def test_build_current_symptoms_semantic_with_active_items() -> None:
    payload = build_current_symptoms_semantic(
        day=date(2026, 4, 1),
        window_hours=12,
        summary={
            "active_count": 2,
            "improving_count": 0,
            "worse_count": 1,
        },
        items=[
            {"label": "Headache"},
            {"label": "Fatigue"},
        ],
        contributing_drivers=[
            {"label": "Pressure Swing"},
            {"label": "Air Quality"},
        ],
        pattern_context=[
            {"text": "Pressure swings have appeared with headache before."},
        ],
        follow_up_settings={
            "enabled": True,
            "notification_family_enabled": False,
            "push_enabled": True,
        },
    )

    rendered = payload.to_dict()
    assert rendered["kind"] == "current_symptoms_snapshot"
    assert rendered["facts"]["active_labels"] == ["Headache", "Fatigue"]
    assert "2 symptoms are active right now." in rendered["interpretation"]["header_summary"]
    assert "Pressure Swing" in rendered["interpretation"]["header_summary"] or "one looks worse" in rendered["interpretation"]["header_summary"]
    assert "Headache and Fatigue" in rendered["interpretation"]["active_summary"]
    assert rendered["guardrails"]["max_urgency"] == "watch"
    assert rendered["guardrails"]["claim_strength"] == "may_notice"


def test_build_current_symptoms_semantic_with_no_active_items() -> None:
    payload = build_current_symptoms_semantic(
        day=date(2026, 4, 1),
        window_hours=12,
        summary={
            "active_count": 0,
            "improving_count": 0,
            "worse_count": 0,
        },
        items=[],
        contributing_drivers=[],
        pattern_context=[],
        follow_up_settings={
            "enabled": False,
            "notification_family_enabled": False,
            "push_enabled": False,
        },
    )

    rendered = payload.to_dict()
    assert rendered["interpretation"]["header_summary"] == "Nothing looks active right now. Log anything new here if it starts."
    assert rendered["interpretation"]["empty_state"]
    assert rendered["interpretation"]["contributing_empty"]
    assert rendered["interpretation"]["pattern_empty"]
    assert rendered["guardrails"]["claim_strength"] == "observe_only"
    assert rendered["guardrails"]["max_urgency"] == "quiet"
