from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from services.external import pollen


_SEVERITY_RANK = {
    "high": 4,
    "watch": 3,
    "elevated": 3,
    "mild": 2,
    "low": 1,
}
_DEFAULT_SIGNAL_STRENGTH = {
    "high": 1.0,
    "watch": 0.78,
    "elevated": 0.78,
    "mild": 0.55,
    "low": 0.25,
}
_HARD_SIGNAL_THRESHOLD = 0.9

_DRIVER_ORDER = {
    "pressure": 1,
    "temp": 2,
    "humidity": 3,
    "aqi": 4,
    "allergens": 5,
    "kp": 6,
    "bz": 7,
    "sw": 8,
    "schumann": 9,
}

_DRIVER_META = {
    "pressure": {"label": "Pressure Swing", "unit": "hPa"},
    "temp": {"label": "Temperature Swing", "unit": "C"},
    "humidity": {"label": "Humidity", "unit": "%"},
    "aqi": {"label": "Air Quality", "unit": "AQI"},
    "allergens": {"label": "Allergens", "unit": "index"},
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
    "earthweather.allergens": "allergens",
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
    "alert.allergen_load": "allergens",
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


def _clamp_signal_strength(value: float) -> float:
    return max(0.0, min(1.0, value))


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
    allergens = local_payload.get("allergens") or {}
    if key == "pressure":
        return _safe_float(
            weather.get("baro_delta_12h_hpa")
            or weather.get("pressure_delta_12h")
            or weather.get("baro_delta_24h_hpa")
            or weather.get("pressure_delta_24h_hpa")
        )
    if key == "temp":
        return _safe_float(weather.get("temp_delta_24h_c") or weather.get("temp_delta_24h"))
    if key == "humidity":
        return _safe_float(weather.get("humidity_pct") or weather.get("humidity"))
    if key == "aqi":
        return _safe_float(air.get("aqi"))
    if key == "allergens":
        return _safe_float(allergens.get("overall_index") or allergens.get("relevance_score"))
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
    if key == "humidity":
        if value >= 85 or value <= 25:
            return "high"
        if value >= 78 or value <= 30:
            return "watch"
        if value >= 70 or value <= 35:
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
    if key == "allergens":
        if value >= 5:
            return "high"
        if value >= 4:
            return "watch"
        if value >= 3:
            return "mild"
        return "low"
    return "low"


def _signal_strength_from_driver(key: str, value: Optional[float], severity: str) -> float:
    fallback = _DEFAULT_SIGNAL_STRENGTH.get(severity, 0.25)
    if value is None:
        return fallback

    abs_value = abs(value)
    if key == "pressure":
        if abs_value >= 12:
            return 1.0
        if abs_value >= 10:
            return 0.92
        if abs_value >= 8:
            return 0.8
        if abs_value >= 6:
            return 0.6
        return fallback
    if key == "temp":
        if abs_value >= 12:
            return 1.0
        if abs_value >= 10:
            return 0.9
        if abs_value >= 8:
            return 0.78
        if abs_value >= 6:
            return 0.58
        return fallback
    if key == "humidity":
        if value >= 85 or value <= 25:
            return 0.88
        if value >= 78 or value <= 30:
            return 0.72
        if value >= 70 or value <= 35:
            return 0.52
        return fallback
    if key == "aqi":
        if value >= 151:
            return 1.0
        if value >= 101:
            return 0.82
        if value >= 51:
            return 0.58
        return fallback
    if key == "allergens":
        if value >= 5:
            return 1.0
        if value >= 4:
            return 0.82
        if value >= 3:
            return 0.6
        return fallback
    if key == "kp":
        if value >= 6:
            return 1.0
        if value >= 5:
            return 0.84
        if value >= 4:
            return 0.66
        return fallback
    if key == "bz":
        if value <= -10:
            return 1.0
        if value <= -8:
            return 0.82
        if value <= -5:
            return 0.64
        return fallback
    if key == "sw":
        if value >= 700:
            return 1.0
        if value >= 650:
            return 0.96
        if value >= 550:
            return 0.82
        if value >= 500:
            return 0.68
        return fallback
    if key == "schumann":
        return 0.82 if severity in {"watch", "elevated", "high"} else fallback
    return fallback


def _format_value(key: str, value: Optional[float], unit: str) -> Optional[str]:
    if value is None:
        return None
    if key == "humidity":
        return f"{int(round(value, 0))}%"
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


def _driver_label_from_local(key: str, local_payload: Dict[str, Any]) -> Optional[str]:
    if key != "allergens":
        return None
    allergens = local_payload.get("allergens") or {}
    primary_label = str(allergens.get("primary_label") or "").strip()
    if primary_label:
        return primary_label
    primary_type = str(allergens.get("primary_type") or "").strip().lower()
    return pollen.TYPE_LABELS.get(primary_type)


def _candidate(
    key: str,
    *,
    severity: str,
    state: str,
    value: Optional[float],
    label_override: Optional[str] = None,
    signal_strength: Optional[float] = None,
    force_visible: bool = False,
    show_driver: bool = True,
) -> Dict[str, Any]:
    meta = _DRIVER_META.get(key) or {"label": key.replace("_", " ").title(), "unit": ""}
    unit = str(meta.get("unit") or "")
    label = str(label_override or meta.get("label") or key)
    rounded_value: Optional[float] = None
    if value is not None:
        if key in {"aqi", "sw"}:
            rounded_value = float(int(round(value, 0)))
        elif key == "schumann":
            rounded_value = round(value, 3)
        else:
            rounded_value = round(value, 1)

    state_title = _state_title(state) if state else _severity_title(severity)
    strength = _clamp_signal_strength(signal_strength if signal_strength is not None else _signal_strength_from_driver(key, rounded_value, severity))
    hard_visible = force_visible or (severity == "high" and strength >= _HARD_SIGNAL_THRESHOLD)
    visible = bool(show_driver) and severity != "low"
    if hard_visible:
        visible = True
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
        "_signal_strength": strength,
        "_force_visible": hard_visible,
        "_show_driver": visible,
    }


def _pick_stronger(existing: Optional[Dict[str, Any]], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return incoming
    existing_rank = (
        int(existing.get("_force_visible") is True),
        int(existing.get("_rank") or 0),
        float(existing.get("_signal_strength") or 0.0),
        float(existing.get("_value_abs") or -1.0),
    )
    incoming_rank = (
        int(incoming.get("_force_visible") is True),
        int(incoming.get("_rank") or 0),
        float(incoming.get("_signal_strength") or 0.0),
        float(incoming.get("_value_abs") or -1.0),
    )
    return incoming if incoming_rank > existing_rank else existing


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
        explicit_severity = str(state.get("severity") or "").strip().lower()
        severity = explicit_severity if explicit_severity in _SEVERITY_RANK else _severity_from_state(raw_state)
        value = _safe_float(state.get("value"))
        picked[driver_key] = _pick_stronger(
            picked.get(driver_key),
            _candidate(
                driver_key,
                severity=severity,
                state=raw_state or severity,
                value=value,
                label_override=_driver_label_from_local(driver_key, normalized_local),
                signal_strength=_safe_float(state.get("signal_strength")),
                force_visible=bool(state.get("force_visibility") or state.get("force_signal")),
                show_driver=bool(state.get("show_driver", True)),
            ),
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
            _candidate(
                driver_key,
                severity=severity,
                state=state,
                value=value,
                label_override=_driver_label_from_local(driver_key, normalized_local),
            ),
        )

    for driver_key in ("pressure", "temp", "humidity", "aqi"):
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
            label_override=_driver_label_from_local(driver_key, normalized_local),
        )

    rows = list(picked.values())
    rows.sort(
        key=lambda item: (
            -int(item.get("_force_visible") is True),
            -int(item.get("_rank") or 0),
            -float(item.get("_signal_strength") or 0.0),
            -float(item.get("_value_abs") or 0),
            int(_DRIVER_ORDER.get(item.get("key"), 999)),
        )
    )

    out: List[Dict[str, Any]] = []
    visible_rows = [item for item in rows if bool(item.get("_show_driver"))]
    for item in visible_rows[: max(1, int(limit or 6))]:
        out.append(
            {
                "key": item.get("key"),
                "label": item.get("label"),
                "severity": item.get("severity"),
                "state": item.get("state"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "display": item.get("display"),
                "signal_strength": round(float(item.get("_signal_strength") or 0.0), 3),
                "force_visible": bool(item.get("_force_visible")),
                "show_driver": bool(item.get("_show_driver")),
            }
        )
    return out


def signal_bar_driver_candidates(signal_bar: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    """Promote active signal-bar-only readings into driver-shaped rows.

    Schumann live amplitude is intentionally shown in the top signal bar even when
    the daily variability trigger is not active. This keeps the drivers list and
    Guide influences aligned with the same visible status.
    """
    if not isinstance(signal_bar, Mapping):
        return []

    key_map = {
        "kp": "kp",
        "solar_wind": "sw",
        "schumann": "schumann",
        "pressure": "pressure",
    }
    severity_map = {
        "strong": "high",
        "storm": "high",
        "elevated": "watch",
        "watch": "watch",
        "active": "mild",
    }
    rows: List[Dict[str, Any]] = []
    for item in signal_bar.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        bar_key = str(item.get("key") or "").strip().lower()
        driver_key = key_map.get(bar_key)
        if not driver_key:
            continue
        raw_state = str(item.get("state") or "").strip().lower()
        severity = severity_map.get(raw_state)
        if not severity:
            continue
        state = str(item.get("value") or item.get("state") or severity).strip() or severity
        rows.append(
            _candidate(
                driver_key,
                severity=severity,
                state=state,
                value=_safe_float(item.get("value")),
                signal_strength=0.9 if severity == "high" else 0.76 if severity == "watch" else 0.55,
                force_visible=severity == "high",
            )
        )
    return rows
