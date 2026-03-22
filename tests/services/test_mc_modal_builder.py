import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.mc_modals.modal_builder import build_earthscope_summary, build_modal_models


def test_build_modal_models_returns_gauge_and_driver_models() -> None:
    drivers = [
        {
            "key": "pressure",
            "label": "Pressure Swing",
            "severity": "high",
            "state": "High",
            "value": -12.4,
            "unit": "hPa",
            "display": "Pressure Swing: High (delta24h -12.4 hPa)",
        },
        {
            "key": "sw",
            "label": "Solar Wind",
            "severity": "elevated",
            "state": "Elevated",
            "value": 602.0,
            "unit": "km/s",
            "display": "Solar Wind: Elevated (602 km/s)",
        },
    ]

    payload = build_modal_models(
        day=date(2026, 2, 27),
        gauges={"pain": 82, "sleep": 77, "health_status": 64},
        gauges_meta={
            "pain": {"zone": "high", "label": "Flare"},
            "sleep": {"zone": "elevated", "label": "Disrupted"},
            "health_status": {"zone": "elevated", "label": "Moderate strain"},
        },
        gauge_labels={"pain": "Pain", "sleep": "Sleep", "health_status": "Health Status"},
        drivers=drivers,
    )

    assert "gauges" in payload
    assert "drivers" in payload
    assert payload["gauges"]["pain"]["title"] == "Pain \u2014 Flare"
    assert payload["gauges"]["pain"]["cta"]["action"] == "open_symptom_log"
    assert payload["gauges"]["pain"]["quick_log"]["default_severity"] == 5
    assert payload["drivers"]["pressure"]["title"] == "Pressure Swing \u2014 High"
    assert payload["drivers"]["pressure"]["cta"]["prefill"]
    assert payload["drivers"]["pressure"]["quick_log"]["default_severity"] == 5


def test_pressure_modal_personalizes_for_migraine_history() -> None:
    payload = build_modal_models(
        day=date(2026, 2, 27),
        gauges={"pain": 82},
        gauges_meta={"pain": {"zone": "high", "label": "Flare"}},
        gauge_labels={"pain": "Pain"},
        drivers=[
            {
                "key": "pressure",
                "label": "Pressure Swing",
                "severity": "high",
                "state": "High",
                "value": -10.4,
                "unit": "hPa",
            }
        ],
        user_tags=["migraine_history"],
    )

    pressure = payload["drivers"]["pressure"]
    assert pressure["quick_log"]["options"][0]["code"] == "HEADACHE"
    assert pressure["quick_log"]["options"][1]["code"] == "SINUS_PRESSURE"
    assert pressure["quick_log"]["options"][2]["code"] == "LIGHT_SENSITIVITY"
    assert "head" in pressure["what_you_may_notice"][0].lower()


def test_aqi_modal_personalizes_for_allergies() -> None:
    payload = build_modal_models(
        day=date(2026, 2, 27),
        gauges={"energy": 68},
        gauges_meta={"energy": {"zone": "elevated", "label": "Variable"}},
        gauge_labels={"energy": "Energy"},
        drivers=[
            {
                "key": "aqi",
                "label": "AQI",
                "severity": "high",
                "state": "High",
                "value": 118.0,
                "unit": "AQI",
            }
        ],
        user_tags=["allergies_sinus"],
    )

    aqi = payload["drivers"]["aqi"]
    assert [item["code"] for item in aqi["quick_log"]["options"]] == [
        "SINUS_PRESSURE",
        "BRAIN_FOG",
        "HEADACHE",
    ]
    assert "sinus" in aqi["what_you_may_notice"][0].lower()


def test_allergen_modal_personalizes_for_allergies() -> None:
    payload = build_modal_models(
        day=date(2026, 2, 27),
        gauges={"energy": 68},
        gauges_meta={"energy": {"zone": "elevated", "label": "Variable"}},
        gauge_labels={"energy": "Energy"},
        drivers=[
            {
                "key": "allergens",
                "label": "Allergens",
                "severity": "high",
                "state": "High",
                "value": 4.0,
                "unit": "index",
            }
        ],
        user_tags=["allergies_sinus"],
    )

    allergens = payload["drivers"]["allergens"]
    assert [item["code"] for item in allergens["quick_log"]["options"]] == [
        "SINUS_PRESSURE",
        "HEADACHE",
        "BRAIN_FOG",
    ]
    assert "sinus" in allergens["what_you_may_notice"][0].lower()


def test_solar_wind_modal_personalizes_for_autonomic_context() -> None:
    payload = build_modal_models(
        day=date(2026, 2, 27),
        gauges={"heart": 61},
        gauges_meta={"heart": {"zone": "elevated", "label": "Elevated"}},
        gauge_labels={"heart": "Heart"},
        drivers=[
            {
                "key": "sw",
                "label": "Solar Wind",
                "severity": "elevated",
                "state": "Elevated",
                "value": 612.0,
                "unit": "km/s",
            }
        ],
        user_tags=["pots_dysautonomia"],
    )

    sw = payload["drivers"]["sw"]
    assert [item["code"] for item in sw["quick_log"]["options"]] == [
        "PALPITATIONS",
        "WIRED",
        "DRAINED",
    ]
    assert "palpitations" in sw["what_you_may_notice"][0].lower()


def test_build_earthscope_summary_mentions_top_drivers_and_gauges() -> None:
    summary = build_earthscope_summary(
        user_id="user-123",
        day=date(2026, 2, 27),
        gauges={"pain": 88, "sleep": 74, "focus": 42},
        gauges_meta={
            "pain": {"zone": "high", "label": "Flare"},
            "sleep": {"zone": "elevated", "label": "Disrupted"},
            "focus": {"zone": "mild", "label": "Patchy"},
        },
        gauge_labels={"pain": "Pain", "sleep": "Sleep", "focus": "Focus"},
        drivers=[
            {"key": "pressure", "label": "Pressure Swing", "severity": "high", "state": "High"},
            {"key": "sw", "label": "Solar Wind", "severity": "elevated", "state": "Elevated"},
        ],
        user_tags=["fibromyalgia"],
    )

    assert "Pressure Swing" in summary
    assert "right now" in summary.lower()
    assert "patterns to watch, not certainties" in summary.lower()
    assert "today" not in summary.lower()
