from __future__ import annotations

import os
from datetime import UTC, date, datetime
from typing import Any, Mapping

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - local unit tests can run without httpx installed.
    httpx = None


API_KEY = os.getenv("GOOGLE_POLLEN_API_KEY", "")
BASE = "https://pollen.googleapis.com/v1/forecast:lookup"

TYPE_KEY_MAP = {
    "TREE": "tree",
    "GRASS": "grass",
    "WEED": "weed",
    "MOLD": "mold",
}

TYPE_LABELS = {
    "tree": "Tree pollen",
    "grass": "Grass pollen",
    "weed": "Weed pollen",
    "mold": "Mold",
}

LEVEL_RANK = {
    "low": 1,
    "moderate": 2,
    "high": 3,
    "very_high": 4,
}

STATE_LABELS = {
    "low": "Quiet",
    "moderate": "Moderate",
    "high": "Elevated",
    "very_high": "High",
}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _normalize_level(*, category: Any = None, display_name: Any = None, index_value: Any = None) -> str | None:
    token = str(category or display_name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token in {"very_high", "veryhigh"}:
        return "very_high"
    if token == "high":
        return "high"
    if token == "moderate":
        return "moderate"
    if token in {"none", "very_low", "low"}:
        return "low"

    numeric = _safe_int(index_value)
    if numeric is None:
        return None
    if numeric >= 5:
        return "very_high"
    if numeric >= 4:
        return "high"
    if numeric >= 3:
        return "moderate"
    if numeric >= 0:
        return "low"
    return None


def _parse_day(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, Mapping):
        year = _safe_int(value.get("year"))
        month = _safe_int(value.get("month"))
        day_num = _safe_int(value.get("day"))
        if year and month and day_num:
            try:
                return date(year, month, day_num)
            except Exception:
                return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _type_key_from_item(item: Mapping[str, Any]) -> str | None:
    code = str(item.get("code") or item.get("displayName") or "").strip().upper().replace(" ", "_")
    if code in TYPE_KEY_MAP:
        return TYPE_KEY_MAP[code]
    if "TREE" in code:
        return "tree"
    if "GRASS" in code:
        return "grass"
    if "WEED" in code or "RAGWEED" in code or "MUGWORT" in code:
        return "weed"
    if "MOLD" in code:
        return "mold"
    return None


def _index_block(item: Mapping[str, Any]) -> Mapping[str, Any]:
    index_info = item.get("indexInfo")
    return index_info if isinstance(index_info, Mapping) else {}


def _normalize_type_infos(daily_info: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in daily_info.get("pollenTypeInfo") or []:
        if not isinstance(item, Mapping):
            continue
        type_key = _type_key_from_item(item)
        if not type_key:
            continue
        index_info = _index_block(item)
        value = _safe_float(index_info.get("value"))
        level = _normalize_level(
            category=index_info.get("category"),
            display_name=index_info.get("displayName") or item.get("displayName"),
            index_value=value,
        )
        out[type_key] = {
            "level": level,
            "index": value,
            "display_name": item.get("displayName") or TYPE_LABELS.get(type_key),
            "recommendations": item.get("healthRecommendations") if isinstance(item.get("healthRecommendations"), list) else [],
            "in_season": bool(item.get("inSeason")) if item.get("inSeason") is not None else None,
        }
    return out


def _overall_level(types: Mapping[str, Mapping[str, Any]]) -> str | None:
    ranks = [LEVEL_RANK.get(str((item or {}).get("level") or "")) for item in types.values()]
    ranks = [rank for rank in ranks if rank is not None]
    if not ranks:
        return None
    max_rank = max(ranks)
    moderate_plus = sum(1 for rank in ranks if rank >= LEVEL_RANK["moderate"])
    if max_rank == LEVEL_RANK["moderate"] and moderate_plus >= 2:
        return "high"
    for key, rank in LEVEL_RANK.items():
        if rank == max_rank:
            return key
    return None


def _primary_type(types: Mapping[str, Mapping[str, Any]]) -> str | None:
    ranked: list[tuple[int, float, int, str]] = []
    for idx, type_key in enumerate(("tree", "grass", "weed", "mold")):
        item = types.get(type_key) or {}
        rank = LEVEL_RANK.get(str(item.get("level") or ""))
        if rank is None:
            continue
        ranked.append((rank, _safe_float(item.get("index")) or 0.0, -idx, type_key))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][3]


def _overall_index(types: Mapping[str, Mapping[str, Any]], overall_level: str | None) -> float | None:
    indices = [_safe_float((item or {}).get("index")) for item in types.values()]
    indices = [value for value in indices if value is not None]
    if indices:
        return round(max(indices), 1)
    if overall_level:
        return float(LEVEL_RANK.get(overall_level, 0))
    return None


def _relevance_score(types: Mapping[str, Mapping[str, Any]], overall_level: str | None) -> float | None:
    base = _overall_index(types, overall_level)
    if base is None:
        return None
    moderate_plus = sum(
        1
        for item in types.values()
        if LEVEL_RANK.get(str((item or {}).get("level") or "")) is not None
        and LEVEL_RANK.get(str((item or {}).get("level") or "")) >= LEVEL_RANK["moderate"]
    )
    bonus = max(0, moderate_plus - 1) * 0.35
    return round(min(base + bonus, 5.0), 1)


def _state_label(level: str | None) -> str | None:
    return STATE_LABELS.get(str(level or ""))


async def forecast_by_latlon(lat: float, lon: float, *, days: int = 3, language_code: str = "en") -> dict[str, Any]:
    if not API_KEY or httpx is None:
        return {}

    params = {
        "location.latitude": f"{float(lat):.4f}",
        "location.longitude": f"{float(lon):.4f}",
        "days": max(1, min(int(days), 5)),
        "languageCode": language_code,
        "plantsDescription": "false",
        "key": API_KEY,
    }
    async with httpx.AsyncClient(timeout=30.0) as cx:
        response = await cx.get(BASE, params=params)
        response.raise_for_status()
        return response.json() if response.text.strip() else {}


def normalize_daily_forecast(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []

    updated_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for daily_info in payload.get("dailyInfo") or []:
        if not isinstance(daily_info, Mapping):
            continue
        day_value = _parse_day(daily_info.get("date"))
        if day_value is None:
            continue
        types = _normalize_type_infos(daily_info)
        overall_level = _overall_level(types)
        primary_type = _primary_type(types)
        overall_index = _overall_index(types, overall_level)
        recommendations: list[str] = []
        for item in types.values():
            for text in item.get("recommendations") or []:
                normalized = str(text or "").strip()
                if normalized and normalized not in recommendations:
                    recommendations.append(normalized)

        rows.append(
            {
                "day": day_value,
                "pollen_tree_level": (types.get("tree") or {}).get("level"),
                "pollen_grass_level": (types.get("grass") or {}).get("level"),
                "pollen_weed_level": (types.get("weed") or {}).get("level"),
                "pollen_mold_level": (types.get("mold") or {}).get("level"),
                "pollen_tree_index": _safe_float((types.get("tree") or {}).get("index")),
                "pollen_grass_index": _safe_float((types.get("grass") or {}).get("index")),
                "pollen_weed_index": _safe_float((types.get("weed") or {}).get("index")),
                "pollen_mold_index": _safe_float((types.get("mold") or {}).get("index")),
                "pollen_overall_level": overall_level,
                "pollen_overall_index": overall_index,
                "pollen_primary_type": primary_type,
                "pollen_primary_label": TYPE_LABELS.get(primary_type) if primary_type else None,
                "pollen_state_label": _state_label(overall_level),
                "pollen_source": "google-pollen:forecast",
                "pollen_updated_at": updated_at,
                "allergen_relevance_score": _relevance_score(types, overall_level),
                "recommendations": recommendations,
                "raw_types": {
                    key: {
                        "level": value.get("level"),
                        "index": value.get("index"),
                        "display_name": value.get("display_name"),
                        "in_season": value.get("in_season"),
                    }
                    for key, value in types.items()
                },
            }
        )
    rows.sort(key=lambda row: row["day"])
    return rows


def current_snapshot(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    rows = normalize_daily_forecast(payload)
    if not rows:
        return {}

    first = dict(rows[0])
    return {
        "overall_level": first.get("pollen_overall_level"),
        "overall_label": first.get("pollen_state_label"),
        "overall_index": first.get("pollen_overall_index"),
        "primary_type": first.get("pollen_primary_type"),
        "primary_label": first.get("pollen_primary_label"),
        "tree_level": first.get("pollen_tree_level"),
        "grass_level": first.get("pollen_grass_level"),
        "weed_level": first.get("pollen_weed_level"),
        "mold_level": first.get("pollen_mold_level"),
        "tree_index": first.get("pollen_tree_index"),
        "grass_index": first.get("pollen_grass_index"),
        "weed_index": first.get("pollen_weed_index"),
        "mold_index": first.get("pollen_mold_index"),
        "source": first.get("pollen_source"),
        "updated_at": first.get("pollen_updated_at"),
        "state": first.get("pollen_overall_level"),
        "state_label": first.get("pollen_state_label"),
        "relevance_score": first.get("allergen_relevance_score"),
        "recommendations": first.get("recommendations") or [],
    }
