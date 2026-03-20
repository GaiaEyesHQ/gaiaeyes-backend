#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from bots.definitions.load_definition_base import load_definition_base
from bots.gauges.gauge_scorer import fetch_user_tags
from bots.gauges.local_payload import get_local_payload
from bots.gauges.signal_resolver import resolve_signals
from bots.notifications.push_logic import (
    NotificationCandidate,
    allows_severity,
    build_dedupe_key,
    can_emit_with_cooldown,
    flare_class_rank,
    gauge_zone,
    is_within_quiet_hours,
    normalize_preferences,
    previous_gauge_value,
    utc_now,
)
from services.db import pg
from services.personalization.health_context import (
    AUTONOMIC_KEYS,
    HEAD_PRESSURE_KEYS,
    PAIN_FLARE_KEYS,
    SLEEP_DISRUPTION_KEYS,
    build_personalization_profile,
)


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

_SIGNAL_FAMILIES = {"geomagnetic", "solar_wind", "flare_cme_sep", "schumann"}
_LOCAL_FAMILIES = {"pressure", "aqi", "temp"}
_GAUGE_FAMILIES = {"pain", "energy", "sleep", "heart", "health_status"}

_PRESSURE_SIGNAL_KEYS = {
    "earthweather.pressure_swing_12h",
    "earthweather.pressure_drop_3h",
    "earthweather.pressure_swing_24h_big",
}
_TEMP_SIGNAL_KEYS = {
    "earthweather.temp_swing_24h",
    "earthweather.temp_swing_24h_big",
}

_GAUGE_LABELS = {
    "pain": "Pain",
    "energy": "Energy",
    "sleep": "Sleep",
    "heart": "Heart",
    "health_status": "Health status",
}


def _today_utc() -> str:
    return utc_now().date().isoformat()


def _coerce_day(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return utc_now().date()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _normalize_json_map(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _normalize_local_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("payload"), dict):
        return dict(payload["payload"])
    if isinstance(payload.get("data"), dict):
        return dict(payload["data"])
    if isinstance(payload.get("local"), dict):
        return dict(payload["local"])
    return dict(payload)


def _fetch_notification_users(limit: int | None = None, user_id: str | None = None) -> List[Dict[str, Any]]:
    params: List[Any] = []
    where = ["enabled = true"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    limit_sql = ""
    if limit and limit > 0:
        limit_sql = "limit %s"
        params.append(limit)

    sql = f"""
        select user_id,
               enabled,
               signal_alerts_enabled,
               local_condition_alerts_enabled,
               personalized_gauge_alerts_enabled,
               quiet_hours_enabled,
               to_char(quiet_start, 'HH24:MI') as quiet_start,
               to_char(quiet_end, 'HH24:MI') as quiet_end,
               time_zone,
               sensitivity,
               families
          from app.user_notification_preferences
         where {' and '.join(where)}
           and exists (
             select 1
               from app.user_push_tokens t
              where t.user_id = app.user_notification_preferences.user_id
                and t.enabled = true
           )
         order by updated_at desc, created_at desc
         {limit_sql}
    """
    return pg.fetch(sql, *params)


def _fetch_space_weather_daily(day: date) -> Dict[str, Any]:
    row = pg.fetchrow(
        """
        select day,
               kp_now,
               kp_max,
               bz_now,
               bz_min,
               sw_speed_now_kms,
               sw_speed_avg,
               xray_max_class,
               flares_count,
               cmes_count,
               sep_s_max,
               drap_absorption_polar_db,
               drap_absorption_midlat_db,
               updated_at
          from marts.space_weather_daily
         where day <= %s
         order by day desc
         limit 1
        """,
        day,
    )
    return row or {}


def _fetch_next_cme_arrival(now_utc: datetime) -> Dict[str, Any]:
    row = pg.fetchrow(
        """
        select arrival_time, simulation_id, location, kp_estimate, cme_speed_kms, confidence
          from marts.cme_arrivals
         where arrival_time >= %s
           and arrival_time <= %s
         order by arrival_time asc
         limit 1
        """,
        now_utc - timedelta(hours=6),
        now_utc + timedelta(hours=72),
    )
    return row or {}


def _fetch_latest_sep() -> Dict[str, Any]:
    row = pg.fetchrow(
        """
        select ts_utc, energy_band, flux, s_scale, s_scale_index
          from ext.sep_flux
         order by ts_utc desc
         limit 1
        """
    )
    return row or {}


def _fetch_gauges_row(user_id: str, day: date) -> Dict[str, Any]:
    row = pg.fetchrow(
        """
        select day, pain, energy, sleep, heart, health_status
          from marts.user_gauges_day
         where user_id = %s
           and day <= %s
         order by day desc
         limit 1
        """,
        user_id,
        day,
    )
    return row or {}


def _fetch_gauge_deltas(user_id: str, day: date) -> Dict[str, int]:
    row = pg.fetchrow(
        """
        select deltas_json
          from marts.user_gauges_delta_day
         where user_id = %s
           and day <= %s
         order by day desc
         limit 1
        """,
        user_id,
        day,
    )
    payload = _normalize_json_map((row or {}).get("deltas_json"))
    deltas: Dict[str, int] = {}
    for key in _GAUGE_FAMILIES:
        try:
            deltas[key] = int(round(float(payload.get(key) or 0), 0))
        except Exception:
            deltas[key] = 0
    return deltas


def _family_allowed(preferences: Dict[str, Any], family: str, severity: str) -> bool:
    if not preferences.get("enabled"):
        return False
    if not allows_severity(str(preferences.get("sensitivity") or "normal"), severity):
        return False

    family_flags = preferences.get("families") or {}
    if family in _SIGNAL_FAMILIES:
        return bool(preferences.get("signal_alerts_enabled")) and bool(family_flags.get(family, True))
    if family in _LOCAL_FAMILIES:
        return bool(preferences.get("local_condition_alerts_enabled")) and bool(family_flags.get(family, True))
    if family in _GAUGE_FAMILIES:
        return bool(preferences.get("personalized_gauge_alerts_enabled")) and bool(family_flags.get("gauge_spikes", True))
    return False


def _queue_candidate(
    *,
    user_id: str,
    candidate: NotificationCandidate,
    now_utc: datetime,
    status: str,
    error_text: str | None = None,
) -> bool:
    dedupe_key = build_dedupe_key(user_id, candidate.family, candidate.event_key, now_utc)
    payload = json.dumps(candidate.event_payload(), separators=(",", ":"), sort_keys=True, default=str)
    row = pg.fetchrow(
        """
        insert into content.push_notification_events (
            user_id,
            family,
            event_key,
            severity,
            title,
            body,
            payload,
            dedupe_key,
            status,
            created_at,
            error_text
        )
        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
        on conflict (dedupe_key) do nothing
        returning id
        """,
        user_id,
        candidate.family,
        candidate.event_key,
        candidate.severity,
        candidate.title,
        candidate.body,
        payload,
        dedupe_key,
        status,
        now_utc,
        error_text,
    )
    return row is not None


def _latest_events_by_family(user_id: str) -> Dict[str, Dict[str, Any]]:
    rows = pg.fetch(
        """
        select distinct on (family)
               family,
               severity,
               status,
               created_at,
               event_key
          from content.push_notification_events
         where user_id = %s
           and status in ('queued', 'sent', 'skipped')
         order by family, created_at desc
        """,
        user_id,
    )
    return {str(row.get("family") or ""): row for row in rows if row.get("family")}


def _signal_context(active_states: Iterable[Dict[str, Any]]) -> Dict[str, bool]:
    keys = {str(item.get("signal_key") or "").strip() for item in active_states if item.get("signal_key")}
    pressure_active = bool(keys & _PRESSURE_SIGNAL_KEYS)
    temp_active = bool(keys & _TEMP_SIGNAL_KEYS)
    aqi_active = "earthweather.air_quality" in keys
    solar_wind_active = "spaceweather.bz_coupling" in keys or "spaceweather.sw_speed" in keys
    geomagnetic_active = "spaceweather.kp" in keys or solar_wind_active
    schumann_active = "schumann.variability_24h" in keys
    return {
        "pressure_active": pressure_active,
        "temp_active": temp_active,
        "aqi_active": aqi_active,
        "solar_wind_active": solar_wind_active,
        "geomagnetic_active": geomagnetic_active,
        "schumann_active": schumann_active,
        "any_environment_active": any(
            [
                pressure_active,
                temp_active,
                aqi_active,
                solar_wind_active,
                geomagnetic_active,
                schumann_active,
            ]
        ),
    }


def _build_signal_candidates(
    *,
    space_daily: Dict[str, Any],
    cme_row: Dict[str, Any],
    sep_row: Dict[str, Any],
    active_states: List[Dict[str, Any]],
) -> List[NotificationCandidate]:
    out: List[NotificationCandidate] = []
    asof = None
    updated_at = space_daily.get("updated_at")
    if isinstance(updated_at, datetime):
        asof = updated_at.astimezone(timezone.utc).isoformat()

    kp_now = _safe_float(space_daily.get("kp_now"))
    if kp_now is None:
        kp_now = _safe_float(space_daily.get("kp_max"))
    if kp_now is not None:
        if kp_now >= 6:
            out.append(
                NotificationCandidate(
                    family="geomagnetic",
                    event_key="kp_g2_plus",
                    severity="high",
                    title="Geomagnetic storm elevated",
                    body="Kp has moved into a stronger storm range. Open Gaia Eyes for context.",
                    target_type="driver",
                    target_key="kp",
                    asof=asof,
                    payload={"kp_now": kp_now},
                )
            )
        elif kp_now >= 5:
            out.append(
                NotificationCandidate(
                    family="geomagnetic",
                    event_key="kp_g1_plus",
                    severity="watch",
                    title="Geomagnetic storm watch",
                    body="Kp has reached G1-level activity. Open Gaia Eyes for context.",
                    target_type="driver",
                    target_key="kp",
                    asof=asof,
                    payload={"kp_now": kp_now},
                )
            )

    bz_now = _safe_float(space_daily.get("bz_now"))
    sw_speed_now = _safe_float(space_daily.get("sw_speed_now_kms"))
    sw_speed_avg = _safe_float(space_daily.get("sw_speed_avg"))
    sw_speed_signal = max(
        [value for value in (sw_speed_now, sw_speed_avg) if value is not None],
        default=None,
    )
    solar_wind_payload = {"sw_speed_now_kms": sw_speed_now, "sw_speed_avg": sw_speed_avg}
    if sw_speed_signal is not None:
        if sw_speed_signal >= 650:
            out.append(
                NotificationCandidate(
                    family="solar_wind",
                    event_key="solar_wind_speed_high",
                    severity="high",
                    title="Solar wind speed high",
                    body="Solar wind speed is running in a stronger range. Open Gaia Eyes for details.",
                    target_type="driver",
                    target_key="solar_wind",
                    asof=asof,
                    payload=solar_wind_payload,
                )
            )
        elif sw_speed_signal >= 550:
            out.append(
                NotificationCandidate(
                    family="solar_wind",
                    event_key="solar_wind_speed_watch",
                    severity="watch",
                    title="Solar wind speed watch",
                    body="Solar wind speed is elevated enough to watch. Open Gaia Eyes for details.",
                    target_type="driver",
                    target_key="solar_wind",
                    asof=asof,
                    payload=solar_wind_payload,
                )
            )
    if bz_now is not None:
        if bz_now <= -12 or ((sw_speed_signal or 0) >= 650 and bz_now <= -8):
            out.append(
                NotificationCandidate(
                    family="solar_wind",
                    event_key="bz_coupling_high",
                    severity="high",
                    title="Solar wind coupling high",
                    body="Southward Bz and solar wind are strongly coupled right now. Open Gaia Eyes for details.",
                    target_type="driver",
                    target_key="solar_wind",
                    asof=asof,
                    payload={"bz_now": bz_now, **solar_wind_payload},
                )
            )
        elif bz_now <= -8 or ((sw_speed_signal or 0) >= 550 and bz_now <= -5):
            out.append(
                NotificationCandidate(
                    family="solar_wind",
                    event_key="bz_coupling_elevated",
                    severity="watch",
                    title="Solar wind elevated",
                    body="Solar wind and Bz coupling have moved into a more active range. Open Gaia Eyes for details.",
                    target_type="driver",
                    target_key="solar_wind",
                    asof=asof,
                    payload={"bz_now": bz_now, **solar_wind_payload},
                )
            )

    flare_class = str(space_daily.get("xray_max_class") or "").strip().upper() or None
    flare_rank = flare_class_rank(flare_class)
    if flare_rank[0] >= 4:
        out.append(
            NotificationCandidate(
                family="flare_cme_sep",
                event_key="flare_x_class",
                severity="high",
                title="Major flare event",
                body="An X-class flare was observed in the last day. Open Gaia Eyes for context.",
                target_type="driver",
                target_key="flares",
                asof=asof,
                payload={"xray_max_class": flare_class},
            )
        )
    elif flare_rank[0] == 3 and flare_rank[1] >= 5.0:
        out.append(
            NotificationCandidate(
                family="flare_cme_sep",
                event_key="flare_m5_plus",
                severity="watch",
                title="Flare activity elevated",
                body="An M5+ flare was observed in the last day. Open Gaia Eyes for context.",
                target_type="driver",
                target_key="flares",
                asof=asof,
                payload={"xray_max_class": flare_class},
            )
        )

    if cme_row:
        kp_estimate = _safe_float(cme_row.get("kp_estimate"))
        cme_speed = _safe_float(cme_row.get("cme_speed_kms"))
        arrival_time = cme_row.get("arrival_time")
        cme_asof = arrival_time.astimezone(timezone.utc).isoformat() if isinstance(arrival_time, datetime) else asof
        if (kp_estimate or 0) >= 6 or (cme_speed or 0) >= 1200:
            out.append(
                NotificationCandidate(
                    family="flare_cme_sep",
                    event_key="cme_watch_high",
                    severity="high",
                    title="CME watch elevated",
                    body="A stronger CME arrival is being tracked. Open Gaia Eyes for context.",
                    target_type="driver",
                    target_key="cme",
                    asof=cme_asof,
                    payload={"kp_estimate": kp_estimate, "cme_speed_kms": cme_speed},
                )
            )
        elif cme_speed or kp_estimate:
            out.append(
                NotificationCandidate(
                    family="flare_cme_sep",
                    event_key="cme_watch",
                    severity="watch",
                    title="CME watch",
                    body="A CME arrival is being tracked in the next few days. Open Gaia Eyes for context.",
                    target_type="driver",
                    target_key="cme",
                    asof=cme_asof,
                    payload={"kp_estimate": kp_estimate, "cme_speed_kms": cme_speed},
                )
            )

    sep_scale_index = _safe_float(space_daily.get("sep_s_max"))
    if sep_scale_index is None:
        sep_scale_index = _safe_float(sep_row.get("s_scale_index"))
    sep_asof = None
    if isinstance(sep_row.get("ts_utc"), datetime):
        sep_asof = sep_row["ts_utc"].astimezone(timezone.utc).isoformat()
    if sep_scale_index is not None:
        if sep_scale_index >= 2:
            out.append(
                NotificationCandidate(
                    family="flare_cme_sep",
                    event_key="sep_s2_plus",
                    severity="high",
                    title="Solar radiation elevated",
                    body="Proton activity has moved into a stronger range. Open Gaia Eyes for context.",
                    target_type="driver",
                    target_key="sep",
                    asof=sep_asof or asof,
                    payload={"s_scale_index": sep_scale_index},
                )
            )
        elif sep_scale_index >= 1:
            out.append(
                NotificationCandidate(
                    family="flare_cme_sep",
                    event_key="sep_s1_plus",
                    severity="watch",
                    title="Solar radiation watch",
                    body="Proton activity has moved into an elevated range. Open Gaia Eyes for context.",
                    target_type="driver",
                    target_key="sep",
                    asof=sep_asof or asof,
                    payload={"s_scale_index": sep_scale_index},
                )
            )

    drap_polar = _safe_float(space_daily.get("drap_absorption_polar_db"))
    drap_midlat = _safe_float(space_daily.get("drap_absorption_midlat_db"))
    if (drap_midlat or 0) >= 10 or (drap_polar or 0) >= 20:
        out.append(
            NotificationCandidate(
                family="flare_cme_sep",
                event_key="drap_absorption_high",
                severity="high",
                title="Radio absorption elevated",
                body="D-RAP absorption has moved into a stronger range. Open Gaia Eyes for context.",
                target_type="driver",
                target_key="drap",
                asof=asof,
                payload={"drap_midlat_db": drap_midlat, "drap_polar_db": drap_polar},
            )
        )
    elif (drap_midlat or 0) >= 5 or (drap_polar or 0) >= 10:
        out.append(
            NotificationCandidate(
                family="flare_cme_sep",
                event_key="drap_absorption_elevated",
                severity="watch",
                title="Radio absorption watch",
                body="D-RAP absorption has become more noticeable. Open Gaia Eyes for context.",
                target_type="driver",
                target_key="drap",
                asof=asof,
                payload={"drap_midlat_db": drap_midlat, "drap_polar_db": drap_polar},
            )
        )

    schumann_signal = next(
        (item for item in active_states if str(item.get("signal_key") or "") == "schumann.variability_24h"),
        None,
    )
    if schumann_signal:
        evidence = schumann_signal.get("evidence") or {}
        zscore = _safe_float(evidence.get("zscore_30d"))
        severity = "high" if (zscore or 0) >= 3.0 else "watch"
        event_key = "schumann_variability_high" if severity == "high" else "schumann_variability_elevated"
        title = "Schumann elevated" if severity == "watch" else "Schumann variability high"
        body = "Resonance variability is running above baseline. Open Gaia Eyes for context."
        out.append(
            NotificationCandidate(
                family="schumann",
                event_key=event_key,
                severity=severity,
                title=title,
                body=body,
                target_type="driver",
                target_key="schumann",
                asof=evidence.get("ts") or asof,
                payload={"signal": schumann_signal},
            )
        )

    return out


def _build_local_candidates(local_payload: Dict[str, Any]) -> List[NotificationCandidate]:
    out: List[NotificationCandidate] = []
    payload = _normalize_local_payload(local_payload)
    weather = payload.get("weather") or {}
    air = payload.get("air") or {}
    asof = payload.get("asof") or payload.get("as_of")

    pressure_12h = _safe_float(weather.get("baro_delta_12h_hpa") or weather.get("pressure_delta_12h"))
    pressure_24h = _safe_float(weather.get("baro_delta_24h_hpa") or weather.get("pressure_delta_24h_hpa"))
    abs_pressure_12h = abs(pressure_12h) if pressure_12h is not None else 0.0
    abs_pressure_24h = abs(pressure_24h) if pressure_24h is not None else 0.0
    if abs_pressure_24h >= 12 or abs_pressure_12h >= 10:
        out.append(
            NotificationCandidate(
                family="pressure",
                event_key="pressure_swing_high",
                severity="high",
                title="Pressure swing — High",
                body="Head pressure and pain sensitivity may rise for some people. Open Gaia Eyes for context.",
                target_type="driver",
                target_key="pressure",
                asof=asof,
                payload={"pressure_delta_12h_hpa": pressure_12h, "pressure_delta_24h_hpa": pressure_24h},
            )
        )
    elif abs_pressure_24h >= 8 or abs_pressure_12h >= 6:
        out.append(
            NotificationCandidate(
                family="pressure",
                event_key="pressure_swing_watch",
                severity="watch",
                title="Pressure swing — Watch",
                body="Pressure is shifting enough to be worth a closer look. Open Gaia Eyes for context.",
                target_type="driver",
                target_key="pressure",
                asof=asof,
                payload={"pressure_delta_12h_hpa": pressure_12h, "pressure_delta_24h_hpa": pressure_24h},
            )
        )

    aqi = _safe_float(air.get("aqi"))
    if aqi is not None:
        if aqi >= 101:
            out.append(
                NotificationCandidate(
                    family="aqi",
                    event_key="aqi_unhealthy",
                    severity="high",
                    title="AQI elevated",
                    body="Air quality is trending less friendly right now. Open Gaia Eyes for local guidance.",
                    target_type="driver",
                    target_key="aqi",
                    asof=asof,
                    payload={"aqi": aqi},
                )
            )
        elif aqi >= 51:
            out.append(
                NotificationCandidate(
                    family="aqi",
                    event_key="aqi_moderate",
                    severity="watch",
                    title="AQI moderate",
                    body="Air quality is trending less friendly. Open Gaia Eyes for local guidance.",
                    target_type="driver",
                    target_key="aqi",
                    asof=asof,
                    payload={"aqi": aqi},
                )
            )

    temp_delta = _safe_float(weather.get("temp_delta_24h_c") or weather.get("temp_delta_24h"))
    abs_temp = abs(temp_delta) if temp_delta is not None else 0.0
    if abs_temp >= 12:
        out.append(
            NotificationCandidate(
                family="temp",
                event_key="temp_swing_high",
                severity="high",
                title="Temperature swing — High",
                body="A larger temperature swing is in play. Open Gaia Eyes for local guidance.",
                target_type="driver",
                target_key="temp",
                asof=asof,
                payload={"temp_delta_24h_c": temp_delta},
            )
        )
    elif abs_temp >= 8:
        out.append(
            NotificationCandidate(
                family="temp",
                event_key="temp_swing_watch",
                severity="watch",
                title="Temperature swing — Watch",
                body="Temperature is moving enough to be worth a closer look. Open Gaia Eyes for local guidance.",
                target_type="driver",
                target_key="temp",
                asof=asof,
                payload={"temp_delta_24h_c": temp_delta},
            )
        )

    return out


def _gauge_related_driver_active(gauge_key: str, context: Dict[str, bool]) -> bool:
    if gauge_key == "pain":
        return context["pressure_active"] or context["temp_active"]
    if gauge_key == "energy":
        return context["solar_wind_active"] or context["geomagnetic_active"] or context["temp_active"] or context["aqi_active"]
    if gauge_key == "sleep":
        return context["solar_wind_active"] or context["geomagnetic_active"] or context["schumann_active"]
    if gauge_key == "heart":
        return context["solar_wind_active"] or context["geomagnetic_active"]
    if gauge_key == "health_status":
        return context["any_environment_active"]
    return False


def _gauge_context_matches(gauge_key: str, profile) -> bool:
    if gauge_key == "pain":
        return profile.includes_any(HEAD_PRESSURE_KEYS) or profile.includes_any(PAIN_FLARE_KEYS)
    if gauge_key == "energy":
        return (
            profile.includes_any(PAIN_FLARE_KEYS)
            or profile.includes_any(AUTONOMIC_KEYS)
            or profile.includes_any(SLEEP_DISRUPTION_KEYS)
            or profile.has_any("geomagnetic_sensitive")
        )
    if gauge_key == "sleep":
        return profile.includes_any(SLEEP_DISRUPTION_KEYS) or profile.has_any("geomagnetic_sensitive")
    if gauge_key == "heart":
        return profile.includes_any(AUTONOMIC_KEYS) or profile.has_any("geomagnetic_sensitive")
    if gauge_key == "health_status":
        return bool(getattr(profile, "all_tags", None))
    return False


def _gauge_message(gauge_key: str) -> tuple[str, str]:
    if gauge_key == "pain":
        return (
            "Pain load increased",
            "Pressure and temperature shifts may be contributing. Tap to review and log symptoms.",
        )
    if gauge_key == "energy":
        return (
            "Energy load increased",
            "Environmental changes may be contributing to a heavier body load. Open Gaia Eyes for context.",
        )
    if gauge_key == "sleep":
        return (
            "Sleep load increased",
            "Space weather or resonance changes may be adding variability. Open Gaia Eyes for context.",
        )
    if gauge_key == "heart":
        return (
            "Heart load increased",
            "Solar wind conditions may be affecting rhythm sensitivity. Open Gaia Eyes for context.",
        )
    return (
        "Health status shifted upward",
        "Environmental conditions may be adding to your current load. Open Gaia Eyes for context.",
    )


def _build_gauge_candidates(
    *,
    gauges_row: Dict[str, Any],
    deltas: Dict[str, int],
    active_states: List[Dict[str, Any]],
    sensitivity: str,
    profile,
    asof: str | None,
) -> List[NotificationCandidate]:
    if not gauges_row:
        return []

    threshold_delta = 10 if sensitivity == "detailed" else 12
    context = _signal_context(active_states)
    out: List[NotificationCandidate] = []

    for gauge_key in sorted(_GAUGE_FAMILIES):
        current_value = _safe_float(gauges_row.get(gauge_key))
        delta = int(deltas.get(gauge_key) or 0)
        previous_value = previous_gauge_value(current_value, delta)
        current_zone = gauge_zone(current_value)
        previous_zone = gauge_zone(previous_value)

        entered_elevated = (
            current_value is not None
            and current_value >= 60
            and (previous_value is None or previous_value < 60)
        )
        spike_up = delta >= threshold_delta

        if not entered_elevated and not spike_up:
            continue
        if not _gauge_related_driver_active(gauge_key, context):
            continue
        if sensitivity != "detailed" and not _gauge_context_matches(gauge_key, profile):
            continue

        severity = "high" if (current_value or 0) >= 80 or delta >= 15 else "watch"
        if spike_up and severity == "high":
            event_key = f"{gauge_key}_spike_high"
        elif spike_up:
            event_key = f"{gauge_key}_spike_watch"
        elif current_zone == "high" and previous_zone != "high":
            event_key = f"{gauge_key}_high"
        else:
            event_key = f"{gauge_key}_elevated"

        title, body = _gauge_message(gauge_key)
        out.append(
            NotificationCandidate(
                family=gauge_key,
                event_key=event_key,
                severity=severity,
                title=title,
                body=body,
                target_type="gauge",
                target_key=gauge_key,
                asof=asof,
                payload={
                    "gauge": gauge_key,
                    "current_value": current_value,
                    "delta": delta,
                    "current_zone": current_zone,
                    "previous_zone": previous_zone,
                },
            )
        )

    return out


def _collapse_candidates_by_family(candidates: Iterable[NotificationCandidate]) -> List[NotificationCandidate]:
    chosen: Dict[str, NotificationCandidate] = {}
    for candidate in candidates:
        existing = chosen.get(candidate.family)
        if existing is None:
            chosen[candidate.family] = candidate
            continue
        if candidate.severity == "high" and existing.severity != "high":
            chosen[candidate.family] = candidate
    return list(chosen.values())


def _build_candidates_for_user(user_id: str, day: date, preferences: Dict[str, Any]) -> List[NotificationCandidate]:
    definition, _ = load_definition_base()
    local_payload = get_local_payload(user_id, day)
    active_states = resolve_signals(user_id, day, local_payload=local_payload, definition=definition)
    active_states = active_states if isinstance(active_states, list) else []

    space_daily = _fetch_space_weather_daily(day)
    cme_row = _fetch_next_cme_arrival(utc_now())
    sep_row = _fetch_latest_sep()
    gauges_row = _fetch_gauges_row(user_id, day)
    deltas = _fetch_gauge_deltas(user_id, day)

    tags = fetch_user_tags(user_id)
    profile = build_personalization_profile(tags)

    local_data = _normalize_local_payload(local_payload)
    local_asof = local_data.get("asof") or local_data.get("as_of")
    gauge_day = gauges_row.get("day")
    gauge_asof = f"{gauge_day.isoformat()}T00:00:00+00:00" if isinstance(gauge_day, date) else None

    candidates: List[NotificationCandidate] = []
    candidates.extend(
        _build_signal_candidates(
            space_daily=space_daily,
            cme_row=cme_row,
            sep_row=sep_row,
            active_states=active_states,
        )
    )
    candidates.extend(_build_local_candidates(local_data))
    candidates.extend(
        _build_gauge_candidates(
            gauges_row=gauges_row,
            deltas=deltas,
            active_states=active_states,
            sensitivity=str(preferences.get("sensitivity") or "normal"),
            profile=profile,
            asof=local_asof or gauge_asof,
        )
    )
    return _collapse_candidates_by_family(candidates)


def evaluate_user_notifications(user_id: str, day: date, preferences: Dict[str, Any]) -> Dict[str, int]:
    now_utc = utc_now()
    candidates = _build_candidates_for_user(user_id, day, preferences)
    latest_events = _latest_events_by_family(user_id)
    queued = 0
    skipped = 0

    for candidate in candidates:
        if not _family_allowed(preferences, candidate.family, candidate.severity):
            continue

        previous_event = latest_events.get(candidate.family) or {}
        if not can_emit_with_cooldown(
            previous_created_at=previous_event.get("created_at"),
            previous_severity=str(previous_event.get("severity") or "").strip().lower() or None,
            family=candidate.family,
            current_severity=candidate.severity,
            now_utc=now_utc,
        ):
            continue

        if is_within_quiet_hours(
            now_utc,
            enabled=bool(preferences.get("quiet_hours_enabled")),
            time_zone_name=str(preferences.get("time_zone") or "UTC"),
            quiet_start=str(preferences.get("quiet_start") or "22:00"),
            quiet_end=str(preferences.get("quiet_end") or "08:00"),
        ):
            if _queue_candidate(
                user_id=user_id,
                candidate=candidate,
                now_utc=now_utc,
                status="skipped",
                error_text="quiet_hours",
            ):
                skipped += 1
                latest_events[candidate.family] = {
                    "family": candidate.family,
                    "severity": candidate.severity,
                    "status": "skipped",
                    "created_at": now_utc,
                    "event_key": candidate.event_key,
                }
            continue

        if _queue_candidate(
            user_id=user_id,
            candidate=candidate,
            now_utc=now_utc,
            status="queued",
            error_text=None,
        ):
            queued += 1
            latest_events[candidate.family] = {
                "family": candidate.family,
                "severity": candidate.severity,
                "status": "queued",
                "created_at": now_utc,
                "event_key": candidate.event_key,
            }

    return {"queued": queued, "skipped": skipped, "candidates": len(candidates)}


def _iter_user_rows(rows: Iterable[Dict[str, Any]], limit: int | None) -> Iterable[Dict[str, Any]]:
    count = 0
    for row in rows:
        yield row
        count += 1
        if limit and count >= limit:
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate push notification candidates for Gaia Eyes users.")
    parser.add_argument("--day", default=_today_utc(), help="Day in YYYY-MM-DD (UTC).")
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of users processed.")
    args = parser.parse_args()

    day = _coerce_day(args.day)
    user_rows = _fetch_notification_users(limit=args.limit, user_id=args.user_id)
    logger.info("[push-eval] users=%d day=%s", len(user_rows), day.isoformat())

    total_queued = 0
    total_skipped = 0
    for row in _iter_user_rows(user_rows, args.limit):
        user_id = str(row.get("user_id") or "").strip()
        if not user_id:
            continue
        preferences = normalize_preferences(row)
        try:
            result = evaluate_user_notifications(user_id, day, preferences)
            total_queued += result["queued"]
            total_skipped += result["skipped"]
            logger.info(
                "[push-eval] user=%s queued=%d skipped=%d candidates=%d",
                user_id,
                result["queued"],
                result["skipped"],
                result["candidates"],
            )
        except Exception as exc:
            logger.exception("[push-eval] user=%s failed: %s", user_id, exc)

    logger.info("[push-eval] done queued=%d skipped=%d", total_queued, total_skipped)


if __name__ == "__main__":
    main()
