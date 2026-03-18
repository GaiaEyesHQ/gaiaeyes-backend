from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

try:
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - local unit tests can run without psycopg installed.
    dict_row = None

from bots.patterns.pattern_engine_job import select_best_lag
from services.drivers.driver_normalize import normalize_environmental_drivers
from services.personalization.health_context import (
    AIRWAY_KEYS,
    AUTONOMIC_KEYS,
    HEAD_PRESSURE_KEYS,
    PAIN_FLARE_KEYS,
    SINUS_KEYS,
    SLEEP_DISRUPTION_KEYS,
    PersonalizationProfile,
    build_personalization_profile,
)


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

THEME_LABELS = {
    "headache_day": "Headache watch",
    "pain_flare_day": "Pain flare watch",
    "fatigue_day": "Fatigue watch",
    "anxiety_day": "Restless-day watch",
    "poor_sleep_day": "Sleep watch",
    "focus_fog_day": "Focus watch",
    "hrv_dip_day": "Body-signal watch",
    "high_hr_day": "Heart-load watch",
    "short_sleep_day": "Short-sleep watch",
}

DRIVER_TO_SIGNAL_KEY = {
    "pressure": "pressure_swing_exposed",
    "temp": "temp_swing_exposed",
    "aqi": "aqi_moderate_plus_exposed",
    "kp": "kp_g1_plus_exposed",
    "bz": "bz_south_exposed",
    "sw": "solar_wind_exposed",
    "schumann": "schumann_exposed",
}

GAUGE_OUTCOME_KEYS = {
    "pain": ("pain_flare_day", "headache_day"),
    "focus": ("focus_fog_day", "headache_day"),
    "heart": ("high_hr_day", "anxiety_day", "hrv_dip_day"),
    "stamina": ("fatigue_day", "short_sleep_day"),
    "energy": ("fatigue_day", "anxiety_day"),
    "sleep": ("poor_sleep_day", "short_sleep_day"),
    "mood": ("anxiety_day", "poor_sleep_day"),
    "health_status": ("fatigue_day", "short_sleep_day", "high_hr_day"),
}

GAUGE_LABELS = {
    "pain": "Pain",
    "focus": "Focus",
    "heart": "Heart",
    "stamina": "Recovery Load",
    "energy": "Energy",
    "sleep": "Sleep",
    "mood": "Mood",
    "health_status": "Health Status",
}

OUTCOME_KEYS = list(OUTCOME_LABELS.keys())

CONFIDENCE_RANK = {
    "Strong": 3,
    "Moderate": 2,
    "Emerging": 1,
}

CONFIDENCE_WEIGHT = {
    "Strong": 2.6,
    "Moderate": 1.8,
    "Emerging": 1.0,
}

DRIVER_SEVERITY_SCORE = {
    "high": 4.0,
    "watch": 3.0,
    "elevated": 3.0,
    "mild": 2.0,
    "low": 1.0,
}

ROLE_LABELS = {
    0: ("primary", "Primary today"),
    1: ("supporting", "Also relevant"),
    2: ("supporting", "Background context"),
}


def _cursor_kwargs() -> dict[str, Any]:
    return {"row_factory": dict_row} if dict_row is not None else {}


def signal_label(signal_key: str) -> str:
    return SIGNAL_LABELS.get(signal_key, signal_key.replace("_", " ").title())


def outcome_label(outcome_key: str) -> str:
    return OUTCOME_LABELS.get(outcome_key, outcome_key.replace("_", " ").title())


def confidence_rank(value: str | None) -> int:
    return CONFIDENCE_RANK.get(str(value or "").strip().title(), 0)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _severity_score(value: Any) -> float:
    token = str(value or "").strip().lower()
    return DRIVER_SEVERITY_SCORE.get(token, 1.0)


def _relative_lift_bonus(value: Any) -> float:
    lift = _safe_float(value) or 0.0
    return min(max(lift, 0.0), 3.5) * 0.35


def _recent_outcome_boost(outcome_key: str, recent_outcomes: Mapping[str, Any]) -> float:
    counts = recent_outcomes.get("counts") or {}
    try:
        count = int(counts.get(outcome_key) or 0)
    except Exception:
        count = 0
    if count >= 2:
        return 0.85
    if count >= 1:
        return 0.45
    return 0.0


def _driver_sensitivity_boost(driver_key: str, profile: PersonalizationProfile) -> float:
    if driver_key == "pressure":
        if profile.has_any("pressure_sensitive") or profile.has_any("migraine_history"):
            return 1.15
        if profile.includes_any(PAIN_FLARE_KEYS):
            return 0.55
    if driver_key == "temp":
        if profile.has_any("temperature_sensitive") or profile.includes_any(PAIN_FLARE_KEYS):
            return 0.85
    if driver_key == "aqi":
        if profile.includes_any(SINUS_KEYS) or profile.includes_any(AIRWAY_KEYS):
            return 1.0
    if driver_key in {"kp", "bz", "sw", "schumann"}:
        if profile.has_any("geomagnetic_sensitive"):
            return 1.0
        if profile.includes_any(AUTONOMIC_KEYS) or profile.includes_any(SLEEP_DISRUPTION_KEYS):
            return 0.9
        if driver_key == "schumann" and profile.has_any("anxiety_sensitive"):
            return 0.75
    return 0.0


def _outcome_relevance_weight(outcome_key: str, profile: PersonalizationProfile) -> float:
    if outcome_key == "headache_day":
        return 1.65 if profile.has_any("migraine_history") else 1.2
    if outcome_key == "pain_flare_day":
        return 1.6 if profile.includes_any(PAIN_FLARE_KEYS) else 1.25
    if outcome_key in {"poor_sleep_day", "short_sleep_day"}:
        return 1.55 if profile.includes_any(SLEEP_DISRUPTION_KEYS) else 1.2
    if outcome_key in {"high_hr_day", "hrv_dip_day"}:
        return 1.55 if profile.includes_any(AUTONOMIC_KEYS) else 1.25
    if outcome_key == "fatigue_day":
        if profile.includes_any(PAIN_FLARE_KEYS) or profile.includes_any(AUTONOMIC_KEYS):
            return 1.45
        return 1.15
    if outcome_key == "anxiety_day":
        if profile.has_any("anxiety_sensitive") or profile.includes_any(AUTONOMIC_KEYS):
            return 1.4
        return 1.1
    if outcome_key == "focus_fog_day":
        if profile.includes_any(SINUS_KEYS) or profile.has_any("migraine_history"):
            return 1.35
        return 1.1
    return 1.0


def pattern_anchor_statement(row: Mapping[str, Any]) -> str:
    signal_key = str(row.get("signal_key") or "")
    outcome_key = str(row.get("outcome_key") or "")

    if signal_key == "pressure_swing_exposed" and outcome_key == "pain_flare_day":
        return "Pressure swings are a known repeating pattern in your pain flare history."
    if signal_key == "pressure_swing_exposed" and outcome_key == "headache_day":
        return "Pressure swings are a known repeating pattern in your headache history."
    if signal_key == "pressure_swing_exposed" and outcome_key == "focus_fog_day":
        return "Pressure swings have shown up before brain-fog days in your recent history."
    if signal_key == "temp_swing_exposed" and outcome_key == "pain_flare_day":
        return "Temperature swings have shown up before your pain flare days."
    if signal_key == "temp_swing_exposed" and outcome_key == "fatigue_day":
        return "Temperature swings have lined up with fatigue in your recent history."
    if signal_key == "aqi_moderate_plus_exposed" and outcome_key == "fatigue_day":
        return "AQI has lined up with fatigue in your recent history."
    if signal_key == "aqi_moderate_plus_exposed" and outcome_key == "focus_fog_day":
        return "AQI has lined up with brain-fog days in your recent history."
    if signal_key == "aqi_moderate_plus_exposed" and outcome_key == "headache_day":
        return "AQI has lined up with headache days in your recent history."
    if signal_key == "solar_wind_exposed" and outcome_key == "high_hr_day":
        return "Elevated solar wind has shown up before higher heart-rate days in your recent history."
    if signal_key == "solar_wind_exposed" and outcome_key == "short_sleep_day":
        return "Elevated solar wind has shown up before shorter-sleep days in your recent history."
    if signal_key == "solar_wind_exposed" and outcome_key == "fatigue_day":
        return "Elevated solar wind has lined up with fatigue in your recent history."
    if signal_key == "solar_wind_exposed" and outcome_key == "anxiety_day":
        return "Elevated solar wind has lined up with restless days in your recent history."
    if signal_key == "kp_g1_plus_exposed" and outcome_key == "poor_sleep_day":
        return "Geomagnetic activity has shown up before poorer-sleep days in your recent history."
    if signal_key == "bz_south_exposed" and outcome_key == "poor_sleep_day":
        return "Strong southward Bz has shown up before poorer-sleep days in your recent history."
    if signal_key == "schumann_exposed" and outcome_key in {"poor_sleep_day", "short_sleep_day"}:
        return "Elevated Schumann variability has shown up before lighter or shorter sleep in your recent history."
    if signal_key == "schumann_exposed" and outcome_key == "focus_fog_day":
        return "Elevated Schumann variability has lined up with focus drift in your recent history."
    if signal_key == "schumann_exposed" and outcome_key == "anxiety_day":
        return "Elevated Schumann variability has lined up with restless days in your recent history."
    return f"{signal_label(signal_key)} have lined up with {outcome_label(outcome_key).lower()} in your recent history."


def _role_for_index(index: int) -> tuple[str | None, str | None]:
    return ROLE_LABELS.get(index, (None, None))


def _driver_reason(driver: Mapping[str, Any], top_refs: Sequence[Mapping[str, Any]], profile: PersonalizationProfile) -> str:
    if top_refs:
        return pattern_anchor_statement(top_refs[0])
    key = str(driver.get("key") or "")
    if _driver_sensitivity_boost(key, profile) > 0:
        label = str(driver.get("label") or key.replace("_", " ").title())
        return f"{label} matters a bit more for you because it matches your sensitivity profile."
    label = str(driver.get("label") or key.replace("_", " ").title())
    return f"{label} is active today, but no stronger personal pattern is leading with it yet."


def _serialize_pattern_ref(
    row: Mapping[str, Any],
    *,
    driver_key: str,
    score: float,
) -> Dict[str, Any]:
    signal_key = str(row.get("signal_key") or "")
    outcome_key = str(row.get("outcome_key") or "")
    lag_hours = int(row.get("lag_hours") or 0)
    last_seen = row.get("last_seen_at")
    return {
        "id": f"{signal_key}|{outcome_key}|{lag_hours}",
        "driver_key": driver_key,
        "signal_key": signal_key,
        "signal": signal_label(signal_key),
        "outcome_key": outcome_key,
        "outcome": outcome_label(outcome_key),
        "confidence": row.get("confidence"),
        "lag_hours": lag_hours,
        "relative_lift": float(row.get("relative_lift") or 0.0),
        "last_seen_at": (
            last_seen.astimezone(timezone.utc).isoformat() if isinstance(last_seen, datetime) else None
        ),
        "used_today": True,
        "used_today_label": "Used today",
        "relevance_score": round(score, 2),
        "explanation": pattern_anchor_statement(row),
    }


def _dedupe_pattern_refs(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        ident = str(row.get("id") or "")
        if not ident or ident in seen:
            continue
        seen.add(ident)
        out.append(dict(row))
    return out


def _theme_summary(label: str, ref: Mapping[str, Any]) -> str:
    signal = str(ref.get("signal") or "This signal")
    return f"{label} rises in priority today because {signal.lower()} matches your recent pattern history."


def _compact_driver_line(driver: Mapping[str, Any]) -> str:
    label = str(driver.get("label") or driver.get("key") or "Driver")
    role_label = str(driver.get("role_label") or "").strip()
    reason = str(driver.get("personal_reason") or "").strip()
    if role_label and reason:
        return f"{role_label}: {label} — {reason}"
    if role_label:
        return f"{role_label}: {label}"
    if reason:
        return f"{label} — {reason}"
    state = str(driver.get("state") or "").strip()
    return f"{label}: {state}" if state else label


def compute_personal_relevance(
    *,
    day: date,
    drivers: Optional[Iterable[Mapping[str, Any]]],
    pattern_rows: Optional[Iterable[Mapping[str, Any]]],
    user_tags: Optional[Iterable[Any]],
    recent_outcomes: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    profile = build_personalization_profile(user_tags)
    recent_outcomes = dict(recent_outcomes or {})
    pattern_rows = [dict(row) for row in list(pattern_rows or []) if isinstance(row, Mapping)]

    raw_rows: List[Dict[str, Any]] = [dict(driver) for driver in list(drivers or []) if isinstance(driver, Mapping)]
    raw_top_drivers = [dict(row) for row in raw_rows[:3]]
    scored_rows: List[Dict[str, Any]] = []

    for raw_index, driver in enumerate(raw_rows):
        key = str(driver.get("key") or "").strip()
        if not key:
            continue
        signal_key = DRIVER_TO_SIGNAL_KEY.get(key)
        severity_score = _severity_score(driver.get("severity"))
        sensitivity_boost = _driver_sensitivity_boost(key, profile)
        refs_with_score: List[tuple[float, Dict[str, Any]]] = []

        if signal_key:
            for row in pattern_rows:
                if str(row.get("signal_key") or "") != signal_key:
                    continue
                outcome_key = str(row.get("outcome_key") or "")
                score = (
                    CONFIDENCE_WEIGHT.get(str(row.get("confidence") or "").strip().title(), 0.0)
                    + _outcome_relevance_weight(outcome_key, profile)
                    + _recent_outcome_boost(outcome_key, recent_outcomes)
                    + _relative_lift_bonus(row.get("relative_lift"))
                )
                refs_with_score.append((score, _serialize_pattern_ref(row, driver_key=key, score=score)))

        refs_with_score.sort(
            key=lambda item: (
                -item[0],
                -confidence_rank(item[1].get("confidence")),
                -float(item[1].get("relative_lift") or 0.0),
            )
        )
        top_refs = [ref for _, ref in refs_with_score[:2]]
        personal_score = severity_score + sensitivity_boost + sum(score for score, _ in refs_with_score[:2])

        enriched = dict(driver)
        enriched["raw_severity_score"] = round(severity_score, 2)
        enriched["personal_relevance_score"] = round(personal_score, 2)
        enriched["active_pattern_refs"] = top_refs
        enriched["personal_reason"] = _driver_reason(enriched, top_refs, profile)
        enriched["_sort_index"] = raw_index
        scored_rows.append(enriched)

    scored_rows.sort(
        key=lambda row: (
            -float(row.get("personal_relevance_score") or 0.0),
            -float(row.get("raw_severity_score") or 0.0),
            int(row.get("_sort_index") or 0),
        )
    )

    for index, row in enumerate(scored_rows):
        role, role_label = _role_for_index(index)
        if role:
            row["role"] = role
        if role_label:
            row["role_label"] = role_label
        row.pop("_sort_index", None)

    primary_driver = dict(scored_rows[0]) if scored_rows else None
    supporting_drivers = [dict(row) for row in scored_rows[1:3]]
    active_pattern_refs = _dedupe_pattern_refs(
        ref
        for row in scored_rows[:3]
        for ref in list(row.get("active_pattern_refs") or [])
    )

    theme_scores: Dict[str, float] = {}
    theme_ref: Dict[str, Dict[str, Any]] = {}
    for ref in active_pattern_refs:
        outcome_key = str(ref.get("outcome_key") or "")
        if not outcome_key:
            continue
        score = float(ref.get("relevance_score") or 0.0)
        theme_scores[outcome_key] = theme_scores.get(outcome_key, 0.0) + score
        if outcome_key not in theme_ref or score > float(theme_ref[outcome_key].get("relevance_score") or 0.0):
            theme_ref[outcome_key] = ref

    ordered_themes = sorted(theme_scores.items(), key=lambda item: (-item[1], item[0]))
    today_personal_themes: List[Dict[str, Any]] = []
    for outcome_key, score in ordered_themes[:3]:
        label = THEME_LABELS.get(outcome_key, outcome_label(outcome_key))
        ref = theme_ref.get(outcome_key, {})
        today_personal_themes.append(
            {
                "key": outcome_key,
                "label": label,
                "score": round(score, 2),
                "summary": _theme_summary(label, ref),
            }
        )

    pattern_relevant_gauges: List[Dict[str, Any]] = []
    for gauge_key, outcome_keys in GAUGE_OUTCOME_KEYS.items():
        refs = [ref for ref in active_pattern_refs if str(ref.get("outcome_key") or "") in outcome_keys]
        if not refs:
            continue
        refs.sort(key=lambda ref: (-float(ref.get("relevance_score") or 0.0), str(ref.get("outcome_key") or "")))
        summary = str(refs[0].get("explanation") or "").strip()
        if not summary:
            continue
        pattern_relevant_gauges.append(
            {
                "gauge_key": gauge_key,
                "gauge_label": GAUGE_LABELS.get(gauge_key, gauge_key.replace("_", " ").title()),
                "summary": summary,
                "active_pattern_refs": refs[:2],
            }
        )

    primary_reason = str(primary_driver.get("personal_reason") or "").strip() if primary_driver else ""
    supporting_reasons = [
        str(row.get("personal_reason") or "").strip()
        for row in supporting_drivers
        if str(row.get("personal_reason") or "").strip()
    ]
    daily_brief = ""
    if primary_driver:
        label = str(primary_driver.get("label") or primary_driver.get("key") or "Today")
        if primary_reason:
            daily_brief = f"Lead with {label.lower()} today. {primary_reason}"
        else:
            daily_brief = f"Lead with {label.lower()} today. It is the strongest current driver in your mix."
        if supporting_drivers:
            support_label = str(supporting_drivers[0].get("label") or supporting_drivers[0].get("key") or "").strip()
            if support_label:
                daily_brief += f" {support_label} stays secondary."

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_top_drivers": raw_top_drivers,
        "ranked_drivers": scored_rows,
        "primary_driver": primary_driver,
        "supporting_drivers": supporting_drivers,
        "active_pattern_refs": active_pattern_refs,
        "pattern_relevant_gauges": pattern_relevant_gauges,
        "today_personal_themes": today_personal_themes,
        "today_relevance_explanations": {
            "primary_driver": primary_reason,
            "supporting_drivers": supporting_reasons,
            "daily_brief": daily_brief,
        },
        "compact_driver_lines": [_compact_driver_line(row) for row in scored_rows[:3]],
    }


async def fetch_best_pattern_rows(conn, user_id: str) -> List[Dict[str, Any]]:
    try:
        async with conn.cursor(**_cursor_kwargs()) as cur:
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
            rows = await cur.fetchall()
            if rows:
                return [dict(row) for row in rows]
    except Exception:
        try:
            await conn.rollback()
        except Exception:
            pass

    try:
        async with conn.cursor(**_cursor_kwargs()) as cur:
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
    except Exception:
        try:
            await conn.rollback()
        except Exception:
            pass
        return []

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in raw_rows:
        grouped.setdefault((str(row.get("signal_key")), str(row.get("outcome_key"))), []).append(row)
    return [best for best in (select_best_lag(group) for group in grouped.values()) if best]


async def fetch_recent_outcome_summary(
    conn,
    user_id: str,
    day: date,
    *,
    days: int = 7,
) -> Dict[str, Any]:
    since_day = day - timedelta(days=max(days - 1, 0))
    counts = {key: 0 for key in OUTCOME_KEYS}
    latest: Dict[str, str] = {}

    try:
        async with conn.cursor(**_cursor_kwargs()) as cur:
            await cur.execute(
                f"""
                select day, {", ".join(OUTCOME_KEYS)}
                  from marts.user_daily_outcomes
                 where user_id = %s
                   and day between %s and %s
                 order by day desc
                """,
                (user_id, since_day, day),
                prepare=False,
            )
            rows = await cur.fetchall()
    except Exception:
        try:
            await conn.rollback()
        except Exception:
            pass
        return {"counts": counts, "latest": latest, "days": days}

    for row in rows:
        row_day = row.get("day")
        for key in OUTCOME_KEYS:
            if row.get(key) is not True:
                continue
            counts[key] += 1
            if key not in latest and isinstance(row_day, date):
                latest[key] = row_day.isoformat()

    return {"counts": counts, "latest": latest, "days": days}


async def resolve_current_drivers(
    *,
    user_id: str,
    day: date,
    definition: Optional[Mapping[str, Any]] = None,
    alerts_json: Any = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    from bots.gauges.local_payload import get_local_payload
    from bots.gauges.signal_resolver import resolve_signals

    def _run() -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        local_payload = get_local_payload(user_id, day)
        active_states = resolve_signals(
            user_id,
            day,
            local_payload=local_payload,
            definition=dict(definition or {}) or None,
        )
        return [dict(item) for item in active_states or [] if isinstance(item, Mapping)], local_payload or {}

    try:
        active_states, local_payload = await asyncio.to_thread(_run)
    except Exception:
        return [], [], {}

    drivers = normalize_environmental_drivers(
        active_states=active_states,
        local_payload=local_payload,
        alerts_json=alerts_json,
        limit=6,
    )
    return [dict(item) for item in drivers], active_states, local_payload
