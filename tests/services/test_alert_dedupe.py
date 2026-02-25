import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gauges.alerts import dedupe_alert_pills


def test_alert_dedupe_keeps_highest_severity_per_family() -> None:
    alerts = [
        {"key": "alert.pressure_swing", "severity": "watch", "triggered_by": [{"signal_key": "a", "state": "watch"}]},
        {"key": "alert.pressure_swing_24h", "severity": "high", "triggered_by": [{"signal_key": "b", "state": "high"}]},
        {"key": "alert.solar_wind_speed", "severity": "watch"},
        {"key": "alert.geomagnetic_active", "severity": "watch"},
        {"key": "alert.bz_coupling", "severity": "high"},
    ]

    deduped = dedupe_alert_pills(alerts)
    keys = {item.get("key") for item in deduped}

    assert "alert.pressure_swing_24h" in keys
    assert "alert.pressure_swing" not in keys
    assert "alert.bz_coupling" in keys
    assert "alert.geomagnetic_active" not in keys
    assert "alert.solar_wind_speed" in keys


def test_alert_dedupe_prefers_more_specific_when_severity_ties() -> None:
    alerts = [
        {"key": "alert.air_quality", "severity": "watch", "triggered_by": []},
        {
            "key": "alert.air_quality",
            "severity": "watch",
            "triggered_by": [{"signal_key": "earthweather.air_quality", "state": "usg"}],
        },
    ]
    deduped = dedupe_alert_pills(alerts)
    assert len(deduped) == 1
    assert deduped[0].get("triggered_by")
