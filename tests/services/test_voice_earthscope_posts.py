import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.voice.earthscope_posts import (
    build_member_earthscope_semantic,
    build_public_earthscope_semantic,
    render_member_earthscope_post,
    render_public_earthscope_post,
)


def test_public_earthscope_post_renderer_builds_playful_public_bundle() -> None:
    payload = build_public_earthscope_semantic(
        day=date(2026, 3, 30),
        ctx={
            "day": "2026-03-30",
            "platform": "default",
            "kp_now": 4.8,
            "kp_max_24h": 6.2,
            "bz_min": -9.4,
            "solar_wind_kms": 655.0,
            "flares_24h": 3,
            "cmes_24h": 1,
            "schumann_value_hz": 7.91,
            "aurora_headline": "G2 aurora possible",
            "quakes_count": 2,
            "severe_summary": "Regional severe-weather alerts active",
            "first_person": True,
        },
    )

    rendered = render_public_earthscope_post(payload)

    assert payload.kind == "earthscope_public_post"
    assert rendered["title"] == "Geomagnetic Storm Watch"
    assert "Kp 6.2" in rendered["caption"]
    assert "SW 655 km/s" in rendered["caption"]
    assert rendered["snapshot"].startswith("- Kp now:")
    assert rendered["qualitative_snapshot"].startswith("Space Weather Snapshot")
    assert "Drivers:" in rendered["qualitative_snapshot"]
    assert "Gaia Eyes — Daily EarthScope" in rendered["body_markdown"]
    assert rendered["hashtags"].startswith("#GaiaEyes")


def test_member_earthscope_post_renderer_preserves_seeded_sections() -> None:
    payload = build_member_earthscope_semantic(
        day=date(2026, 3, 30),
        health_status=54,
        highlights=[{"key": "pain", "label": "Pain", "value": 68}],
        drivers=[
            {"key": "solar_wind", "label": "Solar Wind", "severity": "high", "state": "High"},
            {"key": "aqi", "label": "Air Quality", "severity": "moderate", "state": "Moderate"},
        ],
        driver_lines=["Solar wind: High (610 km/s)", "AQI: Moderate (59)"],
        ranked_symptoms=[{"phrase": "fatigue"}],
        condition_note="This is still a possibility, not a guarantee.",
        actions=["hydrate steadily", "pace heavy tasks"],
        disclaimer="Context only.",
        seed_now_text="Solar Wind is setting the pace right now. Body load looks moderate right now.",
        seed_summary="Based on the current drivers and your gauges, the strongest possibilities right now are fatigue.",
        title="Your EarthScope",
        caption=None,
    )

    rendered = render_member_earthscope_post(payload)

    assert payload.kind == "earthscope_member_post"
    assert rendered["title"] == "Your EarthScope"
    assert rendered["caption"] is None
    assert "## Now" in rendered["body_markdown"]
    assert "## Current Drivers" in rendered["body_markdown"]
    assert "## What You May Feel" in rendered["body_markdown"]
    assert "## Supportive Actions" in rendered["body_markdown"]
    assert "Solar Wind is setting the pace right now." in rendered["body_markdown"]
    assert "strongest possibilities right now are fatigue" in rendered["body_markdown"]
