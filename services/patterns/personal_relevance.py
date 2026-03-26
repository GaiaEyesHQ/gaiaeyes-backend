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
    "pollen_overall_exposed": "Allergen load",
    "pollen_tree_exposed": "Tree pollen",
    "pollen_grass_exposed": "Grass pollen",
    "pollen_weed_exposed": "Weed pollen",
    "pollen_mold_exposed": "Mold",
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
    "allergens": "pollen_overall_exposed",
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
CONFIDENCE_VALUE = {
    "Strong": 1.0,
    "Moderate": 0.7,
    "Emerging": 0.4,
}

DRIVER_SEVERITY_SCORE = {
    "high": 4.0,
    "watch": 3.0,
    "elevated": 3.0,
    "mild": 2.0,
    "low": 1.0,
}
DEFAULT_SIGNAL_STRENGTH = {
    "high": 1.0,
    "watch": 0.78,
    "elevated": 0.78,
    "mild": 0.55,
    "low": 0.25,
}
HARD_VISIBILITY_THRESHOLD = 0.9
PATTERN_RECENT_VISIBILITY_DAYS = 14

ROLE_LABELS = {
    0: ("primary", "Leading now"),
    1: ("supporting", "Also in play"),
    2: ("background", "In the background"),
}

_PATTERN_MESSAGE_MAP = {
    ("pressure_swing_exposed", "pain_flare_day"): {
        "full": "Pressure swings are a known repeating pattern in your pain flare history.",
        "short": "Pressure often matches your pain pattern.",
        "clause": "it often matches your pain pattern",
    },
    ("pressure_swing_exposed", "headache_day"): {
        "full": "Pressure swings are a known repeating pattern in your headache history.",
        "short": "Pressure often matches your headache pattern.",
        "clause": "it often matches your headache pattern",
    },
    ("pressure_swing_exposed", "focus_fog_day"): {
        "full": "Pressure swings have shown up before brain-fog days in your history.",
        "short": "Pressure can precede brain-fog days for you.",
        "clause": "it can precede brain-fog days for you",
    },
    ("temp_swing_exposed", "pain_flare_day"): {
        "full": "Temperature swings have shown up before your pain flare days.",
        "short": "Temperature swings often show up before pain flare days.",
        "clause": "they often show up before pain flare days",
    },
    ("temp_swing_exposed", "fatigue_day"): {
        "full": "Temperature swings often match fatigue in your pattern history.",
        "short": "Temperature swings often match fatigue for you.",
        "clause": "they often match fatigue for you",
    },
    ("aqi_moderate_plus_exposed", "fatigue_day"): {
        "full": "AQI often matches fatigue in your pattern history.",
        "short": "AQI often matches fatigue for you.",
        "clause": "it often matches fatigue for you",
    },
    ("aqi_moderate_plus_exposed", "focus_fog_day"): {
        "full": "AQI often matches brain-fog days in your pattern history.",
        "short": "AQI often matches brain-fog days for you.",
        "clause": "it often matches brain-fog days for you",
    },
    ("aqi_moderate_plus_exposed", "headache_day"): {
        "full": "AQI often matches headache days in your pattern history.",
        "short": "AQI often matches headache days for you.",
        "clause": "it often matches headache days for you",
    },
    ("pollen_overall_exposed", "headache_day"): {
        "full": "Allergen load often matches headache days in your pattern history.",
        "short": "Allergen load often matches headache days for you.",
        "clause": "it often matches headache days for you",
    },
    ("pollen_overall_exposed", "fatigue_day"): {
        "full": "Allergen load often matches fatigue in your pattern history.",
        "short": "Allergen load often matches fatigue for you.",
        "clause": "it often matches fatigue for you",
    },
    ("pollen_overall_exposed", "focus_fog_day"): {
        "full": "Allergen load often matches brain-fog days in your pattern history.",
        "short": "Allergen load often matches brain-fog days for you.",
        "clause": "it often matches brain-fog days for you",
    },
    ("solar_wind_exposed", "high_hr_day"): {
        "full": "Elevated solar wind has shown up before higher heart-rate days in your history.",
        "short": "Elevated solar wind has shown up before higher heart-rate days for you.",
        "clause": "it has shown up before higher heart-rate days for you",
    },
    ("solar_wind_exposed", "short_sleep_day"): {
        "full": "Elevated solar wind has shown up before shorter-sleep days in your history.",
        "short": "Elevated solar wind has shown up before shorter-sleep days for you.",
        "clause": "it has shown up before shorter-sleep days for you",
    },
    ("solar_wind_exposed", "fatigue_day"): {
        "full": "Elevated solar wind often matches fatigue in your pattern history.",
        "short": "Elevated solar wind often matches fatigue for you.",
        "clause": "it often matches fatigue for you",
    },
    ("solar_wind_exposed", "anxiety_day"): {
        "full": "Elevated solar wind often matches restless days in your pattern history.",
        "short": "Elevated solar wind often matches restless days for you.",
        "clause": "it often matches restless days for you",
    },
    ("kp_g1_plus_exposed", "poor_sleep_day"): {
        "full": "Geomagnetic activity has shown up before poorer-sleep days in your history.",
        "short": "Geomagnetic activity has shown up before poorer sleep for you.",
        "clause": "it has shown up before poorer sleep for you",
    },
    ("bz_south_exposed", "poor_sleep_day"): {
        "full": "Strong southward Bz has shown up before poorer-sleep days in your history.",
        "short": "Strong southward Bz has shown up before poorer sleep for you.",
        "clause": "it has shown up before poorer sleep for you",
    },
    ("schumann_exposed", "poor_sleep_day"): {
        "full": "Elevated Schumann variability has shown up before lighter or shorter sleep in your history.",
        "short": "Schumann variability has shown up before lighter sleep for you.",
        "clause": "it has shown up before lighter sleep for you",
    },
    ("schumann_exposed", "short_sleep_day"): {
        "full": "Elevated Schumann variability has shown up before lighter or shorter sleep in your history.",
        "short": "Schumann variability has shown up before shorter sleep for you.",
        "clause": "it has shown up before shorter sleep for you",
    },
    ("schumann_exposed", "focus_fog_day"): {
        "full": "Elevated Schumann variability often matches focus drift in your pattern history.",
        "short": "Schumann variability often matches focus drift for you.",
        "clause": "it often matches focus drift for you",
    },
    ("schumann_exposed", "anxiety_day"): {
        "full": "Elevated Schumann variability often matches restless days in your pattern history.",
        "short": "Schumann variability often matches restless days for you.",
        "clause": "it often matches restless days for you",
    },
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


def _normalized_signal_strength(driver: Mapping[str, Any]) -> float:
    strength = _safe_float(driver.get("signal_strength"))
    if strength is not None:
        return max(0.0, min(1.0, strength))
    severity = str(driver.get("severity") or "").strip().lower()
    return DEFAULT_SIGNAL_STRENGTH.get(severity, 0.25)


def _confidence_label(value: Any) -> str | None:
    token = str(value or "").strip().title()
    return token if token in CONFIDENCE_VALUE else None


def _confidence_value(value: Any) -> float:
    return CONFIDENCE_VALUE.get(str(value or "").strip().title(), 0.0)


def _recent_pattern_seen(row: Mapping[str, Any], *, day: date) -> bool:
    last_seen = row.get("last_seen_at")
    if not isinstance(last_seen, datetime):
        return False
    return last_seen.astimezone(timezone.utc).date() >= (day - timedelta(days=PATTERN_RECENT_VISIBILITY_DAYS))


def _visible_pattern_row(row: Mapping[str, Any], *, day: date) -> Optional[Dict[str, Any]]:
    out = dict(row)
    confidence = _confidence_label(out.get("confidence"))
    recent = _recent_pattern_seen(out, day=day)
    if _confidence_value(confidence) < 0.4 and not recent:
        return None

    if confidence is None and recent:
        confidence = "Emerging"
    if confidence:
        out["confidence"] = confidence
        out["confidence_rank"] = max(confidence_rank(confidence), int(out.get("confidence_rank") or 0))
    out["surfaceable"] = True
    out["recently_seen"] = recent
    return out


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
    if driver_key == "allergens":
        if profile.includes_any(SINUS_KEYS) or profile.includes_any(AIRWAY_KEYS):
            return 1.2
        if profile.has_any("migraine_history"):
            return 0.85
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
        if (
            profile.includes_any(PAIN_FLARE_KEYS)
            or profile.includes_any(AUTONOMIC_KEYS)
            or profile.includes_any(SINUS_KEYS)
            or profile.includes_any(AIRWAY_KEYS)
        ):
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


def pattern_anchor_statement(row: Mapping[str, Any], *, variant: str = "full") -> str:
    signal_key = str(row.get("signal_key") or "")
    outcome_key = str(row.get("outcome_key") or "")
    entry = _PATTERN_MESSAGE_MAP.get((signal_key, outcome_key)) or {}
    if entry.get(variant):
        return str(entry[variant])
    if variant == "short":
        return f"{signal_label(signal_key)} often match your {outcome_label(outcome_key).lower()} pattern."
    if variant == "clause":
        return f"they often match your {outcome_label(outcome_key).lower()} pattern"
    return f"{signal_label(signal_key)} have lined up with {outcome_label(outcome_key).lower()} in your history."


def _role_for_index(index: int) -> tuple[str | None, str | None]:
    return ROLE_LABELS.get(index, (None, None))


def _driver_reason(
    driver: Mapping[str, Any],
    top_refs: Sequence[Mapping[str, Any]],
    profile: PersonalizationProfile,
    *,
    variant: str = "full",
) -> str:
    if top_refs:
        return pattern_anchor_statement(top_refs[0], variant=variant)
    key = str(driver.get("key") or "")
    if _driver_sensitivity_boost(key, profile) > 0:
        label = str(driver.get("label") or key.replace("_", " ").title())
        if variant == "clause":
            return "it lines up with your sensitivity profile"
        if variant == "short":
            return f"{label} lines up with your sensitivity profile."
        return f"{label} matters a bit more for you because it matches your sensitivity profile."
    label = str(driver.get("label") or key.replace("_", " ").title())
    if variant == "clause":
        return "it is active right now"
    if variant == "short":
        return f"{label} is active right now."
    return f"{label} is active right now, but no stronger personal pattern is leading with it yet."


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
        "used_today_label": "Active now",
        "relevance_score": round(score, 2),
        "explanation": pattern_anchor_statement(row, variant="full"),
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
    return f"{label} rises in priority right now because {signal.lower()} matches your pattern history."


def _compact_driver_line(driver: Mapping[str, Any]) -> str:
    label = str(driver.get("label") or driver.get("key") or "Driver")
    role_label = str(driver.get("role_label") or "").strip()
    reason = str(driver.get("personal_reason_short") or driver.get("personal_reason") or "").strip()
    clause = str(driver.get("personal_reason_clause") or "").strip().rstrip(".")
    if str(driver.get("role") or "").strip() == "primary" and driver.get("override_active") and clause:
        reason = f"More relevant for you right now because {clause}."
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

    raw_rows: List[Dict[str, Any]] = [
        dict(driver)
        for driver in list(drivers or [])
        if isinstance(driver, Mapping) and bool(driver.get("show_driver", True))
    ]
    raw_top_drivers = [dict(row) for row in raw_rows[:3]]
    scored_rows: List[Dict[str, Any]] = []

    for raw_index, driver in enumerate(raw_rows):
        key = str(driver.get("key") or "").strip()
        if not key:
            continue
        signal_key = DRIVER_TO_SIGNAL_KEY.get(key)
        signal_strength = _normalized_signal_strength(driver)
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
        pattern_weight_score = sum(score for score, _ in refs_with_score[:2])
        personal_weight = 1.0 + min(1.0, (sensitivity_boost * 0.18) + (pattern_weight_score * 0.12))
        driver_score = signal_strength * personal_weight
        display_score = max(signal_strength, driver_score)
        hard_visible = bool(driver.get("force_visible")) or signal_strength >= HARD_VISIBILITY_THRESHOLD
        show_driver = bool(driver.get("show_driver", True)) or hard_visible

        enriched = dict(driver)
        enriched["raw_severity_score"] = round(severity_score, 2)
        enriched["personal_relevance_score"] = round(driver_score, 3)
        enriched["signal_strength"] = round(signal_strength, 3)
        enriched["personal_weight"] = round(personal_weight, 3)
        enriched["driver_score"] = round(driver_score, 3)
        enriched["display_score"] = round(display_score, 3)
        enriched["hard_visible"] = hard_visible
        enriched["show_driver"] = show_driver
        enriched["active_pattern_refs"] = top_refs
        enriched["personal_reason"] = _driver_reason(enriched, top_refs, profile, variant="full")
        enriched["personal_reason_short"] = _driver_reason(enriched, top_refs, profile, variant="short")
        enriched["personal_reason_clause"] = _driver_reason(enriched, top_refs, profile, variant="clause")
        enriched["_sort_index"] = raw_index
        scored_rows.append(enriched)

    scored_rows.sort(
        key=lambda row: (
            -int(bool(row.get("hard_visible"))),
            -float(row.get("display_score") or 0.0),
            -float(row.get("signal_strength") or 0.0),
            -float(row.get("raw_severity_score") or 0.0),
            int(row.get("_sort_index") or 0),
        )
    )
    scored_rows = [row for row in scored_rows if bool(row.get("show_driver", True))]

    for index, row in enumerate(scored_rows):
        role, role_label = _role_for_index(index)
        if role:
            row["role"] = role
        if role_label:
            row["role_label"] = role_label
        row.pop("_sort_index", None)

    primary_driver = dict(scored_rows[0]) if scored_rows else None
    supporting_drivers = [dict(row) for row in scored_rows[1:3]]
    raw_primary = dict(raw_top_drivers[0]) if raw_top_drivers else None
    override_note = ""
    if primary_driver and raw_primary:
        raw_key = str(raw_primary.get("key") or "").strip()
        primary_key = str(primary_driver.get("key") or "").strip()
        if raw_key and primary_key and raw_key != primary_key:
            primary_driver["override_active"] = True
            for row in scored_rows:
                if str(row.get("key") or "").strip() == primary_key:
                    row["override_active"] = True
            clause = str(primary_driver.get("personal_reason_clause") or "").strip().rstrip(".")
            raw_label = str(raw_primary.get("label") or raw_key.replace("_", " ").title())
            primary_label = str(primary_driver.get("label") or primary_key.replace("_", " ").title())
            if clause:
                override_note = (
                    f"{raw_label} is active, but {primary_label} matters more for you right now because {clause}."
                )
            else:
                override_note = f"{raw_label} is active, but {primary_label} looks more relevant for you right now."
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
        str(row.get("personal_reason_short") or row.get("personal_reason") or "").strip()
        for row in supporting_drivers
        if str(row.get("personal_reason_short") or row.get("personal_reason") or "").strip()
    ]
    daily_brief = ""
    if primary_driver:
        label = str(primary_driver.get("label") or primary_driver.get("key") or "This signal")
        primary_short = str(primary_driver.get("personal_reason_short") or "").strip()
        if override_note:
            daily_brief = override_note
        elif primary_short:
            daily_brief = f"Right now, {label.lower()} looks most relevant for you. {primary_short}"
        else:
            daily_brief = f"Right now, {label.lower()} looks like the clearest current driver in your mix."
        if supporting_drivers:
            support_label = str(supporting_drivers[0].get("label") or supporting_drivers[0].get("key") or "").strip()
            if support_label:
                daily_brief += f" {support_label} is also in the mix."

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
            "override_note": override_note,
        },
        "compact_driver_lines": [_compact_driver_line(row) for row in scored_rows[:3]],
    }


async def fetch_best_pattern_rows(conn, user_id: str) -> List[Dict[str, Any]]:
    try:
        async with conn.cursor(**_cursor_kwargs()) as cur:
            await cur.execute(
                """
                select *
                  from marts.user_pattern_associations
                 where user_id = %s
                 order by confidence_rank desc, relative_lift desc, rate_diff desc, lag_hours asc
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

    today = datetime.now(timezone.utc).date()
    visible_rows = [row for row in (_visible_pattern_row(item, day=today) for item in raw_rows) if row]
    if not visible_rows:
        return []

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in visible_rows:
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
