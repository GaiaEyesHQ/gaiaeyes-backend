from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.db import pg
from services.time.moon import moon_phase
from bots.definitions.load_definition_base import load_definition_base


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

_SYNODIC_DAYS = 29.53058867


def _coerce_day(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date()


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _iso_ts(ts: Any) -> Optional[str]:
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat()
    return None


def _fetch_local_payload(user_id: str, day: date) -> Optional[Dict[str, Any]]:
    sqls = [
        ("select app.get_local_signals_for_user(%s::uuid, %s::date) as payload", (user_id, day)),
        ("select app.get_local_signals_for_user(%s::date, %s::uuid) as payload", (day, user_id)),
        ("select app.get_local_signals_for_user(%s::date) as payload", (day,)),
        ("select app.get_local_signals_for_user(%s::uuid) as payload", (user_id,)),
    ]
    for sql, params in sqls:
        try:
            row = pg.fetchrow(sql, *params)
        except Exception:
            continue
        if not row:
            continue
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return None
        if isinstance(payload, dict):
            return payload
    return None


def _normalize_local_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if "payload" in payload and isinstance(payload["payload"], dict):
        return payload["payload"]
    if "data" in payload and isinstance(payload["data"], dict):
        return payload["data"]
    if "local" in payload and isinstance(payload["local"], dict):
        return payload["local"]
    return payload


def _fetch_space_snapshot(day: date) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    row = None
    try:
        row = pg.fetchrow(
            """
            select day, kp_now, kp_max, bz_now, bz_min,
                   sw_speed_now_kms, sw_speed_avg, sw_density_now_cm3,
                   updated_at
              from marts.space_weather_daily
             where day = %s
             limit 1
            """,
            day,
        )
    except Exception:
        row = None

    if row:
        out.update(row)

    try:
        latest = pg.fetchrow(
            """
            select ts_utc, kp_index, bz_nt, sw_speed_kms
              from ext.space_weather
             where kp_index is not null or bz_nt is not null or sw_speed_kms is not null
             order by ts_utc desc
             limit 1
            """
        )
    except Exception:
        latest = None

    if latest:
        if out.get("kp_now") is None and latest.get("kp_index") is not None:
            out["kp_now"] = latest.get("kp_index")
        if out.get("bz_now") is None and latest.get("bz_nt") is not None:
            out["bz_now"] = latest.get("bz_nt")
        if out.get("sw_speed_now_kms") is None and latest.get("sw_speed_kms") is not None:
            out["sw_speed_now_kms"] = latest.get("sw_speed_kms")
        out["space_now_ts"] = latest.get("ts_utc")

    return out


def _fetch_schumann_stddev_24h() -> Optional[float]:
    """Approximate 24h Schumann variability using absolute day-to-day change in f0.

    Telemetry marts may be empty in some deployments; daily marts are more reliable.
    """
    # Prefer v2 daily (single-series)
    try:
        rows = pg.fetch(
            """
            select day, f0
              from marts.schumann_daily_v2
             where day >= (now() at time zone 'utc')::date - interval '3 days'
               and f0 is not null
             order by day desc
             limit 2
            """
        )
    except Exception:
        rows = []

    if rows and len(rows) >= 2:
        f0_today = _safe_float(rows[0].get("f0"))
        f0_yday = _safe_float(rows[1].get("f0"))
        if f0_today is not None and f0_yday is not None:
            return abs(float(f0_today) - float(f0_yday))

    # Fallback: use Cumiana station from schumann_daily
    try:
        rows = pg.fetch(
            """
            with daily as (
              select day, f0_avg_hz::float as f0_mean
                from marts.schumann_daily
               where station_id = 'cumiana'
                 and day >= (now() at time zone 'utc')::date - interval '3 days'
                 and f0_avg_hz is not null
            )
            select day, f0_mean
              from daily
             order by day desc
             limit 2
            """
        )
    except Exception:
        rows = []

    if rows and len(rows) >= 2:
        f0_today = _safe_float(rows[0].get("f0_mean"))
        f0_yday = _safe_float(rows[1].get("f0_mean"))
        if f0_today is not None and f0_yday is not None:
            return abs(float(f0_today) - float(f0_yday))

    return None


def _fetch_schumann_daily_stddev_series(lookback_days: int) -> List[Dict[str, Any]]:
    """Return a daily variability series based on absolute day-to-day change in f0.

    Output rows are shaped as {day, stddev_day} for compatibility with the existing z-score logic.
    """
    # Prefer v2 daily series
    try:
        rows = pg.fetch(
            """
            with s as (
              select day, f0
                from marts.schumann_daily_v2
               where day >= (now() at time zone 'utc')::date - (%s || ' days')::interval
                 and f0 is not null
               order by day asc
            ),
            d as (
              select day,
                     abs(f0 - lag(f0) over (order by day)) as delta_f0
                from s
            )
            select day, delta_f0 as stddev_day
              from d
             where delta_f0 is not null
             order by day asc
            """,
            lookback_days,
        )
        if rows:
            return [dict(r) for r in rows]
    except Exception:
        pass

    # Fallback: use Cumiana station from schumann_daily
    try:
        rows = pg.fetch(
            """
            with s as (
              select day, f0_avg_hz::float as f0_mean
                from marts.schumann_daily
               where station_id = 'cumiana'
                 and day >= (now() at time zone 'utc')::date - (%s || ' days')::interval
                 and f0_avg_hz is not null
               order by day asc
            ),
            d as (
              select day,
                     abs(f0_mean - lag(f0_mean) over (order by day)) as delta_f0
                from s
            )
            select day, delta_f0 as stddev_day
              from d
             where delta_f0 is not null
             order by day asc
            """,
            lookback_days,
        )
        return [dict(r) for r in rows] if rows else []
    except Exception:
        return []


def _percentile_rank(values: List[float], x: float) -> Optional[float]:
    """Percentile rank of x in values in [0,1]. Uses inclusive rank. Returns None if values empty."""
    if not values:
        return None
    vs = sorted(values)
    # inclusive rank: count of values <= x divided by n
    n = len(vs)
    k = 0
    for v in vs:
        if v <= x:
            k += 1
        else:
            break
    return k / float(n)


def _full_moon_days_to(dt: datetime) -> float:
    m = moon_phase(dt)
    cycle = m.get("cycle") if isinstance(m, dict) else None
    try:
        cycle = float(cycle)
    except Exception:
        return 99.0
    delta = abs(0.5 - cycle)
    return delta * _SYNODIC_DAYS


def resolve_signals(
    user_id: str,
    day: str | date | None = None,
    *,
    local_payload: Optional[Dict[str, Any]] = None,
    definition: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    definition = definition or load_definition_base()[0]
    day = _coerce_day(day)
    sig_defs = {s.get("key"): s for s in definition.get("signal_definitions", [])}

    payload = _normalize_local_payload(local_payload or _fetch_local_payload(user_id, day))
    weather = payload.get("weather") or {}
    air = payload.get("air") or {}
    health_flags = (payload.get("health") or {}).get("flags") or {}

    out: List[Dict[str, Any]] = []

    # Pressure swing (prefer 12h, fallback to 24h)
    delta_12h = _safe_float(weather.get("baro_delta_12h_hpa") or weather.get("pressure_delta_12h"))
    delta_24h = _safe_float(weather.get("baro_delta_24h_hpa") or weather.get("pressure_delta_24h_hpa"))
    pressure_delta = delta_12h if delta_12h is not None else delta_24h
    if pressure_delta is not None:
        abs_delta = abs(pressure_delta)
        state = None
        if abs_delta >= 10:
            state = "high"
        elif abs_delta >= 6:
            state = "moderate"
        if state:
            sig = sig_defs.get("earthweather.pressure_swing_12h") or {}
            out.append(
                {
                    "signal_key": "earthweather.pressure_swing_12h",
                    "state": state,
                    "value": pressure_delta,
                    "confidence": sig.get("confidence"),
                    "evidence": {
                        "source": "local_signals",
                        "field": "baro_delta_12h_hpa" if delta_12h is not None else "baro_delta_24h_hpa",
                        "ts": payload.get("asof") or payload.get("as_of"),
                    },
                }
            )

    # Rapid pressure drop (3h)
    baro_delta_3h = _safe_float(weather.get("baro_delta_3h_hpa") or weather.get("pressure_delta_3h_hpa"))
    rapid_drop = bool(health_flags.get("pressure_rapid_drop"))
    drop_state = None
    if baro_delta_3h is not None and baro_delta_3h <= -5.0:
        drop_state = "high"
    elif baro_delta_3h is not None and baro_delta_3h <= -3.0:
        drop_state = "watch"
    elif rapid_drop:
        drop_state = "watch"
    if drop_state:
        sig = sig_defs.get("earthweather.pressure_drop_3h") or {}
        out.append(
            {
                "signal_key": "earthweather.pressure_drop_3h",
                "state": drop_state,
                "value": baro_delta_3h if baro_delta_3h is not None else -3.0,
                "confidence": sig.get("confidence"),
                "evidence": {
                    "source": "local_signals",
                    "field": "baro_delta_3h_hpa" if baro_delta_3h is not None else "health.flags.pressure_rapid_drop",
                    "ts": payload.get("asof") or payload.get("as_of"),
                },
            }
        )

    # Big 24h pressure swing
    if delta_24h is not None:
        abs_24h = abs(delta_24h)
        state = None
        if abs_24h >= 12:
            state = "high"
        elif abs_24h >= 8:
            state = "watch"
        if state:
            sig = sig_defs.get("earthweather.pressure_swing_24h_big") or {}
            out.append(
                {
                    "signal_key": "earthweather.pressure_swing_24h_big",
                    "state": state,
                    "value": delta_24h,
                    "confidence": sig.get("confidence"),
                    "evidence": {
                        "source": "local_signals",
                        "field": "baro_delta_24h_hpa",
                        "ts": payload.get("asof") or payload.get("as_of"),
                    },
                }
            )

    # Temperature swing (24h)
    temp_delta = _safe_float(weather.get("temp_delta_24h_c") or weather.get("temp_delta_24h"))
    if temp_delta is not None:
        abs_delta = abs(temp_delta)
        state = None
        if abs_delta >= 10:
            state = "high"
        elif abs_delta >= 6:
            state = "moderate"
        if state:
            sig = sig_defs.get("earthweather.temp_swing_24h") or {}
            out.append(
                {
                    "signal_key": "earthweather.temp_swing_24h",
                    "state": state,
                    "value": temp_delta,
                    "confidence": sig.get("confidence"),
                    "evidence": {
                        "source": "local_signals",
                        "field": "temp_delta_24h_c",
                        "ts": payload.get("asof") or payload.get("as_of"),
                    },
                }
            )

        # Big 24h temperature swing (alert-only)
        state_big = None
        if abs_delta >= 12:
            state_big = "high"
        elif abs_delta >= 8:
            state_big = "watch"
        if state_big:
            sig = sig_defs.get("earthweather.temp_swing_24h_big") or {}
            out.append(
                {
                    "signal_key": "earthweather.temp_swing_24h_big",
                    "state": state_big,
                    "value": temp_delta,
                    "confidence": sig.get("confidence"),
                    "evidence": {
                        "source": "local_signals",
                        "field": "temp_delta_24h_c",
                        "ts": payload.get("asof") or payload.get("as_of"),
                    },
                }
            )

    # Air quality (AQI)
    aqi = _safe_float(air.get("aqi"))
    aqi_state = None
    if aqi is not None:
        if aqi >= 151:
            aqi_state = "unhealthy"
        elif aqi >= 101:
            aqi_state = "usg"
        elif aqi >= 51:
            aqi_state = "moderate"
    if aqi_state:
        out.append(
            {
                "signal_key": "earthweather.air_quality",
                "state": aqi_state,
                "value": aqi,
                "confidence": "established",
                "evidence": {
                    "source": "local_signals",
                    "field": "air.aqi",
                    "ts": payload.get("asof") or payload.get("as_of"),
                },
            }
        )

    # Space weather: KP + Bz
    space = _fetch_space_snapshot(day)
    kp_now = _safe_float(space.get("kp_now"))
    kp_max = _safe_float(space.get("kp_max"))
    kp_val = kp_now if kp_now is not None else kp_max
    if kp_val is not None:
        state = None
        if kp_val >= 6:
            state = "storm"
        elif kp_val >= 4:
            state = "elevated"
        if state:
            sig = sig_defs.get("spaceweather.kp") or {}
            out.append(
                {
                    "signal_key": "spaceweather.kp",
                    "state": state,
                    "value": kp_val,
                    "confidence": sig.get("confidence"),
                    "evidence": {
                        "source": "marts.space_weather_daily",
                        "ts": _iso_ts(space.get("space_now_ts") or space.get("updated_at")),
                    },
                }
            )

    bz_now = _safe_float(space.get("bz_now"))
    if bz_now is not None:
        state = None
        if bz_now <= -10:
            state = "strong"
        elif bz_now <= -5:
            state = "active"
        if state:
            sig = sig_defs.get("spaceweather.bz_coupling") or {}
            out.append(
                {
                    "signal_key": "spaceweather.bz_coupling",
                    "state": state,
                    "value": bz_now,
                    "confidence": sig.get("confidence"),
                    "evidence": {
                        "source": "marts.space_weather_daily",
                        "ts": _iso_ts(space.get("space_now_ts") or space.get("updated_at")),
                    },
                }
            )

    sw_speed = _safe_float(space.get("sw_speed_now_kms"))
    if sw_speed is not None:
        state = None
        if sw_speed >= 700:
            state = "very_high"
        elif sw_speed >= 600:
            state = "high"
        elif sw_speed >= 500:
            state = "elevated"
        if state:
            out.append(
                {
                    "signal_key": "spaceweather.sw_speed",
                    "state": state,
                    "value": sw_speed,
                    "confidence": "emerging",
                    "evidence": {
                        "source": "marts.space_weather_daily",
                        "ts": _iso_ts(space.get("space_now_ts") or space.get("updated_at")),
                    },
                }
            )

    # Schumann variability (24h stddev) using rolling 30d z-score / percentile thresholds
    stddev_24h = _fetch_schumann_stddev_24h()
    sch_def = sig_defs.get("schumann.variability_24h") or {}
    params = sch_def.get("activation_params") or {}
    lookback_days = int(params.get("lookback_days") or 30)
    min_points = int(params.get("min_points") or 14)
    z_thr = float(params.get("zscore_threshold") or 2.0)
    p_thr = float(params.get("percentile_threshold") or 0.9)

    zscore_30d = None
    pct_30d = None
    n_points = 0

    if stddev_24h is not None:
        series = _fetch_schumann_daily_stddev_series(lookback_days)
        vals = [float(r["stddev_day"]) for r in series if r.get("stddev_day") is not None]
        n_points = len(vals)

        if n_points >= min_points:
            mean = sum(vals) / n_points
            var = 0.0
            if n_points > 1:
                var = sum((v - mean) ** 2 for v in vals) / (n_points - 1)
            std = var ** 0.5
            if std > 0:
                zscore_30d = (float(stddev_24h) - mean) / std
            pct_30d = _percentile_rank(vals, float(stddev_24h))

    activate = False
    if stddev_24h is not None and n_points >= min_points:
        if (zscore_30d is not None and zscore_30d >= z_thr) or (pct_30d is not None and pct_30d >= p_thr):
            activate = True

    if activate:
        out.append(
            {
                "signal_key": "schumann.variability_24h",
                "state": "elevated",
                "value": float(stddev_24h),
                "confidence": sch_def.get("confidence"),
                "evidence": {
                    "source": "marts.schumann_daily_v2_or_daily",
                    "metric": "abs_delta_f0_day_to_day",
                    "stddev_24h": float(stddev_24h),
                    "zscore_30d": zscore_30d,
                    "pct_30d": pct_30d,
                    "lookback_days": lookback_days,
                    "n_points": n_points,
                    "z_thr": z_thr,
                    "p_thr": p_thr,
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
            }
        )

    # Full moon window
    now = datetime.now(timezone.utc)
    days_to_full = _full_moon_days_to(now)
    if days_to_full <= 2.0:
        sig = sig_defs.get("lunar.full_moon_window") or {}
        out.append(
            {
                "signal_key": "lunar.full_moon_window",
                "state": "active",
                "value": round(days_to_full, 2),
                "confidence": sig.get("confidence"),
                "evidence": {
                    "source": "services.time.moon",
                    "ts": now.isoformat(),
                },
            }
        )

    return out
