from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from bots.gauges import signal_resolver


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _coerce_iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _signal_state(
    active_states: Sequence[Mapping[str, Any]],
    signal_key: str,
) -> Optional[str]:
    for item in active_states:
        if str(item.get("signal_key") or "").strip() != signal_key:
            continue
        state = str(item.get("state") or "").strip().lower()
        if state:
            return state
    return None


def _pressure_state(
    weather: Mapping[str, Any],
    *,
    active_states: Sequence[Mapping[str, Any]],
) -> str:
    delta_12h = _safe_float(weather.get("baro_delta_12h_hpa") or weather.get("pressure_delta_12h"))
    delta_24h = _safe_float(weather.get("baro_delta_24h_hpa") or weather.get("pressure_delta_24h_hpa"))
    delta_3h = _safe_float(weather.get("baro_delta_3h_hpa") or weather.get("pressure_delta_3h_hpa"))
    pressure_drop_state = _signal_state(active_states, "earthweather.pressure_drop_3h")
    pressure_24h_state = _signal_state(active_states, "earthweather.pressure_swing_24h_big")

    if (
        pressure_drop_state == "high"
        or pressure_24h_state == "high"
        or (delta_3h is not None and delta_3h <= -5.0)
        or (delta_24h is not None and abs(delta_24h) >= 12.0)
        or (delta_12h is not None and abs(delta_12h) >= 10.0)
    ):
        return "strong"

    if (
        pressure_drop_state == "watch"
        or pressure_24h_state == "watch"
        or (delta_3h is not None and delta_3h <= -3.0)
        or (delta_24h is not None and abs(delta_24h) >= 8.0)
    ):
        return "elevated"

    if delta_12h is not None and abs(delta_12h) >= 6.0:
        return "watch"

    return "quiet"


def _pressure_arrow(weather: Mapping[str, Any]) -> str:
    raw = str(weather.get("pressure_trend") or weather.get("baro_trend") or "").strip().lower()
    if raw in {"rising", "up"}:
        return "↑"
    if raw in {"falling", "down"}:
        return "↓"
    if raw in {"steady", "stable"}:
        return "→"

    delta = _safe_float(weather.get("baro_delta_12h_hpa") or weather.get("baro_delta_24h_hpa") or weather.get("pressure_delta_24h_hpa"))
    if delta is None:
        return "→"
    if delta >= 0.5:
        return "↑"
    if delta <= -0.5:
        return "↓"
    return "→"


def _format_pressure_value(weather: Mapping[str, Any]) -> str:
    pressure_hpa = _safe_float(weather.get("pressure_hpa"))
    if pressure_hpa is not None:
        return f"{int(round(pressure_hpa))} {_pressure_arrow(weather)}"

    delta = _safe_float(weather.get("baro_delta_12h_hpa") or weather.get("baro_delta_24h_hpa") or weather.get("pressure_delta_24h_hpa"))
    if delta is not None:
        return f"{delta:+.1f}"

    return "—"


def _kp_state(kp_value: Optional[float]) -> str:
    if kp_value is None:
        return "quiet"
    if kp_value >= 6.0:
        return "strong"
    if kp_value >= 4.0:
        return "elevated"
    return "quiet"


def _solar_wind_state(speed: Optional[float]) -> str:
    if speed is None:
        return "quiet"
    if speed >= 700.0:
        return "strong"
    if speed >= 650.0:
        return "elevated"
    if speed >= 550.0:
        return "watch"
    return "quiet"


def _state_label(state: str) -> str:
    return {
        "quiet": "Quiet",
        "watch": "Watch",
        "elevated": "Elevated",
        "strong": "Strong",
    }.get(state, "Quiet")


def build_signal_bar(
    *,
    day: date,
    active_states: Sequence[Mapping[str, Any]] | None,
    local_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized_active = [item for item in list(active_states or []) if isinstance(item, Mapping)]
    payload = signal_resolver._normalize_local_payload(dict(local_payload or {}))
    weather = dict(payload.get("weather") or {})
    space = signal_resolver._fetch_space_snapshot(day) or {}

    kp_now = _safe_float(space.get("kp_now"))
    kp_max = _safe_float(space.get("kp_max"))
    kp_value = kp_now if kp_now is not None else kp_max

    sw_now = _safe_float(space.get("sw_speed_now_kms"))
    sw_avg = _safe_float(space.get("sw_speed_avg"))
    sw_candidates = [value for value in (sw_now, sw_avg) if value is not None]
    sw_value = max(sw_candidates) if sw_candidates else None

    schumann_state = "elevated" if _signal_state(normalized_active, "schumann.variability_24h") else "quiet"
    schumann_updated_at = None
    for item in normalized_active:
        if str(item.get("signal_key") or "").strip() != "schumann.variability_24h":
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
        schumann_updated_at = _coerce_iso(evidence.get("ts"))
        break

    pressure_updated_at = _coerce_iso(payload.get("asof") or payload.get("as_of"))
    space_updated_at = _coerce_iso(space.get("space_now_ts") or space.get("updated_at"))

    items = [
        {
            "key": "kp",
            "label": "KP",
            "value": "—" if kp_value is None else f"{kp_value:.1f}",
            "state": _kp_state(kp_value),
            "driver_key": "kp",
            "detail_target": "driver",
            "updated_at": space_updated_at,
        },
        {
            "key": "solar_wind",
            "label": "SW",
            "value": "—" if sw_value is None else f"{int(round(sw_value))} km/s",
            "state": _solar_wind_state(sw_value),
            "driver_key": "solar_wind",
            "detail_target": "driver",
            "updated_at": space_updated_at,
        },
        {
            "key": "schumann",
            "label": "SR",
            "value": _state_label(schumann_state),
            "state": schumann_state,
            "driver_key": "schumann",
            "detail_target": "schumann",
            "updated_at": schumann_updated_at,
        },
        {
            "key": "pressure",
            "label": "hPa",
            "value": _format_pressure_value(weather),
            "state": _pressure_state(weather, active_states=normalized_active),
            "driver_key": "pressure",
            "detail_target": "local_conditions",
            "updated_at": pressure_updated_at,
        },
    ]

    return {
        "updated_at": space_updated_at or pressure_updated_at or schumann_updated_at,
        "items": items,
    }
