import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.voice.outlook import build_user_outlook_overview_semantic, build_user_outlook_window_semantic


def test_build_user_outlook_window_semantic_tracks_domains_and_support() -> None:
    payload = build_user_outlook_window_semantic(
        day=date(2026, 3, 24),
        window_hours=24,
        top_drivers=[
            {
                "key": "pressure",
                "label": "Pressure swing",
                "severity": "watch",
                "detail": "Pressure may swing more than usual into tomorrow.",
            }
        ],
        likely_domains=[{"key": "pain", "label": "Pain"}, {"key": "sleep", "label": "Sleep"}],
        summary="Pressure may swing more than usual into tomorrow.",
        support_line="Keep pacing and hydration steadier than usual.",
    ).to_dict()

    assert payload["kind"] == "user_outlook_window"
    assert payload["facts"]["window_hours"] == 24
    assert "pressure may swing" in payload["interpretation"]["header_summary"].lower()
    assert "pain and sleep" in payload["interpretation"]["domains_summary"].lower()
    assert payload["interpretation"]["support_summary"] == "Keep pacing and hydration steadier than usual."


def test_build_user_outlook_overview_semantic_handles_missing_location() -> None:
    payload = build_user_outlook_overview_semantic(
        day=date(2026, 3, 24),
        available_windows=[],
        forecast_data_ready={
            "location_found": False,
            "local_forecast_daily": False,
            "space_forecast_daily": True,
        },
        windows=[],
    ).to_dict()

    assert payload["kind"] == "user_outlook_overview"
    assert payload["facts"]["location_found"] is False
    assert payload["interpretation"]["header_summary"] == "Add location to unlock the local side of your personal outlook."
    assert payload["interpretation"]["empty_state"].startswith("No outlook yet. Add your location")
    assert payload["guardrails"]["claim_strength"] == "observe_only"
