import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.voice.drivers import (
    build_driver_reason_semantic,
    build_driver_summary_semantic,
    render_driver_daily_brief,
    render_driver_reason,
)


def test_render_driver_daily_brief_uses_primary_and_supporting() -> None:
    payload = build_driver_summary_semantic(
        day=date(2026, 3, 17),
        raw_top_drivers=[{"key": "pressure", "label": "Pressure Swing"}],
        primary_driver={
            "key": "pressure",
            "label": "Pressure Swing",
            "personal_reason_short": "Pressure often matches your pain pattern.",
            "confidence": "Moderate",
        },
        supporting_drivers=[{"key": "aqi", "label": "Air Quality"}],
        today_personal_themes=[],
        override_note="",
    )

    rendered = render_driver_daily_brief(payload)
    assert rendered.startswith("Right now, pressure swing looks most relevant for you.")
    assert rendered.endswith("Air Quality is also in the mix.")


def test_render_driver_reason_prefers_seed_text() -> None:
    payload = build_driver_reason_semantic(
        day=date(2026, 3, 26),
        row={
            "key": "solar_wind",
            "label": "Solar Wind",
            "state": "strong",
            "severity": "high",
            "short_reason": "Solar wind speed is elevated right now.",
            "personal_reason": "Elevated solar wind often matches fatigue for you.",
            "pattern_status": "strong",
        },
    )

    assert render_driver_reason(payload, variant="short") == "Solar wind speed is elevated right now."
    assert render_driver_reason(payload, variant="full") == "Elevated solar wind often matches fatigue for you."
