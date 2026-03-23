from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping, Sequence


_DISPLAY_LABELS = {
    "Quiet": "Quiet",
    "Active (diffuse)": "Active",
    "Elevated (coherent)": "Elevated",
    "Strong (coherent)": "Strong",
}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1"}:
            return True
        if normalized in {"false", "f", "no", "n", "0"}:
            return False
    return None


def _normalize_quality_flags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            return _normalize_quality_flags(decoded)
        return [stripped]
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        out: list[str] = []
        for item in raw:
            text = _clean_text(item)
            if text and text not in out:
                out.append(text)
        return out
    text = _clean_text(raw)
    return [text] if text else []


def map_ulf_context_label(raw_class: str | None) -> str | None:
    cleaned = _clean_text(raw_class)
    if not cleaned:
        return None
    return _DISPLAY_LABELS.get(cleaned, cleaned)


def map_ulf_confidence_label(score: float | None) -> str | None:
    if score is None:
        return None
    if score < 0.35:
        return "Low"
    if score < 0.65:
        return "Moderate"
    return "High"


def derive_ulf_quality_flags(flags: list[str] | None) -> dict[str, bool]:
    normalized = _normalize_quality_flags(flags)
    return {
        "missing_samples": "missing_samples" in normalized,
        "low_history": "low_history" in normalized,
    }


def normalize_ulf_context(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None

    class_raw = _clean_text(raw.get("ulf_context_class_raw") or raw.get("context_class"))
    label = _clean_text(raw.get("ulf_context_label")) or map_ulf_context_label(class_raw)
    confidence_score = _to_float(raw.get("ulf_confidence_score") or raw.get("confidence_score"))
    confidence_label = _clean_text(raw.get("ulf_confidence_label")) or map_ulf_confidence_label(confidence_score)
    regional_intensity = _to_float(raw.get("ulf_regional_intensity") or raw.get("regional_intensity"))
    regional_coherence = _to_float(raw.get("ulf_regional_coherence") or raw.get("regional_coherence"))
    regional_persistence = _to_float(raw.get("ulf_regional_persistence") or raw.get("regional_persistence"))
    quality_flags = _normalize_quality_flags(raw.get("ulf_quality_flags") or raw.get("quality_flags"))
    quality = derive_ulf_quality_flags(quality_flags)

    station_count = _to_int(raw.get("ulf_station_count"))
    if station_count is None:
        stations_used = raw.get("stations_used")
        if isinstance(stations_used, Sequence) and not isinstance(stations_used, (str, bytes, bytearray)):
            station_count = len([item for item in stations_used if _clean_text(item)])

    has_context = any(
        value is not None
        for value in (
            class_raw,
            label,
            confidence_score,
            regional_intensity,
            regional_coherence,
            regional_persistence,
            station_count,
        )
    ) or bool(quality_flags)
    if not has_context:
        return None

    is_provisional = _to_bool(raw.get("ulf_is_provisional"))
    if is_provisional is None:
        is_provisional = quality["low_history"]

    is_usable = _to_bool(raw.get("ulf_is_usable"))
    if is_usable is None:
        is_usable = confidence_score is not None and confidence_score >= 0.20

    is_high_confidence = _to_bool(raw.get("ulf_is_high_confidence"))
    if is_high_confidence is None:
        is_high_confidence = bool(
            confidence_score is not None
            and confidence_score >= 0.65
            and not is_provisional
            and not quality["missing_samples"]
        )

    return {
        "label": label,
        "class_raw": class_raw,
        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
        "regional_intensity": regional_intensity,
        "regional_coherence": regional_coherence,
        "regional_persistence": regional_persistence,
        "quality_flags": quality_flags,
        "is_provisional": bool(is_provisional),
        "is_usable": bool(is_usable),
        "is_high_confidence": bool(is_high_confidence),
        "station_count": station_count,
        "missing_samples": quality["missing_samples"],
        "low_history": quality["low_history"],
        "ts_utc": _clean_text(raw.get("ts_utc") or raw.get("ulf_ts_utc")),
    }


def build_ulf_payload(
    raw: Mapping[str, Any] | None,
    *,
    include_empty: bool = False,
) -> dict[str, Any]:
    context = normalize_ulf_context(raw)
    if context is None:
        if not include_empty:
            return {}
        return {
            "ulf_context_class_raw": None,
            "ulf_context_label": None,
            "ulf_confidence_score": None,
            "ulf_confidence_label": None,
            "ulf_regional_intensity": None,
            "ulf_regional_coherence": None,
            "ulf_regional_persistence": None,
            "ulf_quality_flags": [],
            "ulf_is_provisional": False,
            "ulf_is_usable": False,
            "ulf_is_high_confidence": False,
            "ulf_station_count": None,
            "ulf_missing_samples": False,
            "ulf_low_history": False,
            "geomagnetic_context": None,
        }

    return {
        "ulf_context_class_raw": context["class_raw"],
        "ulf_context_label": context["label"],
        "ulf_confidence_score": context["confidence_score"],
        "ulf_confidence_label": context["confidence_label"],
        "ulf_regional_intensity": context["regional_intensity"],
        "ulf_regional_coherence": context["regional_coherence"],
        "ulf_regional_persistence": context["regional_persistence"],
        "ulf_quality_flags": context["quality_flags"],
        "ulf_is_provisional": context["is_provisional"],
        "ulf_is_usable": context["is_usable"],
        "ulf_is_high_confidence": context["is_high_confidence"],
        "ulf_station_count": context["station_count"],
        "ulf_missing_samples": context["missing_samples"],
        "ulf_low_history": context["low_history"],
        "geomagnetic_context": context,
    }
