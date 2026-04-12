from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.rows import dict_row

from app.db import get_db
from app.routers.profile import _fetch_profile_preferences
from services.patterns.personal_relevance import fetch_best_pattern_rows
from services.time.moon import lunar_overlay_windows, moon_context_for_day


router = APIRouter(prefix="/v1", tags=["lunar"])

MIN_TOTAL_OBSERVATIONS = 20
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

def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


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
    visible_rows = [
        row
        for row in await fetch_best_pattern_rows(conn, user_id)
        if str(row.get("signal_key") or "") in LUNAR_SIGNAL_KEYS
        and str(row.get("outcome_key") or "") in LUNAR_OUTCOME_KEYS
        and int(row.get("lag_hours") or 0) == 0
    ]

    strongest = None
    if visible_rows:
        strongest = visible_rows[0]
    elif rows:
        strongest = rows[0]

    observed_days = 0
    if rows:
        observed_days = max(_int_or_zero(row.get("exposed_n")) + _int_or_zero(row.get("unexposed_n")) for row in rows)
    pattern_strength = _canonical_pattern_strength(strongest)
    insufficient_data = observed_days < MIN_TOTAL_OBSERVATIONS and pattern_strength == "none"

    return {
        "user_id": "current",
        "declared_lunar_sensitivity": declared_lunar_sensitivity,
        "current_lunar_context": current_context,
        "observed_days": observed_days,
        "n_nights": observed_days,
        "pattern_strength": pattern_strength,
        "highlight_window": LUNAR_SIGNAL_TO_WINDOW.get(str((strongest or {}).get("signal_key") or "")),
        "highlight_metric": LUNAR_OUTCOME_TO_METRIC.get(str((strongest or {}).get("outcome_key") or "")),
        "message_scientific": _canonical_lunar_message(strongest, scientific=True, insufficient_data=insufficient_data),
        "message_mystical": _canonical_lunar_message(strongest, scientific=False, insufficient_data=insufficient_data),
        "insufficient_data": insufficient_data,
    }
