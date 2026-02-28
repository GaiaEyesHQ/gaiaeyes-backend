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
    assert payload["drivers"]["pressure"]["title"] == "Pressure Swing \u2014 High"
    assert payload["drivers"]["pressure"]["cta"]["prefill"]


def test_build_earthscope_summary_mentions_top_drivers_and_gauges() -> None:
    summary = build_earthscope_summary(
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
    )

    assert "Pressure Swing" in summary
    assert "Pain" in summary
    assert "Tap highlighted gauges or drivers" in summary
