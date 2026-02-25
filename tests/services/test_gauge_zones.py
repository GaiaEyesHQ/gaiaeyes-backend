import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.definitions.load_definition_base import load_definition_base
from services.gauges.zones import decorate_gauge, label_for_gauge, zone_for_value


def _definition():
    definition, _ = load_definition_base()
    return definition


def test_zone_for_value_boundaries() -> None:
    zones = _definition()["gauge_zones"]["default"]
    assert zone_for_value(0, zones)["key"] == "low"
    assert zone_for_value(24, zones)["key"] == "low"
    assert zone_for_value(25, zones)["key"] == "mild"
    assert zone_for_value(49, zones)["key"] == "mild"
    assert zone_for_value(50, zones)["key"] == "elevated"
    assert zone_for_value(74, zones)["key"] == "elevated"
    assert zone_for_value(75, zones)["key"] == "high"
    assert zone_for_value(100, zones)["key"] == "high"


def test_label_for_gauge_reads_definition_zone_labels() -> None:
    definition = _definition()
    assert label_for_gauge("pain", "mild", definition) == "Elevated"
    assert label_for_gauge("stamina", "high", definition) == "Drained"
    assert label_for_gauge("health_status", "low", definition) == "Low strain"


def test_decorate_gauge_includes_zone_and_label() -> None:
    definition = _definition()
    decorated = decorate_gauge("health_status", 10, definition)
    assert decorated["zone_key"] == "low"
    assert decorated["zone_label"] == "Low strain"

    calibrating = decorate_gauge("sleep", None, definition)
    assert calibrating["zone_key"] is None
    assert calibrating["zone_label"] == "Calibrating"
