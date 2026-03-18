from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.rows import dict_row

from app.db import get_db
from app.security.auth import require_read_auth
from bots.definitions.load_definition_base import load_definition_base
from bots.gauges.gauge_scorer import fetch_user_tags
from bots.patterns.pattern_engine_job import confidence_rank, select_best_lag
from services.personalization.health_context import canonicalize_tag_keys
from services.patterns.personal_relevance import (
    compute_personal_relevance,
    fetch_best_pattern_rows,
    fetch_recent_outcome_summary,
    resolve_current_drivers,
)


router = APIRouter(prefix="/v1/patterns", tags=["patterns"])


SIGNAL_LABELS = {
    "pressure_swing_exposed": "Pressure swings",
    "aqi_moderate_plus_exposed": "Air quality",
    "temp_swing_exposed": "Temperature swings",
    "kp_g1_plus_exposed": "Kp 5+",
    "bz_south_exposed": "Southward Bz",
    "solar_wind_exposed": "Solar wind",
    "schumann_exposed": "Schumann variability",
}

OUTCOME_LABELS = {
    "headache_day": "Headaches",
    "pain_flare_day": "Pain flares",
    "fatigue_day": "Fatigue",
    "anxiety_day": "Anxious or restless days",
    "poor_sleep_day": "Poor sleep",
    "focus_fog_day": "Brain fog",
    "hrv_dip_day": "HRV dips",
    "high_hr_day": "Higher heart-rate days",
    "short_sleep_day": "Short sleep",
}


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


def _lag_label(lag_hours: int) -> str:
    if lag_hours == 0:
        return "same day"
    if lag_hours in {12, 24}:
        return "next day"
    if lag_hours == 48:
        return "2 days later"
    return f"{lag_hours}h"


def _signal_label(signal_key: str) -> str:
    return SIGNAL_LABELS.get(signal_key, signal_key.replace("_", " ").title())


def _outcome_label(outcome_key: str) -> str:
    return OUTCOME_LABELS.get(outcome_key, outcome_key.replace("_", " ").title())


def _build_explanation(row: Dict[str, Any]) -> str:
    signal_key = str(row.get("signal_key") or "")
    outcome_key = str(row.get("outcome_key") or "")
    outcome = _outcome_label(outcome_key)

    if signal_key == "pressure_swing_exposed":
        return f"{outcome} appear more often for you when pressure swings exceed 6 hPa."
    if signal_key == "aqi_moderate_plus_exposed":
        return f"{outcome} are more common for you on moderate-or-higher AQI days."
    if signal_key == "temp_swing_exposed":
        return f"{outcome} appear more often for you when temperatures swing 6 C or more in 24 hours."
    if signal_key == "kp_g1_plus_exposed":
        return f"{outcome} tend to show up more often for you after Kp 5+ days."
    if signal_key == "bz_south_exposed":
        return f"{outcome} tend to show up more often for you after strong southward Bz days."
    if signal_key == "solar_wind_exposed":
        return f"{outcome} tend to show up more often for you after elevated solar wind days."
    if signal_key == "schumann_exposed":
        return f"{outcome} appear more often for you on elevated Schumann variability days."
    return f"{outcome} appear more often for you when {_signal_label(signal_key).lower()} are elevated."


def _priority_boost(user_tags: set[str], row: Dict[str, Any]) -> int:
    outcome_key = str(row.get("outcome_key") or "")
    signal_key = str(row.get("signal_key") or "")

    score = 0
    if outcome_key == "headache_day" and "migraine_history" in user_tags:
        score += 40
    if outcome_key == "pain_flare_day" and user_tags.intersection(
        {"arthritis", "autoimmune_condition", "chronic_pain", "fibromyalgia", "hypermobility_eds"}
    ):
        score += 35
    if outcome_key in {"poor_sleep_day", "fatigue_day", "hrv_dip_day", "high_hr_day"} and user_tags.intersection(
        {"pots_dysautonomia", "heart_rhythm_sensitive", "nervous_system_dysregulation"}
    ):
        score += 25
    if signal_key == "aqi_moderate_plus_exposed" and user_tags.intersection(
        {"air_quality_sensitive", "allergies_sinus", "asthma_breathing_sensitive", "mcas_histamine"}
    ):
        score += 20
    return score


def _sort_rows(rows: List[Dict[str, Any]], user_tags: set[str]) -> List[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -_priority_boost(user_tags, row),
            -confidence_rank(str(row.get("confidence"))),
            -float(row.get("relative_lift") or 0),
            -int(row.get("exposed_outcome_n") or 0),
            -(row.get("last_seen_at").timestamp() if isinstance(row.get("last_seen_at"), datetime) else 0.0),
        ),
    )


def _serialize_card(row: Dict[str, Any], *, used_today_ids: Optional[set[str]] = None) -> Dict[str, Any]:
    last_seen_at = row.get("last_seen_at")
    signal_key = str(row.get("signal_key") or "")
    outcome_key = str(row.get("outcome_key") or "")
    lag_hours = int(row.get("lag_hours") or 0)
    card_id = f"{signal_key}|{outcome_key}|{lag_hours}"
    used_today = card_id in (used_today_ids or set())
    return {
        "signalKey": signal_key,
        "signal": _signal_label(signal_key),
        "outcomeKey": outcome_key,
        "outcome": _outcome_label(outcome_key),
        "explanation": _build_explanation(row),
        "confidence": row.get("confidence"),
        "sampleSize": int(row.get("exposed_n") or 0),
        "lagHours": lag_hours,
        "lagLabel": _lag_label(lag_hours),
        "lastSeenAt": last_seen_at.astimezone(timezone.utc).isoformat() if isinstance(last_seen_at, datetime) else None,
        "relativeLift": float(row.get("relative_lift") or 0),
        "exposedRate": float(row.get("exposed_rate") or 0),
        "unexposedRate": float(row.get("unexposed_rate") or 0),
        "rateDiff": float(row.get("rate_diff") or 0),
        "exposedDays": int(row.get("exposed_n") or 0),
        "unexposedDays": int(row.get("unexposed_n") or 0),
        "thresholdValue": float(row.get("exposure_threshold")) if row.get("exposure_threshold") is not None else None,
        "thresholdOperator": row.get("exposure_operator"),
        "thresholdText": row.get("exposure_threshold_text"),
        "usedToday": used_today,
        "usedTodayLabel": "Active now" if used_today else None,
    }


async def _fetch_best_rows(conn, user_id: str) -> List[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select *
              from marts.user_pattern_associations_best
             where user_id = %s
             order by confidence_rank desc, relative_lift desc, rate_diff desc, lag_hours asc
            """,
            (user_id,),
            prepare=False,
        )
        return [dict(row) for row in await cur.fetchall()]


@router.get("", dependencies=[Depends(require_read_auth)])
async def user_patterns(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    today = datetime.now(timezone.utc).date()

    rows = await fetch_best_pattern_rows(conn, user_id)

    # Defensive fallback when older databases do not yet have the best-lag view.
    if not rows:
        try:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    select *
                      from marts.user_pattern_associations
                     where user_id = %s
                       and surfaceable = true
                    """,
                    (user_id,),
                    prepare=False,
                )
                raw_rows = [dict(row) for row in await cur.fetchall()]
                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for row in raw_rows:
                    grouped.setdefault((str(row.get("signal_key")), str(row.get("outcome_key"))), []).append(row)
                rows = [best for best in (select_best_lag(group) for group in grouped.values()) if best]
        except Exception:
            try:
                await conn.rollback()
            except Exception:
                pass
            rows = []

    raw_tags = await asyncio.to_thread(fetch_user_tags, user_id)
    user_tags = set(canonicalize_tag_keys(raw_tags))
    try:
        definition, _ = load_definition_base()
    except Exception:
        definition = {}
    recent_outcomes = await fetch_recent_outcome_summary(conn, user_id, today)
    today_drivers, _, _ = await resolve_current_drivers(
        user_id=user_id,
        day=today,
        definition=definition,
    )
    personal_relevance = compute_personal_relevance(
        day=today,
        drivers=today_drivers,
        pattern_rows=rows,
        user_tags=user_tags,
        recent_outcomes=recent_outcomes,
    )
    used_today_ids = {
        str(item.get("id") or "")
        for item in personal_relevance.get("active_pattern_refs") or []
        if str(item.get("id") or "")
    }

    body_rows = _sort_rows([row for row in rows if str(row.get("outcome_kind") or "") == "biometric"], user_tags)[:3]
    strongest_rows = _sort_rows(
        [
            row
            for row in rows
            if str(row.get("outcome_kind") or "") != "biometric"
            and str(row.get("confidence") or "") in {"Strong", "Moderate"}
        ],
        user_tags,
    )[:3]
    emerging_rows = _sort_rows(
        [
            row
            for row in rows
            if str(row.get("outcome_kind") or "") != "biometric"
            and str(row.get("confidence") or "") == "Emerging"
        ],
        user_tags,
    )[:3]

    return {
        "ok": True,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Patterns are based on your self-reported logs and recent sensor history. "
            "They do not diagnose, prove causes, or replace medical care."
        ),
        "strongestPatterns": [_serialize_card(row, used_today_ids=used_today_ids) for row in strongest_rows],
        "emergingPatterns": [_serialize_card(row, used_today_ids=used_today_ids) for row in emerging_rows],
        "bodySignalsPatterns": [_serialize_card(row, used_today_ids=used_today_ids) for row in body_rows],
    }
