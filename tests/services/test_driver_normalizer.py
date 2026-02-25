import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gauges.drivers import normalize_drivers


def test_normalize_drivers_merges_pressure_solar_and_aqi() -> None:
    raw = [
        "Pressure swing (12h) is high",
        "Pressure swing (24h) is high (Δ24h -13.2 hPa)",
        "Solar wind speed is high (600 km/s)",
        "Air quality is moderate (AQI 59)",
    ]
    compact = normalize_drivers(raw)

    assert compact[0] == "Pressure swing: High (12h, 24h) (Δ24h -13.2 hPa)"
    assert "Solar wind: High (600 km/s)" in compact
    assert "AQI: Moderate (59)" in compact


def test_normalize_drivers_dedupes_case_and_limits_to_five() -> None:
    raw = [
        "Pressure swing: High (12h)",
        "pressure swing: high (12h)",
        "Solar wind: High (610 km/s)",
        "AQI: Moderate (59)",
        "Schumann variability: Elevated (24h)",
        "Rapid pressure drop: Watch (3h)",
        "Geomagnetic: Elevated",
    ]
    compact = normalize_drivers(raw)

    assert len(compact) == 5
    assert compact.count("Pressure swing: High (12h)") == 1
