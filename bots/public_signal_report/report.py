from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from .contract import empty_report


DRIVER_RULES: dict[str, dict[str, Any]] = {
    "thunderstorms": {
        "label": "Thunderstorms",
        "weight": 5,
        "health_context": ["head or sinus pressure", "migraine sensitivity", "joint or chronic-condition flares"],
    },
    "pressure_swings": {
        "label": "Pressure swings",
        "weight": 5,
        "health_context": ["head or sinus pressure", "migraine sensitivity", "joint discomfort"],
    },
    "temperature_shifts": {
        "label": "Rapid temperature shifts",
        "weight": 4,
        "health_context": ["fatigue", "joint discomfort", "chronic-condition flares"],
    },
    "heat_humidity": {
        "label": "Heat and humidity",
        "weight": 4,
        "health_context": ["fatigue", "sleep disruption", "lower exercise tolerance"],
    },
    "cold": {
        "label": "Intense cold",
        "weight": 3,
        "health_context": ["joint stiffness", "pain sensitivity", "fatigue"],
    },
    "high_wind": {
        "label": "Strong winds or gusts",
        "weight": 3,
        "health_context": ["head or sinus irritation", "fatigue", "allergen exposure"],
    },
    "poor_air": {
        "label": "Poor air quality",
        "weight": 5,
        "health_context": ["breathing irritation", "headache", "fatigue", "reduced exercise tolerance"],
    },
    "elevated_pollen": {
        "label": "Elevated pollen",
        "weight": 3,
        "health_context": ["sinus pressure", "headache", "breathing irritation", "fatigue"],
    },
    "heavy_precipitation": {
        "label": "Heavy precipitation",
        "weight": 3,
        "health_context": ["pressure sensitivity", "fatigue", "joint discomfort"],
    },
}

US_REGION_PREFIX = "us_"


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first_number(row: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _float(row.get(key))
        if value is not None:
            return value
    return None


def _anchor_signals(observation: Mapping[str, Any]) -> set[str]:
    weather = observation.get("weather") if isinstance(observation.get("weather"), Mapping) else {}
    air = observation.get("air") if isinstance(observation.get("air"), Mapping) else {}
    pollen = observation.get("pollen") if isinstance(observation.get("pollen"), Mapping) else {}
    signals: set[str] = set()

    condition = f"{weather.get('condition') or ''} {weather.get('condition_summary') or ''}".lower()
    condition_code = int(_float(weather.get("condition_code")) or 0)
    temp = _float(weather.get("temp_c"))
    feels = _float(weather.get("feels_like_c"))
    humidity = _float(weather.get("humidity_pct"))
    temp_delta = _float(weather.get("temp_delta_24h_c"))
    pressure_delta = _float(weather.get("pressure_delta_24h_hpa"))
    wind = _float(weather.get("wind_speed_mps"))
    gust = _float(weather.get("wind_gust_mps"))
    rain = _float(weather.get("rain_1h_mm")) or 0.0
    snow = _float(weather.get("snow_1h_mm")) or 0.0
    aqi = _float(air.get("openweather_aqi"))
    pm25 = _float(air.get("pm2_5"))
    pollen_state = str(pollen.get("state") or pollen.get("overall_level") or "").lower()

    if 200 <= condition_code < 300 or "thunderstorm" in condition:
        signals.add("thunderstorms")
    if pressure_delta is not None and abs(pressure_delta) >= 4.0:
        signals.add("pressure_swings")
    if temp_delta is not None and abs(temp_delta) >= 5.0:
        signals.add("temperature_shifts")
    if (temp is not None and temp >= 32.0) or (feels is not None and feels >= 35.0):
        signals.add("heat_humidity")
    elif temp is not None and temp >= 28.0 and humidity is not None and humidity >= 70.0:
        signals.add("heat_humidity")
    if temp is not None and temp <= -10.0:
        signals.add("cold")
    if (wind is not None and wind >= 12.0) or (gust is not None and gust >= 15.0):
        signals.add("high_wind")
    if (aqi is not None and aqi >= 4.0) or (pm25 is not None and pm25 >= 35.0):
        signals.add("poor_air")
    if pollen_state in {"moderate", "high", "very_high", "elevated"}:
        signals.add("elevated_pollen")
    if rain >= 7.5 or snow >= 5.0:
        signals.add("heavy_precipitation")
    return signals


def _regional_evidence(observations: Iterable[Mapping[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for observation in observations:
        if observation.get("region_key"):
            grouped[str(observation["region_key"])].append(observation)

    candidates: list[dict[str, Any]] = []
    for region_key, rows in grouped.items():
        usable = [row for row in rows if bool((row.get("provider_status") or {}).get("weather"))]
        if len(usable) < 2:
            continue
        signal_anchors: dict[str, list[str]] = defaultdict(list)
        for row in usable:
            for signal in _anchor_signals(row):
                signal_anchors[signal].append(str(row.get("location_label") or row.get("anchor_id") or ""))
        supported = {key: labels for key, labels in signal_anchors.items() if len(labels) >= 2}
        if not supported:
            continue

        drivers = []
        health_context: list[str] = []
        score = 0
        for key, labels in supported.items():
            rule = DRIVER_RULES[key]
            score += int(rule["weight"]) + len(labels)
            for item in rule["health_context"]:
                if item not in health_context:
                    health_context.append(item)
            drivers.append(
                {
                    "key": key,
                    "label": rule["label"],
                    "support_count": len(labels),
                    "supporting_locations": labels,
                }
            )
        drivers.sort(key=lambda item: (-int(DRIVER_RULES[item["key"]]["weight"]), item["label"]))
        candidates.append(
            {
                "region_key": region_key,
                "label": str(usable[0].get("region_label") or region_key),
                "macro_region": str(usable[0].get("macro_region") or ""),
                "sample_count": len(usable),
                "required_support": 2,
                "drivers": drivers,
                "health_context": health_context,
                "confidence": "high" if len(usable) >= 3 and any(item["support_count"] >= 3 for item in drivers) else "moderate",
                "selection_score": score,
            }
        )
    candidates.sort(key=lambda item: (-int(item["selection_score"]), item["label"]))
    return candidates[:limit]


def _space_watch(space: Mapping[str, Any]) -> dict[str, Any]:
    kp = _first_number(space, ("kp_max", "kp_max_24h"))
    bz = _first_number(space, ("bz_min", "bz_min_24h"))
    wind = _first_number(space, ("sw_speed_avg", "solar_wind_kms", "sw_speed_now_kms"))
    if (kp is not None and kp >= 5) or (bz is not None and bz <= -8 and wind is not None and wind >= 550):
        level = "high"
    elif (kp is not None and kp >= 3.5) or (bz is not None and bz <= -6) or (wind is not None and wind >= 550):
        level = "moderate"
    else:
        level = "low"
    return {
        "signal_strength": level,
        "recovery_frame": level == "low",
        "metrics": {
            "kp_max": kp,
            "bz_min": bz,
            "solar_wind_kms": wind,
            "flares_count": _first_number(space, ("flares_count", "flares_24h")),
            "cmes_count": _first_number(space, ("cmes_count", "cmes_24h")),
        },
        "source_row": dict(space),
    }


def _earth_signal(schumann: Mapping[str, Any], ulf: Mapping[str, Any]) -> dict[str, Any]:
    confidence = _first_number(ulf, ("confidence_score",))
    return {
        "schumann": dict(schumann),
        "ulf": dict(ulf),
        "ulf_usable": bool(ulf.get("context_class")) and (confidence is None or confidence >= 0.55),
        "health_language": "Possible effects may use 'may', 'can', or 'some people notice' without an appended disclaimer.",
    }


def _major_events(hazards: Iterable[Mapping[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    severity_rank = {"red": 4, "orange": 3, "yellow": 2, "high": 3, "severe": 4, "moderate": 2}
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for hazard in hazards:
        payload = hazard.get("payload") if isinstance(hazard.get("payload"), Mapping) else {}
        severity = str(hazard.get("severity") or "").lower()
        title = str(hazard.get("title") or "").strip()
        title_level = title.split(maxsplit=1)[0].lower() if title else ""
        if str(hazard.get("source") or "").lower() == "gdacs" and title_level in {"green", "yellow", "orange", "red"}:
            severity = title_level
        rank = severity_rank.get(severity, 0)
        if rank < 2:
            continue
        kind = str(hazard.get("kind") or hazard.get("type") or "event")
        location = str(hazard.get("location") or "").strip()
        event_id = str(payload.get("id") or "").strip().lower()
        key = (str(hazard.get("source") or "").lower(), kind.lower(), event_id or f"{title.lower()}|{location.lower()}")
        if key in seen:
            continue
        seen.add(key)
        selected.append(
            {
                "kind": kind,
                "title": title,
                "location": location or None,
                "severity": severity,
                "started_at": hazard.get("started_at") or payload.get("ts"),
                "source": hazard.get("source"),
                "url": payload.get("url") or payload.get("link") or payload.get("detail_url"),
                "selection_score": rank,
            }
        )
    # The source query is newest-first, so a stable severity sort preserves freshness on ties.
    selected.sort(key=lambda item: -int(item["selection_score"]))
    return selected[:limit]


def _country_codes(value: Any) -> set[str]:
    if isinstance(value, str):
        aliases = {
            "UNITED STATES": "US",
            "UNITED STATES OF AMERICA": "US",
        }
        return {
            aliases.get(part.strip().upper(), part.strip().upper())
            for part in value.replace(";", ",").split(",")
            if part.strip()
        }
    if isinstance(value, Mapping):
        code = value.get("code") or value.get("country_code") or value.get("iso2") or value.get("iso3")
        return _country_codes(code)
    if isinstance(value, (list, tuple, set)):
        return {code for item in value for code in _country_codes(item)}
    return set()


def _hazard_has_us_scope(hazard: Mapping[str, Any]) -> bool:
    payload = hazard.get("payload") if isinstance(hazard.get("payload"), Mapping) else {}
    codes: set[str] = set()
    for source in (hazard, payload):
        for key in ("country_code", "country_codes", "affected_country_codes", "affected_countries"):
            codes.update(_country_codes(source.get(key)))
    return bool(codes & {"US", "USA"})


def build_daily_signal_report(
    *,
    day: str | date,
    observations: Iterable[Mapping[str, Any]],
    context: Mapping[str, Any],
    expected_anchor_count: int = 120,
    edition: str = "global",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    observation_rows = list(observations)
    report = empty_report(day=day, edition=edition, generated_at=generated_at)
    scoped_rows = (
        [row for row in observation_rows if str(row.get("region_key") or "").startswith(US_REGION_PREFIX)]
        if edition == "us"
        else observation_rows
    )
    scoped_expected_anchor_count = expected_anchor_count
    successful_weather = sum(bool((row.get("provider_status") or {}).get("weather")) for row in scoped_rows)
    successful_air = sum(bool((row.get("provider_status") or {}).get("air")) for row in scoped_rows)
    successful_pollen = sum(bool((row.get("provider_status") or {}).get("pollen")) for row in scoped_rows)
    regions_seen = {str(row.get("region_key")) for row in scoped_rows if row.get("region_key")}

    regional_items = _regional_evidence(scoped_rows)
    report["regional_watch"] = {
        "items": regional_items,
        "selection_method": "At least two fixed anchors must support the same driver.",
    }
    report["space_watch"] = _space_watch(context.get("space") if isinstance(context.get("space"), Mapping) else {})
    report["earth_signal"] = _earth_signal(
        context.get("schumann") if isinstance(context.get("schumann"), Mapping) else {},
        context.get("ulf") if isinstance(context.get("ulf"), Mapping) else {},
    )
    hazards = context.get("hazards") if isinstance(context.get("hazards"), list) else []
    scoped_hazards = [hazard for hazard in hazards if _hazard_has_us_scope(hazard)] if edition == "us" else hazards
    report["major_events"] = {
        "items": _major_events(scoped_hazards),
        "selection_method": "Fresh yellow-or-higher GDACS/USGS events, deduplicated and capped.",
    }
    report["coverage"] = {
        "expected_anchors": scoped_expected_anchor_count,
        "observed_anchors": len(scoped_rows),
        "weather_anchors": successful_weather,
        "air_anchors": successful_air,
        "pollen_anchors": successful_pollen,
        "pollen_configured": any((row.get("provider_status") or {}).get("pollen") is not None for row in scoped_rows),
        "regions_observed": len(regions_seen),
        "weather_ratio": round(successful_weather / scoped_expected_anchor_count, 3) if scoped_expected_anchor_count else 0.0,
        "public_global_claims_allowed": bool(
            edition == "global"
            and scoped_expected_anchor_count
            and successful_weather / scoped_expected_anchor_count >= 0.75
        ),
        "provider_failures": dict(
            Counter(
                provider
                for row in scoped_rows
                for provider, ok in (row.get("provider_status") or {}).items()
                if ok is False
            )
        ),
    }
    report["sources"] = [
        "OpenWeather current weather",
        "OpenWeather air pollution",
        "Google Pollen when available",
        "marts.space_weather_daily",
        "marts.schumann_daily_v2 or marts.schumann_daily",
        "marts.ulf_context_5m",
        "ext.global_hazards",
    ]
    return report
