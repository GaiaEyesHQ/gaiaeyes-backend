import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.drivers.driver_normalize import normalize_environmental_drivers


def test_normalize_environmental_drivers_dedupes_family_and_prefers_stronger() -> None:
    active_states = [
        {"signal_key": "earthweather.pressure_swing_12h", "state": "moderate", "value": -6.4},
        {"signal_key": "earthweather.pressure_drop_3h", "state": "high", "value": -5.2},
        {"signal_key": "spaceweather.sw_speed", "state": "high", "value": 622.0},
        {"signal_key": "spaceweather.kp", "state": "elevated", "value": 5.0},
    ]
    alerts = [{"key": "alert.air_quality", "severity": "watch"}]
    local_payload = {"weather": {"baro_delta_12h_hpa": -6.0}, "air": {"aqi": 119}}

    rows = normalize_environmental_drivers(
        active_states=active_states,
        local_payload=local_payload,
        alerts_json=alerts,
    )

    keys = [row["key"] for row in rows]
    assert keys.count("pressure") == 1
    pressure = next(row for row in rows if row["key"] == "pressure")
    assert pressure["severity"] == "high"
    assert pressure["state"] == "High"

    aqi = next(row for row in rows if row["key"] == "aqi")
    assert aqi["severity"] == "watch"
    assert aqi["value"] == 119.0


def test_normalize_environmental_drivers_uses_local_payload_when_no_active_signals() -> None:
    local_payload = {
        "weather": {
            "baro_delta_12h_hpa": -9.1,
            "temp_delta_24h_c": 6.2,
        },
        "air": {"aqi": 58},
    }

    rows = normalize_environmental_drivers(
        active_states=[],
        local_payload=local_payload,
        alerts_json=[],
    )

    keys = [row["key"] for row in rows]
    assert keys[0] == "pressure"
    assert set(keys) == {"pressure", "temp", "aqi"}

    pressure = rows[0]
    assert pressure["severity"] == "watch"
    assert "Pressure Swing" in pressure["display"]
