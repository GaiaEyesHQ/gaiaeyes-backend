from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.rows import dict_row

from app.db import get_db
from app.routers.profile import _fetch_profile_preferences
from services.time.moon import lunar_overlay_windows, moon_context_for_day


router = APIRouter(prefix="/v1", tags=["lunar"])

MIN_TOTAL_OBSERVATIONS = 20
MIN_WINDOW_OBSERVATIONS = 4
LUNAR_SIGNAL_KEYS = ("lunar_full_window_exposed", "lunar_new_window_exposed")
LUNAR_OUTCOME_KEYS = ("poor_sleep_day", "short_sleep_day", "restlessness_day")
LUNAR_SIGNAL_TO_WINDOW = {
    "lunar_full_window_exposed": "full",
    "lunar_new_window_exposed": "new",
}
LUNAR_OUTCOME_TO_METRIC = {
    "poor_sleep_day": "sleep",
    "short_sleep_day": "short_sleep",
    "restlessness_day": "restlessness",
}

_METRIC_SPECS: Dict[str, Dict[str, Any]] = {
    "hrv": {
        "window_keys": {"full": "hrv_full_avg", "new": "hrv_new_avg"},
        "baseline_key": "hrv_baseline_avg",
        "observed_key": "hrv_observed_days",
        "window_days": {"full": "hrv_full_days", "new": "hrv_new_days"},
        "baseline_days_key": "hrv_baseline_days",
        "label": "HRV",
        "scientific_label": "HRV",
        "mystical_label": "recovery",
        "weak_ratio": 0.08,
        "moderate_ratio": 0.18,
        "weak_abs": 2.0,
        "moderate_abs": 5.0,
        "baseline_floor": 10.0,
    },
    "sleep_efficiency": {
        "window_keys": {"full": "sleep_full_avg", "new": "sleep_new_avg"},
        "baseline_key": "sleep_baseline_avg",
        "observed_key": "sleep_observed_days",
        "window_days": {"full": "sleep_full_days", "new": "sleep_new_days"},
        "baseline_days_key": "sleep_baseline_days",
        "label": "sleep efficiency",
        "scientific_label": "sleep efficiency",
        "mystical_label": "rest",
        "weak_ratio": 0.05,
        "moderate_ratio": 0.10,
        "weak_abs": 2.0,
        "moderate_abs": 4.0,
        "baseline_floor": 10.0,
    },
    "symptom_events": {
        "window_keys": {"full": "symptom_events_full_avg", "new": "symptom_events_new_avg"},
        "baseline_key": "symptom_events_baseline_avg",
        "observed_key": "symptom_observed_days",
        "window_days": {"full": "symptom_full_days", "new": "symptom_new_days"},
        "baseline_days_key": "symptom_baseline_days",
        "label": "symptom frequency",
        "scientific_label": "symptom frequency",
        "mystical_label": "symptom activity",
        "weak_ratio": 0.10,
        "moderate_ratio": 0.22,
        "weak_abs": 0.5,
        "moderate_abs": 1.0,
        "baseline_floor": 1.0,
    },
    "symptom_severity": {
        "window_keys": {"full": "symptom_severity_full_avg", "new": "symptom_severity_new_avg"},
        "baseline_key": "symptom_severity_baseline_avg",
        "observed_key": "symptom_observed_days",
        "window_days": {"full": "symptom_full_days", "new": "symptom_new_days"},
        "baseline_days_key": "symptom_baseline_days",
        "label": "symptom severity",
        "scientific_label": "symptom severity",
        "mystical_label": "symptom intensity",
        "weak_ratio": 0.10,
        "moderate_ratio": 0.22,
        "weak_abs": 0.35,
        "moderate_abs": 0.75,
        "baseline_floor": 1.0,
    },
}


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value.is_nan():
            return None
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        if value.is_nan():
            return 0
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _window_payload(row: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    return {
        "days": _int_or_zero(row.get(f"{prefix}_window_days")),
        "hrv_avg": _float_or_none(row.get(f"hrv_{prefix}_avg")),
        "sleep_efficiency_avg": _float_or_none(row.get(f"sleep_{prefix}_avg")),
        "symptom_events_avg": _float_or_none(row.get(f"symptom_events_{prefix}_avg")),
        "symptom_severity_avg": _float_or_none(row.get(f"symptom_severity_{prefix}_avg")),
    }


def _sample_sizes(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "hrv": {
            "observed_days": _int_or_zero(row.get("hrv_observed_days")),
            "full_window_days": _int_or_zero(row.get("hrv_full_days")),
            "new_window_days": _int_or_zero(row.get("hrv_new_days")),
            "baseline_days": _int_or_zero(row.get("hrv_baseline_days")),
        },
        "sleep_efficiency": {
            "observed_days": _int_or_zero(row.get("sleep_observed_days")),
            "full_window_days": _int_or_zero(row.get("sleep_full_days")),
            "new_window_days": _int_or_zero(row.get("sleep_new_days")),
            "baseline_days": _int_or_zero(row.get("sleep_baseline_days")),
        },
        "symptom_events": {
            "observed_days": _int_or_zero(row.get("symptom_observed_days")),
            "full_window_days": _int_or_zero(row.get("symptom_full_days")),
            "new_window_days": _int_or_zero(row.get("symptom_new_days")),
            "baseline_days": _int_or_zero(row.get("symptom_baseline_days")),
        },
    }


def _strength_for_candidate(delta: float, ratio: float, spec: Dict[str, Any]) -> str:
    if ratio >= spec["moderate_ratio"] or abs(delta) >= spec["moderate_abs"]:
        return "moderate"
    if ratio >= spec["weak_ratio"] or abs(delta) >= spec["weak_abs"]:
        return "weak"
    return "none"


def _build_candidate(row: Dict[str, Any], metric_key: str, window: str) -> Optional[Dict[str, Any]]:
    spec = _METRIC_SPECS[metric_key]
    observed_days = _int_or_zero(row.get(spec["observed_key"]))
    window_days = _int_or_zero(row.get(spec["window_days"][window]))
    baseline_days = _int_or_zero(row.get(spec["baseline_days_key"]))

    if observed_days < MIN_TOTAL_OBSERVATIONS or window_days < MIN_WINDOW_OBSERVATIONS or baseline_days < MIN_WINDOW_OBSERVATIONS:
        return None

    window_value = _float_or_none(row.get(spec["window_keys"][window]))
    baseline_value = _float_or_none(row.get(spec["baseline_key"]))
    if window_value is None or baseline_value is None:
        return None

    delta = window_value - baseline_value
    ratio = abs(delta) / max(abs(baseline_value), spec["baseline_floor"])
    strength = _strength_for_candidate(delta, ratio, spec)
    return {
        "metric_key": metric_key,
        "window": window,
        "window_value": window_value,
        "baseline_value": baseline_value,
        "delta": delta,
        "ratio": ratio,
        "strength": strength,
        "score": max(ratio, abs(delta) / max(spec["moderate_abs"], 0.001)),
        "observed_days": observed_days,
        "window_days": window_days,
        "baseline_days": baseline_days,
        "spec": spec,
    }


def _window_label(window: str) -> str:
    return "full moon windows" if window == "full" else "new moon windows"


def _direction(delta: float) -> str:
    if delta > 0:
        return "higher"
    if delta < 0:
        return "lower"
    return "about the same"


def _scientific_message(candidate: Optional[Dict[str, Any]], *, insufficient_data: bool) -> Optional[str]:
    if insufficient_data:
        return "Gaia needs more nights before comparing lunar windows with your baseline."
    if not candidate:
        return "Current comparisons do not show a consistent lunar pattern yet."

    qualifier = "slightly" if candidate["strength"] == "weak" else "more noticeably"
    direction = _direction(candidate["delta"])
    return (
        f"Across {candidate['observed_days']} days with {candidate['spec']['scientific_label']} data, "
        f"your {candidate['spec']['scientific_label']} was {qualifier} {direction} near "
        f"{_window_label(candidate['window'])} than outside them."
    )


def _mystical_message(candidate: Optional[Dict[str, Any]], *, insufficient_data: bool) -> Optional[str]:
    if insufficient_data:
        return "Gaia is still gathering enough nights to see whether lunar windows stand out for you."
    if not candidate:
        return "Your recent data does not point to a clear lunar sensitivity yet."

    direction = _direction(candidate["delta"])
    qualifier = "a bit" if candidate["strength"] == "weak" else "more"
    return (
        f"Your data suggests you may be {qualifier} sensitive around {_window_label(candidate['window'])}, "
        f"with {direction} {candidate['spec']['mystical_label']} in the same window."
    )


async def _fetch_user_lunar_pattern_row(conn, user_id: str) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select *
            from marts.user_lunar_patterns
            where user_id = %s
            limit 1
            """,
            (user_id,),
            prepare=False,
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def _fetch_canonical_lunar_pattern_rows(conn, user_id: str) -> list[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select *
              from marts.user_pattern_associations
             where user_id = %s
               and signal_key = any(%s)
               and outcome_key = any(%s)
               and lag_hours = 0
             order by confidence_rank desc, relative_lift desc, rate_diff desc, exposed_n desc
            """,
            (user_id, list(LUNAR_SIGNAL_KEYS), list(LUNAR_OUTCOME_KEYS)),
            prepare=False,
        )
        return [dict(row) for row in await cur.fetchall()]


def _canonical_pattern_strength(row: Optional[Dict[str, Any]]) -> str:
    confidence = str((row or {}).get("confidence") or "").strip().lower()
    if confidence in {"strong", "moderate"}:
        return "moderate"
    if confidence == "emerging":
        return "weak"
    return "none"


def _canonical_lunar_message(row: Optional[Dict[str, Any]], *, scientific: bool, insufficient_data: bool) -> str:
    if insufficient_data:
        if scientific:
            return "Gaia needs more overlap before comparing lunar windows with your sleep and restlessness patterns."
        return "Gaia is still gathering enough overlap to see whether lunar windows stand out for you."
    if not row:
        if scientific:
            return "Current comparisons do not show a consistent lunar pattern yet."
        return "Your recent data does not point to a clear lunar sensitivity yet."

    signal_key = str(row.get("signal_key") or "")
    outcome_key = str(row.get("outcome_key") or "")
    window = "full moon windows" if LUNAR_SIGNAL_TO_WINDOW.get(signal_key) == "full" else "new moon windows"

    if scientific:
        if outcome_key == "poor_sleep_day":
            return f"In your history, poor-sleep nights have overlapped more during {window}."
        if outcome_key == "short_sleep_day":
            return f"In your history, short-sleep nights have overlapped more during {window}."
        return f"In your history, restless or reactive days have overlapped more during {window}."

    if outcome_key == "poor_sleep_day":
        return f"Your data suggests {window} may coincide with lighter or more fragile sleep for you."
    if outcome_key == "short_sleep_day":
        return f"Your data suggests {window} may coincide with shorter nights for you."
    return f"Your data suggests {window} may coincide with more restless or reactive days for you."


@router.get("/lunar/current")
async def lunar_current() -> Dict[str, Any]:
    utc_day = datetime.now(timezone.utc).date()
    return moon_context_for_day(utc_day)


@router.get("/series/lunar-overlay")
async def lunar_overlay_series(
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Dict[str, Any]:
    utc_today = datetime.now(timezone.utc).date()
    end_day = end or utc_today
    start_day = start or (end_day - timedelta(days=29))
    return {"windows": lunar_overlay_windows(start_day, end_day)}


@router.get("/insights/lunar")
async def lunar_insights(request: Request, conn=Depends(get_db)) -> Dict[str, Any]:
    user_id = _require_user_id(request)
    utc_day = datetime.now(timezone.utc).date()
    current_context = moon_context_for_day(utc_day)
    preferences = await _fetch_profile_preferences(conn, user_id)
    declared_lunar_sensitivity = bool(preferences.get("lunar_sensitivity_declared"))
    rows = await _fetch_canonical_lunar_pattern_rows(conn, user_id)

    strongest = None
    surfaced_rows = [row for row in rows if bool(row.get("surfaceable"))]
    if surfaced_rows:
        strongest = surfaced_rows[0]

    observed_days = 0
    if rows:
        observed_days = max(_int_or_zero(row.get("exposed_n")) + _int_or_zero(row.get("unexposed_n")) for row in rows)
    insufficient_data = observed_days < MIN_TOTAL_OBSERVATIONS

    return {
        "user_id": "current",
        "declared_lunar_sensitivity": declared_lunar_sensitivity,
        "current_lunar_context": current_context,
        "observed_days": observed_days,
        "n_nights": observed_days,
        "pattern_strength": _canonical_pattern_strength(strongest),
        "highlight_window": LUNAR_SIGNAL_TO_WINDOW.get(str((strongest or {}).get("signal_key") or "")),
        "highlight_metric": LUNAR_OUTCOME_TO_METRIC.get(str((strongest or {}).get("outcome_key") or "")),
        "message_scientific": _canonical_lunar_message(strongest, scientific=True, insufficient_data=insufficient_data),
        "message_mystical": _canonical_lunar_message(strongest, scientific=False, insufficient_data=insufficient_data),
        "insufficient_data": insufficient_data,
    }
