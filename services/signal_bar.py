from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from bots.gauges import signal_resolver
from services.db import pg


_STATE_RANK = {
    "quiet": 0,
    "watch": 1,
    "elevated": 2,
    "strong": 3,
}

_SCHUMANN_CALM_UPPER = 0.03
_SCHUMANN_STABLE_UPPER = 0.06
_SCHUMANN_ACTIVE_UPPER = 0.10
_SCHUMANN_ELEVATED_UPPER = 0.16


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


def _normalize_bar_state(raw_state: Any) -> Optional[str]:
    token = str(raw_state or "").strip().lower().replace(" ", "_")
    if token in {"strong", "storm", "intense", "high"}:
        return "strong"
    if token in {"elevated", "moderate"}:
        return "elevated"
    if token in {"watch", "active"}:
        return "watch"
    if token in {"quiet", "calm", "stable", "mild", "low"}:
        return "quiet"
    return None


def _pick_stronger_state(*states: Optional[str]) -> str:
    picked = "quiet"
    picked_rank = _STATE_RANK[picked]
    for state in states:
        normalized = _normalize_bar_state(state)
        if normalized is None:
            continue
        rank = _STATE_RANK.get(normalized, 0)
        if rank > picked_rank:
            picked = normalized
            picked_rank = rank
    return picked


def _schumann_live_level(amplitude: Optional[float]) -> Optional[dict[str, str]]:
    if amplitude is None:
        return None
    if amplitude < _SCHUMANN_CALM_UPPER:
        return {"label": "Calm", "state": "quiet"}
    if amplitude < _SCHUMANN_STABLE_UPPER:
        return {"label": "Stable", "state": "quiet"}
    if amplitude < _SCHUMANN_ACTIVE_UPPER:
        return {"label": "Active", "state": "watch"}
    if amplitude < _SCHUMANN_ELEVATED_UPPER:
        return {"label": "Elevated", "state": "elevated"}
    return {"label": "Intense", "state": "strong"}


def _fetch_schumann_snapshot() -> Optional[dict[str, Any]]:
    try:
        row = pg.fetchrow(
            """
            with latest_ts as (
              select max(ts_utc) as ts_utc
              from ext.schumann
              where channel = 'fundamental_hz'
                and (meta->>'source') = 'cumiana'
                and (meta->>'status') = 'ok'
            )
            select
              s.ts_utc,
              coalesce(
                max(s.value_num) filter (where s.channel = 'sr_total_0_20'),
                max((s.meta->'amplitude_idx'->>'sr_total_0_20')::float)
              ) as sr_total_0_20
            from ext.schumann s
            join latest_ts on latest_ts.ts_utc = s.ts_utc
            group by s.ts_utc
            limit 1
            """
        )
    except Exception:
        row = None

    if not row:
        return None

    level = _schumann_live_level(_safe_float(row.get("sr_total_0_20")))
    if not level:
        return None

    return {
        "label": level["label"],
        "state": level["state"],
        "updated_at": _coerce_iso(row.get("ts_utc")),
    }


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

    schumann_live = _fetch_schumann_snapshot()
    schumann_trigger_state = _signal_state(normalized_active, "schumann.variability_24h")
    schumann_state = _pick_stronger_state(
        schumann_live.get("state") if schumann_live else None,
        schumann_trigger_state,
    )
    schumann_value = _state_label(schumann_state)
    schumann_updated_at = schumann_live.get("updated_at") if schumann_live else None
    if schumann_live and _normalize_bar_state(schumann_live.get("state")) == schumann_state:
        schumann_value = str(schumann_live.get("label") or schumann_value)
    for item in normalized_active:
        if str(item.get("signal_key") or "").strip() != "schumann.variability_24h":
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
        if not schumann_updated_at:
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
            "value": schumann_value,
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
