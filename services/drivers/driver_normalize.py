from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


_SEVERITY_RANK = {
    "high": 4,
    "watch": 3,
    "elevated": 3,
    "mild": 2,
    "low": 1,
}

_DRIVER_ORDER = {
    "pressure": 1,
    "temp": 2,
    "aqi": 3,
    "kp": 4,
    "bz": 5,
    "sw": 6,
    "schumann": 7,
}

_DRIVER_META = {
    "pressure": {"label": "Pressure Swing", "unit": "hPa"},
    "temp": {"label": "Temperature Swing", "unit": "C"},
    "aqi": {"label": "Air Quality", "unit": "AQI"},
    "kp": {"label": "Kp Index", "unit": "Kp"},
    "bz": {"label": "Bz Coupling", "unit": "nT"},
    "sw": {"label": "Solar Wind", "unit": "km/s"},
    "schumann": {"label": "Schumann", "unit": "Hz Δ"},
}

_SIGNAL_TO_DRIVER = {
    "earthweather.pressure_swing_12h": "pressure",
    "earthweather.pressure_drop_3h": "pressure",
    "earthweather.pressure_swing_24h_big": "pressure",
    "earthweather.temp_swing_24h": "temp",
    "earthweather.temp_swing_24h_big": "temp",
    "earthweather.air_quality": "aqi",
    "spaceweather.kp": "kp",
    "spaceweather.bz_coupling": "bz",
    "spaceweather.sw_speed": "sw",
    "schumann.variability_24h": "schumann",
}

_ALERT_KEY_TO_DRIVER = {
    "alert.pressure_swing": "pressure",
    "alert.pressure_drop_3h": "pressure",
    "alert.pressure_swing_24h": "pressure",
    "alert.temp_swing_24h": "temp",
    "alert.air_quality": "aqi",
    "alert.geomagnetic_active": "kp",
    "alert.bz_coupling": "bz",
    "alert.solar_wind_speed": "sw",
}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _severity_from_state(state: Any) -> str:
    token = str(state or "").strip().lower()
    if token in {"high", "very_high", "storm", "strong", "unhealthy"}:
        return "high"
    if token in {"watch", "usg"}:
        return "watch"
    if token in {"elevated", "active"}:
        return "elevated"
    if token in {"moderate", "info"}:
        return "mild"
    return "low"


def _severity_from_alert(alert: Dict[str, Any]) -> str:
    token = str(alert.get("severity") or "").strip().lower()
    if token == "high":
        return "high"
    if token == "watch":
        return "watch"
    return "mild"


def _state_title(value: str) -> str:
    key = str(value or "").strip().lower().replace("_", " ")
    if key == "usg":
        return "USG"
    return key[:1].upper() + key[1:] if key else "Low"


def _severity_title(severity: str) -> str:
    if severity == "watch":
        return "Watch"
    if severity == "elevated":
        return "Elevated"
    if severity == "high":
        return "High"
    if severity == "mild":
        return "Mild"
    return "Low"


def _normalize_local_payload(local_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(local_payload, dict):
        return {}
    if isinstance(local_payload.get("payload"), dict):
        return local_payload["payload"]
    if isinstance(local_payload.get("data"), dict):
        return local_payload["data"]
    if isinstance(local_payload.get("local"), dict):
        return local_payload["local"]
    return local_payload


def _driver_value_from_local(key: str, local_payload: Dict[str, Any]) -> Optional[float]:
    weather = local_payload.get("weather") or {}
    air = local_payload.get("air") or {}
    if key == "pressure":
        return _safe_float(
            weather.get("baro_delta_12h_hpa")
            or weather.get("pressure_delta_12h")
            or weather.get("baro_delta_24h_hpa")
            or weather.get("pressure_delta_24h_hpa")
        )
    if key == "temp":
        return _safe_float(weather.get("temp_delta_24h_c") or weather.get("temp_delta_24h"))
    if key == "aqi":
        return _safe_float(air.get("aqi"))
    return None


def _severity_from_local_value(key: str, value: Optional[float]) -> str:
    if value is None:
        return "low"
    abs_value = abs(value)
    if key == "pressure":
        if abs_value >= 12:
            return "high"
        if abs_value >= 8:
            return "watch"
        if abs_value >= 6:
            return "mild"
        return "low"
    if key == "temp":
        if abs_value >= 12:
            return "high"
        if abs_value >= 8:
            return "watch"
        if abs_value >= 6:
            return "mild"
        return "low"
    if key == "aqi":
        if value >= 151:
            return "high"
        if value >= 101:
            return "watch"
        if value >= 51:
            return "mild"
        return "low"
    return "low"


def _format_value(key: str, value: Optional[float], unit: str) -> Optional[str]:
    if value is None:
        return None
    if key == "sw":
        return f"{int(round(value, 0))} {unit}"
    if key == "aqi":
        return f"{int(round(value, 0))}"
    if key == "kp":
        return f"{value:.1f}"
    if key == "schumann":
        return f"{value:.2f} {unit}"
    if key == "temp":
        return f"{value:+.1f}\u00b0C"
    if key in {"pressure", "bz"}:
        return f"{value:+.1f} {unit}"
    return f"{value:.1f} {unit}".strip()


def _display_text(label: str, state: str, key: str, value: Optional[float], unit: str) -> str:
    formatted = _format_value(key, value, unit)
    if formatted:
        return f"{label}: {state} ({formatted})"
    return f"{label}: {state}"


def _candidate(
    key: str,
    *,
    severity: str,
    state: str,
    value: Optional[float],
) -> Dict[str, Any]:
    meta = _DRIVER_META.get(key) or {"label": key.replace("_", " ").title(), "unit": ""}
    unit = str(meta.get("unit") or "")
    label = str(meta.get("label") or key)
    rounded_value: Optional[float] = None
    if value is not None:
        if key in {"aqi", "sw"}:
            rounded_value = float(int(round(value, 0)))
        elif key == "schumann":
            rounded_value = round(value, 3)
        else:
            rounded_value = round(value, 1)

    state_title = _state_title(state) if state else _severity_title(severity)
    return {
        "key": key,
        "label": label,
        "severity": severity,
        "state": state_title,
        "value": rounded_value,
        "unit": unit,
        "display": _display_text(label, state_title, key, rounded_value, unit),
        "_rank": _SEVERITY_RANK.get(severity, 0),
        "_value_abs": abs(rounded_value) if rounded_value is not None else -1.0,
    }


def _pick_stronger(existing: Optional[Dict[str, Any]], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return incoming
    if incoming["_rank"] > existing["_rank"]:
        return incoming
    if incoming["_rank"] < existing["_rank"]:
        return existing
    if incoming["_value_abs"] > existing["_value_abs"]:
        return incoming
    return existing


def _alerts_list(alerts_json: Any) -> List[Dict[str, Any]]:
    if not isinstance(alerts_json, list):
        return []
    return [item for item in alerts_json if isinstance(item, dict)]


def normalize_environmental_drivers(
    *,
    active_states: Optional[Iterable[Dict[str, Any]]],
    local_payload: Optional[Dict[str, Any]],
    alerts_json: Any,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    normalized_local = _normalize_local_payload(local_payload)
    picked: Dict[str, Dict[str, Any]] = {}

    for state in list(active_states or []):
        if not isinstance(state, dict):
            continue
        signal_key = str(state.get("signal_key") or "").strip()
        driver_key = _SIGNAL_TO_DRIVER.get(signal_key)
        if not driver_key:
            continue

        raw_state = str(state.get("state") or "").strip()
        severity = _severity_from_state(raw_state)
        value = _safe_float(state.get("value"))
        picked[driver_key] = _pick_stronger(
            picked.get(driver_key),
            _candidate(driver_key, severity=severity, state=raw_state or severity, value=value),
        )

    for alert in _alerts_list(alerts_json):
        key = str(alert.get("key") or "").strip()
        driver_key = _ALERT_KEY_TO_DRIVER.get(key)
        if not driver_key:
            continue
        severity = _severity_from_alert(alert)
        state = _severity_title(severity)
        existing = picked.get(driver_key)
        value = existing.get("value") if existing else _driver_value_from_local(driver_key, normalized_local)
        picked[driver_key] = _pick_stronger(
            existing,
            _candidate(driver_key, severity=severity, state=state, value=value),
        )

    for driver_key in ("pressure", "temp", "aqi"):
        if driver_key in picked:
            continue
        local_value = _driver_value_from_local(driver_key, normalized_local)
        if local_value is None:
            continue
        severity = _severity_from_local_value(driver_key, local_value)
        picked[driver_key] = _candidate(
            driver_key,
            severity=severity,
            state=_severity_title(severity),
            value=local_value,
        )

    rows = list(picked.values())
    rows.sort(
        key=lambda item: (
            -int(item.get("_rank") or 0),
            -float(item.get("_value_abs") or 0),
            int(_DRIVER_ORDER.get(item.get("key"), 999)),
        )
    )

    out: List[Dict[str, Any]] = []
    for item in rows[: max(1, int(limit or 6))]:
        out.append(
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "severity": item.get("severity"),
                "state": item.get("state"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "display": item.get("display"),
            }
        )
    return out
