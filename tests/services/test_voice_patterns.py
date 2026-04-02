import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.voice.patterns import build_pattern_card_semantic, build_patterns_overview_semantic


def test_build_pattern_card_semantic_marks_used_today_context() -> None:
    payload = build_pattern_card_semantic(
        day=date(2026, 3, 22),
        row={
            "signal_key": "pressure_swing_exposed",
            "signal": "Pressure swings",
            "outcome_key": "pain_flare_day",
            "outcome": "Pain flares",
            "explanation": "Pain flares appear more often for you when pressure swings exceed 6 hPa.",
            "confidence": "Strong",
            "sample_size": 14,
            "lag_hours": 24,
            "lag_label": "next day",
            "relative_lift": 2.4,
            "exposed_rate": 0.57,
            "unexposed_rate": 0.23,
        },
        used_today=True,
    )

    rendered = payload.to_dict()
    assert rendered["kind"] == "personal_pattern_card"
    assert rendered["facts"]["used_today"] is True
    assert "pressure swings" in rendered["interpretation"]["header_summary"].lower()
    assert "exposed days" in rendered["interpretation"]["evidence_summary"].lower()
    assert rendered["guardrails"]["claim_strength"] == "strong_repeat_pattern"


def test_build_patterns_overview_semantic_summarizes_sections() -> None:
    payload = build_patterns_overview_semantic(
        day=date(2026, 3, 22),
        strongest_count=2,
        emerging_count=1,
        body_count=0,
        used_today_count=1,
        partial=False,
    ).to_dict()

    assert payload["kind"] == "patterns_overview"
    assert "2 clearer patterns" in payload["interpretation"]["header_summary"]
    assert "active in today's signal mix" in payload["interpretation"]["header_summary"]
    assert payload["interpretation"]["emerging_subtitle"].startswith("Possible repeats")
    assert payload["guardrails"]["max_urgency"] == "watch"


def test_build_pattern_card_semantic_reads_router_camel_case_fields() -> None:
    payload = build_pattern_card_semantic(
        day=date(2026, 3, 22),
        row={
            "signalKey": "aqi_moderate_plus_exposed",
            "signal": "Air quality",
            "outcomeKey": "fatigue_day",
            "outcome": "Fatigue",
            "explanation": "Fatigue are more common for you on moderate-or-higher AQI days.",
            "confidence": "Strong",
            "sampleSize": 36,
            "lagHours": 24,
            "lagLabel": "next day",
            "relativeLift": 4.6,
            "exposedRate": 0.31,
            "unexposedRate": 0.07,
            "lastSeenAt": "2026-03-27T18:00:00+00:00",
        },
        used_today=False,
    ).to_dict()

    assert (
        payload["interpretation"]["evidence_summary"]
        == "4.6x more common when exposed • 36 exposed days • Lag next day"
    )
    assert (
        payload["interpretation"]["baseline_summary"]
        == "When exposed: 31% • When not exposed: 7% • Last seen: Mar 27, 2026"
    )
