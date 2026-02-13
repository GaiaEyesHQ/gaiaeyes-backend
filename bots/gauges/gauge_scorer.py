#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.db import pg
from bots.definitions.load_definition_base import load_definition_base
from bots.gauges.db_utils import pick_column, table_columns, upsert_row
from bots.gauges.signal_resolver import resolve_signals


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

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

_HRV_CANDIDATES = ["hrv_avg", "hrv_rmssd", "rmssd", "hrv", "hrv_ms"]
_DAY_CANDIDATES = ["day", "date", "day_local", "day_utc"]
_TS_CANDIDATES = ["ts_utc", "ts", "sample_ts", "created_at", "timestamp"]


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


def _iso_day(day_val: date) -> str:
    return day_val.isoformat()


def _hash_inputs(snapshot: Dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fetch_local_payload(user_id: str, day: date) -> Optional[Dict[str, Any]]:
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
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    summary = {"total_24h": 0, "max_severity": None, "top_symptoms": []}

    try:
        row = pg.fetchrow(
            """
            select count(*) as total,
                   max(severity) as max_severity
              from raw.user_symptom_events
             where user_id = %s
               and ts_utc >= %s
               and ts_utc < %s
            """,
            user_id,
            start,
            end,
        )
        if row:
            summary["total_24h"] = int(row.get("total") or 0)
            summary["max_severity"] = row.get("max_severity")
    except Exception:
        pass

    try:
        rows = pg.fetch(
            """
            select symptom_code, count(*) as events
              from raw.user_symptom_events
             where user_id = %s
               and ts_utc >= %s
               and ts_utc < %s
             group by symptom_code
             order by events desc
             limit 5
            """,
            user_id,
            start,
            end,
        )
        summary["top_symptoms"] = rows or []
    except Exception:
        pass

    return summary


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
    metrics = [m for m in _METRIC_SPECS.keys() if m in cols]
    if not metrics:
        return {}
    sql = f"""
        select day, {', '.join(metrics)}
          from marts.daily_features
         where user_id = %s and day = %s
         limit 1
    """
    return pg.fetchrow(sql, user_id, day) or {}


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
) -> Tuple[Optional[float], Optional[str]]:
    if today_row and today_row.get("hrv_avg") is not None:
        return _safe_float(today_row.get("hrv_avg")), "marts.daily_features.hrv_avg"

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
                return _safe_float(row.get("hrv")), f"gaia.daily_summary.{hrv_col}"

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
                return _safe_float(row.get("hrv")), f"gaia.samples.{hrv_col}"

    return None, None


def _compute_baseline_stats(
    baseline_rows: List[Dict[str, Any]],
    metrics: List[str],
) -> Tuple[int, Dict[str, Dict[str, float]]]:
    baseline_days = 0
    values: Dict[str, List[float]] = {m: [] for m in metrics}

    for row in baseline_rows:
        any_val = False
        for m in metrics:
            v = _safe_float(row.get(m))
            if v is None:
                continue
            any_val = True
            values[m].append(v)
        if any_val:
            baseline_days += 1

    stats: Dict[str, Dict[str, float]] = {}
    for m, vals in values.items():
        if len(vals) < 2:
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        std = var ** 0.5
        stats[m] = {"mean": mean, "std": std, "n": float(len(vals))}

    return baseline_days, stats


def compute_health_status(
    today_row: Dict[str, Any],
    baseline_rows: List[Dict[str, Any]],
    symptoms: Dict[str, Any],
    *,
    hrv_value: Optional[float] = None,
    hrv_source: Optional[str] = None,
) -> Tuple[Optional[float], Dict[str, Any]]:
    metrics = list(_METRIC_SPECS.keys())
    baseline_days, stats = _compute_baseline_stats(baseline_rows, metrics)

    if baseline_days < 14:
        return None, {
            "calibrating": True,
            "baseline_days": baseline_days,
            "metrics_used": [],
            "hrv_source": hrv_source,
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

    if not weights:
        return None, {
            "calibrating": True,
            "baseline_days": baseline_days,
            "metrics_used": [],
            "hrv_source": hrv_source,
        }

    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        return None, {
            "calibrating": True,
            "baseline_days": baseline_days,
            "metrics_used": [],
            "hrv_source": hrv_source,
        }

    load_raw = 0.0
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

    severity_max = _safe_float(symptoms.get("max_severity"))
    if severity_max:
        health_status = min(100.0, health_status + min(15.0, severity_max * 1.5))

    return health_status, {
        "calibrating": False,
        "baseline_days": baseline_days,
        "metrics_used": list(metric_inputs.keys()),
        "metric_inputs": metric_inputs,
        "hrv_source": hrv_source,
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

    return alerts


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
    return {"baseline_day": prev.get("day"), "gauges": gauges}


def _score_gauges(
    definition: Dict[str, Any],
    active_states: List[Dict[str, Any]],
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
                per_signal[g] = per_signal.get(g, 0.0) + weight

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
    symptoms = fetch_symptom_summary(user_id, day)
    wearable = fetch_local_health_summary(user_id)
    today_features = fetch_daily_features(user_id, day)
    baseline_rows = fetch_daily_features_baseline(user_id, day)
    hrv_value, hrv_source = fetch_hrv_fallback(user_id, day, today_features)
    health_status, health_meta = compute_health_status(
        today_features,
        baseline_rows,
        symptoms,
        hrv_value=hrv_value,
        hrv_source=hrv_source,
    )

    gauges = _score_gauges(definition, active_states)

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
        "wearable": wearable,
        "health_status_inputs": health_meta,
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
        "trend_json": json.dumps(trend),
        "alerts_json": json.dumps(alerts),
        "inputs_hash": inputs_hash,
        "model_version": version,
        "updated_at": datetime.now(timezone.utc),
    }

    upsert_row("marts", "user_gauges_day", payload, ["user_id", "day"])
    return {"ok": True, "skipped": False, "user_id": user_id, "day": _iso_day(day)}


if __name__ == "__main__":
    uid = os.getenv("USER_ID")
    day_env = os.getenv("DAY")
    if not uid:
        raise SystemExit("USER_ID is required (env)")
    out = score_user_day(uid, day_env)
    print(json.dumps(out, indent=2))
