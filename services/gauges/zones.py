from __future__ import annotations

from typing import Any, Dict, List, Optional


_CALIBRATING_LABEL = "Calibrating"


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _normalize_zones(zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for zone in zones or []:
        if not isinstance(zone, dict):
            continue
        key = str(zone.get("key") or "").strip()
        minimum = _as_float(zone.get("min"))
        maximum = _as_float(zone.get("max"))
        if not key or minimum is None or maximum is None:
            continue
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        normalized.append(
            {
                "key": key,
                "min": int(round(minimum)),
                "max": int(round(maximum)),
            }
        )
    normalized.sort(key=lambda item: (item["min"], item["max"]))
    return normalized


def _find_gauge_definition(gauge_key: str, definition_base: Dict[str, Any]) -> Dict[str, Any]:
    for gauge in definition_base.get("gauges") or []:
        if isinstance(gauge, dict) and gauge.get("key") == gauge_key:
            return gauge
    health_output = (definition_base.get("health_metrics_overlay") or {}).get("output_gauge")
    if isinstance(health_output, dict) and health_output.get("key") == gauge_key:
        return health_output
    return {}


def zone_for_value(value: int, zones: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = _normalize_zones(zones)
    numeric = _as_float(value)
    if numeric is None or not normalized:
        return {}
    for zone in normalized:
        if zone["min"] <= numeric <= zone["max"]:
            return zone
    if numeric < normalized[0]["min"]:
        return normalized[0]
    return normalized[-1]


def label_for_gauge(gauge_key: str, zone_key: str, definition_base: Dict[str, Any]) -> str:
    zone = str(zone_key or "").strip()
    if not zone:
        return ""
    gauge = _find_gauge_definition(gauge_key, definition_base)
    labels = gauge.get("zone_labels") if isinstance(gauge, dict) else None
    if isinstance(labels, dict):
        value = labels.get(zone)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return zone.replace("_", " ").title()


def decorate_gauge(gauge_key: str, value: Any, definition_base: Dict[str, Any]) -> Dict[str, Any]:
    numeric = _as_float(value)
    if numeric is None:
        return {
            "value": None,
            "zone_key": None,
            "zone_label": _CALIBRATING_LABEL,
        }

    gauge_zones = (definition_base.get("gauge_zones") or {}).get("default") or []
    zone = zone_for_value(int(round(numeric)), gauge_zones)
    zone_key = str(zone.get("key") or "").strip() or None
    zone_label = label_for_gauge(gauge_key, zone_key or "", definition_base) if zone_key else ""

    return {
        "value": numeric,
        "zone_key": zone_key,
        "zone_label": zone_label,
    }
