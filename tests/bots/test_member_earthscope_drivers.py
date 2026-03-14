import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SUPABASE_DB_URL", "postgresql://localhost/test")
fake_openai = types.ModuleType("openai")


class _FakeOpenAI:  # pragma: no cover - test shim
    pass


fake_openai.OpenAI = _FakeOpenAI
sys.modules.setdefault("openai", fake_openai)

from bots.earthscope_post.member_earthscope_generate import (
    _active_state_lines,
    _observed_driver_lines,
    _render_member_post,
)


def test_active_state_lines_merges_pressure_solar_and_aqi() -> None:
    active_states = [
        {"signal_key": "earthweather.pressure_swing_12h", "state": "moderate", "value": 7.2},
        {"signal_key": "earthweather.pressure_swing_24h_big", "state": "high", "value": 12.1},
        {"signal_key": "spaceweather.sw_speed", "state": "elevated", "value": 550.0},
        {"signal_key": "spaceweather.sw_speed", "state": "high", "value": 610.0},
        {"signal_key": "earthweather.air_quality", "state": "moderate", "value": 59.0},
    ]

    lines = _active_state_lines(active_states)

    assert "Pressure swing: High (12h, 24h) (Δ24h +12.1 hPa)" in lines
    assert "Solar wind: High (610 km/s)" in lines
    assert "AQI: Moderate (59)" in lines


def test_observed_driver_lines_dedupes_alert_repeats() -> None:
    active_states = [
        {"signal_key": "earthweather.pressure_swing_12h", "state": "high", "value": 10.5},
        {"signal_key": "earthweather.pressure_swing_24h_big", "state": "high", "value": 12.0},
    ]
    alerts = [
        {"title": "Pressure swing", "severity": "high"},
        {"title": "Pressure swing (24h)", "severity": "high"},
    ]

    lines = _observed_driver_lines(active_states, alerts, local_payload={})

    pressure_lines = [line for line in lines if "Pressure swing" in line]
    assert pressure_lines == ["Pressure swing: High (12h, 24h) (Δ24h +12.0 hPa)"]


def test_render_member_post_uses_now_headings_and_live_tone() -> None:
    rendered = _render_member_post(
        "user-123",
        "2026-03-13T20:45:00+00:00",
        {
            "gauges": [
                {"key": "pain", "label": "Pain"},
                {"key": "energy", "label": "Energy"},
                {"key": "health_status", "label": "Health Status"},
            ],
            "normalization": {"alert_thresholds": {"info": 40, "watch": 70, "high": 85}},
            "global_disclaimer": "Self-reported context only.",
        },
        {
            "day": "2026-03-13",
            "pain": 52,
            "energy": 31,
            "health_status": 22,
            "alerts_json": [],
        },
        [
            {"signal_key": "spaceweather.sw_speed", "state": "elevated", "value": 615.0},
            {"signal_key": "earthweather.air_quality", "state": "moderate", "value": 61.0},
        ],
        {},
        [],
        {},
        None,
    )

    body = rendered["body_markdown"]
    assert "## Now" in body
    assert "## Current Drivers" in body
    assert "## What You May Feel" in body
    assert "## Supportive Actions" in body
    assert "Today’s Check-in" not in body
    assert "Summary Note" not in body
    assert "Today" not in rendered["caption"]
