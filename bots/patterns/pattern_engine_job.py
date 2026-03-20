#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import defaultdict, deque
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - exercised in environments without the DB client installed.
    psycopg = None
    dict_row = None


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.personalization.health_context import canonicalize_tag_key


LOG_LEVEL = "INFO"
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

GAUGE_KEYS = [
    "pain",
    "focus",
    "heart",
    "stamina",
    "energy",
    "sleep",
    "mood",
    "health_status",
]

SENSITIVITY_FLAG_KEYS = [
    "air_quality_sensitive",
    "anxiety_sensitive",
    "geomagnetic_sensitive",
    "pressure_sensitive",
    "sleep_sensitive",
    "temperature_sensitive",
]

HEALTH_CONTEXT_FLAG_KEYS = [
    "migraine_history",
    "chronic_pain",
    "arthritis",
    "fibromyalgia",
    "hypermobility_eds",
    "pots_dysautonomia",
    "mcas_histamine",
    "allergies_sinus",
    "asthma_breathing_sensitive",
    "heart_rhythm_sensitive",
    "autoimmune_condition",
    "nervous_system_dysregulation",
    "insomnia_sleep_disruption",
]

ALL_FLAG_KEYS = SENSITIVITY_FLAG_KEYS + HEALTH_CONTEXT_FLAG_KEYS

# Symptom groupings come directly from the v1 addendum. They are observational
# groupings for self-reported logs only; they do not imply diagnosis.
OUTCOME_SYMPTOM_CODES = {
    "headache_day": {"headache", "migraine", "sinus_pressure", "light_sensitivity"},
    "pain_flare_day": {"pain", "joint_pain", "nerve_pain", "stiffness", "muscle_pain"},
    "fatigue_day": {"drained", "fatigue", "wired_tired", "low_energy"},
    "anxiety_day": {"anxious", "irritable", "panic", "restless", "wired"},
    "poor_sleep_day": {"insomnia", "restless_sleep", "poor_sleep"},
    "focus_fog_day": {"brain_fog", "focus_issues", "spacy"},
}

OUTCOME_EVENT_FIELDS = {
    "headache_day": "headache_symptom_events",
    "pain_flare_day": "pain_symptom_events",
    "fatigue_day": "fatigue_symptom_events",
    "anxiety_day": "anxiety_symptom_events",
    "poor_sleep_day": "poor_sleep_symptom_events",
    "focus_fog_day": "focus_fog_symptom_events",
}

OUTCOME_KIND = {
    "headache_day": "symptom",
    "pain_flare_day": "symptom",
    "fatigue_day": "symptom",
    "anxiety_day": "symptom",
    "poor_sleep_day": "symptom",
    "focus_fog_day": "symptom",
    "hrv_dip_day": "biometric",
    "high_hr_day": "biometric",
    "short_sleep_day": "biometric",
}

# Exposure rules are the explicit v1 thresholds from the task addendum.
SIGNAL_DEFINITIONS = {
    "pressure_drop_exposed": {
        "family": "pressure",
        "operator": "<=",
        "threshold": -6.0,
        "threshold_text": "pressure_delta_24h_hpa <= -6.0",
    },
    "pressure_swing_exposed": {
        "family": "pressure",
        "operator": "abs>=",
        "threshold": 6.0,
        "threshold_text": "abs(pressure_delta_24h_hpa) >= 6.0",
    },
    "aqi_moderate_plus_exposed": {
        "family": "aqi",
        "operator": ">=",
        "threshold": 50.0,
        "threshold_text": "aqi >= 50",
    },
    "aqi_unhealthy_plus_exposed": {
        "family": "aqi",
        "operator": ">=",
        "threshold": 100.0,
        "threshold_text": "aqi >= 100",
    },
    "pollen_overall_exposed": {
        "family": "allergens",
        "operator": "bucket>=",
        "threshold": 2.0,
        "threshold_text": "pollen_overall_level >= moderate",
    },
    "pollen_tree_exposed": {
        "family": "allergens",
        "operator": "bucket>=",
        "threshold": 2.0,
        "threshold_text": "pollen_tree_level >= moderate",
    },
    "pollen_grass_exposed": {
        "family": "allergens",
        "operator": "bucket>=",
        "threshold": 2.0,
        "threshold_text": "pollen_grass_level >= moderate",
    },
    "pollen_weed_exposed": {
        "family": "allergens",
        "operator": "bucket>=",
        "threshold": 2.0,
        "threshold_text": "pollen_weed_level >= moderate",
    },
    "pollen_mold_exposed": {
        "family": "allergens",
        "operator": "bucket>=",
        "threshold": 2.0,
        "threshold_text": "pollen_mold_level >= moderate",
    },
    "temp_swing_exposed": {
        "family": "temperature",
        "operator": "abs>=",
        "threshold": 6.0,
        "threshold_text": "abs(temp_delta_24h_c) >= 6.0",
    },
    "kp_g1_plus_exposed": {
        "family": "geomagnetic",
        "operator": ">=",
        "threshold": 5.0,
        "threshold_text": "kp_max >= 5.0",
    },
    "bz_south_exposed": {
        "family": "geomagnetic",
        "operator": "<=",
        "threshold": -8.0,
        "threshold_text": "bz_min <= -8.0",
    },
    "solar_wind_exposed": {
        "family": "solar_wind",
        "operator": ">=",
        "threshold": 550.0,
        "threshold_text": "sw_speed_avg >= 550",
    },
    "schumann_exposed": {
        "family": "schumann",
        "operator": ">=p80",
        "threshold": None,
        "threshold_text": "schumann_variability_proxy >= rolling station p80 (60 daily rows)",
    },
}

# Initial single-signal pairs from the task addendum.
ASSOCIATION_PAIRS = [
    ("pressure_swing_exposed", "headache_day"),
    ("pressure_swing_exposed", "pain_flare_day"),
    ("pressure_swing_exposed", "focus_fog_day"),
    ("aqi_moderate_plus_exposed", "fatigue_day"),
    ("aqi_moderate_plus_exposed", "focus_fog_day"),
    ("aqi_moderate_plus_exposed", "headache_day"),
    ("pollen_overall_exposed", "headache_day"),
    ("pollen_overall_exposed", "fatigue_day"),
    ("pollen_overall_exposed", "focus_fog_day"),
    ("pollen_overall_exposed", "poor_sleep_day"),
    ("pollen_tree_exposed", "headache_day"),
    ("pollen_tree_exposed", "fatigue_day"),
    ("pollen_tree_exposed", "focus_fog_day"),
    ("pollen_grass_exposed", "headache_day"),
    ("pollen_grass_exposed", "fatigue_day"),
    ("pollen_grass_exposed", "focus_fog_day"),
    ("pollen_weed_exposed", "headache_day"),
    ("pollen_weed_exposed", "fatigue_day"),
    ("pollen_weed_exposed", "focus_fog_day"),
    ("pollen_mold_exposed", "headache_day"),
    ("pollen_mold_exposed", "fatigue_day"),
    ("pollen_mold_exposed", "focus_fog_day"),
    ("temp_swing_exposed", "pain_flare_day"),
    ("temp_swing_exposed", "fatigue_day"),
    ("kp_g1_plus_exposed", "poor_sleep_day"),
    ("bz_south_exposed", "poor_sleep_day"),
    ("solar_wind_exposed", "fatigue_day"),
    ("solar_wind_exposed", "anxiety_day"),
    ("schumann_exposed", "poor_sleep_day"),
    ("schumann_exposed", "focus_fog_day"),
    ("schumann_exposed", "anxiety_day"),
    # Body-signal cards should use the biometric outcomes we already derive
    # from watch history, not just HRV. This keeps the section useful for
    # users with sleep and heart-rate data but no HRV feed.
    ("kp_g1_plus_exposed", "short_sleep_day"),
    ("bz_south_exposed", "short_sleep_day"),
    ("solar_wind_exposed", "short_sleep_day"),
    ("solar_wind_exposed", "high_hr_day"),
    ("schumann_exposed", "short_sleep_day"),
    ("solar_wind_exposed", "hrv_dip_day"),
]

# The engine is daily-grain today, so 12h uses the next-day proxy just like 24h.
LAG_SPECS = {
    0: 0,
    12: 1,
    24: 1,
    48: 2,
}


def _resolve_dsn() -> str:
    import os

    dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing SUPABASE_DB_URL, DIRECT_URL, or DATABASE_URL for database access")
    return dsn


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _coerce_day(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return _today_utc()


def _require_psycopg() -> None:
    if psycopg is None or dict_row is None:
        raise RuntimeError("psycopg is required to run the pattern engine job")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(round(float(value)))
    except Exception:
        return default


def _parse_json_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _bucket_rank(value: Any) -> int | None:
    token = str(value or "").strip().lower()
    if token == "very_high":
        return 4
    if token == "high":
        return 3
    if token == "moderate":
        return 2
    if token == "low":
        return 1
    return None


def _table_columns(conn: psycopg.Connection, schema: str, table: str) -> list[str]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select column_name
              from information_schema.columns
             where table_schema = %s
               and table_name = %s
             order by ordinal_position
            """,
            (schema, table),
        )
        return [str(row["column_name"]) for row in cur.fetchall()]


def _table_exists(conn: psycopg.Connection, schema: str, table: str) -> bool:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            select exists (
              select 1
                from information_schema.tables
               where table_schema = %s
                 and table_name = %s
            ) as ok
            """,
            (schema, table),
        )
        row = cur.fetchone() or {}
    return bool(row.get("ok"))


def _pick(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    lowered = {col.lower(): col for col in columns}
    for candidate in candidates:
        found = lowered.get(candidate.lower())
        if found:
            return found
    return None


def percentile_nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    rank = max(1, math.ceil(max(0.0, min(1.0, percentile)) * len(ordered)))
    return ordered[rank - 1]


def confidence_bucket(
    *,
    exposed_n: int,
    relative_lift: float,
    rate_diff: float,
    observed_weeks: int,
    last_outcome_day: date | None,
    as_of_day: date,
) -> str | None:
    if (
        exposed_n >= 12
        and relative_lift >= 2.2
        and rate_diff >= 0.20
        and observed_weeks >= 3
        and last_outcome_day is not None
        and last_outcome_day >= as_of_day - timedelta(days=30)
    ):
        return "Strong"
    if exposed_n >= 8 and relative_lift >= 1.8 and rate_diff >= 0.15 and observed_weeks >= 2:
        return "Moderate"
    if exposed_n >= 6 and relative_lift >= 1.4 and rate_diff >= 0.10:
        return "Emerging"
    return None


def confidence_rank(confidence: str | None) -> int:
    return {"Emerging": 1, "Moderate": 2, "Strong": 3}.get(str(confidence or ""), 0)


def select_best_lag(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            -confidence_rank(str(row.get("confidence"))),
            -float(row.get("relative_lift") or 0),
            -float(row.get("rate_diff") or 0),
            int(row.get("lag_hours") or 0),
        ),
    )[0]


def _utc_midnight(day_value: date | None) -> datetime | None:
    if day_value is None:
        return None
    return datetime.combine(day_value, time.min, tzinfo=timezone.utc)


def signal_exposure(row: dict[str, Any], signal_key: str) -> tuple[bool | None, float | None]:
    if signal_key == "pressure_drop_exposed":
        value = _safe_float(row.get("pressure_delta_24h"))
        return (value <= -6.0, -6.0) if value is not None else (None, -6.0)
    if signal_key == "pressure_swing_exposed":
        value = _safe_float(row.get("pressure_delta_24h"))
        return (abs(value) >= 6.0, 6.0) if value is not None else (None, 6.0)
    if signal_key == "aqi_moderate_plus_exposed":
        value = _safe_float(row.get("aqi"))
        return (value >= 50.0, 50.0) if value is not None else (None, 50.0)
    if signal_key == "aqi_unhealthy_plus_exposed":
        value = _safe_float(row.get("aqi"))
        return (value >= 100.0, 100.0) if value is not None else (None, 100.0)
    if signal_key == "pollen_overall_exposed":
        rank = _bucket_rank(row.get("pollen_overall_level"))
        return (rank >= 2, 2.0) if rank is not None else (None, 2.0)
    if signal_key == "pollen_tree_exposed":
        rank = _bucket_rank(row.get("pollen_tree_level"))
        return (rank >= 2, 2.0) if rank is not None else (None, 2.0)
    if signal_key == "pollen_grass_exposed":
        rank = _bucket_rank(row.get("pollen_grass_level"))
        return (rank >= 2, 2.0) if rank is not None else (None, 2.0)
    if signal_key == "pollen_weed_exposed":
        rank = _bucket_rank(row.get("pollen_weed_level"))
        return (rank >= 2, 2.0) if rank is not None else (None, 2.0)
    if signal_key == "pollen_mold_exposed":
        rank = _bucket_rank(row.get("pollen_mold_level"))
        return (rank >= 2, 2.0) if rank is not None else (None, 2.0)
    if signal_key == "temp_swing_exposed":
        value = _safe_float(row.get("temp_delta_24h"))
        return (abs(value) >= 6.0, 6.0) if value is not None else (None, 6.0)
    if signal_key == "kp_g1_plus_exposed":
        value = _safe_float(row.get("kp_max"))
        return (value >= 5.0, 5.0) if value is not None else (None, 5.0)
    if signal_key == "bz_south_exposed":
        value = _safe_float(row.get("bz_min"))
        return (value <= -8.0, -8.0) if value is not None else (None, -8.0)
    if signal_key == "solar_wind_exposed":
        value = _safe_float(row.get("sw_speed_avg"))
        return (value >= 550.0, 550.0) if value is not None else (None, 550.0)
    if signal_key == "schumann_exposed":
        proxy = _safe_float(row.get("schumann_variability_proxy"))
        threshold = _safe_float(row.get("schumann_variability_p80"))
        if proxy is None or threshold is None:
            return None, threshold
        return proxy >= threshold, threshold
    return None, None


def _fetch_rows(
    conn: psycopg.Connection,
    sql: str,
    params: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, tuple(params or []))
        return [dict(row) for row in cur.fetchall()]


def _fetch_base_daily_features(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
    user_id: str | None,
) -> list[dict[str, Any]]:
    columns = _table_columns(conn, "marts", "daily_features")
    select_columns = [
        "user_id",
        "day",
        "hr_min",
        "hr_max",
        "hrv_avg",
        "steps_total",
        "sleep_total_minutes",
        "sleep_rem_minutes",
        "sleep_core_minutes",
        "sleep_deep_minutes",
        "sleep_awake_minutes",
        "sleep_efficiency",
        "spo2_avg",
        "bp_sys_avg",
        "bp_dia_avg",
        "kp_max",
        "bz_min",
        "sw_speed_avg",
        "flares_count",
        "cmes_count",
        "sch_fundamental_avg_hz",
        "sch_cumiana_fundamental_avg_hz",
        "sch_any_fundamental_avg_hz",
    ]
    optional_columns = [
        "aurora_hp_north_gw",
        "aurora_hp_south_gw",
        "drap_absorption_polar_db",
    ]
    final_columns = [col for col in select_columns if col in columns]
    final_columns.extend([col for col in optional_columns if col in columns])

    params: list[Any] = [since_day, as_of_day]
    where = ["day >= %s", "day <= %s"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    sql = f"""
        select {", ".join(final_columns)}
          from marts.daily_features
         where {" and ".join(where)}
         order by user_id, day
    """
    return _fetch_rows(conn, sql, params)


def _fetch_gauges(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
    user_id: str | None,
) -> dict[tuple[str, date], dict[str, Any]]:
    if not _table_exists(conn, "marts", "user_gauges_day"):
        return {}
    columns = _table_columns(conn, "marts", "user_gauges_day")
    selected = ["user_id", "day"] + [key for key in GAUGE_KEYS if key in columns]
    if len(selected) <= 2:
        return {}

    params: list[Any] = [since_day, as_of_day]
    where = ["day >= %s", "day <= %s"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    sql = f"""
        select {", ".join(selected)}
          from marts.user_gauges_day
         where {" and ".join(where)}
    """
    rows = _fetch_rows(conn, sql, params)
    return {(str(row["user_id"]), row["day"]): row for row in rows}


def _fetch_gauge_deltas(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
    user_id: str | None,
) -> dict[tuple[str, date], dict[str, int]]:
    if not _table_exists(conn, "marts", "user_gauges_delta_day"):
        return {}

    params: list[Any] = [since_day, as_of_day]
    where = ["day >= %s", "day <= %s"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    sql = f"""
        select user_id, day, deltas_json
          from marts.user_gauges_delta_day
         where {" and ".join(where)}
    """
    rows = _fetch_rows(conn, sql, params)
    out: dict[tuple[str, date], dict[str, int]] = {}
    for row in rows:
        payload = _parse_json_map(row.get("deltas_json"))
        out[(str(row["user_id"]), row["day"])] = {
            f"{key}_delta": _safe_int(payload.get(key), 0) for key in GAUGE_KEYS
        }
    return out


def _build_symptom_stats(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, date], dict[str, Any]]:
    stats: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["user_id"]), row["day"])
        current = stats.setdefault(
            key,
            {
                "symptom_total_events": 0,
                "symptom_distinct_codes": 0,
                "headache_symptom_events": 0,
                "pain_symptom_events": 0,
                "fatigue_symptom_events": 0,
                "anxiety_symptom_events": 0,
                "poor_sleep_symptom_events": 0,
                "focus_fog_symptom_events": 0,
            },
        )
        events = _safe_int(row.get("events"), 0)
        code = canonicalize_tag_key(row.get("symptom_code"))
        current["symptom_total_events"] += events
        current["symptom_distinct_codes"] += 1
        for outcome_key, codes in OUTCOME_SYMPTOM_CODES.items():
            if code in codes:
                field_name = OUTCOME_EVENT_FIELDS[outcome_key]
                current[field_name] += events
    return stats


def _fetch_symptom_rows(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
    user_id: str | None,
) -> dict[tuple[str, date], dict[str, Any]]:
    params: list[Any] = [since_day, as_of_day]
    where = ["day >= %s", "day <= %s"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    if _table_exists(conn, "marts", "symptom_daily"):
        sql = f"""
            select user_id, day, symptom_code, events
              from marts.symptom_daily
             where {" and ".join(where)}
        """
        rows = _fetch_rows(conn, sql, params)
        return _build_symptom_stats(rows)

    if not _table_exists(conn, "raw", "user_symptom_events"):
        return {}

    raw_params: list[Any] = [since_day, as_of_day + timedelta(days=1)]
    raw_where = ["ts_utc >= %s", "ts_utc < %s"]
    if user_id:
        raw_where.append("user_id = %s")
        raw_params.append(user_id)

    sql = f"""
        select
          user_id,
          (ts_utc at time zone 'utc')::date as day,
          symptom_code,
          count(*) as events
        from raw.user_symptom_events
        where {" and ".join(raw_where)}
        group by user_id, (ts_utc at time zone 'utc')::date, symptom_code
    """
    rows = _fetch_rows(conn, sql, raw_params)
    return _build_symptom_stats(rows)


def _fetch_camera_rows(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
    user_id: str | None,
) -> dict[tuple[str, date], dict[str, Any]]:
    if not _table_exists(conn, "marts", "camera_health_daily"):
        return {}

    params: list[Any] = [since_day, as_of_day]
    where = ["day >= %s", "day <= %s"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    sql = f"""
        select
          user_id,
          day,
          bpm,
          rmssd_ms,
          stress_index,
          quality_score,
          quality_label
        from marts.camera_health_daily
        where {" and ".join(where)}
    """
    rows = _fetch_rows(conn, sql, params)
    return {(str(row["user_id"]), row["day"]): row for row in rows}


def _fetch_tag_flags(
    conn: psycopg.Connection,
    *,
    user_ids: set[str],
) -> dict[str, dict[str, bool]]:
    default_flags = {key: False for key in ALL_FLAG_KEYS}
    if not user_ids or not _table_exists(conn, "app", "user_tags"):
        return {user_id: dict(default_flags) for user_id in user_ids}

    columns = _table_columns(conn, "app", "user_tags")
    user_col = _pick(columns, ["user_id"])
    tag_col = _pick(columns, ["tag_key", "key", "tag", "code"])
    params: list[Any] = []

    if not user_col:
        return {user_id: dict(default_flags) for user_id in user_ids}

    sql: str
    if tag_col:
        sql = f"select {user_col} as user_id, {tag_col} as tag_key from app.user_tags"
    elif "tag_id" in columns and _table_exists(conn, "dim", "user_tag_catalog"):
        cat_columns = _table_columns(conn, "dim", "user_tag_catalog")
        if "id" not in cat_columns or "tag_key" not in cat_columns:
            return {user_id: dict(default_flags) for user_id in user_ids}
        sql = """
            select ut.user_id as user_id, c.tag_key as tag_key
              from app.user_tags ut
              left join dim.user_tag_catalog c on ut.tag_id = c.id
        """
    else:
        return {user_id: dict(default_flags) for user_id in user_ids}

    rows = _fetch_rows(conn, sql, params)
    out = {user_id: dict(default_flags) for user_id in user_ids}
    for row in rows:
        raw_user = str(row.get("user_id") or "").strip()
        if raw_user not in out:
            continue
        key = canonicalize_tag_key(row.get("tag_key"))
        if key in out[raw_user]:
            out[raw_user][key] = True
    return out


def _fetch_current_zip_map(conn: psycopg.Connection) -> dict[str, str]:
    if not _table_exists(conn, "app", "user_locations"):
        return {}
    columns = _table_columns(conn, "app", "user_locations")
    user_col = _pick(columns, ["user_id"])
    zip_col = _pick(columns, ["zip", "postal_code"])
    primary_col = _pick(columns, ["is_primary", "primary", "is_default"])
    updated_col = _pick(columns, ["updated_at", "created_at"])
    if not user_col or not zip_col:
        return {}

    order_parts = []
    if primary_col:
        order_parts.append(f"{primary_col} desc")
    if updated_col:
        order_parts.append(f"{updated_col} desc")
    order_sql = ", ".join(order_parts) if order_parts else user_col

    sql = f"""
        select distinct on ({user_col})
          {user_col} as user_id,
          {zip_col} as zip
        from app.user_locations
        where {zip_col} is not null
        order by {user_col}, {order_sql}
    """
    rows = _fetch_rows(conn, sql)
    return {str(row["user_id"]): str(row["zip"]) for row in rows if row.get("zip")}


def _fetch_day_zip_map(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
    user_id: str | None,
) -> dict[tuple[str, date], str]:
    if not _table_exists(conn, "marts", "user_location_context_day"):
        return {}
    columns = _table_columns(conn, "marts", "user_location_context_day")
    if "user_id" not in columns or "day" not in columns or "zip" not in columns:
        return {}

    params: list[Any] = [since_day, as_of_day]
    where = ["day >= %s", "day <= %s", "zip is not null"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    sql = f"""
        select user_id, day, zip
          from marts.user_location_context_day
         where {" and ".join(where)}
    """
    rows = _fetch_rows(conn, sql, params)
    return {(str(row["user_id"]), row["day"]): str(row["zip"]) for row in rows if row.get("zip")}


def _extract_local_signal_daily(payload: dict[str, Any]) -> dict[str, Any]:
    weather = payload.get("weather") if isinstance(payload.get("weather"), dict) else {}
    air = payload.get("air") if isinstance(payload.get("air"), dict) else {}
    allergens = payload.get("allergens") if isinstance(payload.get("allergens"), dict) else {}

    def _from_paths(paths: Sequence[tuple[dict[str, Any], str]]) -> float | None:
        for source, key in paths:
            value = _safe_float(source.get(key))
            if value is not None:
                return value
        return None

    return {
        "aqi": _from_paths(((air, "aqi"),)),
        "pressure": _from_paths(((weather, "pressure_hpa"),)),
        "pressure_delta_12h": _from_paths(
            (
                (weather, "baro_delta_12h_hpa"),
                (weather, "pressure_delta_12h"),
                (weather, "pressure_delta_12h_hpa"),
            )
        ),
        "pressure_delta_24h": _from_paths(
            (
                (weather, "baro_delta_24h_hpa"),
                (weather, "pressure_delta_24h"),
                (weather, "pressure_delta_24h_hpa"),
            )
        ),
        "temp_delta_24h": _from_paths(((weather, "temp_delta_24h_c"), (weather, "temp_delta_24h"))),
        "humidity": _from_paths(((weather, "humidity_pct"),)),
        "pollen_overall_index": _from_paths(((allergens, "overall_index"), (allergens, "relevance_score"))),
        "pollen_tree_index": _from_paths(((allergens, "tree_index"),)),
        "pollen_grass_index": _from_paths(((allergens, "grass_index"),)),
        "pollen_weed_index": _from_paths(((allergens, "weed_index"),)),
        "pollen_mold_index": _from_paths(((allergens, "mold_index"),)),
        "pollen_overall_level": str(allergens.get("overall_level") or allergens.get("state") or "").strip().lower() or None,
        "pollen_tree_level": str(allergens.get("tree_level") or "").strip().lower() or None,
        "pollen_grass_level": str(allergens.get("grass_level") or "").strip().lower() or None,
        "pollen_weed_level": str(allergens.get("weed_level") or "").strip().lower() or None,
        "pollen_mold_level": str(allergens.get("mold_level") or "").strip().lower() or None,
        "pollen_primary_type": str(allergens.get("primary_type") or "").strip().lower() or None,
    }


def _fetch_local_signals_daily(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
) -> dict[tuple[str, date], dict[str, Any]]:
    if not _table_exists(conn, "ext", "local_signals_cache"):
        return {}
    sql = """
        with ranked as (
          select
            zip,
            (asof at time zone 'utc')::date as day,
            asof,
            payload,
            row_number() over (
              partition by zip, (asof at time zone 'utc')::date
              order by asof desc
            ) as rn
          from ext.local_signals_cache
          where (asof at time zone 'utc')::date >= %s
            and (asof at time zone 'utc')::date <= %s
        )
        select zip, day, asof, payload
          from ranked
         where rn = 1
    """
    rows = _fetch_rows(conn, sql, [since_day, as_of_day])
    out: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        payload = _parse_json_map(row.get("payload"))
        out[(str(row["zip"]), row["day"])] = _extract_local_signal_daily(payload)
    return out


def _fetch_schumann_variability_daily(
    conn: psycopg.Connection,
    *,
    since_day: date,
    as_of_day: date,
    base_rows: Sequence[dict[str, Any]],
) -> dict[date, dict[str, Any]]:
    lookback_start = since_day - timedelta(days=61)
    series: list[dict[str, Any]] = []

    if _table_exists(conn, "marts", "schumann_daily_v2"):
        series = _fetch_rows(
            conn,
            """
            select day, f0
              from marts.schumann_daily_v2
             where day >= %s
               and day <= %s
               and f0 is not null
             order by day asc
            """,
            [lookback_start, as_of_day],
        )
    elif _table_exists(conn, "marts", "schumann_daily"):
        series = _fetch_rows(
            conn,
            """
            select day, f0_avg_hz as f0
              from marts.schumann_daily
             where station_id = 'cumiana'
               and day >= %s
               and day <= %s
               and f0_avg_hz is not null
             order by day asc
            """,
            [lookback_start, as_of_day],
        )

    if not series:
        dedup: dict[date, float] = {}
        for row in base_rows:
            day_value = row.get("day")
            f0 = _safe_float(row.get("sch_any_fundamental_avg_hz"))
            if isinstance(day_value, date) and f0 is not None and day_value not in dedup:
                dedup[day_value] = f0
        series = [{"day": day_value, "f0": value} for day_value, value in sorted(dedup.items())]

    out: dict[date, dict[str, Any]] = {}
    previous_f0: float | None = None
    proxy_window: deque[float] = deque(maxlen=60)

    for row in series:
        day_value = row.get("day")
        f0 = _safe_float(row.get("f0"))
        if not isinstance(day_value, date) or f0 is None:
            continue
        if previous_f0 is not None:
            proxy = abs(f0 - previous_f0)
            proxy_window.append(proxy)
            p80 = percentile_nearest_rank(list(proxy_window), 0.80)
            out[day_value] = {
                "schumann_variability_proxy": proxy,
                "schumann_variability_p80": p80,
                "schumann_exposed": (proxy >= p80) if p80 is not None else None,
            }
        previous_f0 = f0

    return out


def build_user_daily_features(
    *,
    base_rows: Sequence[dict[str, Any]],
    gauges: dict[tuple[str, date], dict[str, Any]],
    gauge_deltas: dict[tuple[str, date], dict[str, int]],
    symptom_stats: dict[tuple[str, date], dict[str, Any]],
    camera_rows: dict[tuple[str, date], dict[str, Any]],
    tag_flags: dict[str, dict[str, bool]],
    day_zip_map: dict[tuple[str, date], str],
    current_zip_map: dict[str, str],
    local_signals_daily: dict[tuple[str, date], dict[str, Any]],
    schumann_daily: dict[date, dict[str, Any]],
    updated_at: datetime,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for base in base_rows:
        raw_user_id = str(base.get("user_id") or "").strip()
        day_value = base.get("day")
        if not raw_user_id or not isinstance(day_value, date):
            continue

        key = (raw_user_id, day_value)
        gauge_row = gauges.get(key, {})
        delta_row = gauge_deltas.get(key, {})
        symptom_row = symptom_stats.get(key, {})
        camera_row = camera_rows.get(key, {})
        flags = tag_flags.get(raw_user_id, {flag: False for flag in ALL_FLAG_KEYS})
        zip_code = day_zip_map.get(key) or current_zip_map.get(raw_user_id)
        local_row = local_signals_daily.get((zip_code, day_value), {}) if zip_code else {}
        sch_row = schumann_daily.get(day_value, {})

        row = {
            "user_id": raw_user_id,
            "day": day_value,
            "hr_min": base.get("hr_min"),
            "hr_max": base.get("hr_max"),
            "hrv_avg": base.get("hrv_avg"),
            "steps_total": base.get("steps_total"),
            "sleep_total_minutes": base.get("sleep_total_minutes"),
            "sleep_rem_minutes": base.get("sleep_rem_minutes"),
            "sleep_core_minutes": base.get("sleep_core_minutes"),
            "sleep_deep_minutes": base.get("sleep_deep_minutes"),
            "sleep_awake_minutes": base.get("sleep_awake_minutes"),
            "sleep_efficiency": base.get("sleep_efficiency"),
            "spo2_avg": base.get("spo2_avg"),
            "bp_sys_avg": base.get("bp_sys_avg"),
            "bp_dia_avg": base.get("bp_dia_avg"),
            "kp_max": base.get("kp_max"),
            "bz_min": base.get("bz_min"),
            "sw_speed_avg": base.get("sw_speed_avg"),
            "flares_count": _safe_int(base.get("flares_count"), 0),
            "cmes_count": _safe_int(base.get("cmes_count"), 0),
            "sch_fundamental_avg_hz": base.get("sch_fundamental_avg_hz"),
            "sch_cumiana_fundamental_avg_hz": base.get("sch_cumiana_fundamental_avg_hz"),
            "sch_any_fundamental_avg_hz": base.get("sch_any_fundamental_avg_hz"),
            "schumann_variability_proxy": sch_row.get("schumann_variability_proxy"),
            "schumann_variability_p80": sch_row.get("schumann_variability_p80"),
            "aqi": local_row.get("aqi"),
            "pollen_overall_index": local_row.get("pollen_overall_index"),
            "pollen_tree_index": local_row.get("pollen_tree_index"),
            "pollen_grass_index": local_row.get("pollen_grass_index"),
            "pollen_weed_index": local_row.get("pollen_weed_index"),
            "pollen_mold_index": local_row.get("pollen_mold_index"),
            "pollen_overall_level": local_row.get("pollen_overall_level"),
            "pollen_tree_level": local_row.get("pollen_tree_level"),
            "pollen_grass_level": local_row.get("pollen_grass_level"),
            "pollen_weed_level": local_row.get("pollen_weed_level"),
            "pollen_mold_level": local_row.get("pollen_mold_level"),
            "pollen_primary_type": local_row.get("pollen_primary_type"),
            "pressure": local_row.get("pressure"),
            "pressure_delta_12h": local_row.get("pressure_delta_12h"),
            "pressure_delta_24h": local_row.get("pressure_delta_24h"),
            "temp_delta_24h": local_row.get("temp_delta_24h"),
            "humidity": local_row.get("humidity"),
            "aurora_hp_north_gw": base.get("aurora_hp_north_gw"),
            "aurora_hp_south_gw": base.get("aurora_hp_south_gw"),
            "drap_absorption_polar_db": base.get("drap_absorption_polar_db"),
            "camera_bpm": camera_row.get("bpm"),
            "camera_rmssd_ms": camera_row.get("rmssd_ms"),
            "camera_stress_index": camera_row.get("stress_index"),
            "camera_quality_score": camera_row.get("quality_score"),
            "camera_quality_label": camera_row.get("quality_label"),
            "symptom_total_events": _safe_int(symptom_row.get("symptom_total_events"), 0),
            "symptom_distinct_codes": _safe_int(symptom_row.get("symptom_distinct_codes"), 0),
            "headache_symptom_events": _safe_int(symptom_row.get("headache_symptom_events"), 0),
            "pain_symptom_events": _safe_int(symptom_row.get("pain_symptom_events"), 0),
            "fatigue_symptom_events": _safe_int(symptom_row.get("fatigue_symptom_events"), 0),
            "anxiety_symptom_events": _safe_int(symptom_row.get("anxiety_symptom_events"), 0),
            "poor_sleep_symptom_events": _safe_int(symptom_row.get("poor_sleep_symptom_events"), 0),
            "focus_fog_symptom_events": _safe_int(symptom_row.get("focus_fog_symptom_events"), 0),
            "updated_at": updated_at,
        }

        for gauge_key in GAUGE_KEYS:
            row[gauge_key] = gauge_row.get(gauge_key)
            row[f"{gauge_key}_delta"] = _safe_int(delta_row.get(f"{gauge_key}_delta"), 0)

        for flag_key in ALL_FLAG_KEYS:
            row[flag_key] = bool(flags.get(flag_key, False))

        for signal_key in SIGNAL_DEFINITIONS:
            exposed, _ = signal_exposure(row, signal_key)
            row[signal_key] = exposed

        out.append(row)

    return out


def build_user_daily_outcomes(
    feature_rows: Sequence[dict[str, Any]],
    *,
    updated_at: datetime,
) -> list[dict[str, Any]]:
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in feature_rows:
        by_user[str(row["user_id"])].append(row)

    outcome_rows: list[dict[str, Any]] = []
    for user_id, rows in by_user.items():
        rows.sort(key=lambda row: row["day"])
        hrv_history: deque[tuple[date, float]] = deque()
        hr_proxy_history: deque[tuple[date, float]] = deque()
        sleep_history: deque[tuple[date, float]] = deque()

        for row in rows:
            day_value = row["day"]
            while hrv_history and hrv_history[0][0] < day_value - timedelta(days=30):
                hrv_history.popleft()
            while hr_proxy_history and hr_proxy_history[0][0] < day_value - timedelta(days=30):
                hr_proxy_history.popleft()
            while sleep_history and sleep_history[0][0] < day_value - timedelta(days=14):
                sleep_history.popleft()

            hrv_baseline_values = [value for _, value in hrv_history]
            hr_baseline_values = [value for _, value in hr_proxy_history]
            sleep_baseline_values = [value for _, value in sleep_history]

            hrv_baseline = median(hrv_baseline_values) if len(hrv_baseline_values) >= 7 else None
            hr_baseline = median(hr_baseline_values) if len(hr_baseline_values) >= 7 else None
            sleep_baseline = median(sleep_baseline_values) if len(sleep_baseline_values) >= 5 else None

            hrv_today = _safe_float(row.get("hrv_avg"))
            hr_proxy_today = _safe_float(row.get("hr_min"))
            sleep_today = _safe_float(row.get("sleep_total_minutes"))

            headache_events = _safe_int(row.get("headache_symptom_events"), 0)
            pain_events = _safe_int(row.get("pain_symptom_events"), 0)
            fatigue_events = _safe_int(row.get("fatigue_symptom_events"), 0)
            anxiety_events = _safe_int(row.get("anxiety_symptom_events"), 0)
            poor_sleep_events = _safe_int(row.get("poor_sleep_symptom_events"), 0)
            focus_events = _safe_int(row.get("focus_fog_symptom_events"), 0)

            # Biometric flags stay nullable when there is not enough history to make a
            # conservative comparison.
            hrv_dip = None
            if hrv_today is not None and hrv_baseline is not None:
                hrv_dip = hrv_today <= (0.85 * hrv_baseline)

            high_hr = None
            if hr_proxy_today is not None and hr_baseline is not None:
                high_hr = hr_proxy_today >= (1.10 * hr_baseline)

            short_sleep = None
            if sleep_today is not None:
                short_sleep = sleep_today < 360.0
                if sleep_baseline is not None:
                    short_sleep = bool(short_sleep or sleep_today <= (0.85 * sleep_baseline))

            outcome_rows.append(
                {
                    "user_id": user_id,
                    "day": day_value,
                    "headache_day": headache_events > 0,
                    "pain_flare_day": pain_events > 0,
                    "anxiety_day": anxiety_events > 0,
                    "poor_sleep_day": poor_sleep_events > 0,
                    "fatigue_day": fatigue_events > 0,
                    "focus_fog_day": focus_events > 0,
                    "hrv_dip_day": hrv_dip,
                    "high_hr_day": high_hr,
                    "short_sleep_day": short_sleep,
                    "headache_events": headache_events,
                    "pain_flare_events": pain_events,
                    "anxiety_events": anxiety_events,
                    "poor_sleep_events": poor_sleep_events,
                    "fatigue_events": fatigue_events,
                    "focus_fog_events": focus_events,
                    "symptom_total_events": _safe_int(row.get("symptom_total_events"), 0),
                    "hrv_baseline_median": hrv_baseline,
                    "hr_baseline_median": hr_baseline,
                    "sleep_baseline_median": sleep_baseline,
                    "updated_at": updated_at,
                }
            )

            if hrv_today is not None:
                hrv_history.append((day_value, hrv_today))
            if hr_proxy_today is not None:
                hr_proxy_history.append((day_value, hr_proxy_today))
            if sleep_today is not None:
                sleep_history.append((day_value, sleep_today))

    return outcome_rows


def build_associations(
    feature_rows: Sequence[dict[str, Any]],
    outcome_rows: Sequence[dict[str, Any]],
    *,
    as_of_day: date,
    updated_at: datetime,
) -> list[dict[str, Any]]:
    features_by_user: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
    outcomes_by_user: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)

    for row in feature_rows:
        features_by_user[str(row["user_id"])][row["day"]] = row
    for row in outcome_rows:
        outcomes_by_user[str(row["user_id"])][row["day"]] = row

    association_rows: list[dict[str, Any]] = []
    for user_id, feature_map in features_by_user.items():
        outcome_map = outcomes_by_user.get(user_id, {})
        if not feature_map or not outcome_map:
            continue

        ordered_days = sorted(feature_map.keys())
        for signal_key, outcome_key in ASSOCIATION_PAIRS:
            signal_meta = SIGNAL_DEFINITIONS[signal_key]
            outcome_kind = OUTCOME_KIND.get(outcome_key, "symptom")

            for lag_hours, lag_offset in LAG_SPECS.items():
                a = b = c = d = 0
                observed_weeks: set[tuple[int, int]] = set()
                threshold_values: list[float] = []
                first_outcome_day: date | None = None
                last_outcome_day: date | None = None

                for source_day in ordered_days:
                    feature_row = feature_map[source_day]
                    exposed = feature_row.get(signal_key)
                    if exposed is None:
                        continue

                    target_day = source_day + timedelta(days=lag_offset)
                    outcome_row = outcome_map.get(target_day)
                    if not outcome_row:
                        continue

                    outcome_value = outcome_row.get(outcome_key)
                    if outcome_value is None:
                        continue

                    _, threshold_value = signal_exposure(feature_row, signal_key)
                    if threshold_value is not None:
                        threshold_values.append(threshold_value)

                    if bool(exposed):
                        if bool(outcome_value):
                            a += 1
                            if first_outcome_day is None or target_day < first_outcome_day:
                                first_outcome_day = target_day
                            if last_outcome_day is None or target_day > last_outcome_day:
                                last_outcome_day = target_day
                            iso_year, iso_week, _ = target_day.isocalendar()
                            observed_weeks.add((iso_year, iso_week))
                        else:
                            b += 1
                    else:
                        if bool(outcome_value):
                            c += 1
                        else:
                            d += 1

                exposed_n = a + b
                unexposed_n = c + d
                exposed_rate = (a / exposed_n) if exposed_n else 0.0
                unexposed_rate = (c / unexposed_n) if unexposed_n else 0.0
                relative_lift = exposed_rate / max(unexposed_rate, 0.01)
                rate_diff = exposed_rate - unexposed_rate

                odds_a = a
                odds_b = b
                odds_c = c
                odds_d = d
                if 0 in {odds_a, odds_b, odds_c, odds_d}:
                    odds_a += 0.5
                    odds_b += 0.5
                    odds_c += 0.5
                    odds_d += 0.5
                odds_ratio = (odds_a / max(odds_b, 0.5)) / (odds_c / max(odds_d, 0.5))

                confidence = confidence_bucket(
                    exposed_n=exposed_n,
                    relative_lift=relative_lift,
                    rate_diff=rate_diff,
                    observed_weeks=len(observed_weeks),
                    last_outcome_day=last_outcome_day,
                    as_of_day=as_of_day,
                )
                surfaceable = bool(
                    exposed_n >= 6
                    and unexposed_n >= 6
                    and a >= 3
                    and relative_lift >= 1.4
                    and rate_diff >= 0.10
                    and confidence is not None
                )

                threshold_to_store = None
                if threshold_values:
                    threshold_to_store = median(threshold_values)
                elif signal_meta.get("threshold") is not None:
                    threshold_to_store = float(signal_meta["threshold"])

                association_rows.append(
                    {
                        "user_id": user_id,
                        "signal_key": signal_key,
                        "signal_family": signal_meta["family"],
                        "outcome_key": outcome_key,
                        "outcome_kind": outcome_kind,
                        "lag_hours": lag_hours,
                        "lag_day_offset": lag_offset,
                        "exposure_operator": signal_meta["operator"],
                        "exposure_threshold": threshold_to_store,
                        "exposure_threshold_text": signal_meta["threshold_text"],
                        "exposed_n": exposed_n,
                        "unexposed_n": unexposed_n,
                        "exposed_outcome_n": a,
                        "unexposed_outcome_n": c,
                        "exposed_rate": round(exposed_rate, 6),
                        "unexposed_rate": round(unexposed_rate, 6),
                        "relative_lift": round(relative_lift, 6),
                        "odds_ratio": round(odds_ratio, 6),
                        "rate_diff": round(rate_diff, 6),
                        "observed_weeks": len(observed_weeks),
                        "confidence": confidence,
                        "confidence_rank": confidence_rank(confidence),
                        "surfaceable": surfaceable,
                        "first_outcome_day": first_outcome_day,
                        "last_outcome_day": last_outcome_day,
                        "first_seen_at": _utc_midnight(first_outcome_day) or updated_at,
                        "last_seen_at": _utc_midnight(last_outcome_day),
                        "updated_at": updated_at,
                    }
                )

    return association_rows


def _delete_scope(
    conn: psycopg.Connection,
    table_name: str,
    *,
    since_day: date | None,
    user_id: str | None,
    day_scoped: bool,
) -> None:
    conditions: list[str] = []
    params: list[Any] = []
    if user_id:
        conditions.append("user_id = %s")
        params.append(user_id)
    if day_scoped and since_day is not None:
        conditions.append("day >= %s")
        params.append(since_day)

    sql = f"delete from {table_name}"
    if conditions:
        sql += f" where {' and '.join(conditions)}"

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))


def _insert_rows(
    conn: psycopg.Connection,
    table_name: str,
    columns: Sequence[str],
    rows: Sequence[dict[str, Any]],
) -> None:
    if not rows:
        return
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"insert into {table_name} ({', '.join(columns)}) values ({placeholders})"
    values = [tuple(row.get(column) for column in columns) for row in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)


def _feature_insert_columns() -> list[str]:
    return [
        "user_id",
        "day",
        "hr_min",
        "hr_max",
        "hrv_avg",
        "steps_total",
        "sleep_total_minutes",
        "sleep_rem_minutes",
        "sleep_core_minutes",
        "sleep_deep_minutes",
        "sleep_awake_minutes",
        "sleep_efficiency",
        "spo2_avg",
        "bp_sys_avg",
        "bp_dia_avg",
        "kp_max",
        "bz_min",
        "sw_speed_avg",
        "flares_count",
        "cmes_count",
        "sch_fundamental_avg_hz",
        "sch_cumiana_fundamental_avg_hz",
        "sch_any_fundamental_avg_hz",
        "schumann_variability_proxy",
        "schumann_variability_p80",
        "aqi",
        "pollen_overall_index",
        "pollen_tree_index",
        "pollen_grass_index",
        "pollen_weed_index",
        "pollen_mold_index",
        "pollen_overall_level",
        "pollen_tree_level",
        "pollen_grass_level",
        "pollen_weed_level",
        "pollen_mold_level",
        "pollen_primary_type",
        "pressure",
        "pressure_delta_12h",
        "pressure_delta_24h",
        "temp_delta_24h",
        "humidity",
        "aurora_hp_north_gw",
        "aurora_hp_south_gw",
        "drap_absorption_polar_db",
        "pain",
        "focus",
        "heart",
        "stamina",
        "energy",
        "sleep",
        "mood",
        "health_status",
        "pain_delta",
        "focus_delta",
        "heart_delta",
        "stamina_delta",
        "energy_delta",
        "sleep_delta",
        "mood_delta",
        "health_status_delta",
        "symptom_total_events",
        "symptom_distinct_codes",
        "headache_symptom_events",
        "pain_symptom_events",
        "fatigue_symptom_events",
        "anxiety_symptom_events",
        "poor_sleep_symptom_events",
        "focus_fog_symptom_events",
        "camera_bpm",
        "camera_rmssd_ms",
        "camera_stress_index",
        "camera_quality_score",
        "camera_quality_label",
        "pressure_drop_exposed",
        "pressure_swing_exposed",
        "aqi_moderate_plus_exposed",
        "aqi_unhealthy_plus_exposed",
        "pollen_overall_exposed",
        "pollen_tree_exposed",
        "pollen_grass_exposed",
        "pollen_weed_exposed",
        "pollen_mold_exposed",
        "temp_swing_exposed",
        "kp_g1_plus_exposed",
        "bz_south_exposed",
        "solar_wind_exposed",
        "schumann_exposed",
        "air_quality_sensitive",
        "anxiety_sensitive",
        "geomagnetic_sensitive",
        "pressure_sensitive",
        "sleep_sensitive",
        "temperature_sensitive",
        "migraine_history",
        "chronic_pain",
        "arthritis",
        "fibromyalgia",
        "hypermobility_eds",
        "pots_dysautonomia",
        "mcas_histamine",
        "allergies_sinus",
        "asthma_breathing_sensitive",
        "heart_rhythm_sensitive",
        "autoimmune_condition",
        "nervous_system_dysregulation",
        "insomnia_sleep_disruption",
        "updated_at",
    ]


def _outcome_insert_columns() -> list[str]:
    return [
        "user_id",
        "day",
        "headache_day",
        "pain_flare_day",
        "anxiety_day",
        "poor_sleep_day",
        "fatigue_day",
        "focus_fog_day",
        "hrv_dip_day",
        "high_hr_day",
        "short_sleep_day",
        "headache_events",
        "pain_flare_events",
        "anxiety_events",
        "poor_sleep_events",
        "fatigue_events",
        "focus_fog_events",
        "symptom_total_events",
        "hrv_baseline_median",
        "hr_baseline_median",
        "sleep_baseline_median",
        "updated_at",
    ]


def _association_insert_columns() -> list[str]:
    return [
        "user_id",
        "signal_key",
        "signal_family",
        "outcome_key",
        "outcome_kind",
        "lag_hours",
        "lag_day_offset",
        "exposure_operator",
        "exposure_threshold",
        "exposure_threshold_text",
        "exposed_n",
        "unexposed_n",
        "exposed_outcome_n",
        "unexposed_outcome_n",
        "exposed_rate",
        "unexposed_rate",
        "relative_lift",
        "odds_ratio",
        "rate_diff",
        "observed_weeks",
        "confidence",
        "confidence_rank",
        "surfaceable",
        "first_outcome_day",
        "last_outcome_day",
        "first_seen_at",
        "last_seen_at",
        "updated_at",
    ]


def run_pattern_engine(
    *,
    as_of_day: date,
    days_back: int,
    user_id: str | None,
    dsn: str | None = None,
) -> dict[str, int]:
    _require_psycopg()
    since_day = as_of_day - timedelta(days=max(days_back - 1, 0))
    updated_at = datetime.now(timezone.utc)

    with psycopg.connect(dsn or _resolve_dsn(), row_factory=dict_row) as conn:
        base_rows = _fetch_base_daily_features(conn, since_day=since_day, as_of_day=as_of_day, user_id=user_id)
        if not base_rows and user_id is None:
            logger.warning(
                "Skipping full pattern-engine refresh because marts.daily_features returned no rows for %s through %s.",
                since_day,
                as_of_day,
            )
            return {"features": 0, "outcomes": 0, "associations": 0, "surfaced": 0}

        user_ids = {str(row["user_id"]) for row in base_rows if row.get("user_id")}
        if user_id:
            user_ids.add(user_id)

        gauges = _fetch_gauges(conn, since_day=since_day, as_of_day=as_of_day, user_id=user_id)
        gauge_deltas = _fetch_gauge_deltas(conn, since_day=since_day, as_of_day=as_of_day, user_id=user_id)
        symptom_rows = _fetch_symptom_rows(conn, since_day=since_day, as_of_day=as_of_day, user_id=user_id)
        camera_rows = _fetch_camera_rows(conn, since_day=since_day, as_of_day=as_of_day, user_id=user_id)
        tag_flags = _fetch_tag_flags(conn, user_ids=user_ids)
        day_zip_map = _fetch_day_zip_map(conn, since_day=since_day, as_of_day=as_of_day, user_id=user_id)
        current_zip_map = _fetch_current_zip_map(conn)
        local_signals_daily = _fetch_local_signals_daily(conn, since_day=since_day, as_of_day=as_of_day)
        schumann_daily = _fetch_schumann_variability_daily(
            conn,
            since_day=since_day,
            as_of_day=as_of_day,
            base_rows=base_rows,
        )

        feature_rows = build_user_daily_features(
            base_rows=base_rows,
            gauges=gauges,
            gauge_deltas=gauge_deltas,
            symptom_stats=symptom_rows,
            camera_rows=camera_rows,
            tag_flags=tag_flags,
            day_zip_map=day_zip_map,
            current_zip_map=current_zip_map,
            local_signals_daily=local_signals_daily,
            schumann_daily=schumann_daily,
            updated_at=updated_at,
        )
        outcome_rows = build_user_daily_outcomes(feature_rows, updated_at=updated_at)
        association_rows = build_associations(
            feature_rows,
            outcome_rows,
            as_of_day=as_of_day,
            updated_at=updated_at,
        )

        _delete_scope(conn, "marts.user_pattern_associations", since_day=None, user_id=user_id, day_scoped=False)
        _delete_scope(conn, "marts.user_daily_outcomes", since_day=since_day, user_id=user_id, day_scoped=True)
        _delete_scope(conn, "marts.user_daily_features", since_day=since_day, user_id=user_id, day_scoped=True)

        _insert_rows(conn, "marts.user_daily_features", _feature_insert_columns(), feature_rows)
        _insert_rows(conn, "marts.user_daily_outcomes", _outcome_insert_columns(), outcome_rows)
        _insert_rows(conn, "marts.user_pattern_associations", _association_insert_columns(), association_rows)
        conn.commit()

    surfaced = sum(1 for row in association_rows if row.get("surfaceable"))
    return {
        "features": len(feature_rows),
        "outcomes": len(outcome_rows),
        "associations": len(association_rows),
        "surfaced": surfaced,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the deterministic personal pattern engine marts.")
    parser.add_argument("--day", default=_today_utc().isoformat(), help="As-of day in YYYY-MM-DD (UTC).")
    parser.add_argument(
        "--days-back",
        type=int,
        default=180,
        help="History window used for the deterministic v1 analysis. Default 180 days.",
    )
    parser.add_argument("--user-id", default=None, help="Optional single user_id scope.")
    args = parser.parse_args()

    as_of_day = _coerce_day(args.day)
    summary = run_pattern_engine(
        as_of_day=as_of_day,
        days_back=max(args.days_back, 1),
        user_id=args.user_id,
    )
    logger.info(
        "[pattern_engine] day=%s user=%s features=%d outcomes=%d associations=%d surfaced=%d",
        as_of_day.isoformat(),
        args.user_id or "all",
        summary["features"],
        summary["outcomes"],
        summary["associations"],
        summary["surfaced"],
    )


if __name__ == "__main__":
    main()
