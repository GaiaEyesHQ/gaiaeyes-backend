from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

try:
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - local unit tests can run without psycopg installed.
    dict_row = None

from bots.notifications.push_logic import flare_class_rank
from bots.patterns.pattern_engine_job import OUTCOME_SYMPTOM_CODES
from services.drivers.driver_normalize import normalize_environmental_drivers
from services.patterns.personal_relevance import (
    compute_personal_relevance,
    fetch_best_pattern_rows,
    fetch_recent_outcome_summary,
    resolve_current_drivers,
)
from services.voice.drivers import build_driver_reason_semantic, render_driver_reason


UTC = timezone.utc

_CATEGORY_LABELS = {
    "space": "Space",
    "earth": "Earth / Resonance",
    "local": "Local",
    "body_context": "Body Context",
}

_DRIVER_CATEGORY = {
    "pressure": "local",
    "temp": "local",
    "aqi": "local",
    "allergens": "local",
    "overexertion": "body_context",
    "allergen_exposure": "body_context",
    "kp": "space",
    "bz": "space",
    "sw": "space",
    "solar_wind": "space",
    "ulf": "space",
    "flare": "space",
    "cme": "space",
    "sep": "space",
    "drap": "space",
    "schumann": "earth",
}

_BASE_DRIVER_ORDER = {
    "pressure": 1,
    "temp": 2,
    "aqi": 3,
    "allergens": 4,
    "kp": 5,
    "bz": 6,
    "sw": 7,
    "ulf": 8,
    "flare": 9,
    "cme": 10,
    "sep": 11,
    "drap": 12,
    "schumann": 13,
    "overexertion": 200,
    "allergen_exposure": 201,
}

_SEVERITY_RANK = {
    "high": 4,
    "watch": 3,
    "elevated": 3,
    "mild": 2,
    "low": 1,
}

_CANONICAL_KEY_MAP = {
    "sw": "solar_wind",
    "radio": "drap",
    "radiation": "sep",
    "flares": "flare",
}

_KEY_ALIASES = {
    "pressure": ["pressure"],
    "temp": ["temp", "temperature"],
    "aqi": ["aqi"],
    "allergens": ["allergens", "allergen_load"],
    "kp": ["kp", "geomagnetic", "geomagnetic_activity"],
    "bz": ["bz", "bz_coupling"],
    "solar_wind": ["solar_wind", "sw"],
    "ulf": ["ulf"],
    "flare": ["flare", "flares"],
    "cme": ["cme"],
    "sep": ["sep", "radiation"],
    "drap": ["drap", "radio"],
    "schumann": ["schumann"],
    "overexertion": ["overexertion", "heavy_activity"],
    "allergen_exposure": ["allergen_exposure", "allergen exposure"],
}

_WHAT_IT_IS = {
    "pressure": "Rapid barometric changes in your local weather.",
    "temp": "A larger-than-usual local temperature swing.",
    "aqi": "Ambient air quality in your current area.",
    "allergens": "Current pollen and allergen load around you.",
    "kp": "Geomagnetic activity measured on the planetary Kp scale.",
    "bz": "The north-south magnetic field orientation in the solar wind.",
    "solar_wind": "The speed and pressure of charged particles flowing from the Sun.",
    "ulf": "Ultra-low-frequency geomagnetic field motion measured across stations.",
    "flare": "Recent solar flare activity visible in X-ray output.",
    "cme": "A coronal mass ejection watch or tracked arrival window.",
    "sep": "Solar energetic particle activity.",
    "drap": "High-frequency radio absorption from disturbed ionospheric conditions.",
    "schumann": "Recent variability in Earth-ionosphere resonance activity.",
    "overexertion": "Recent heavy activity or overexertion you logged for today.",
    "allergen_exposure": "Recent allergen exposure you logged for today.",
}

_SCIENCE_NOTES = {
    "pressure": "Fast pressure changes are a common weather-context variable in symptom tracking.",
    "temp": "Bigger day-to-day temperature swings can increase physical load even when absolute temperatures look manageable.",
    "aqi": "AQI is an observational air-quality measure, not a diagnosis of exposure effects.",
    "allergens": "Pollen intensity is a local environmental signal and can change quickly by day, wind, and source type.",
    "kp": "Kp reflects planetary geomagnetic disturbance aggregated across magnetometer stations.",
    "bz": "More southward Bz can couple more efficiently into geomagnetic activity.",
    "solar_wind": "Higher solar-wind speed can support more noticeable geomagnetic coupling when conditions line up.",
    "ulf": "ULF context reflects broad field-motion structure, coherence, and persistence across stations.",
    "flare": "Flare classes are observational solar X-ray categories rather than a measure of personal effect.",
    "cme": "CME watches describe a tracked arrival window, not a guaranteed ground-level effect.",
    "sep": "SEP levels describe energetic particle activity in near-Earth space.",
    "drap": "DRAP-style absorption reflects ionospheric radio absorption, especially on higher-latitude paths.",
    "schumann": "Schumann readings here are contextual environmental measurements, not a medical marker.",
    "overexertion": "Logged exposures are body-context inputs that help explain recovery load alongside environmental drivers.",
    "allergen_exposure": "Logged allergen exposure is body context from your own report, not a measured ambient pollen level.",
}

_BODY_CONTEXT_NOTE = (
    "Body context is personal context from your recent health and symptom data. "
    "It is not the same thing as an external environmental signal."
)

_EXPOSURE_DRIVER_WINDOWS_HOURS = {
    "overexertion": 18.0,
    "allergen_exposure": 24.0,
}

_EXPOSURE_DRIVER_META = {
    "overexertion": {
        "label": "Heavy Activity",
        "short_reason": "Recent heavy activity may still be adding recovery load.",
        "active_now_text": "Recent heavy activity is still in the mix for today.",
    },
    "allergen_exposure": {
        "label": "Allergen Exposure",
        "short_reason": "Recent allergen exposure may still be part of today’s body context.",
        "active_now_text": "Recent allergen exposure is still in the mix for today.",
    },
}


def _cursor_kwargs() -> dict[str, Any]:
    return {"row_factory": dict_row} if dict_row is not None else {}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return int(float(value))
    except Exception:
        return None


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.astimezone(UTC).isoformat()
    text = _clean_text(value)
    return text


def _parse_utc_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_local_payload(local_payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(local_payload, Mapping):
        return {}
    for key in ("payload", "data", "local"):
        nested = local_payload.get(key)
        if isinstance(nested, Mapping):
            return dict(nested)
    return dict(local_payload)


def _normalize_symptom_code(value: str) -> str:
    return value.strip().replace("-", "_").replace(" ", "_").upper()


def _symptom_label(value: str) -> str:
    return _normalize_symptom_code(value).replace("_", " ").title()


def _natural_label_series(value: str) -> tuple[str, int]:
    parts = [item.strip() for item in str(value or "").split(",") if item.strip()]
    if not parts:
        return "", 0
    if len(parts) == 1:
        return parts[0], 1

    normalized_tail = []
    for item in parts[1:]:
        if not item:
            continue
        normalized_tail.append(item[:1].lower() + item[1:] if item[:1].isupper() else item)

    if len(parts) == 2:
        return f"{parts[0]} and {normalized_tail[0]}", 2
    return f"{parts[0]}, {', '.join(normalized_tail[:-1])}, and {normalized_tail[-1]}", len(parts)


def _canonical_key(raw_key: str) -> str:
    key = str(raw_key or "").strip().lower()
    return _CANONICAL_KEY_MAP.get(key, key)


def _aliases_for_key(key: str) -> list[str]:
    canonical = _canonical_key(key)
    base = list(_KEY_ALIASES.get(canonical, []))
    if key and key not in base:
        base.append(key)
    if canonical and canonical not in base:
        base.append(canonical)
    return list(dict.fromkeys([item for item in base if item]))


def _category_for_key(key: str) -> str:
    normalized = str(key or "").strip().lower()
    if normalized.startswith("body_"):
        return "body_context"
    return _DRIVER_CATEGORY.get(_canonical_key(normalized), "local")


def _driver_order(key: str) -> int:
    normalized = str(key or "").strip().lower()
    if normalized.startswith("body_"):
        return 200
    return _BASE_DRIVER_ORDER.get(normalized, _BASE_DRIVER_ORDER.get(_canonical_key(normalized), 999))


def _role_for_index(index: int, *, state_key: str) -> tuple[str, str]:
    if index == 0 and state_key != "quiet":
        return "leading", "Leading now"
    if index < 3 and state_key != "quiet":
        return "supporting", "Also in play"
    return "background", "In the background"


def _state_for_driver(key: str, raw_state: Any, severity: Any) -> tuple[str, str]:
    token = str(raw_state or "").strip().lower().replace(" ", "_")
    normalized_key = _canonical_key(key)

    if token in {"storm", "strong", "strong_(coherent)"}:
        return ("storm", "Storm") if normalized_key == "kp" else ("strong", "Strong")
    if token in {"watch", "usg"}:
        return "watch", "Watch"
    if token in {"active", "active_(diffuse)"}:
        return "active", "Active"
    if token in {"elevated", "elevated_(coherent)"}:
        return "elevated", "Elevated"
    if token in {"quiet", "low"}:
        return "quiet", "Quiet"

    normalized_severity = str(severity or "").strip().lower()
    if normalized_key == "kp" and normalized_severity == "high":
        return "storm", "Storm"
    if normalized_severity == "high":
        return "strong", "Strong"
    if normalized_severity in {"watch", "elevated"}:
        return "watch", "Watch"
    if normalized_severity == "mild":
        return "active", "Active"
    return "quiet", "Quiet"


def _reading_from_value(key: str, value: Any, unit: str | None = None) -> Optional[str]:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    suffix = f" {unit}" if unit else ""
    canonical = _canonical_key(key)
    if canonical in {"pressure", "bz", "temp"}:
        return f"{numeric:+.1f}{suffix}".strip()
    if canonical in {"aqi", "solar_wind"}:
        return f"{int(round(numeric))}{suffix}".strip()
    if canonical == "kp":
        return f"{numeric:.1f}{suffix}".strip()
    return f"{numeric:.1f}{suffix}".strip()


def _allergen_severity(level: str | None, index_value: float | None) -> str:
    from services.external import pollen

    if level:
        rank = pollen.LEVEL_RANK.get(level, 0)
        if rank >= pollen.LEVEL_RANK.get("very_high", 5):
            return "high"
        if rank >= pollen.LEVEL_RANK.get("high", 4):
            return "watch"
        if rank >= pollen.LEVEL_RANK.get("moderate", 3):
            return "mild"
    if index_value is None:
        return "low"
    if index_value >= 5:
        return "high"
    if index_value >= 4:
        return "watch"
    if index_value >= 3:
        return "mild"
    return "low"


def _build_base_driver(
    *,
    key: str,
    label: str,
    severity: str,
    state: str,
    value: Any = None,
    unit: str | None = None,
    reading: str | None = None,
    signal_strength: float | None = None,
    force_visible: bool = False,
    show_driver: bool = True,
    short_reason: str,
    active_now_text: str,
    what_it_is: str | None = None,
    science_note: str | None = None,
    source_hint: str | None = None,
    updated_at: str | None = None,
    aliases: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "severity": severity,
        "state": state,
        "value": value,
        "unit": unit,
        "display": f"{label}: {state}",
        "signal_strength": round(max(0.0, min(1.0, float(signal_strength if signal_strength is not None else 0.4))), 3),
        "force_visible": bool(force_visible),
        "show_driver": bool(show_driver),
        "reading": reading,
        "short_reason": short_reason,
        "active_now_text": active_now_text,
        "what_it_is": what_it_is or _WHAT_IT_IS.get(_canonical_key(key)),
        "science_note": science_note or _SCIENCE_NOTES.get(_canonical_key(key)),
        "source_hint": source_hint,
        "updated_at": updated_at,
        "aliases": list(aliases or []),
        "category": _category_for_key(key),
        "category_label": _CATEGORY_LABELS.get(_category_for_key(key), "Local"),
    }


def _base_short_reason(key: str, value: float | None, local_payload: Mapping[str, Any]) -> tuple[str, str, str | None]:
    from services.external import pollen

    weather = dict(local_payload.get("weather") or {})
    air = dict(local_payload.get("air") or {})
    allergens = dict(local_payload.get("allergens") or {})
    canonical = _canonical_key(key)

    if canonical == "pressure":
        pressure_12h = _safe_float(weather.get("baro_delta_12h_hpa") or weather.get("pressure_delta_12h"))
        pressure_24h = _safe_float(weather.get("baro_delta_24h_hpa") or weather.get("pressure_delta_24h_hpa"))
        if pressure_12h is not None:
            abs_delta = abs(pressure_12h)
            reading = f"{pressure_12h:+.1f} hPa / 12h"
            return (
                "Pressure moved sharply over the last 12 hours."
                if abs_delta >= 8
                else "Pressure is moving more than usual."
                if abs_delta >= 6
                else "Pressure looks relatively steady right now.",
                f"Pressure is running at a {pressure_12h:+.1f} hPa 12-hour change right now."
                if abs_delta >= 6
                else f"Pressure changes are limited right now at about {pressure_12h:+.1f} hPa over 12 hours.",
                reading,
            )
        if pressure_24h is not None:
            abs_delta = abs(pressure_24h)
            reading = f"{pressure_24h:+.1f} hPa / 24h"
            return (
                "Pressure moved sharply over the last day."
                if abs_delta >= 8
                else "Pressure moved noticeably over the last day."
                if abs_delta >= 6
                else "Pressure looks relatively steady right now.",
                f"Pressure is running at a {pressure_24h:+.1f} hPa day-over-day change."
                if abs_delta >= 6
                else f"Pressure changes are limited right now at about {pressure_24h:+.1f} hPa over the last day.",
                reading,
            )
    if canonical == "temp":
        temp_delta = _safe_float(weather.get("temp_delta_24h_c") or weather.get("temp_delta_24h"))
        if temp_delta is not None:
            abs_delta = abs(temp_delta)
            reading = f"{temp_delta:+.1f} C / 24h"
            return (
                "Temperature is swinging more than usual today."
                if abs_delta >= 8
                else "Temperature has shifted noticeably over the last day."
                if abs_delta >= 6
                else "Temperature looks relatively steady today.",
                f"Temperature is tracking at a {temp_delta:+.1f} C day-over-day swing."
                if abs_delta >= 6
                else f"Temperature change is limited right now at about {temp_delta:+.1f} C over the last day.",
                reading,
            )
    if canonical == "aqi":
        aqi = _safe_float(air.get("aqi"))
        if aqi is not None:
            reading = f"{int(round(aqi))} AQI"
            return (
                "Air quality is running above your quieter baseline." if aqi >= 51 else "Air quality looks relatively calm.",
                f"AQI is currently {int(round(aqi))}.",
                reading,
            )
    if canonical == "allergens":
        index_value = _safe_float(allergens.get("overall_index") or allergens.get("relevance_score"))
        level = str(allergens.get("overall_level") or "").strip().lower()
        primary_type = str(allergens.get("primary_type") or "").strip().lower()
        level_label = pollen.STATE_LABELS.get(level, level.replace("_", " ").title() if level else "Elevated")
        primary_label = pollen.TYPE_LABELS.get(primary_type) if primary_type else None
        reading = level_label if index_value is None else f"{level_label} ({index_value:.1f})"
        short = "Allergen load is elevated in your area right now."
        if primary_label:
            short = f"{primary_label} pollen is leading right now."
        active = f"Allergen load looks {level_label.lower()} right now."
        if primary_label:
            active = f"{primary_label} pollen is the main local allergen signal right now."
        return short, active, reading
    if canonical == "kp":
        reading = _reading_from_value(key, value, "Kp")
        return (
            "Geomagnetic activity is elevated right now.",
            f"Geomagnetic conditions are running around Kp {reading or 'elevated'} right now.",
            reading,
        )
    if canonical == "bz":
        reading = _reading_from_value(key, value, "nT")
        return (
            "Southward Bz is helping space-weather coupling.",
            f"Bz is running near {reading or 'a more southward orientation'} right now.",
            reading,
        )
    if canonical == "solar_wind":
        reading = _reading_from_value(key, value, "km/s")
        return (
            "Solar wind speed is elevated right now.",
            f"Solar wind speed is running near {reading or 'an elevated level'} right now.",
            reading,
        )
    if canonical == "schumann":
        reading = _reading_from_value(key, value, "Hz delta")
        return (
            "Resonance variability is elevated versus recent conditions.",
            "Resonance variability is running higher than its quieter recent baseline.",
            reading,
        )
    fallback_label = _WHAT_IT_IS.get(canonical, canonical.replace("_", " ").title())
    return (
        f"{fallback_label} is active right now.",
        f"{fallback_label} is active right now.",
        _reading_from_value(key, value, unit=None),
    )


def _seed_environmental_drivers(
    drivers: Sequence[Mapping[str, Any]],
    *,
    local_payload: Mapping[str, Any],
    generated_at: str,
) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for driver in drivers:
        key = str(driver.get("key") or "").strip().lower()
        if not key:
            continue
        label = str(driver.get("label") or key.replace("_", " ").title())
        short_reason, active_now_text, reading = _base_short_reason(key, _safe_float(driver.get("value")), local_payload)
        rows.append(
            _build_base_driver(
                key=key,
                label=label,
                severity=str(driver.get("severity") or "low").strip().lower() or "low",
                state=str(driver.get("state") or "Quiet"),
                value=_safe_float(driver.get("value")),
                unit=_clean_text(driver.get("unit")),
                reading=reading or _clean_text(driver.get("display")),
                signal_strength=_safe_float(driver.get("signal_strength")) or 0.4,
                force_visible=bool(driver.get("force_visible")),
                show_driver=bool(driver.get("show_driver", True)),
                short_reason=short_reason,
                active_now_text=active_now_text,
                source_hint="Current environmental signal",
                updated_at=generated_at,
                aliases=_aliases_for_key(key),
            )
        )
    return rows


def _seed_allergen_driver(local_payload: Mapping[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    from services.external import pollen

    allergens = dict(local_payload.get("allergens") or {})
    level = str(allergens.get("overall_level") or "").strip().lower() or None
    index_value = _safe_float(allergens.get("overall_index") or allergens.get("relevance_score"))
    primary_type = str(allergens.get("primary_type") or "").strip().lower() or None
    if level is None and index_value is None:
        return None

    severity = _allergen_severity(level, index_value)
    state_key, state_label = _state_for_driver("allergens", level or severity, severity)
    primary_label = pollen.TYPE_LABELS.get(primary_type) if primary_type else None
    level_label = pollen.STATE_LABELS.get(level, level.replace("_", " ").title() if level else state_label)
    reading = level_label if index_value is None else f"{level_label} ({index_value:.1f})"
    short_reason = "Allergen load is elevated in your area right now."
    active_now_text = f"Allergen load looks {level_label.lower()} right now."
    if primary_label:
        short_reason = f"{primary_label} pollen is leading right now."
        active_now_text = f"{primary_label} pollen is the main local allergen signal right now."

    return _build_base_driver(
        key="allergens",
        label="Allergens",
        severity=severity,
        state=state_label,
        value=index_value,
        unit="index" if index_value is not None else None,
        reading=reading,
        signal_strength=1.0 if severity == "high" else 0.82 if severity == "watch" else 0.58 if severity == "mild" else 0.25,
        force_visible=severity == "high",
        show_driver=True,
        short_reason=short_reason,
        active_now_text=active_now_text,
        source_hint="Local pollen context",
        updated_at=generated_at,
        aliases=_aliases_for_key("allergens"),
    )


def _seed_ulf_driver(raw_context: Mapping[str, Any] | None) -> Optional[Dict[str, Any]]:
    from services.geomagnetic_context import normalize_ulf_context

    context = normalize_ulf_context(raw_context)
    if not context or not bool(context.get("is_usable")):
        return None
    label = str(context.get("label") or "").strip()
    severity = "low"
    if label.lower().startswith("strong"):
        severity = "high"
    elif label.lower().startswith("elevated"):
        severity = "watch"
    elif label.lower().startswith("active"):
        severity = "mild"
    if severity == "low":
        return None

    confidence_label = _clean_text(context.get("confidence_label"))
    station_count = _safe_int(context.get("station_count"))
    reading_bits = [label]
    if confidence_label:
        reading_bits.append(f"{confidence_label} confidence")
    if station_count:
        reading_bits.append(f"{station_count} stations")
    reading = " • ".join(reading_bits)
    active_now_text = f"ULF field motion is {label.lower()} right now."
    if confidence_label:
        active_now_text += f" Confidence looks {confidence_label.lower()}."

    return _build_base_driver(
        key="ulf",
        label="ULF Activity",
        severity=severity,
        state=label,
        reading=reading,
        signal_strength=0.92 if severity == "high" else 0.72 if severity == "watch" else 0.54,
        force_visible=severity == "high",
        show_driver=True,
        short_reason="Regional ULF field motion is elevated right now.",
        active_now_text=active_now_text,
        source_hint="Regional ULF context",
        updated_at=_iso(context.get("ts_utc")),
        aliases=_aliases_for_key("ulf"),
    )


def _space_driver_reading_from_time(arrival_iso: str | None) -> Optional[str]:
    if not arrival_iso:
        return None
    try:
        arrival = datetime.fromisoformat(arrival_iso.replace("Z", "+00:00"))
    except Exception:
        return arrival_iso
    return arrival.astimezone(UTC).strftime("ETA %b %d %H:%M UTC")


def _seed_space_context_drivers(space_context: Mapping[str, Any]) -> list[Dict[str, Any]]:
    daily = dict(space_context.get("daily") or {})
    cme_row = dict(space_context.get("cme") or {})
    sep_row = dict(space_context.get("sep") or {})
    updated_at = _iso(daily.get("updated_at"))
    rows: list[Dict[str, Any]] = []

    flare_class = str(daily.get("xray_max_class") or "").strip().upper()
    flare_rank = flare_class_rank(flare_class)
    if flare_rank[0] >= 3 and flare_rank[1] >= 1.0:
        severity = "high" if flare_rank[0] >= 4 or flare_rank[1] >= 5.0 else "watch"
        rows.append(
            _build_base_driver(
                key="flare",
                label="Solar Flare Context",
                severity=severity,
                state="Strong" if severity == "high" else "Elevated",
                reading=flare_class,
                signal_strength=0.94 if severity == "high" else 0.74,
                force_visible=severity == "high",
                show_driver=True,
                short_reason=f"Solar flare activity reached {flare_class} today.",
                active_now_text=f"Today’s strongest flare has reached {flare_class}.",
                source_hint="Current solar flare context",
                updated_at=updated_at,
                aliases=_aliases_for_key("flare"),
            )
        )

    kp_estimate = _safe_float(cme_row.get("kp_estimate"))
    cme_speed = _safe_float(cme_row.get("cme_speed_kms"))
    arrival = _iso(cme_row.get("arrival_time"))
    if cme_row and (kp_estimate is not None or cme_speed is not None or arrival):
        severity = "high" if (kp_estimate or 0.0) >= 6 or (cme_speed or 0.0) >= 1200 else "watch"
        rows.append(
            _build_base_driver(
                key="cme",
                label="CME Context",
                severity=severity,
                state="Watch",
                reading=_space_driver_reading_from_time(arrival),
                signal_strength=0.9 if severity == "high" else 0.7,
                force_visible=severity == "high",
                show_driver=True,
                short_reason="A tracked CME arrival is in view.",
                active_now_text="A CME arrival is being tracked in the near-term space-weather window.",
                source_hint="Tracked CME arrivals",
                updated_at=arrival or updated_at,
                aliases=_aliases_for_key("cme"),
            )
        )

    sep_scale_index = _safe_float(daily.get("sep_s_max"))
    if sep_scale_index is None:
        sep_scale_index = _safe_float(sep_row.get("s_scale_index"))
    sep_ts = _iso(sep_row.get("ts_utc"))
    if sep_scale_index is not None and sep_scale_index >= 1:
        severity = "high" if sep_scale_index >= 2 else "watch"
        rows.append(
            _build_base_driver(
                key="sep",
                label="Solar Radiation",
                severity=severity,
                state="Strong" if severity == "high" else "Elevated",
                reading=f"S{int(round(sep_scale_index))}",
                signal_strength=0.94 if severity == "high" else 0.74,
                force_visible=severity == "high",
                show_driver=True,
                short_reason="Solar energetic particle activity is elevated.",
                active_now_text=f"Solar radiation activity is running at about S{int(round(sep_scale_index))} right now.",
                source_hint="Latest SEP feed",
                updated_at=sep_ts or updated_at,
                aliases=_aliases_for_key("sep"),
            )
        )

    drap_polar = _safe_float(daily.get("drap_absorption_polar_db"))
    drap_midlat = _safe_float(daily.get("drap_absorption_midlat_db"))
    if (drap_midlat or 0.0) >= 5.0 or (drap_polar or 0.0) >= 10.0:
        severity = "high" if (drap_midlat or 0.0) >= 10.0 or (drap_polar or 0.0) >= 20.0 else "watch"
        reading_bits: list[str] = []
        if drap_midlat is not None:
            reading_bits.append(f"{drap_midlat:.1f} dB mid-lat")
        if drap_polar is not None:
            reading_bits.append(f"{drap_polar:.1f} dB polar")
        rows.append(
            _build_base_driver(
                key="drap",
                label="Radio Absorption",
                severity=severity,
                state="Strong" if severity == "high" else "Elevated",
                reading=" • ".join(reading_bits) if reading_bits else None,
                signal_strength=0.94 if severity == "high" else 0.74,
                force_visible=severity == "high",
                show_driver=True,
                short_reason="HF radio absorption is elevated right now.",
                active_now_text="Radio absorption is elevated in the current ionospheric picture.",
                source_hint="Current DRAP absorption context",
                updated_at=updated_at,
                aliases=_aliases_for_key("drap"),
            )
        )

    return rows


def _body_driver_strength(points: float | None, *, key: str) -> float:
    if points is None:
        return 0.42 if key == "body_cycle_context" else 0.35
    return max(0.35, min(1.0, points / 10.0))


def _body_driver_severity(points: float | None) -> str:
    if points is None:
        return "mild"
    if points >= 8:
        return "high"
    if points >= 4:
        return "watch"
    return "mild"


def _seed_body_context_drivers(health_status_explainer: Mapping[str, Any] | None, *, generated_at: str) -> list[Dict[str, Any]]:
    if not isinstance(health_status_explainer, Mapping):
        return []

    rows: list[Dict[str, Any]] = []
    for payload in health_status_explainer.get("drivers") or []:
        if not isinstance(payload, Mapping):
            continue
        source_key = str(payload.get("key") or "").strip().lower()
        label = str(payload.get("label") or source_key.replace("_", " ").title()).strip()
        if not source_key or not label:
            continue
        body_key = f"body_{source_key}"
        points = _safe_float(payload.get("points"))
        severity = _body_driver_severity(points)
        state_key, state_label = _state_for_driver(body_key, payload.get("impact"), severity)
        display = _clean_text(payload.get("display"))
        short_reason = f"{label} is adding more body context right now."
        active_now = f"{label} is part of your current body context."
        what_it_is = f"{label} from your recent health context."
        if display:
            short_reason = f"{label} is adding body context right now: {display}."
            active_now = f"{label} is showing {display.lower()} right now."
        if source_key == "symptoms":
            symptom_series, symptom_count = _natural_label_series(display or "")
            short_reason = "Current symptoms are part of your body context right now."
            active_now = "Current symptoms are part of your body context right now."
            what_it_is = "Symptoms you recently logged as active."
            if symptom_series:
                verb = "is" if symptom_count == 1 else "are"
                short_reason = f"{symptom_series} {verb} active right now."
                active_now = f"Current symptoms in the mix right now: {display}."

        rows.append(
            _build_base_driver(
                key=body_key,
                label=label,
                severity=severity,
                state=state_label,
                reading=display,
                signal_strength=_body_driver_strength(points, key=body_key),
                force_visible=severity == "high",
                show_driver=True,
                short_reason=short_reason,
                active_now_text=active_now,
                what_it_is=what_it_is,
                science_note=_BODY_CONTEXT_NOTE,
                source_hint="Recent health context",
                updated_at=generated_at,
                aliases=[body_key, source_key],
            )
        )

    for payload in health_status_explainer.get("context") or []:
        if not isinstance(payload, Mapping):
            continue
        source_key = str(payload.get("key") or "").strip().lower()
        label = str(payload.get("label") or source_key.replace("_", " ").title()).strip()
        display = _clean_text(payload.get("display"))
        if not source_key or not label or not display:
            continue
        body_key = f"body_{source_key}"
        rows.append(
            _build_base_driver(
                key=body_key,
                label=label,
                severity="mild",
                state="Active",
                reading=display,
                signal_strength=_body_driver_strength(None, key=body_key),
                force_visible=False,
                show_driver=True,
                short_reason=f"{label} is part of your current body context.",
                active_now_text=f"{label} is currently {display.lower()}.",
                what_it_is=f"{label} from your recent body context.",
                science_note=_BODY_CONTEXT_NOTE,
                source_hint="Recent health context",
                updated_at=generated_at,
                aliases=[body_key, source_key],
            )
        )

    return rows


def _exposure_driver_signal_strength(max_intensity: int, events: int) -> float:
    if max_intensity >= 3:
        base = 0.9
    elif max_intensity >= 2 or events >= 2:
        base = 0.74
    else:
        base = 0.58
    return min(0.96, base + (0.04 * max(0, min(events - 1, 2))))


def _exposure_driver_severity(max_intensity: int, events: int) -> tuple[str, str]:
    if max_intensity >= 3:
        return "high", "Strong"
    if max_intensity >= 2 or events >= 2:
        return "watch", "Watch"
    return "mild", "Active"


def build_exposure_driver_rows(
    exposure_summary: Mapping[str, Any] | None,
    *,
    generated_at: str,
    asof: Optional[datetime] = None,
) -> list[Dict[str, Any]]:
    if not isinstance(exposure_summary, Mapping):
        return []

    anchor = asof or datetime.now(UTC)
    rows: list[Dict[str, Any]] = []
    for payload in exposure_summary.get("top_exposures") or []:
        if not isinstance(payload, Mapping):
            continue
        key = str(payload.get("exposure_key") or "").strip().lower()
        meta = _EXPOSURE_DRIVER_META.get(key)
        if not meta:
            continue
        last_ts = _parse_utc_datetime(payload.get("last_ts"))
        window_hours = _EXPOSURE_DRIVER_WINDOWS_HOURS.get(key)
        if last_ts is None or window_hours is None:
            continue
        age_hours = max(0.0, (anchor - last_ts).total_seconds() / 3600.0)
        if age_hours > window_hours:
            continue

        events = max(1, _safe_int(payload.get("events")) or 1)
        max_intensity = max(1, min(3, _safe_int(payload.get("max_intensity")) or 1))
        severity, state = _exposure_driver_severity(max_intensity, events)
        reading = "Logged recently" if events == 1 else f"{events} recent logs"

        rows.append(
            _build_base_driver(
                key=key,
                label=str(meta["label"]),
                severity=severity,
                state=state,
                reading=reading,
                signal_strength=_exposure_driver_signal_strength(max_intensity, events),
                force_visible=max_intensity >= 2,
                show_driver=True,
                short_reason=str(meta["short_reason"]),
                active_now_text=str(meta["active_now_text"]),
                source_hint="Recent exposure logs",
                updated_at=_iso(last_ts) or generated_at,
                aliases=_aliases_for_key(key),
            )
        )

    return rows


def _seed_sort_key(row: Mapping[str, Any]) -> tuple[int, float, int, int]:
    severity = str(row.get("severity") or "").strip().lower()
    return (
        int(bool(row.get("force_visible"))),
        float(row.get("signal_strength") or 0.0),
        _SEVERITY_RANK.get(severity, 0),
        -_driver_order(str(row.get("key") or "")),
    )


def _dedupe_seed_drivers(rows: Sequence[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    picked: dict[str, Dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("key") or "").strip().lower()
        if not key:
            continue
        candidate = dict(item)
        existing = picked.get(key)
        if existing is None or _seed_sort_key(candidate) > _seed_sort_key(existing):
            picked[key] = candidate
    output = list(picked.values())
    output.sort(key=_seed_sort_key, reverse=True)
    return output


def _current_symptom_rows_to_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        code = _normalize_symptom_code(str(row.get("symptom_code") or ""))
        label = _clean_text(row.get("label")) or _symptom_label(code)
        if code and label:
            output[code] = label
    return output


def _pattern_status(refs: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    confidence = ""
    if refs:
        confidence = str(refs[0].get("confidence") or "").strip().lower()
    if confidence == "strong":
        return "strong", "Strong pattern"
    if confidence == "moderate":
        return "moderate", "Moderate pattern"
    if confidence == "emerging":
        return "emerging", "Emerging pattern"
    return "no_clear_pattern_yet", "No clear pattern yet"


def _symptoms_for_driver(
    refs: Sequence[Mapping[str, Any]],
    current_symptom_map: Mapping[str, str],
) -> tuple[list[str], list[str]]:
    historical_codes: list[str] = []
    current_labels: list[str] = []
    for ref in refs:
        outcome_key = str(ref.get("outcome_key") or "").strip()
        for code in sorted(OUTCOME_SYMPTOM_CODES.get(outcome_key, set())):
            normalized_code = _normalize_symptom_code(code)
            historical_codes.append(normalized_code)
            if normalized_code in current_symptom_map:
                current_labels.append(current_symptom_map[normalized_code])

    historical_labels = [
        current_symptom_map.get(code) or _symptom_label(code)
        for code in historical_codes
    ]
    return (
        list(dict.fromkeys([label for label in current_labels if label]))[:4],
        list(dict.fromkeys([label for label in historical_labels if label]))[:6],
    )


def _outlook_match_for_driver(
    driver_key: str,
    outlook_payload: Mapping[str, Any] | None,
) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(outlook_payload, Mapping):
        return None, None
    aliases = {item.lower() for item in _aliases_for_key(driver_key)}
    windows = [
        ("24h", outlook_payload.get("next_24h")),
        ("72h", outlook_payload.get("next_72h")),
        ("7d", outlook_payload.get("next_7d")),
    ]
    for label, window in windows:
        if not isinstance(window, Mapping):
            continue
        for driver in window.get("top_drivers") or []:
            if not isinstance(driver, Mapping):
                continue
            candidate_key = str(driver.get("key") or "").strip().lower()
            if _canonical_key(candidate_key) not in aliases and candidate_key not in aliases:
                continue
            detail = _clean_text(driver.get("detail"))
            if label == "24h":
                lead = "Still worth watching over the next 24 hours."
            elif label == "72h":
                lead = "Forecast to remain relevant over the next 72 hours."
            else:
                lead = "Still part of the broader 7-day outlook."
            return label, f"{lead} {detail}".strip() if detail else lead
    return None, None


def _body_personal_reason(row: Mapping[str, Any]) -> str:
    label = str(row.get("label") or "Body context").strip()
    display = _clean_text(row.get("reading"))
    if display:
        return f"{label} is part of your current body context right now: {display}."
    return f"{label} is part of your current body context right now."


def _canonicalize_pattern_refs(driver_key: str, refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    canonical = _canonical_key(driver_key)
    output: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        payload = dict(ref)
        payload["driver_key"] = canonical
        output.append(payload)
    return output


def _finalize_driver_items(
    ranked_rows: Sequence[Mapping[str, Any]],
    *,
    day: date,
    current_symptom_rows: Sequence[Mapping[str, Any]],
    outlook_payload: Mapping[str, Any] | None,
    generated_at: str,
) -> list[dict[str, Any]]:
    current_symptom_map = _current_symptom_rows_to_map(current_symptom_rows)
    output: list[dict[str, Any]] = []

    for index, row in enumerate(ranked_rows):
        internal_key = str(row.get("key") or "").strip().lower()
        canonical_key = _canonical_key(internal_key)
        state_key, state_label = _state_for_driver(internal_key, row.get("state"), row.get("severity"))
        role, role_label = _role_for_index(index, state_key=state_key)
        pattern_refs = _canonicalize_pattern_refs(internal_key, row.get("active_pattern_refs") or [])
        current_symptoms, historical_symptoms = _symptoms_for_driver(pattern_refs, current_symptom_map)
        pattern_status, pattern_status_label = _pattern_status(pattern_refs)
        pattern_summary = _clean_text(pattern_refs[0].get("explanation")) if pattern_refs else None
        if not pattern_summary:
            pattern_summary = "We’re still learning how this tends to affect you."
        outlook_relevance, outlook_summary = _outlook_match_for_driver(canonical_key, outlook_payload)
        personal_reason = _clean_text(row.get("personal_reason"))
        if _category_for_key(internal_key) == "body_context" and (
            not personal_reason or personal_reason.lower().endswith("no stronger personal pattern is leading with it yet.")
        ):
            personal_reason = _body_personal_reason(row)
        short_reason = row.get("short_reason") or f"{row.get('label') or canonical_key} is active right now."
        reason_row = dict(row)
        reason_row["key"] = canonical_key
        reason_row["label"] = row.get("label") or canonical_key.replace("_", " ").title()
        reason_row["short_reason"] = short_reason
        reason_row["personal_reason"] = personal_reason or f"{row.get('label') or canonical_key} is active right now."
        reason_row["pattern_status"] = pattern_status
        reason_row["current_symptoms"] = current_symptoms
        reason_row["historical_symptoms"] = historical_symptoms
        reason_row["outlook_summary"] = outlook_summary
        reason_semantic = build_driver_reason_semantic(day=day, row=reason_row)

        output.append(
            {
                "id": canonical_key,
                "key": canonical_key,
                "source_key": internal_key,
                "aliases": list(
                    dict.fromkeys(
                        _aliases_for_key(canonical_key) + [alias for alias in row.get("aliases") or [] if alias]
                    )
                ),
                "label": row.get("label") or canonical_key.replace("_", " ").title(),
                "category": row.get("category") or _category_for_key(internal_key),
                "category_label": row.get("category_label") or _CATEGORY_LABELS.get(_category_for_key(internal_key), "Local"),
                "role": role,
                "role_label": role_label,
                "state": state_key,
                "state_label": state_label,
                "severity": row.get("severity"),
                "reading": row.get("reading") or _reading_from_value(internal_key, row.get("value"), row.get("unit")),
                "reading_value": _safe_float(row.get("value")),
                "reading_unit": row.get("unit"),
                "short_reason": render_driver_reason(reason_semantic, variant="short"),
                "personal_reason": render_driver_reason(reason_semantic, variant="full"),
                "current_symptoms": current_symptoms,
                "historical_symptoms": historical_symptoms,
                "pattern_status": pattern_status,
                "pattern_status_label": pattern_status_label,
                "pattern_summary": pattern_summary,
                "pattern_evidence_count": len(pattern_refs),
                "pattern_lag_hours": _safe_int(pattern_refs[0].get("lag_hours")) if pattern_refs else None,
                "pattern_refs": pattern_refs,
                "outlook_relevance": outlook_relevance,
                "outlook_summary": outlook_summary,
                "updated_at": row.get("updated_at") or generated_at,
                "asof": row.get("updated_at") or generated_at,
                "what_it_is": row.get("what_it_is") or _WHAT_IT_IS.get(canonical_key),
                "active_now_text": row.get("active_now_text") or row.get("short_reason"),
                "science_note": row.get("science_note") or _SCIENCE_NOTES.get(canonical_key),
                "source_hint": row.get("source_hint"),
                "signal_strength": _safe_float(row.get("signal_strength")),
                "personal_relevance_score": _safe_float(row.get("personal_relevance_score")),
                "display_score": _safe_float(row.get("display_score")),
                "is_objectively_active": state_key != "quiet",
                "voice_semantic": reason_semantic.to_dict(),
            }
        )

    return output


def _summary_note(drivers: Sequence[Mapping[str, Any]]) -> str:
    if not drivers:
        return "Conditions look relatively calm."
    top = drivers[0]
    top_label = str(top.get("label") or top.get("key") or "Conditions").strip()
    top_state = str(top.get("state") or "").strip().lower()
    if top_state == "quiet":
        return "Nothing especially strong right now."
    if len(drivers) >= 2:
        first_category = str(drivers[0].get("category") or "")
        second_category = str(drivers[1].get("category") or "")
        if first_category and second_category and first_category != second_category:
            return f"{_CATEGORY_LABELS.get(first_category, first_category.title())} + {_CATEGORY_LABELS.get(second_category, second_category.title())} drivers are both active."
    return f"{top_label} is leading right now."


def _setup_hints(
    *,
    local_payload: Mapping[str, Any],
    outlook_payload: Mapping[str, Any] | None,
    health_status_explainer: Mapping[str, Any] | None,
    recent_outcomes: Mapping[str, Any],
    current_symptom_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    if not local_payload or not bool(((outlook_payload or {}).get("forecast_data_ready") or {}).get("location_found")):
        hints.append(
            {
                "key": "location",
                "label": "Add location",
                "reason": "Local drivers and outlook need your location context.",
            }
        )

    health_ready = bool((health_status_explainer or {}).get("drivers")) or bool((health_status_explainer or {}).get("context"))
    if not health_ready:
        hints.append(
            {
                "key": "health_data",
                "label": "Connect health data",
                "reason": "Body context gets better when your baseline data is available.",
            }
        )

    has_recent_outcomes = any(int((recent_outcomes.get("counts") or {}).get(key) or 0) > 0 for key in (recent_outcomes.get("counts") or {}))
    if not current_symptom_rows and not has_recent_outcomes:
        hints.append(
            {
                "key": "symptoms",
                "label": "Log symptoms",
                "reason": "Pattern links improve once you have some symptom history.",
            }
        )
    return hints


def compose_all_drivers_payload(
    *,
    day: date,
    seed_drivers: Sequence[Mapping[str, Any]],
    pattern_rows: Sequence[Mapping[str, Any]],
    user_tags: Iterable[Any],
    recent_outcomes: Mapping[str, Any],
    current_symptom_rows: Sequence[Mapping[str, Any]],
    health_status_explainer: Mapping[str, Any] | None,
    local_payload: Mapping[str, Any],
    outlook_payload: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    personal = compute_personal_relevance(
        day=day,
        drivers=seed_drivers,
        pattern_rows=pattern_rows,
        user_tags=user_tags,
        recent_outcomes=recent_outcomes,
    )
    ranked_rows = [dict(item) for item in personal.get("ranked_drivers") or [] if isinstance(item, Mapping)]
    finalized = _finalize_driver_items(
        ranked_rows,
        day=day,
        current_symptom_rows=current_symptom_rows,
        outlook_payload=outlook_payload,
        generated_at=generated_at,
    )

    active_count = sum(1 for item in finalized if bool(item.get("is_objectively_active")))
    strongest_category = finalized[0].get("category_label") if finalized else None
    primary_state = finalized[0].get("state_label") if finalized else None
    asof_candidates = [str(item.get("asof")) for item in finalized if item.get("asof")]
    asof = max(asof_candidates) if asof_candidates else generated_at

    return {
        "generated_at": generated_at,
        "asof": asof,
        "day": day.isoformat(),
        "summary": {
            "active_driver_count": active_count,
            "total_count": len(finalized),
            "strongest_category": strongest_category,
            "primary_state": primary_state,
            "note": _summary_note(finalized),
            "has_personal_patterns": bool(personal.get("active_pattern_refs")),
        },
        "has_personal_patterns": bool(personal.get("active_pattern_refs")),
        "filters": [
            {"key": "all", "label": "All"},
            {"key": "space", "label": "Space"},
            {"key": "earth", "label": "Earth / Resonance"},
            {"key": "local", "label": "Local"},
            {"key": "body_context", "label": "Body Context"},
        ],
        "drivers": finalized,
        "setup_hints": _setup_hints(
            local_payload=local_payload,
            outlook_payload=outlook_payload,
            health_status_explainer=health_status_explainer,
            recent_outcomes=recent_outcomes,
            current_symptom_rows=current_symptom_rows,
        ),
        "today_relevance_explanations": personal.get("today_relevance_explanations") or {},
        "voice_semantics": {
            "driver_summary": personal.get("driver_summary_semantic") or {},
        },
    }


async def _fetch_current_symptom_rows(conn, user_id: str) -> list[dict[str, Any]]:
    from app.db import symptoms as symptoms_db

    try:
        return await symptoms_db.fetch_current_symptom_items(conn, user_id, window_hours=12)
    except Exception:
        return await symptoms_db.fetch_current_symptom_items_fallback(conn, user_id, window_hours=12)


async def _fetch_space_context(conn, day: date) -> dict[str, Any]:
    today = datetime.now(UTC)
    async with conn.cursor(**_cursor_kwargs()) as cur:
        await cur.execute(
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
                   coalesce(updated_at, now()) as updated_at
              from marts.space_weather_daily
             where day <= %s
             order by day desc
             limit 1
            """,
            (day,),
            prepare=False,
        )
        daily = dict(await cur.fetchone() or {})

        await cur.execute(
            """
            select arrival_time, simulation_id, location, kp_estimate, cme_speed_kms, confidence
              from marts.cme_arrivals
             where arrival_time >= %s
               and arrival_time <= %s
             order by arrival_time asc
             limit 1
            """,
            (today - timedelta(hours=6), today + timedelta(hours=72)),
            prepare=False,
        )
        cme_row = dict(await cur.fetchone() or {})

        await cur.execute(
            """
            select ts_utc, energy_band, flux, s_scale, s_scale_index
              from ext.sep_flux
             order by ts_utc desc
             limit 1
            """,
            prepare=False,
        )
        sep_row = dict(await cur.fetchone() or {})

    return {"daily": daily, "cme": cme_row, "sep": sep_row}


async def build_all_drivers_payload(
    conn,
    *,
    user_id: str,
    day: date,
) -> Dict[str, Any]:
    from app.db import ulf as ulf_db
    from bots.definitions.load_definition_base import load_definition_base
    from bots.gauges.gauge_scorer import fetch_exposure_summary, fetch_health_status_context, fetch_user_tags
    from services.forecast_outlook import build_user_outlook_payload
    from services.personalization.health_context import build_personalization_profile

    generated_at = datetime.now(UTC).isoformat()
    try:
        definition, _ = load_definition_base()
    except Exception:
        definition = {}

    _, active_states, local_payload = await resolve_current_drivers(
        user_id=user_id,
        day=day,
        definition=definition,
    )
    normalized_local = _normalize_local_payload(local_payload)
    environmental = normalize_environmental_drivers(
        active_states=active_states,
        local_payload=local_payload,
        alerts_json=[],
        limit=12,
    )

    user_tags_task = asyncio.create_task(asyncio.to_thread(fetch_user_tags, user_id))
    health_status_task = asyncio.create_task(asyncio.to_thread(fetch_health_status_context, user_id, day))

    pattern_rows = await fetch_best_pattern_rows(conn, user_id)
    recent_outcomes = await fetch_recent_outcome_summary(conn, user_id, day)
    current_symptom_rows = await _fetch_current_symptom_rows(conn, user_id)
    latest_ulf = await ulf_db.get_latest_ulf_context(conn)
    outlook_payload = await build_user_outlook_payload(conn, user_id)
    space_context = await _fetch_space_context(conn, day)

    user_tags = await user_tags_task
    profile = build_personalization_profile(user_tags)
    exposure_summary = await asyncio.to_thread(fetch_exposure_summary, user_id, day, profile=profile)
    health_status_explainer = await health_status_task

    seed_drivers: list[Dict[str, Any]] = []
    seed_drivers.extend(_seed_environmental_drivers(environmental, local_payload=normalized_local, generated_at=generated_at))

    allergen_driver = _seed_allergen_driver(normalized_local, generated_at=generated_at)
    if allergen_driver:
        seed_drivers.append(allergen_driver)

    ulf_driver = _seed_ulf_driver(latest_ulf)
    if ulf_driver:
        seed_drivers.append(ulf_driver)

    seed_drivers.extend(_seed_space_context_drivers(space_context))
    seed_drivers.extend(build_exposure_driver_rows(exposure_summary, generated_at=generated_at))
    seed_drivers.extend(_seed_body_context_drivers(health_status_explainer, generated_at=generated_at))

    return compose_all_drivers_payload(
        day=day,
        seed_drivers=_dedupe_seed_drivers(seed_drivers),
        pattern_rows=[dict(item) for item in pattern_rows or [] if isinstance(item, Mapping)],
        user_tags=list(user_tags or []),
        recent_outcomes=dict(recent_outcomes or {}),
        current_symptom_rows=[dict(item) for item in current_symptom_rows or [] if isinstance(item, Mapping)],
        health_status_explainer=dict(health_status_explainer or {}),
        local_payload=normalized_local,
        outlook_payload=dict(outlook_payload or {}),
    )
