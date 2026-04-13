#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from services.db import pg
from bots.definitions.load_definition_base import load_definition_base
from bots.gauges.db_utils import pick_column, table_columns, upsert_row
from bots.gauges.signal_resolver import resolve_signals
from bots.gauges.local_payload import get_local_payload
from services.gauges.alerts import dedupe_alert_pills
from services.personalization.health_context import (
    build_personalization_profile,
    exposure_personalization_multiplier,
    gauge_personalization_multiplier,
    health_status_contextual_adjustment,
)


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = os.getenv("GAIA_TIMEZONE", "America/Chicago")
try:
    LOCAL_TZ = ZoneInfo(DEFAULT_TIMEZONE)
except Exception:
    DEFAULT_TIMEZONE = "America/Chicago"
    LOCAL_TZ = ZoneInfo(DEFAULT_TIMEZONE)

_METRIC_SPECS = {
    "sleep_total_minutes": {"weight": 0.25, "direction": "lower_is_worse"},
    "sleep_efficiency": {"weight": 0.20, "direction": "lower_is_worse"},
    "sleep_deep_minutes": {"weight": 0.15, "direction": "lower_is_worse"},
    "spo2_avg": {"weight": 0.15, "direction": "lower_is_worse"},
    "hr_max": {"weight": 0.10, "direction": "higher_is_worse"},
    "steps_total": {"weight": 0.05, "direction": "lower_is_worse"},
    "bp_sys_avg": {"weight": 0.05, "direction": "higher_is_worse"},
    "bp_dia_avg": {"weight": 0.05, "direction": "higher_is_worse"},
    "hrv_avg": {"weight": 0.10, "direction": "lower_is_worse"},
}
_HEALTH_CONTEXT_FIELDS = [
    "respiratory_rate_avg",
    "respiratory_rate_sleep_avg",
    "respiratory_rate_baseline_delta",
    "temperature_deviation",
    "temperature_deviation_baseline_delta",
    "temperature_source",
    "resting_hr_avg",
    "resting_hr_baseline_delta",
    "bedtime_consistency_score",
    "waketime_consistency_score",
    "sleep_debt_proxy",
    "sleep_vs_14d_baseline_delta",
    "cycle_tracking_enabled",
    "cycle_phase",
    "menstrual_active",
    "cycle_day",
]

_HRV_CANDIDATES = ["hrv_avg", "hrv_rmssd", "rmssd", "hrv", "hrv_ms"]
_DAY_CANDIDATES = ["day", "date", "day_local", "day_utc"]
_TS_CANDIDATES = ["ts_utc", "ts", "sample_ts", "created_at", "timestamp"]
_CAMERA_QUALITY_OK = {"good", "ok"}
_CAMERA_QUALITY_THRESHOLD = 0.65
_GAUGE_KEYS = ["pain", "focus", "heart", "stamina", "energy", "sleep", "mood"]
_SYMPTOM_EFFECT_KEYS = [*_GAUGE_KEYS, "health_status"]
_RECENT_MATCH_WINDOW_HOURS = 3.0

_SYMPTOM_GAUGE_EFFECTS: Dict[str, Dict[str, float]] = {
    "HEADACHE": {"pain": 1.0, "focus": 0.55, "mood": 0.2, "health_status": 0.55},
    "MIGRAINE": {"pain": 1.0, "focus": 0.65, "mood": 0.25, "health_status": 0.65},
    "PAIN": {"pain": 1.0, "stamina": 0.5, "energy": 0.25, "health_status": 0.55},
    "NERVE_PAIN": {"pain": 1.0, "stamina": 0.55, "energy": 0.3, "health_status": 0.55},
    "JOINT_PAIN": {"pain": 1.0, "stamina": 0.45, "health_status": 0.45},
    "STIFFNESS": {"pain": 0.85, "stamina": 0.45, "health_status": 0.35},
    "SINUS_PRESSURE": {"pain": 1.0, "focus": 0.25, "health_status": 0.35},
    "LIGHT_SENSITIVITY": {"pain": 0.6, "focus": 0.25, "mood": 0.15},
    "ZAPS": {"pain": 0.6, "health_status": 0.2},
    "FATIGUE": {"energy": 1.0, "stamina": 0.7, "focus": 0.45, "mood": 0.2, "health_status": 0.6},
    "DRAINED": {"energy": 1.0, "stamina": 0.8, "focus": 0.4, "mood": 0.25, "health_status": 0.65},
    "BRAIN_FOG": {"focus": 0.9, "energy": 0.6, "mood": 0.45, "health_status": 0.3},
    "FOCUS_DRIFT": {"focus": 0.8, "energy": 0.3},
    "INSOMNIA": {"sleep": 1.0, "energy": 0.55, "mood": 0.2, "health_status": 0.6},
    "RESTLESS_SLEEP": {"sleep": 1.0, "energy": 0.5, "mood": 0.2, "health_status": 0.5},
    "WIRED": {"sleep": 0.65, "mood": 0.75, "energy": 0.25, "health_status": 0.3},
    "ANXIOUS": {"mood": 1.0, "heart": 0.35, "sleep": 0.4, "focus": 0.25, "health_status": 0.35},
    "PALPITATIONS": {"heart": 1.0, "mood": 0.25, "health_status": 0.55},
    "CHEST_TIGHTNESS": {"heart": 1.0, "energy": 0.25, "mood": 0.25, "health_status": 0.6},
    "RESP_IRRITATION": {"heart": 0.55, "energy": 0.45, "mood": 0.2, "health_status": 0.55},
}

_SYMPTOM_CLUSTER_WEIGHTS: Dict[str, str] = {
    "HEADACHE": "pain",
    "MIGRAINE": "pain",
    "PAIN": "pain",
    "NERVE_PAIN": "pain",
    "JOINT_PAIN": "pain",
    "STIFFNESS": "pain",
    "SINUS_PRESSURE": "pain",
    "LIGHT_SENSITIVITY": "pain",
    "ZAPS": "pain",
    "FATIGUE": "energy",
    "DRAINED": "energy",
    "BRAIN_FOG": "energy",
    "WIRED": "sleep",
    "INSOMNIA": "sleep",
    "RESTLESS_SLEEP": "sleep",
    "ANXIOUS": "mood",
    "PALPITATIONS": "heart",
    "CHEST_TIGHTNESS": "heart",
    "RESP_IRRITATION": "heart",
}

_SYMPTOM_GAUGE_CAPS: Dict[str, float] = {
    "pain": 36.0,
    "focus": 18.0,
    "heart": 18.0,
    "stamina": 30.0,
    "energy": 32.0,
    "sleep": 19.0,
    "mood": 18.0,
    "health_status": 30.0,
}
_HEALTH_STATUS_SYMPTOM_WEIGHT = 0.6
_HEALTH_STATUS_SYMPTOM_CAP = 12.0

_CURRENT_SYMPTOM_STATE_MULTIPLIERS: Dict[str, float] = {
    "new": 1.0,
    "ongoing": 0.9,
    "improving": 0.7,
    "resolved": 0.0,
}

_EXPOSURE_GAUGE_EFFECTS: Dict[str, Dict[str, float]] = {
    "ALLERGEN_EXPOSURE": {"pain": 0.55, "focus": 0.45, "energy": 0.35, "sleep": 0.2, "heart": 0.15},
    "OVEREXERTION": {"stamina": 1.0, "energy": 0.75, "pain": 0.35, "sleep": 0.2, "heart": 0.15},
    "TEMPORARY_ILLNESS": {"energy": 0.8, "pain": 0.45, "focus": 0.4, "sleep": 0.35, "heart": 0.25, "mood": 0.15},
}

_EXPOSURE_GAUGE_CAPS: Dict[str, float] = {
    "pain": 10.0,
    "focus": 8.0,
    "heart": 6.0,
    "stamina": 12.0,
    "energy": 10.0,
    "sleep": 8.0,
    "mood": 5.0,
}


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


def _normalize_symptom_code(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("-", "_").replace(" ", "_").upper()


def _symptom_label(value: Any) -> str:
    normalized = _normalize_symptom_code(value)
    if not normalized:
        return ""
    return normalized.replace("_", " ").lower().capitalize()


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _local_day_bounds(day: date) -> Tuple[datetime, datetime]:
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=LOCAL_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _serialize_iso_utc(ts: Any) -> Optional[str]:
    if not isinstance(ts, datetime):
        return None
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_day(day_val: date) -> str:
    return day_val.isoformat()


def _hash_inputs(snapshot: Dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fetch_local_payload(user_id: str, day: date) -> Optional[Dict[str, Any]]:
    return get_local_payload(user_id, day)


def fetch_user_tags(user_id: str) -> List[Dict[str, Any]]:
    ut_cols = table_columns("app", "user_tags")
    if not ut_cols:
        return []
    cat_cols = table_columns("dim", "user_tag_catalog")

    join_clause = ""
    if "tag_id" in ut_cols and "id" in cat_cols:
        join_clause = "left join dim.user_tag_catalog c on ut.tag_id = c.id"
    elif "tag_key" in ut_cols and "tag_key" in cat_cols:
        join_clause = "left join dim.user_tag_catalog c on ut.tag_key = c.tag_key"

    select_cols = ["ut.*"]
    if "label" in cat_cols:
        select_cols.append("c.label as tag_label")
    if "tag_key" in cat_cols and "tag_key" not in ut_cols:
        select_cols.append("c.tag_key as tag_key")
    if "section" in cat_cols:
        select_cols.append("c.section as tag_section")
    elif "tag_type" in cat_cols:
        select_cols.append("c.tag_type as tag_section")

    sql = f"""
        select {', '.join(select_cols)}
          from app.user_tags ut
          {join_clause}
         where ut.user_id = %s
    """
    try:
        return pg.fetch(sql, user_id)
    except Exception:
        return []


def fetch_symptom_summary(user_id: str, day: date) -> Dict[str, Any]:
    start, end = _local_day_bounds(day)
    episode_rows: List[Dict[str, Any]] = []
    episode_cols = table_columns("raw", "user_symptom_episodes")
    if episode_cols:
        try:
            episode_rows = pg.fetch(
                """
                select symptom_code,
                       coalesce(current_severity, original_severity) as severity,
                       last_interaction_at as ts_utc,
                       latest_note_text as free_text,
                       current_state
                  from raw.user_symptom_episodes
                 where user_id = %s
                   and last_interaction_at >= %s
                   and last_interaction_at < %s
                   and current_state in ('new', 'ongoing', 'improving')
                 order by last_interaction_at desc
                """,
                user_id,
                start,
                end,
            ) or []
        except Exception:
            episode_rows = []

    try:
        rows = pg.fetch(
            """
            select symptom_code, severity, ts_utc, free_text, tags
              from raw.user_symptom_events
             where user_id = %s
               and ts_utc >= %s
               and ts_utc < %s
             order by ts_utc desc
            """,
            user_id,
            start,
            end,
        )
    except Exception:
        rows = []

    return _build_symptom_signal_summary([*(rows or []), *episode_rows])


def _severity_points(value: Any) -> float:
    severity = _safe_float(value)
    if severity is None:
        severity = 5.0
    if severity <= 2.0:
        return 2.0
    if severity <= 4.0:
        return 4.0
    if severity <= 6.0:
        return 7.0
    if severity <= 8.0:
        return 10.0
    return 13.0


def _recency_multiplier(ts_utc: Optional[datetime], *, asof: Optional[datetime] = None) -> float:
    if ts_utc is None:
        return 0.25
    anchor = asof or datetime.now(timezone.utc)
    age_hours = max(0.0, (anchor - ts_utc.astimezone(timezone.utc)).total_seconds() / 3600.0)
    if age_hours <= 3.0:
        return 1.0
    if age_hours <= 8.0:
        return 0.6
    if age_hours <= 24.0:
        return 0.25
    return 0.0


def _is_recent_symptom(ts_utc: Optional[datetime], *, asof: Optional[datetime] = None) -> bool:
    if ts_utc is None:
        return False
    anchor = asof or datetime.now(timezone.utc)
    age_hours = max(0.0, (anchor - ts_utc.astimezone(timezone.utc)).total_seconds() / 3600.0)
    return age_hours <= _RECENT_MATCH_WINDOW_HOURS


def _state_multiplier(value: Any) -> float:
    token = str(value or "new").strip().lower()
    return _CURRENT_SYMPTOM_STATE_MULTIPLIERS.get(token, 1.0)


def _build_symptom_signal_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    gauge_boosts: Dict[str, float] = {key: 0.0 for key in _SYMPTOM_EFFECT_KEYS}
    recent_gauge_boosts: Dict[str, float] = {key: 0.0 for key in _SYMPTOM_EFFECT_KEYS}
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    cluster_keys: set[str] = set()
    last_symptom_at: Optional[datetime] = None
    max_severity: Optional[float] = None

    for raw in events:
        code = _normalize_symptom_code(raw.get("symptom_code"))
        severity = _safe_float(raw.get("severity"))
        ts_utc = raw.get("last_interaction_at") or raw.get("state_updated_at") or raw.get("ts_utc")
        if isinstance(ts_utc, str):
            try:
                ts_utc = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
            except Exception:
                ts_utc = None
        if isinstance(ts_utc, datetime) and ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=timezone.utc)

        state_mult = _state_multiplier(raw.get("current_state") or raw.get("state"))
        if state_mult <= 0:
            continue

        grouped[code].append(
            {
                "symptom_code": code,
                "severity": severity,
                "ts_utc": ts_utc,
                "free_text": raw.get("free_text"),
                "tags": raw.get("tags"),
                "current_state": raw.get("current_state") or raw.get("state"),
            }
        )
        if severity is not None:
            max_severity = severity if max_severity is None else max(max_severity, severity)
        if isinstance(ts_utc, datetime):
            last_symptom_at = ts_utc if last_symptom_at is None else max(last_symptom_at, ts_utc)

        effects = _SYMPTOM_GAUGE_EFFECTS.get(code) or {}
        if not effects:
            continue
        recency_mult = _recency_multiplier(ts_utc, asof=now_utc)
        if recency_mult <= 0:
            continue
        severity_points = _severity_points(severity)
        cluster_key = _SYMPTOM_CLUSTER_WEIGHTS.get(code)
        if cluster_key:
            cluster_keys.add(cluster_key)
        for gauge_key, weight in effects.items():
            contribution = severity_points * float(weight) * recency_mult * state_mult
            gauge_boosts[gauge_key] = gauge_boosts.get(gauge_key, 0.0) + contribution
            if _is_recent_symptom(ts_utc, asof=now_utc):
                recent_gauge_boosts[gauge_key] = recent_gauge_boosts.get(gauge_key, 0.0) + (
                    severity_points * float(weight) * state_mult
                )

    cluster_bonus = 0.0
    if len(cluster_keys) >= 2:
        cluster_bonus = min(5.0, float(len(cluster_keys) - 1) * 2.0)
        gauge_boosts["health_status"] = gauge_boosts.get("health_status", 0.0) + cluster_bonus
        if recent_gauge_boosts.get("health_status", 0.0) > 0:
            recent_gauge_boosts["health_status"] = recent_gauge_boosts.get("health_status", 0.0) + cluster_bonus

    top_symptoms: List[Dict[str, Any]] = []
    for code, rows in grouped.items():
        severities = [value for value in (_safe_float(item.get("severity")) for item in rows) if value is not None]
        last_ts = max(
            (item.get("ts_utc") for item in rows if isinstance(item.get("ts_utc"), datetime)),
            default=None,
        )
        top_symptoms.append(
            {
                "symptom_code": code,
                "events": len(rows),
                "max_severity": max(severities) if severities else None,
                "mean_severity": (sum(severities) / len(severities)) if severities else None,
                "last_ts": _serialize_iso_utc(last_ts),
                "current_state": str(rows[0].get("current_state") or "new"),
            }
        )
    top_symptoms.sort(
        key=lambda item: (
            -int(item.get("events") or 0),
            -(_safe_float(item.get("max_severity")) or 0.0),
            str(item.get("last_ts") or ""),
        )
    )

    gauge_boosts = {
        key: round(min(_SYMPTOM_GAUGE_CAPS.get(key, value), value), 2)
        for key, value in gauge_boosts.items()
        if value > 0
    }
    recent_gauge_boosts = {
        key: round(min(_SYMPTOM_GAUGE_CAPS.get(key, value), value), 2)
        for key, value in recent_gauge_boosts.items()
        if value > 0
    }

    return {
        "total_24h": len(events),
        "max_severity": max_severity,
        "top_symptoms": top_symptoms[:5],
        "gauge_boosts": gauge_boosts,
        "recent_gauge_boosts": recent_gauge_boosts,
        "health_status_symptom_boost": gauge_boosts.get("health_status", 0.0),
        "health_status_cluster_bonus": round(cluster_bonus, 2),
        "last_symptom_update_at": _serialize_iso_utc(last_symptom_at),
        "recent_matching_gauges": sorted(key for key, value in recent_gauge_boosts.items() if value > 0),
    }


def fetch_recent_symptom_gauge_context(user_id: str, day: date) -> Dict[str, Any]:
    summary = fetch_symptom_summary(user_id, day)
    return {
        "gauge_recent_log_boosts": summary.get("recent_gauge_boosts") or {},
        "last_symptom_update_at": summary.get("last_symptom_update_at"),
    }


def _exposure_intensity_points(value: Any) -> float:
    try:
        intensity = int(value)
    except Exception:
        intensity = 1
    intensity = max(1, min(3, intensity))
    if intensity == 1:
        return 3.0
    if intensity == 2:
        return 5.0
    return 7.0


def _exposure_recency_multiplier(
    exposure_key: str,
    ts_utc: Optional[datetime],
    *,
    asof: Optional[datetime] = None,
) -> float:
    if ts_utc is None:
        return 0.0
    anchor = asof or datetime.now(timezone.utc)
    age_hours = max(0.0, (anchor - ts_utc.astimezone(timezone.utc)).total_seconds() / 3600.0)
    if exposure_key == "OVEREXERTION":
        if age_hours <= 12.0:
            return 1.0
        if age_hours <= 24.0:
            return 0.7
        if age_hours <= 48.0:
            return 0.35
        return 0.0
    if exposure_key == "ALLERGEN_EXPOSURE":
        if age_hours <= 24.0:
            return 1.0
        if age_hours <= 48.0:
            return 0.6
        if age_hours <= 72.0:
            return 0.3
        return 0.0
    if exposure_key == "TEMPORARY_ILLNESS":
        if age_hours <= 24.0:
            return 1.0
        if age_hours <= 48.0:
            return 0.65
        if age_hours <= 72.0:
            return 0.35
        return 0.0
    return 0.0


def _is_recent_exposure(
    exposure_key: str,
    ts_utc: Optional[datetime],
    *,
    asof: Optional[datetime] = None,
) -> bool:
    if ts_utc is None:
        return False
    anchor = asof or datetime.now(timezone.utc)
    age_hours = max(0.0, (anchor - ts_utc.astimezone(timezone.utc)).total_seconds() / 3600.0)
    if exposure_key == "OVEREXERTION":
        return age_hours <= 18.0
    if exposure_key == "ALLERGEN_EXPOSURE":
        return age_hours <= 24.0
    if exposure_key == "TEMPORARY_ILLNESS":
        return age_hours <= 36.0
    return False


def fetch_exposure_summary(
    user_id: str,
    day: date,
    *,
    profile=None,
) -> Dict[str, Any]:
    cols = table_columns("raw", "user_exposure_events")
    if not cols:
        return {}

    start, end = _local_day_bounds(day)
    window_start = start - timedelta(hours=72)
    try:
        rows = pg.fetch(
            """
            select exposure_key, intensity, event_ts_utc, source, note_text
              from raw.user_exposure_events
             where user_id = %s
               and event_ts_utc >= %s
               and event_ts_utc < %s
             order by event_ts_utc desc, created_at desc
            """,
            user_id,
            window_start,
            end,
        )
    except Exception:
        rows = []

    asof = min(datetime.now(timezone.utc), end)
    return _build_exposure_signal_summary(rows or [], asof=asof, profile=profile or build_personalization_profile([]))


def _build_exposure_signal_summary(
    events: List[Dict[str, Any]],
    *,
    asof: datetime,
    profile,
) -> Dict[str, Any]:
    gauge_boosts: Dict[str, float] = {key: 0.0 for key in _GAUGE_KEYS}
    recent_gauge_boosts: Dict[str, float] = {key: 0.0 for key in _GAUGE_KEYS}
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    last_exposure_at: Optional[datetime] = None
    max_intensity: Optional[int] = None

    for raw in events:
        exposure_key = _normalize_symptom_code(raw.get("exposure_key"))
        effects = _EXPOSURE_GAUGE_EFFECTS.get(exposure_key) or {}
        if not effects:
            continue
        ts_utc = raw.get("event_ts_utc")
        if isinstance(ts_utc, str):
            try:
                ts_utc = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
            except Exception:
                ts_utc = None
        if isinstance(ts_utc, datetime) and ts_utc.tzinfo is None:
            ts_utc = ts_utc.replace(tzinfo=timezone.utc)

        recency_mult = _exposure_recency_multiplier(exposure_key, ts_utc, asof=asof)
        if recency_mult <= 0:
            continue

        intensity = max(1, min(3, int(_safe_float(raw.get("intensity")) or 1)))
        grouped[exposure_key].append(
            {
                "exposure_key": exposure_key,
                "intensity": intensity,
                "event_ts_utc": ts_utc,
                "source": raw.get("source"),
                "note_text": raw.get("note_text"),
            }
        )
        max_intensity = intensity if max_intensity is None else max(max_intensity, intensity)
        if isinstance(ts_utc, datetime):
            last_exposure_at = ts_utc if last_exposure_at is None else max(last_exposure_at, ts_utc)

        intensity_points = _exposure_intensity_points(intensity)
        for gauge_key, weight in effects.items():
            multiplier = exposure_personalization_multiplier(
                profile,
                exposure_key=exposure_key.lower(),
                gauge_key=gauge_key,
            )
            contribution = intensity_points * float(weight) * recency_mult * multiplier
            gauge_boosts[gauge_key] = gauge_boosts.get(gauge_key, 0.0) + contribution
            if _is_recent_exposure(exposure_key, ts_utc, asof=asof):
                recent_gauge_boosts[gauge_key] = recent_gauge_boosts.get(gauge_key, 0.0) + (
                    intensity_points * float(weight) * multiplier
                )

    top_exposures: List[Dict[str, Any]] = []
    for key, rows in grouped.items():
        last_ts = max(
            (item.get("event_ts_utc") for item in rows if isinstance(item.get("event_ts_utc"), datetime)),
            default=None,
        )
        top_exposures.append(
            {
                "exposure_key": key.lower(),
                "events": len(rows),
                "max_intensity": max(int(item.get("intensity") or 1) for item in rows),
                "last_ts": _serialize_iso_utc(last_ts),
                "latest_source": str(rows[0].get("source") or "manual"),
            }
        )
    top_exposures.sort(
        key=lambda item: (
            -int(item.get("events") or 0),
            -int(item.get("max_intensity") or 0),
            str(item.get("last_ts") or ""),
        )
    )

    gauge_boosts = {
        key: round(min(_EXPOSURE_GAUGE_CAPS.get(key, value), value), 2)
        for key, value in gauge_boosts.items()
        if value > 0
    }
    recent_gauge_boosts = {
        key: round(min(_EXPOSURE_GAUGE_CAPS.get(key, value), value), 2)
        for key, value in recent_gauge_boosts.items()
        if value > 0
    }

    return {
        "total_72h": len(events),
        "max_intensity": max_intensity,
        "top_exposures": top_exposures[:5],
        "gauge_boosts": gauge_boosts,
        "recent_gauge_boosts": recent_gauge_boosts,
        "last_exposure_at": _serialize_iso_utc(last_exposure_at),
        "recent_matching_gauges": sorted(key for key, value in recent_gauge_boosts.items() if value > 0),
    }


_USABLE_ENERGY_ADJUSTMENTS = {
    "plenty": -3.0,
    "enough": -1.5,
    "limited": 6.0,
    "very_limited": 10.0,
}

_ENERGY_LEVEL_ADJUSTMENTS = {
    "good": -0.8,
    "manageable": 0.0,
    "low": 1.6,
    "depleted": 3.0,
}

_ENERGY_DETAIL_ADJUSTMENTS = {
    "tired": 1.0,
    "drained": 1.8,
    "heavy_body": 1.6,
    "brain_fog": 1.4,
    "crashed_later": 1.8,
}

_CHECKIN_COMPARISON_ADJUSTMENTS = {
    "better": -0.4,
    "same": 0.0,
    "worse": 0.8,
}

_CHECKIN_RECENCY_WEIGHTS = [1.0, 0.72, 0.48, 0.28]


def fetch_recent_daily_checkins(
    user_id: str,
    day: date,
    *,
    limit: int = 4,
) -> List[Dict[str, Any]]:
    cols = table_columns("raw", "user_daily_checkins")
    if not cols:
        return []
    try:
        rows = pg.fetch(
            """
            select day,
                   compared_to_yesterday,
                   energy_level,
                   usable_energy,
                   energy_detail
              from raw.user_daily_checkins
             where user_id = %s
               and day <= %s
             order by day desc
             limit %s
            """,
            user_id,
            day,
            int(limit),
        )
        return rows or []
    except Exception:
        return []


def apply_daily_check_in_energy_adjustment(
    gauges: Dict[str, Optional[float]],
    daily_checkins: List[Dict[str, Any]],
    symptoms: Dict[str, Any],
) -> Tuple[Dict[str, Optional[float]], Dict[str, Any]]:
    adjusted = dict(gauges)
    current_energy = _safe_float(adjusted.get("energy"))
    if current_energy is None or not daily_checkins:
        return adjusted, {"adjustment": 0.0, "entries_used": 0}

    symptom_pressure = _safe_float((symptoms.get("gauge_boosts") or {}).get("energy")) or 0.0
    weighted_total = 0.0
    latest_entry: Optional[Dict[str, Any]] = None

    for idx, row in enumerate(daily_checkins[: len(_CHECKIN_RECENCY_WEIGHTS)]):
        weight = _CHECKIN_RECENCY_WEIGHTS[idx]
        usable = _normalize_token(row.get("usable_energy"))
        energy_level = _normalize_token(row.get("energy_level"))
        energy_detail = _normalize_token(row.get("energy_detail"))
        comparison = _normalize_token(row.get("compared_to_yesterday"))

        entry_points = _USABLE_ENERGY_ADJUSTMENTS.get(usable, 0.0)
        entry_points += _ENERGY_LEVEL_ADJUSTMENTS.get(energy_level, 0.0)
        entry_points += _ENERGY_DETAIL_ADJUSTMENTS.get(energy_detail, 0.0)
        entry_points += _CHECKIN_COMPARISON_ADJUSTMENTS.get(comparison, 0.0)

        if entry_points < 0 and (current_energy >= 45.0 or symptom_pressure >= 6.0):
            entry_points = 0.0

        if idx == 0 and entry_points != 0:
            latest_entry = {
                "day": row.get("day"),
                "usable_energy": usable,
                "energy_level": energy_level,
                "energy_detail": energy_detail,
                "comparison": comparison,
                "weighted_points": round(entry_points * weight, 2),
            }

        weighted_total += entry_points * weight

    capped = max(-3.0, min(12.0, weighted_total))
    adjusted["energy"] = round(min(100.0, max(0.0, current_energy + capped)), 2)
    return adjusted, {
        "adjustment": round(capped, 2),
        "entries_used": min(len(daily_checkins), len(_CHECKIN_RECENCY_WEIGHTS)),
        "latest_entry": latest_entry,
    }


def fetch_local_health_summary(user_id: str) -> Optional[Dict[str, Any]]:
    cols = table_columns("marts", "local_health_latest")
    if not cols:
        return None
    try:
        row = pg.fetchrow(
            """
            select *
              from marts.local_health_latest
             where user_id = %s
             limit 1
            """,
            user_id,
        )
        return row if row else None
    except Exception:
        return None


def fetch_daily_features(user_id: str, day: date) -> Dict[str, Any]:
    cols = table_columns("marts", "daily_features")
    if not cols:
        return {}
    fields = [m for m in [*list(_METRIC_SPECS.keys()), *_HEALTH_CONTEXT_FIELDS] if m in cols]
    if not fields:
        return {}
    sql = f"""
        select day, {', '.join(fields)}
          from marts.daily_features
         where user_id = %s and day = %s
         limit 1
    """
    row = pg.fetchrow(sql, user_id, day)
    if row:
        return row

    # Fallback: use most recent available row <= day (handles timezone/day-boundary shifts)
    sql_latest = f"""
        select day, {', '.join(fields)}
          from marts.daily_features
         where user_id = %s and day <= %s
         order by day desc
         limit 1
    """
    return pg.fetchrow(sql_latest, user_id, day) or {}


def fetch_daily_features_baseline(
    user_id: str,
    day: date,
    lookback_days: int = 30,
) -> List[Dict[str, Any]]:
    cols = table_columns("marts", "daily_features")
    if not cols:
        return []
    metrics = [m for m in _METRIC_SPECS.keys() if m in cols]
    if not metrics:
        return []
    start = day - timedelta(days=lookback_days)
    sql = f"""
        select day, {', '.join(metrics)}
          from marts.daily_features
         where user_id = %s
           and day >= %s
           and day < %s
         order by day asc
    """
    return pg.fetch(sql, user_id, start, day) or []


def fetch_hrv_fallback(
    user_id: str,
    day: date,
    today_row: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], Optional[str], Optional[float]]:
    if today_row and today_row.get("hrv_avg") is not None:
        return _safe_float(today_row.get("hrv_avg")), "marts.daily_features.hrv_avg", None

    camera_cols = table_columns("marts", "camera_health_daily")
    if camera_cols:
        rmssd_col = pick_column(camera_cols, ["rmssd_ms"])
        ln_rmssd_col = pick_column(camera_cols, ["ln_rmssd"])
        quality_score_col = pick_column(camera_cols, ["quality_score"])
        quality_label_col = pick_column(camera_cols, ["quality_label"])
        stress_col = pick_column(camera_cols, ["stress_index"])
        ts_col = pick_column(camera_cols, ["latest_ts_utc", "ts_utc"])
        if rmssd_col and quality_score_col and quality_label_col and ts_col:
            ln_expr = ln_rmssd_col if ln_rmssd_col else "null"
            stress_expr = stress_col if stress_col else "null"
            row = pg.fetchrow(
                f"""
                select {rmssd_col} as rmssd_ms,
                       {ln_expr} as ln_rmssd,
                       {quality_score_col} as quality_score,
                       {quality_label_col} as quality_label,
                       {stress_expr} as stress_index
                  from marts.camera_health_daily
                 where user_id = %s
                   and day <= %s
                 order by day desc, {ts_col} desc
                 limit 1
                """,
                user_id,
                day,
            )
            if row:
                quality_label = str(row.get("quality_label") or "").strip().lower()
                quality_score = _safe_float(row.get("quality_score")) or 0.0
                quality_ok = (
                    quality_label in _CAMERA_QUALITY_OK and
                    quality_score >= _CAMERA_QUALITY_THRESHOLD
                )
                if quality_ok:
                    stress_index = _safe_float(row.get("stress_index"))
                    rmssd = _safe_float(row.get("rmssd_ms"))
                    if rmssd is not None:
                        return rmssd, "marts.camera_health_daily.rmssd_ms", stress_index
                    ln_rmssd = _safe_float(row.get("ln_rmssd"))
                    if ln_rmssd is not None:
                        inferred_rmssd = math.exp(ln_rmssd) if ln_rmssd < 20 else None
                        if inferred_rmssd is not None:
                            return inferred_rmssd, "marts.camera_health_daily.ln_rmssd(exp)", stress_index

    cols = table_columns("gaia", "daily_summary")
    if cols:
        user_col = pick_column(cols, ["user_id"])
        day_col = pick_column(cols, _DAY_CANDIDATES)
        hrv_col = pick_column(cols, _HRV_CANDIDATES)
        if user_col and day_col and hrv_col:
            sql = f"""
                select {hrv_col} as hrv
                  from gaia.daily_summary
                 where {user_col} = %s and {day_col} = %s
                 limit 1
            """
            row = pg.fetchrow(sql, user_id, day)
            if row and row.get("hrv") is not None:
                return _safe_float(row.get("hrv")), f"gaia.daily_summary.{hrv_col}", None

    cols = table_columns("gaia", "samples")
    if cols:
        user_col = pick_column(cols, ["user_id"])
        ts_col = pick_column(cols, _TS_CANDIDATES)
        hrv_col = pick_column(cols, _HRV_CANDIDATES)
        if user_col and ts_col and hrv_col:
            start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
            end = start + timedelta(days=1)
            sql = f"""
                select avg({hrv_col}) as hrv
                  from gaia.samples
                 where {user_col} = %s
                   and {ts_col} >= %s
                   and {ts_col} < %s
            """
            row = pg.fetchrow(sql, user_id, start, end)
            if row and row.get("hrv") is not None:
                return _safe_float(row.get("hrv")), f"gaia.samples.{hrv_col}", None

    return None, None, None


def _compute_baseline_stats(
    baseline_rows: List[Dict[str, Any]],
    metrics: List[str],
) -> Tuple[int, Dict[str, Dict[str, float]]]:
    baseline_days = len(baseline_rows)
    values: Dict[str, List[float]] = {m: [] for m in metrics}

    for row in baseline_rows:
        for m in metrics:
            v = _safe_float(row.get(m))
            if v is None:
                continue
            values[m].append(v)

    stats: Dict[str, Dict[str, float]] = {}
    for m, vals in values.items():
        if len(vals) < 2:
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        std = var ** 0.5
        stats[m] = {"mean": mean, "std": std, "n": float(len(vals))}

    return baseline_days, stats


def _penalty_from_threshold(
    value: Optional[float],
    *,
    threshold: float,
    span: float,
    cap: float,
) -> float:
    if value is None or value <= threshold or span <= 0:
        return 0.0
    return min(cap, ((value - threshold) / span) * cap)


def _compute_recovery_penalties(today_row: Dict[str, Any]) -> Dict[str, Dict[str, float | str]]:
    penalties: Dict[str, Dict[str, float | str]] = {}

    sleep_delta = _safe_float(today_row.get("sleep_vs_14d_baseline_delta"))
    sleep_delta_points = _penalty_from_threshold(
        abs(sleep_delta) if sleep_delta is not None and sleep_delta < -30.0 else None,
        threshold=30.0,
        span=150.0,
        cap=6.0,
    )
    if sleep_delta_points:
        penalties["sleep_vs_14d_baseline_delta"] = {
            "label": "Last night below usual",
            "value": sleep_delta or 0.0,
            "points": round(sleep_delta_points, 2),
        }

    sleep_debt = _safe_float(today_row.get("sleep_debt_proxy"))
    sleep_debt_points = _penalty_from_threshold(
        sleep_debt,
        threshold=30.0,
        span=180.0,
        cap=12.0,
    )
    if sleep_debt_points and sleep_delta is None:
        penalties["sleep_debt_proxy"] = {
            "label": "Built-up sleep debt",
            "value": sleep_debt or 0.0,
            "points": round(sleep_debt_points, 2),
        }

    resting_hr_delta = _safe_float(today_row.get("resting_hr_baseline_delta"))
    resting_hr_points = _penalty_from_threshold(
        resting_hr_delta,
        threshold=2.0,
        span=8.0,
        cap=12.0,
    )
    if resting_hr_points:
        penalties["resting_hr_baseline_delta"] = {
            "label": "Resting HR above usual",
            "value": resting_hr_delta or 0.0,
            "points": round(resting_hr_points, 2),
        }

    respiratory_delta = _safe_float(today_row.get("respiratory_rate_baseline_delta"))
    respiratory_points = _penalty_from_threshold(
        respiratory_delta,
        threshold=1.0,
        span=3.0,
        cap=8.0,
    )
    if respiratory_points:
        penalties["respiratory_rate_baseline_delta"] = {
            "label": "Respiratory rate above usual",
            "value": respiratory_delta or 0.0,
            "points": round(respiratory_points, 2),
        }

    temperature_delta = _safe_float(today_row.get("temperature_deviation_baseline_delta"))
    if temperature_delta is None:
        temperature_delta = _safe_float(today_row.get("temperature_deviation"))
    temperature_points = _penalty_from_threshold(
        abs(temperature_delta) if temperature_delta is not None else None,
        threshold=0.2,
        span=0.6,
        cap=8.0,
    )
    if temperature_points:
        penalties["temperature_deviation"] = {
            "label": "Temperature shifted from usual",
            "value": temperature_delta or 0.0,
            "points": round(temperature_points, 2),
        }

    consistency_scores = [
        score
        for score in (
            _safe_float(today_row.get("bedtime_consistency_score")),
            _safe_float(today_row.get("waketime_consistency_score")),
        )
        if score is not None
    ]
    if consistency_scores:
        average_consistency = sum(consistency_scores) / len(consistency_scores)
        consistency_points = _penalty_from_threshold(
            100.0 - average_consistency,
            threshold=15.0,
            span=45.0,
            cap=7.0,
        )
        if consistency_points:
            penalties["sleep_consistency"] = {
                "label": "Sleep timing inconsistent",
                "value": round(average_consistency, 1),
                "points": round(consistency_points, 2),
            }

    return penalties


def apply_symptom_gauge_adjustments(
    gauges: Dict[str, Optional[float]],
    symptoms: Dict[str, Any],
) -> Tuple[Dict[str, Optional[float]], Dict[str, Any]]:
    adjusted = dict(gauges)
    applied: Dict[str, float] = {}
    drivers: List[Dict[str, Any]] = []

    all_boosts = symptoms.get("gauge_boosts") or {}
    recent_boosts = symptoms.get("recent_gauge_boosts") or {}
    if not all_boosts:
        derived_boosts: Dict[str, float] = {}
        for row in symptoms.get("top_symptoms") or []:
            code = _normalize_symptom_code(row.get("symptom_code"))
            effects = _SYMPTOM_GAUGE_EFFECTS.get(code) or {}
            if not effects:
                continue
            severity_points = _severity_points(row.get("max_severity"))
            for gauge_key, weight in effects.items():
                if gauge_key not in _GAUGE_KEYS:
                    continue
                derived_boosts[gauge_key] = derived_boosts.get(gauge_key, 0.0) + (severity_points * float(weight))
        all_boosts = derived_boosts
        recent_boosts = recent_boosts or derived_boosts
    for row in symptoms.get("top_symptoms") or []:
        code = _normalize_symptom_code(row.get("symptom_code"))
        effects = _SYMPTOM_GAUGE_EFFECTS.get(code)
        if not effects:
            continue
        drivers.append(
            {
                "symptom_code": code,
                "events": int(row.get("events") or 0),
                "max_severity": _safe_float(row.get("max_severity")),
                "last_ts": row.get("last_ts"),
            }
        )

    for gauge_key in _GAUGE_KEYS:
        points = _safe_float(all_boosts.get(gauge_key))
        if points is None or points <= 0:
            continue
        applied[gauge_key] = points

    for gauge_key, points in applied.items():
        current = _safe_float(adjusted.get(gauge_key))
        if current is None:
            continue
        capped_points = min(points, _SYMPTOM_GAUGE_CAPS.get(gauge_key, points))
        adjusted[gauge_key] = round(min(100.0, current + capped_points), 2)

    return adjusted, {
        "drivers": drivers,
        "adjustments": {key: round(value, 2) for key, value in applied.items() if value > 0},
        "recent_adjustments": {
            key: round(float(value), 2)
            for key, value in recent_boosts.items()
            if key in _GAUGE_KEYS and _safe_float(value) and float(value) > 0
        },
        "last_symptom_update_at": symptoms.get("last_symptom_update_at"),
        "health_status_symptom_boost": round(float(symptoms.get("health_status_symptom_boost") or 0.0), 2),
    }


def apply_exposure_gauge_adjustments(
    gauges: Dict[str, Optional[float]],
    exposures: Dict[str, Any],
) -> Tuple[Dict[str, Optional[float]], Dict[str, Any]]:
    adjusted = dict(gauges)
    applied: Dict[str, float] = {}
    drivers: List[Dict[str, Any]] = []

    all_boosts = exposures.get("gauge_boosts") or {}
    recent_boosts = exposures.get("recent_gauge_boosts") or {}

    for row in exposures.get("top_exposures") or []:
        exposure_key = _normalize_token(row.get("exposure_key"))
        if not exposure_key:
            continue
        drivers.append(
            {
                "exposure_key": exposure_key,
                "events": int(row.get("events") or 0),
                "max_intensity": int(row.get("max_intensity") or 1),
                "last_ts": row.get("last_ts"),
                "latest_source": row.get("latest_source"),
            }
        )

    for gauge_key in _GAUGE_KEYS:
        points = _safe_float(all_boosts.get(gauge_key))
        if points is None or points <= 0:
            continue
        applied[gauge_key] = points

    for gauge_key, points in applied.items():
        current = _safe_float(adjusted.get(gauge_key))
        if current is None:
            continue
        capped_points = min(points, _EXPOSURE_GAUGE_CAPS.get(gauge_key, points))
        adjusted[gauge_key] = round(min(100.0, current + capped_points), 2)

    return adjusted, {
        "drivers": drivers,
        "adjustments": {key: round(value, 2) for key, value in applied.items() if value > 0},
        "recent_adjustments": {
            key: round(float(value), 2)
            for key, value in recent_boosts.items()
            if key in _GAUGE_KEYS and _safe_float(value) and float(value) > 0
        },
        "last_exposure_at": exposures.get("last_exposure_at"),
    }


def _as_int_delta(today_val: Any, yesterday_val: Any) -> int:
    today_num = _safe_float(today_val)
    yday_num = _safe_float(yesterday_val)
    if today_num is None or yday_num is None:
        return 0
    return int(round(today_num - yday_num, 0))


def _upsert_gauge_delta(user_id: str, day: date, gauge_values: Dict[str, Optional[float]]) -> None:
    delta_cols = table_columns("marts", "user_gauges_delta_day")
    if not delta_cols:
        return

    yesterday = day - timedelta(days=1)
    yesterday_row = pg.fetchrow(
        """
        select pain, focus, heart, stamina, energy, sleep, mood, health_status
          from marts.user_gauges_day
         where user_id = %s
           and day = %s
         limit 1
        """,
        user_id,
        yesterday,
    ) or {}

    deltas = {
        key: _as_int_delta(gauge_values.get(key), yesterday_row.get(key))
        for key in [*_GAUGE_KEYS, "health_status"]
    }
    upsert_row(
        "marts",
        "user_gauges_delta_day",
        {
            "user_id": user_id,
            "day": day,
            "deltas_json": json.dumps(deltas, default=str),
            "updated_at": datetime.now(timezone.utc),
        },
        ["user_id", "day"],
    )


def _health_driver_impact(points: float) -> str:
    if points >= 8.0:
        return "high"
    if points >= 4.0:
        return "moderate"
    return "low"


def _format_health_driver_display(key: str, value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return ""
    if key == "sleep_debt_proxy":
        return f"{int(round(numeric))}m behind sleep need"
    if key == "sleep_vs_14d_baseline_delta":
        return f"{int(round(abs(numeric)))}m below your baseline"
    if key == "resting_hr_baseline_delta":
        return f"+{numeric:.1f} bpm vs usual"
    if key == "respiratory_rate_baseline_delta":
        return f"+{numeric:.1f} breaths/min vs usual"
    if key == "temperature_deviation":
        sign = "+" if numeric >= 0 else ""
        return f"{sign}{numeric:.2f} vs usual"
    if key == "sleep_consistency":
        return f"{numeric:.0f}/100 consistency"
    return f"{numeric:.1f}"


def _build_physiology_signals(
    today_row: Dict[str, Any],
    health_meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add_signal(key: str, *, cause_line: str, gauge_keys: List[str], priority: int = 72) -> None:
        if key in seen:
            return
        seen.add(key)
        signals.append(
            {
                "key": key,
                "cause_line": cause_line,
                "gauge_keys": gauge_keys,
                "priority": priority,
            }
        )

    recovery_penalties = health_meta.get("recovery_penalties") or {}
    sleep_delta = _safe_float((recovery_penalties.get("sleep_vs_14d_baseline_delta") or {}).get("value"))
    if sleep_delta is not None and sleep_delta <= -45:
        add_signal(
            "sleep_vs_14d_baseline_delta",
            cause_line="Last night ran shorter than your usual baseline, so recovery is still lower today.",
            gauge_keys=["energy", "sleep", "stamina", "mood", "health_status"],
            priority=80,
        )

    sleep_debt = _safe_float((recovery_penalties.get("sleep_debt_proxy") or {}).get("value"))
    if sleep_debt is not None and sleep_debt >= 60:
        add_signal(
            "sleep_debt_proxy",
            cause_line="Sleep debt has built up across recent nights, which can make recovery feel slower.",
            gauge_keys=["energy", "sleep", "stamina", "health_status"],
            priority=76,
        )

    resting_hr_delta = _safe_float((recovery_penalties.get("resting_hr_baseline_delta") or {}).get("value"))
    if resting_hr_delta is not None and resting_hr_delta >= 4:
        add_signal(
            "resting_hr_baseline_delta",
            cause_line="Resting heart rate is above your usual baseline, so recovery strain is higher.",
            gauge_keys=["heart", "energy", "stamina", "health_status"],
            priority=75,
        )

    metric_inputs = health_meta.get("metric_inputs") or {}
    hrv_input = metric_inputs.get("hrv_avg") if isinstance(metric_inputs, dict) else None
    if isinstance(hrv_input, dict):
        today = _safe_float(hrv_input.get("today"))
        mean = _safe_float(hrv_input.get("mean"))
        std = _safe_float(hrv_input.get("std"))
        if today is not None and mean is not None:
            threshold = max((std or 0.0) * 0.35, 2.5)
            if today <= (mean - threshold):
                add_signal(
                    "hrv_avg",
                    cause_line="HRV is down from your usual range, which can make recovery feel slower.",
                    gauge_keys=["heart", "energy", "sleep", "stamina", "health_status"],
                    priority=78,
                )

    respiratory_delta = _safe_float((recovery_penalties.get("respiratory_rate_baseline_delta") or {}).get("value"))
    if respiratory_delta is not None and respiratory_delta >= 2.0:
        add_signal(
            "respiratory_rate_baseline_delta",
            cause_line="Breathing rate is running above your usual baseline, which can make the day feel a little heavier.",
            gauge_keys=["heart", "energy", "health_status"],
            priority=70,
        )

    if bool(today_row.get("menstrual_active")) and str(today_row.get("cycle_phase") or "").strip().lower() in {"luteal", "menstrual"}:
        add_signal(
            "cycle_context",
            cause_line="Cycle-related load may also be adding to recovery strain right now.",
            gauge_keys=["pain", "energy", "mood", "health_status"],
            priority=62,
        )

    return signals


def build_health_status_explainer(
    today_row: Dict[str, Any],
    symptoms: Dict[str, Any],
    health_status: Optional[float],
    health_meta: Dict[str, Any],
) -> Dict[str, Any]:
    recovery_penalties = health_meta.get("recovery_penalties") or {}
    drivers: List[Dict[str, Any]] = []
    for key, payload in recovery_penalties.items():
        if not isinstance(payload, dict):
            continue
        points = _safe_float(payload.get("points"))
        if points is None or points <= 0:
            continue
        value = payload.get("value")
        drivers.append(
            {
                "key": key,
                "kind": "recovery",
                "label": str(payload.get("label") or key).strip(),
                "display": _format_health_driver_display(key, value),
                "points": round(points, 2),
                "impact": _health_driver_impact(points),
            }
        )

    symptom_points = _safe_float(health_meta.get("symptom_health_boost"))
    if symptom_points is None or symptom_points <= 0:
        symptom_points = _safe_float(symptoms.get("health_status_symptom_boost"))
    if symptom_points is None or symptom_points <= 0:
        symptom_points = min(15.0, max(0.0, (_safe_float(symptoms.get("max_severity")) or 0.0) * 1.5))
    top_symptoms = [
        _normalize_symptom_code(row.get("symptom_code"))
        for row in (symptoms.get("top_symptoms") or [])
        if _normalize_symptom_code(row.get("symptom_code"))
    ]
    if symptom_points > 0:
        summary_labels = [_symptom_label(code) for code in top_symptoms[:2] if _symptom_label(code)]
        summary_codes = ", ".join(summary_labels) if summary_labels else "Recent symptoms"
        drivers.append(
            {
                "key": "symptoms",
                "kind": "symptom",
                "label": "Current symptoms",
                "display": summary_codes,
                "points": round(symptom_points, 2),
                "impact": _health_driver_impact(symptom_points),
            }
        )

    stress_penalty = _safe_float(health_meta.get("stress_penalty"))
    if stress_penalty and stress_penalty > 0:
        drivers.append(
            {
                "key": "camera_stress_index",
                "kind": "camera",
                "label": "Camera stress read",
                "display": f"+{stress_penalty:.1f} load",
                "points": round(stress_penalty, 2),
                "impact": _health_driver_impact(stress_penalty),
            }
        )

    drivers.sort(key=lambda item: float(item.get("points") or 0.0), reverse=True)

    context_items: List[Dict[str, Any]] = []
    if bool(today_row.get("cycle_tracking_enabled")):
        cycle_phase = str(today_row.get("cycle_phase") or "").strip()
        menstrual_active = bool(today_row.get("menstrual_active"))
        cycle_day = today_row.get("cycle_day")
        if menstrual_active or cycle_phase:
            cycle_bits = []
            if cycle_phase:
                cycle_bits.append(cycle_phase.replace("_", " "))
            if cycle_day is not None:
                cycle_bits.append(f"day {cycle_day}")
            if menstrual_active and not cycle_bits:
                cycle_bits.append("menstrual phase active")
            context_items.append(
                {
                    "key": "cycle_context",
                    "label": "Cycle context",
                    "display": ", ".join(cycle_bits) if cycle_bits else "available",
                }
            )

    if health_meta.get("calibrating"):
        summary = "Health Status is still calibrating as more baseline history builds."
    elif drivers:
        labels = [str(item.get("label") or "").strip().lower() for item in drivers[:3] if str(item.get("label") or "").strip()]
        if len(labels) == 1:
            summary = f"Health Status is being pushed mainly by {labels[0]}."
        elif len(labels) == 2:
            summary = f"Health Status is being pushed mainly by {labels[0]} and {labels[1]}."
        else:
            summary = f"Health Status is being pushed mainly by {labels[0]}, {labels[1]}, and {labels[2]}."
    else:
        summary = "No strong body-load drivers stand out right now."

    return {
        "health_status": health_status,
        "summary": summary,
        "drivers": drivers[:4],
        "context": context_items,
        "physiology_signals": _build_physiology_signals(today_row, health_meta),
        "calibrating": bool(health_meta.get("calibrating")),
        "baseline_days": int(health_meta.get("baseline_days") or 0),
    }


def fetch_health_status_context(user_id: str, day: date) -> Dict[str, Any]:
    try:
        today_features = fetch_daily_features(user_id, day)
        baseline_rows = fetch_daily_features_baseline(user_id, day)
        symptoms = fetch_symptom_summary(user_id, day)
        hrv_value, hrv_source, camera_stress_index = fetch_hrv_fallback(user_id, day, today_features)
        health_status, health_meta = compute_health_status(
            today_features,
            baseline_rows,
            symptoms,
            hrv_value=hrv_value,
            hrv_source=hrv_source,
            camera_stress_index=camera_stress_index,
        )
        return build_health_status_explainer(today_features, symptoms, health_status, health_meta)
    except Exception as exc:
        logger.warning(
            "[gauges] health status explainer failed user=%s day=%s err=%s",
            user_id,
            day,
            exc,
        )
        return {}


def compute_health_status(
    today_row: Dict[str, Any],
    baseline_rows: List[Dict[str, Any]],
    symptoms: Dict[str, Any],
    *,
    hrv_value: Optional[float] = None,
    hrv_source: Optional[str] = None,
    camera_stress_index: Optional[float] = None,
) -> Tuple[Optional[float], Dict[str, Any]]:
    metrics = list(_METRIC_SPECS.keys())
    baseline_days, stats = _compute_baseline_stats(baseline_rows, metrics)
    recovery_penalties = _compute_recovery_penalties(today_row)
    recovery_penalty_total = sum(
        float(item.get("points") or 0.0) for item in recovery_penalties.values()
    )

    if baseline_days < 14:
        return None, {
            "calibrating": True,
            "baseline_days": baseline_days,
            "metrics_used": [],
            "hrv_source": hrv_source,
            "recovery_penalties": recovery_penalties,
        }

    today_values: Dict[str, float] = {}
    for m in metrics:
        if m == "hrv_avg" and hrv_value is not None:
            today_values[m] = float(hrv_value)
            continue
        v = _safe_float(today_row.get(m))
        if v is not None:
            today_values[m] = v

    metric_inputs = {}
    weights: Dict[str, float] = {}
    for m, spec in _METRIC_SPECS.items():
        if m not in today_values:
            continue
        stat = stats.get(m)
        if not stat or not stat.get("std") or stat.get("std") == 0:
            continue
        weights[m] = float(spec["weight"])
        metric_inputs[m] = {
            "today": today_values[m],
            "mean": stat["mean"],
            "std": stat["std"],
            "direction": spec["direction"],
        }

    if not weights and recovery_penalty_total <= 0:
        return None, {
            "calibrating": True,
            "baseline_days": baseline_days,
            "metrics_used": [],
            "hrv_source": hrv_source,
            "reason": "no_metrics",
        }

    weight_sum = sum(weights.values())
    if weight_sum <= 0 and recovery_penalty_total <= 0:
        return None, {
            "calibrating": True,
            "baseline_days": baseline_days,
            "metrics_used": [],
            "hrv_source": hrv_source,
            "reason": "no_weights",
        }

    load_raw = 0.0
    if weight_sum > 0:
        for m, spec in _METRIC_SPECS.items():
            if m not in metric_inputs:
                continue
            w = weights[m] / weight_sum
            today = metric_inputs[m]["today"]
            mean = metric_inputs[m]["mean"]
            std = metric_inputs[m]["std"]
            z = (today - mean) / std
            z = max(-3.0, min(3.0, z))
            if spec["direction"] == "lower_is_worse":
                bad = max(0.0, -z)
            else:
                bad = max(0.0, z)
            load_raw += w * bad

    health_status = min(100.0, round(load_raw * 30.0, 0))
    if recovery_penalty_total:
        health_status = min(100.0, round(health_status + recovery_penalty_total, 1))

    symptom_health_boost_raw = _safe_float(symptoms.get("health_status_symptom_boost"))
    if symptom_health_boost_raw is None or symptom_health_boost_raw <= 0:
        severity_max = _safe_float(symptoms.get("max_severity"))
        if severity_max:
            symptom_health_boost_raw = min(15.0, severity_max * 1.5)
    symptom_health_boost = 0.0
    if symptom_health_boost_raw and symptom_health_boost_raw > 0:
        symptom_health_boost = min(
            _HEALTH_STATUS_SYMPTOM_CAP,
            round(float(symptom_health_boost_raw) * _HEALTH_STATUS_SYMPTOM_WEIGHT, 2),
        )
        health_status = min(100.0, health_status + symptom_health_boost)

    stress_penalty = 0.0
    if camera_stress_index is not None:
        stress = max(0.0, float(camera_stress_index))
        if stress > 80.0:
            # Mild additional strain weight when camera quality is already vetted.
            stress_penalty = min(8.0, ((stress - 80.0) / 220.0) * 8.0)
            health_status = min(100.0, round(health_status + stress_penalty, 1))

    return health_status, {
        "calibrating": False,
        "baseline_days": baseline_days,
        "metrics_used": list(metric_inputs.keys()),
        "metric_inputs": metric_inputs,
        "recovery_penalties": recovery_penalties,
        "recovery_penalty_total": round(recovery_penalty_total, 2),
        "hrv_source": hrv_source,
        "camera_stress_index": camera_stress_index,
        "stress_penalty": round(stress_penalty, 2) if stress_penalty else 0.0,
        "symptom_health_boost": round(float(symptom_health_boost or 0.0), 2),
        "symptom_health_boost_raw": round(float(symptom_health_boost_raw or 0.0), 2),
    }


def _build_alerts(definition: Dict[str, Any], active_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rules = (definition.get("alert_pills") or {}).get("rules") or []
    alerts: List[Dict[str, Any]] = []
    severity_rank = {"info": 1, "watch": 2, "high": 3}

    for rule in rules:
        trigger = rule.get("trigger") or {}
        key = trigger.get("signal_key")
        states = trigger.get("state_any_of") or []
        matches = [s for s in active_states if s.get("signal_key") == key and s.get("state") in states]
        if not matches:
            continue

        severity_map = rule.get("severity_by_state") or {}
        severity = "info"
        for m in matches:
            cand = severity_map.get(m.get("state")) or "info"
            if severity_rank.get(cand, 0) > severity_rank.get(severity, 0):
                severity = cand

        alerts.append(
            {
                "key": rule.get("key"),
                "title": rule.get("title"),
                "severity": severity,
                "triggered_by": [{"signal_key": m.get("signal_key"), "state": m.get("state")} for m in matches],
                "suggested_actions": rule.get("suggested_actions") or [],
            }
        )

    return dedupe_alert_pills(alerts)


def _compute_trend(
    user_id: str,
    day: date,
    gauge_values: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    prev = pg.fetchrow(
        """
        select day, pain, focus, heart, stamina, energy, sleep, mood, health_status
          from marts.user_gauges_day
         where user_id = %s and day < %s
         order by day desc
         limit 1
        """,
        user_id,
        day,
    )
    if not prev:
        return {"baseline_day": None, "gauges": {}}

    gauges = {}
    for k, v in gauge_values.items():
        if k not in prev:
            continue
        prev_val = _safe_float(prev.get(k))
        curr_val = _safe_float(v)
        if prev_val is None or curr_val is None:
            continue
        gauges[k] = {
            "prev": round(prev_val, 2),
            "curr": round(curr_val, 2),
            "delta": round(curr_val - prev_val, 2),
        }
    baseline_day = prev.get("day")
    if isinstance(baseline_day, date):
        baseline_day = baseline_day.isoformat()
    return {"baseline_day": baseline_day, "gauges": gauges}


def _score_gauges(
    definition: Dict[str, Any],
    active_states: List[Dict[str, Any]],
    *,
    profile=None,
) -> Dict[str, Optional[float]]:
    model = definition.get("scoring_model") or {}
    base_score = float(model.get("base_score", 0))
    cap_per_signal = float(model.get("cap_per_signal", 0))
    norm = definition.get("normalization") or {}
    gauge_range = norm.get("gauge_range") or {"min": 0, "max": 100}
    min_val = float(gauge_range.get("min", 0))
    max_val = float(gauge_range.get("max", 100))

    conf_map = definition.get("confidence_multiplier") or {}
    sig_defs = {s.get("key"): s for s in definition.get("signal_definitions", [])}
    profile = profile or build_personalization_profile([])

    gauges = {g["key"]: base_score for g in (definition.get("gauges") or []) if g.get("key")}

    for state in active_states:
        sig_key = state.get("signal_key")
        if not sig_key:
            continue
        sig_def = sig_defs.get(sig_key)
        if not sig_def:
            continue
        effects = sig_def.get("effects") or []
        conf = sig_def.get("confidence")
        conf_mult = float(conf_map.get(conf, 1.0))
        state_name = state.get("state")
        per_signal: Dict[str, float] = {}

        # Optional stacking reduction to avoid double-counting correlated signals
        stacking_mult = 1.0
        stacking = sig_def.get("stacking") or {}
        when_any_active = stacking.get("when_any_active") or []
        if when_any_active:
            active_keys = {s.get("signal_key") for s in active_states if s.get("signal_key")}
            if any(k in active_keys for k in when_any_active):
                try:
                    stacking_mult = float(stacking.get("multiplier", 1.0))
                except Exception:
                    stacking_mult = 1.0

        for effect in effects:
            weights = effect.get("weights_by_state") or {}
            weight = weights.get(state_name)
            if weight is None:
                continue
            weight = float(weight) * conf_mult * stacking_mult
            for g in effect.get("gauges") or []:
                contribution = weight
                if g:
                    contribution *= gauge_personalization_multiplier(
                        profile,
                        signal_key=str(sig_key),
                        gauge_key=str(g),
                    )
                per_signal[g] = per_signal.get(g, 0.0) + contribution

        for g, contrib in per_signal.items():
            if cap_per_signal:
                contrib = min(contrib, cap_per_signal)
            if g in gauges:
                gauges[g] = gauges.get(g, 0.0) + contrib

    for g, v in list(gauges.items()):
        try:
            val = float(v)
        except Exception:
            gauges[g] = None
            continue
        val = min(max(val, min_val), max_val)
        gauges[g] = round(val, 2)

    return gauges


def score_user_day(
    user_id: str,
    day: str | date | None = None,
    *,
    local_payload: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    definition, version = load_definition_base()
    day = _coerce_day(day)

    local_payload = local_payload or fetch_local_payload(user_id, day)
    active_states = resolve_signals(user_id, day, local_payload=local_payload, definition=definition)
    tags = fetch_user_tags(user_id)
    profile = build_personalization_profile(tags)
    symptoms = fetch_symptom_summary(user_id, day)
    exposures = fetch_exposure_summary(user_id, day, profile=profile)
    daily_checkins = fetch_recent_daily_checkins(user_id, day)
    wearable = fetch_local_health_summary(user_id)
    today_features = fetch_daily_features(user_id, day)
    baseline_rows = fetch_daily_features_baseline(user_id, day)
    hrv_value, hrv_source, camera_stress_index = fetch_hrv_fallback(user_id, day, today_features)
    health_status, health_meta = compute_health_status(
        today_features,
        baseline_rows,
        symptoms,
        hrv_value=hrv_value,
        hrv_source=hrv_source,
        camera_stress_index=camera_stress_index,
    )
    gauges = _score_gauges(definition, active_states, profile=profile)
    gauges, symptom_gauge_meta = apply_symptom_gauge_adjustments(gauges, symptoms)
    gauges, exposure_gauge_meta = apply_exposure_gauge_adjustments(gauges, exposures)
    gauges, daily_checkin_energy_meta = apply_daily_check_in_energy_adjustment(gauges, daily_checkins, symptoms)
    if health_status is not None:
        health_adjustment = health_status_contextual_adjustment(profile, active_states)
        if health_adjustment:
            health_status = round(min(100.0, max(0.0, float(health_status) + health_adjustment)), 2)

    alerts = _build_alerts(definition, active_states)
    if health_meta.get("calibrating"):
        alerts.append(
            {
                "key": "alert.health_calibrating",
                "title": "Calibrating health gauge",
                "severity": "info",
                "triggered_by": [{"signal_key": "health_status", "state": "calibrating"}],
                "suggested_actions": [
                    "keep logging sleep/health metrics to personalize your baseline"
                ],
            }
        )
    trend = _compute_trend(user_id, day, {**gauges, "health_status": health_status})

    inputs_snapshot = {
        "definition_version": version,
        "day": _iso_day(day),
        "active_states": active_states,
        "local_payload": local_payload,
        "tags": tags,
        "symptoms": symptoms,
        "exposures": exposures,
        "daily_checkins": daily_checkins,
        "wearable": wearable,
        "health_status_inputs": health_meta,
        "symptom_gauge_inputs": symptom_gauge_meta,
        "exposure_gauge_inputs": exposure_gauge_meta,
        "daily_checkin_energy_inputs": daily_checkin_energy_meta,
    }
    inputs_hash = _hash_inputs(inputs_snapshot)

    existing = pg.fetchrow(
        """
        select inputs_hash
          from marts.user_gauges_day
         where user_id = %s and day = %s
         limit 1
        """,
        user_id,
        day,
    )
    if existing and existing.get("inputs_hash") == inputs_hash and not force:
        return {"ok": True, "skipped": True, "user_id": user_id, "day": _iso_day(day)}

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "day": day,
        "pain": gauges.get("pain"),
        "focus": gauges.get("focus"),
        "heart": gauges.get("heart"),
        "stamina": gauges.get("stamina"),
        "energy": gauges.get("energy"),
        "sleep": gauges.get("sleep"),
        "mood": gauges.get("mood"),
        "health_status": health_status,
        "trend_json": json.dumps(trend, default=str),
        "alerts_json": json.dumps(alerts, default=str),
        "inputs_hash": inputs_hash,
        "model_version": version,
        "updated_at": datetime.now(timezone.utc),
    }

    upsert_row("marts", "user_gauges_day", payload, ["user_id", "day"])
    try:
        _upsert_gauge_delta(user_id, day, {**gauges, "health_status": health_status})
    except Exception as exc:
        logger.warning("[gauges] delta refresh failed user=%s day=%s err=%s", user_id, day, exc)
    return {"ok": True, "skipped": False, "user_id": user_id, "day": _iso_day(day)}


if __name__ == "__main__":
    uid = os.getenv("USER_ID")
    day_env = os.getenv("DAY")
    if not uid:
        raise SystemExit("USER_ID is required (env)")
    out = score_user_day(uid, day_env)
    print(json.dumps(out, indent=2))
