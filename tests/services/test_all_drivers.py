from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

from services.drivers.all_drivers import _seed_space_context_drivers, compose_all_drivers_payload
from services.drivers.driver_normalize import normalize_environmental_drivers


def test_compose_all_drivers_payload_keeps_high_signal_and_links_patterns() -> None:
    payload = compose_all_drivers_payload(
        day=date(2026, 3, 26),
        seed_drivers=[
            {
                "key": "sw",
                "label": "Solar Wind",
                "severity": "high",
                "state": "Strong",
                "signal_strength": 0.96,
                "force_visible": True,
                "show_driver": True,
                "reading": "720 km/s",
                "short_reason": "Solar wind speed is elevated right now.",
                "active_now_text": "Solar wind speed is running near 720 km/s right now.",
                "what_it_is": "The speed and pressure of charged particles flowing from the Sun.",
                "science_note": "Higher solar-wind speed can support more noticeable geomagnetic coupling when conditions line up.",
                "aliases": ["sw", "solar_wind"],
                "category": "space",
                "category_label": "Space",
            },
            {
                "key": "pressure",
                "label": "Pressure Swing",
                "severity": "watch",
                "state": "Watch",
                "signal_strength": 0.74,
                "force_visible": False,
                "show_driver": True,
                "reading": "-8.4 hPa / 12h",
                "short_reason": "Pressure moved sharply over the last 12 hours.",
                "active_now_text": "Pressure is running at a -8.4 hPa 12-hour change right now.",
                "what_it_is": "Rapid barometric changes in your local weather.",
                "science_note": "Fast pressure changes are a common weather-context variable in symptom tracking.",
                "aliases": ["pressure"],
                "category": "local",
                "category_label": "Local",
            },
        ],
        pattern_rows=[
            {
                "signal_key": "solar_wind_exposed",
                "outcome_key": "fatigue_day",
                "confidence": "Strong",
                "relative_lift": 2.4,
                "lag_hours": 12,
                "last_seen_at": datetime(2026, 3, 24, 16, 0, tzinfo=UTC),
            },
            {
                "signal_key": "pressure_swing_exposed",
                "outcome_key": "headache_day",
                "confidence": "Moderate",
                "relative_lift": 1.9,
                "lag_hours": 0,
                "last_seen_at": datetime(2026, 3, 25, 9, 0, tzinfo=UTC),
            },
        ],
        user_tags=[],
        recent_outcomes={"counts": {"fatigue_day": 1, "headache_day": 0}},
        current_symptom_rows=[
            {"symptom_code": "fatigue", "label": "Fatigue"},
            {"symptom_code": "headache", "label": "Headache"},
        ],
        health_status_explainer={},
        local_payload={},
        outlook_payload={
            "next_24h": {
                "top_drivers": [
                    {
                        "key": "solar_wind",
                        "detail": "SWPC is still flagging a solar-wind watch in the near-term window.",
                    }
                ]
            }
        },
    )

    assert payload["summary"]["active_driver_count"] == 2
    assert payload["summary"]["strongest_category"] == "Space"
    assert [item["key"] for item in payload["drivers"]] == ["solar_wind", "pressure"]
    assert payload["voice_semantics"]["driver_summary"]["kind"] == "driver_summary"

    solar_wind = payload["drivers"][0]
    assert solar_wind["role"] == "leading"
    assert solar_wind["pattern_status"] == "strong"
    assert solar_wind["current_symptoms"] == ["Fatigue"]
    assert "Fatigue" in solar_wind["historical_symptoms"]
    assert solar_wind["outlook_relevance"] == "24h"
    assert "solar-wind watch" in solar_wind["outlook_summary"].lower()
    assert solar_wind["voice_semantic"]["kind"] == "driver_reason"
    assert solar_wind["voice_semantic"]["interpretation"]["seed_personal_reason"]

    pressure = payload["drivers"][1]
    assert pressure["role"] == "supporting"
    assert pressure["pattern_status"] == "moderate"
    assert pressure["current_symptoms"] == ["Headache"]
    assert pressure["state"] == "watch"


def test_normalize_environmental_drivers_skips_quiet_local_baselines() -> None:
    drivers = normalize_environmental_drivers(
        active_states=[],
        local_payload={
            "weather": {
                "baro_delta_24h_hpa": -2.0,
                "temp_delta_24h_c": -0.6,
            },
            "air": {
                "aqi": 47,
            },
        },
        alerts_json=[],
        limit=6,
    )

    assert drivers == []


def test_seed_space_context_drivers_adds_southward_bz() -> None:
    rows = _seed_space_context_drivers(
        {
            "daily": {
                "bz_now": -7.8,
                "bz_min": -9.1,
                "updated_at": "2026-04-25T03:24:00+00:00",
            }
        }
    )

    bz = next(row for row in rows if row["key"] == "bz")
    assert bz["label"] == "Bz Coupling"
    assert bz["severity"] == "watch"
    assert bz["state"] == "Watch"
    assert bz["value"] == -7.8
    assert bz["reading"] == "-7.8 nT"
    assert "Southward Bz" in bz["short_reason"]
