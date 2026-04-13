from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta, timezone
from statistics import fmean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

try:
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover - unit tests can run without psycopg installed.
    dict_row = None

from services.patterns.personal_relevance import (
    confidence_rank,
    fetch_best_pattern_rows,
    pattern_anchor_statement,
)
from services.voice import build_user_outlook_overview_semantic, build_user_outlook_window_semantic
from services.external import pollen


LOCAL_REFRESH_HOURS = 6
LOCAL_FORECAST_DAYS = 7
SPACE_FORECAST_DAYS = 7
POLLEN_FORECAST_DAYS = 5

DOMAIN_LABELS = {
    "pain": "Pain",
    "focus": "Focus",
    "energy": "Energy",
    "sleep": "Sleep",
    "mood": "Mood",
    "heart": "Heart / Autonomic",
}

OUTCOME_TO_DOMAIN = {
    "headache_day": "pain",
    "pain_flare_day": "pain",
    "focus_fog_day": "focus",
    "fatigue_day": "energy",
    "poor_sleep_day": "sleep",
    "short_sleep_day": "sleep",
    "anxiety_day": "mood",
    "high_hr_day": "heart",
    "hrv_dip_day": "heart",
}

GAUGE_BY_DOMAIN = {
    "pain": "pain",
    "focus": "focus",
    "energy": "energy",
    "sleep": "sleep",
    "mood": "mood",
    "heart": "heart",
}

SIGNAL_TO_DRIVER = {
    "pressure_swing_exposed": "pressure",
    "temp_swing_exposed": "temp",
    "humidity_extreme_exposed": "humidity",
    "aqi_moderate_plus_exposed": "aqi",
    "pollen_overall_exposed": "allergens",
    "kp_g1_plus_exposed": "kp",
}

DRIVER_TO_SIGNAL = {value: key for key, value in SIGNAL_TO_DRIVER.items()}

DRIVER_LABELS = {
    "pressure": "Pressure swing",
    "temp": "Temperature swing",
    "humidity": "Humidity",
    "aqi": "Air quality",
    "allergens": "Allergen load",
    "kp": "Geomagnetic outlook",
    "solar_wind": "Solar-wind watch",
    "radio": "Radio-blackout watch",
    "radiation": "Solar-radiation watch",
    "cme": "CME watch",
    "flare": "Flare watch",
}

DRIVER_ORDER = {
    "pressure": 1,
    "temp": 2,
    "humidity": 3,
    "aqi": 4,
    "allergens": 5,
    "kp": 6,
    "solar_wind": 7,
    "cme": 8,
    "radio": 9,
    "radiation": 10,
    "flare": 11,
}

SEVERITY_RANK = {"high": 3, "watch": 2, "mild": 1, "low": 0}
SEVERITY_WEIGHT = {"high": 1.8, "watch": 1.35, "mild": 0.9, "low": 0.0}

MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

SWPC_ISSUED_RE = re.compile(r"^\s*:?\s*Issued:\s*(\d{4}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{4})\s*UTC", re.IGNORECASE | re.MULTILINE)
SWPC_RANGE_RE = re.compile(
    r"([A-Z][a-z]{2})\s+(\d{1,2})\s*-\s*(?:([A-Z][a-z]{2})\s+)?(\d{1,2})\s+(\d{4})",
    re.IGNORECASE,
)
SWPC_DAY_TOKEN_RE = re.compile(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b")
SWPC_KP_CELL_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:\((G\d)\))?")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
SWPC_GEOMAG_EVENT_RE = re.compile(
    r"(G\d(?:-G\d)?)\s*(?:\([^)]+\))?[^.]*?\bon\s+([^.]+?)(?=(?:,\s*with\s+G\d)|(?:\.)|$)",
    re.IGNORECASE,
)
SWPC_MONTH_DAY_BLOCK_RE = re.compile(
    r"((?:\d{1,2}(?:-\d{1,2})?)(?:\s*(?:,|and)\s*\d{1,2}(?:-\d{1,2})?)*)\s+([A-Z][a-z]{2,8})",
    re.IGNORECASE,
)


def _cursor_kwargs() -> dict[str, Any]:
    return {"row_factory": dict_row} if dict_row is not None else {}


def _pick(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    lowered = {col.lower(): col for col in columns}
    for candidate in candidates:
        found = lowered.get(candidate.lower())
        if found:
            return found
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _safe_round(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_duration_hours(valid_time: str | None) -> float:
    if not valid_time or "/" not in valid_time:
        return 1.0
    _, duration = valid_time.split("/", 1)
    days = 0.0
    hours = 0.0
    minutes = 0.0
    day_match = re.search(r"(\d+(?:\.\d+)?)D", duration)
    hour_match = re.search(r"(\d+(?:\.\d+)?)H", duration)
    minute_match = re.search(r"(\d+(?:\.\d+)?)M", duration)
    if day_match:
        days = float(day_match.group(1))
    if hour_match:
        hours = float(hour_match.group(1))
    if minute_match:
        minutes = float(minute_match.group(1))
    total = days * 24.0 + hours + (minutes / 60.0)
    return total if total > 0 else 1.0


def _coerce_temperature_c(value: Any, unit: Any) -> float | None:
    temp = _safe_float(value)
    if temp is None:
        return None
    token = str(unit or "").strip().upper()
    if token == "F":
        return round((temp - 32.0) * 5.0 / 9.0, 1)
    return round(temp, 1)


def _coerce_pressure_hpa(value: Any) -> float | None:
    pressure = _safe_float(value)
    if pressure is None:
        return None
    if pressure > 2000:
        pressure = pressure / 100.0
    return round(pressure, 1)


def _parse_wind_value(text: Any) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return round(float(text), 1)
    raw = str(text).strip().lower()
    if not raw:
        return None
    nums = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not nums:
        return None
    value = fmean(nums)
    if "mph" in raw:
        value *= 1.60934
    elif "kt" in raw or "kts" in raw:
        value *= 1.852
    return round(value, 1)


def _slugify_condition(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:64] or None


def _severity_from_pressure(delta: float | None) -> str:
    abs_value = abs(delta or 0.0)
    if abs_value >= 12:
        return "high"
    if abs_value >= 8:
        return "watch"
    if abs_value >= 6:
        return "mild"
    return "low"


def _severity_from_temp(delta: float | None) -> str:
    abs_value = abs(delta or 0.0)
    if abs_value >= 12:
        return "high"
    if abs_value >= 8:
        return "watch"
    if abs_value >= 6:
        return "mild"
    return "low"


def _severity_from_aqi(aqi: float | None) -> str:
    if aqi is None:
        return "low"
    if aqi >= 151:
        return "high"
    if aqi >= 101:
        return "watch"
    if aqi >= 51:
        return "mild"
    return "low"


def _severity_from_humidity(humidity: float | None) -> str:
    if humidity is None:
        return "low"
    if humidity >= 85 or humidity <= 25:
        return "high"
    if humidity >= 78 or humidity <= 30:
        return "watch"
    if humidity >= 70 or humidity <= 35:
        return "mild"
    return "low"


def _humidity_departure_score(humidity: float | None) -> float:
    if humidity is None:
        return 0.0
    if humidity >= 70:
        return humidity - 65.0
    if humidity <= 35:
        return 40.0 - humidity
    return 0.0


def _humidity_detail(humidity: float) -> str:
    rounded = int(round(humidity))
    if humidity >= 70:
        return f"Humidity looks muggier than usual around {rounded}% in this window."
    if humidity <= 35:
        return f"Humidity looks drier than usual around {rounded}% in this window."
    return f"Humidity may land around {rounded}% in this window."


def _severity_from_allergen_level(level: str | None) -> str:
    token = str(level or "").strip().lower()
    if token == "very_high":
        return "high"
    if token == "high":
        return "watch"
    if token == "moderate":
        return "mild"
    return "low"


def _severity_from_g_scale(g_scale: str | None) -> str:
    token = str(g_scale or "").strip().upper()
    if token in {"G4", "G5", "G3"}:
        return "high"
    if token in {"G1", "G2"}:
        return "watch"
    return "low"


def _g_scale_int(g_scale: str | None) -> int:
    token = str(g_scale or "").strip().upper()
    if token.startswith("G") and token[1:].isdigit():
        return int(token[1:])
    return 0


def _g_from_kp(kp: float | None) -> int:
    if kp is None:
        return 0
    if kp >= 9:
        return 5
    if kp >= 8:
        return 4
    if kp >= 7:
        return 3
    if kp >= 6:
        return 2
    if kp >= 5:
        return 1
    return 0


def _watch_flag(text: str | None, *patterns: str) -> bool:
    token = (text or "").lower()
    return any(pattern in token for pattern in patterns)


def _severity_bucket_from_probability(primary_pct: float | None, secondary_pct: float | None = None) -> str:
    primary = primary_pct or 0.0
    secondary = secondary_pct or 0.0
    if secondary >= 10 or primary >= 60:
        return "high"
    if secondary >= 1 or primary >= 20:
        return "watch"
    if primary > 0:
        return "mild"
    return "low"


def _compress_whitespace(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def _extract_section(text: str, start_pattern: str, end_pattern: str | None) -> str:
    if end_pattern:
        pattern = rf"{start_pattern}(.*?){end_pattern}"
    else:
        pattern = rf"{start_pattern}(.*)\Z"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _parse_swpc_issued_at(text: str, fallback: datetime) -> datetime:
    match = SWPC_ISSUED_RE.search(text)
    if not match:
        return fallback
    try:
        return datetime.strptime(match.group(1), "%Y %b %d %H%M").replace(tzinfo=UTC)
    except Exception:
        return fallback


def _build_date_range(start_month: str, start_day: int, end_month: str, end_day: int, end_year: int) -> list[date]:
    start_month_num = MONTH_MAP[start_month.lower()[:3]]
    end_month_num = MONTH_MAP[end_month.lower()[:3]]
    start_year = end_year - 1 if start_month_num > end_month_num else end_year
    start = date(start_year, start_month_num, start_day)
    end = date(end_year, end_month_num, end_day)
    out: list[date] = []
    cursor = start
    while cursor <= end and len(out) < 7:
        out.append(cursor)
        cursor += timedelta(days=1)
    return out


def _parse_swpc_dates(section_text: str, issued_at: datetime) -> list[date]:
    range_match = SWPC_RANGE_RE.search(section_text)
    if range_match:
        start_month = range_match.group(1)
        start_day = int(range_match.group(2))
        end_month = range_match.group(3) or start_month
        end_day = int(range_match.group(4))
        end_year = int(range_match.group(5))
        return _build_date_range(start_month, start_day, end_month, end_day, end_year)

    lines = [line.strip() for line in section_text.splitlines() if line.strip()]
    for line in lines:
        tokens = SWPC_DAY_TOKEN_RE.findall(line)
        if len(tokens) < 3:
            continue
        dates: list[date] = []
        year = issued_at.year
        prev_month = None
        for month_name, day_token in tokens[:3]:
            month_num = MONTH_MAP[month_name.lower()[:3]]
            if prev_month is not None and month_num < prev_month:
                year += 1
            dates.append(date(year, month_num, int(day_token)))
            prev_month = month_num
        return dates
    return []


def _parse_rationale(section_text: str) -> str | None:
    match = re.search(r"Rationale:\s*(.*)$", section_text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _compress_whitespace(match.group(1))


def _parse_percent_row(section_text: str, row_label: str) -> list[float | None]:
    compact = _compress_whitespace(section_text) or ""
    pattern = rf"{row_label}\s+((?:\d+(?:\.\d+)?%\s*)+)"
    match = re.search(pattern, compact, re.IGNORECASE)
    if not match:
        return []
    values = PERCENT_RE.findall(match.group(1))
    return [float(item) for item in values]


def _forecast_window_days(start_day: date, *, days: int) -> list[date]:
    return [start_day + timedelta(days=offset) for offset in range(max(0, days))]


def _resolve_month_year(month_num: int, issued_at: datetime) -> int:
    year = issued_at.year
    if issued_at.month >= 10 and month_num <= 3:
        return year + 1
    return year


def _parse_swpc_day_expr(expr: str, issued_at: datetime) -> list[date]:
    out: list[date] = []
    for match in SWPC_MONTH_DAY_BLOCK_RE.finditer(expr.replace(" and ", ", ")):
        day_block = match.group(1)
        month_token = match.group(2)
        month_num = MONTH_MAP.get(month_token.lower()[:3])
        if month_num is None:
            continue
        year = _resolve_month_year(month_num, issued_at)
        for token in re.findall(r"\d{1,2}(?:-\d{1,2})?", day_block):
            if "-" in token:
                start_token, end_token = token.split("-", 1)
                try:
                    start_day = int(start_token)
                    end_day = int(end_token)
                except Exception:
                    continue
                for day_num in range(start_day, end_day + 1):
                    try:
                        out.append(date(year, month_num, day_num))
                    except Exception:
                        continue
            else:
                try:
                    out.append(date(year, month_num, int(token)))
                except Exception:
                    continue
    return out


def _max_g_scale_token(token: str | None) -> str:
    values = [int(item) for item in re.findall(r"G(\d)", str(token or "").upper()) if item.isdigit()]
    max_value = max(values) if values else 0
    return f"G{max_value}"


def _swpc_sentence_list(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text or "") if item.strip()]


def _parse_kp_blocks(section_text: str, forecast_days: Sequence[date]) -> dict[date, list[dict[str, Any]]]:
    compact = _compress_whitespace(section_text) or ""
    out: dict[date, list[dict[str, Any]]] = {day_key: [] for day_key in forecast_days[:3]}
    for match in re.finditer(r"(\d{2}-\d{2}UT)\s+(.*?)(?=\d{2}-\d{2}UT|Rationale:|$)", compact):
        block = match.group(1)
        cells = SWPC_KP_CELL_RE.findall(match.group(2))
        if not cells:
            continue
        for idx, day_key in enumerate(forecast_days[:3]):
            if idx >= len(cells):
                break
            kp_value = _safe_float(cells[idx][0])
            if kp_value is None:
                continue
            g_scale = cells[idx][1] or f"G{_g_from_kp(kp_value)}"
            out[day_key].append(
                {
                    "block": block,
                    "kp": round(kp_value, 2),
                    "g_scale": g_scale,
                }
            )
    return out


def parse_swpc_three_day_forecast(
    body_text: str,
    *,
    source_product_ts: datetime,
    src: str = "noaa-swpc:3-day-forecast",
) -> list[dict[str, Any]]:
    text = (body_text or "").strip()
    if not text:
        return []

    fallback_ts = source_product_ts.astimezone(UTC) if source_product_ts.tzinfo else source_product_ts.replace(tzinfo=UTC)
    issued_at = _parse_swpc_issued_at(text, fallback_ts)
    source_ts = issued_at
    updated_at = datetime.now(UTC)

    geomagnetic_section = _extract_section(
        text,
        r"A\.\s*NOAA Geomagnetic Activity Observation and Forecast",
        r"B\.\s*NOAA Solar Radiation Activity Observation and Forecast",
    )
    radiation_section = _extract_section(
        text,
        r"B\.\s*NOAA Solar Radiation Activity Observation and Forecast",
        r"C\.\s*NOAA Radio Blackout Activity and Forecast",
    )
    radio_section = _extract_section(
        text,
        r"C\.\s*NOAA Radio Blackout Activity and Forecast",
        None,
    )

    forecast_days = _parse_swpc_dates(geomagnetic_section or radiation_section or radio_section, issued_at)
    if not forecast_days:
        return []

    kp_blocks_by_day = _parse_kp_blocks(geomagnetic_section, forecast_days)

    geomagnetic_rationale = _parse_rationale(geomagnetic_section)
    radiation_rationale = _parse_rationale(radiation_section)
    radio_rationale = _parse_rationale(radio_section)

    s1_values = _parse_percent_row(radiation_section, r"S1\s+or\s+greater")
    r1_values = _parse_percent_row(radio_section, r"R1-R2")
    r3_values = _parse_percent_row(radio_section, r"R3\s+or\s+greater")

    rows: list[dict[str, Any]] = []
    for idx, day_key in enumerate(forecast_days[:3]):
        blocks = kp_blocks_by_day.get(day_key) or []
        kp_values = [float(item["kp"]) for item in blocks if item.get("kp") is not None]
        g_scale_values = [_g_scale_int(str(item.get("g_scale"))) for item in blocks]
        kp_max = max(kp_values) if kp_values else None
        g_scale_int = max(g_scale_values) if g_scale_values else _g_from_kp(kp_max)
        g_scale_max = f"G{g_scale_int}" if g_scale_int > 0 else "G0"
        s1_pct = s1_values[idx] if idx < len(s1_values) else None
        r1_pct = r1_values[idx] if idx < len(r1_values) else None
        r3_pct = r3_values[idx] if idx < len(r3_values) else None

        geomagnetic_bucket = _severity_from_g_scale(g_scale_max)
        radiation_bucket = _severity_bucket_from_probability(s1_pct)
        radio_bucket = _severity_bucket_from_probability(r1_pct, r3_pct)
        geomagnetic_text = geomagnetic_rationale or ""
        radio_text = radio_rationale or ""

        rows.append(
            {
                "forecast_day": day_key,
                "issued_at": issued_at,
                "source_product_ts": source_ts,
                "source_src": src,
                "kp_max_forecast": _safe_round(kp_max, 2),
                "g_scale_max": g_scale_max,
                "s1_or_greater_pct": _safe_round(s1_pct, 1),
                "r1_r2_pct": _safe_round(r1_pct, 1),
                "r3_or_greater_pct": _safe_round(r3_pct, 1),
                "geomagnetic_rationale": geomagnetic_rationale,
                "radiation_rationale": radiation_rationale,
                "radio_rationale": radio_rationale,
                "kp_blocks_json": json.dumps(blocks),
                "raw_sections_json": json.dumps(
                    {
                        "geomagnetic": _compress_whitespace(geomagnetic_section),
                        "radiation": _compress_whitespace(radiation_section),
                        "radio": _compress_whitespace(radio_section),
                    }
                ),
                "flare_watch": bool((r1_pct or 0) >= 25 or (r3_pct or 0) >= 1 or _watch_flag(radio_text, "flare")),
                "cme_watch": _watch_flag(geomagnetic_text, "cme"),
                "solar_wind_watch": _watch_flag(geomagnetic_text, "solar wind", "high speed stream", "hss", "coronal hole"),
                "geomagnetic_severity_bucket": geomagnetic_bucket,
                "radiation_severity_bucket": radiation_bucket,
                "radio_severity_bucket": radio_bucket,
                "updated_at": updated_at,
            }
        )

    return rows


def parse_swpc_range_forecast(
    body_text: str,
    *,
    source_product_ts: datetime,
    src: str,
    days: int = SPACE_FORECAST_DAYS,
) -> list[dict[str, Any]]:
    text = (body_text or "").strip()
    if not text:
        return []

    fallback_ts = source_product_ts.astimezone(UTC) if source_product_ts.tzinfo else source_product_ts.replace(tzinfo=UTC)
    issued_at = _parse_swpc_issued_at(text, fallback_ts)
    source_ts = issued_at
    updated_at = datetime.now(UTC)
    forecast_days = _forecast_window_days(issued_at.date(), days=days)
    if not forecast_days:
        return []

    forecast_section = ""
    for marker in (
        r"Forecast of Solar and Geomagnetic Activity",
        r"Outlook For [A-Z][a-z]+\s+\d{1,2}(?:-\d{1,2})?",
    ):
        forecast_section = _extract_section(text, marker, None)
        if forecast_section:
            break
    if not forecast_section:
        forecast_section = text

    compact_section = _compress_whitespace(forecast_section) or ""
    sentences = _swpc_sentence_list(forecast_section or text)
    flare_sentence = next(
        (
            sentence
            for sentence in sentences
            if _watch_flag(sentence, "m-class", "r1-r2", "radio blackout", "flare")
        ),
        None,
    )

    rows_by_day: dict[date, dict[str, Any]] = {
        day_key: {
            "forecast_day": day_key,
            "issued_at": issued_at,
            "source_product_ts": source_ts,
            "source_src": src,
            "kp_max_forecast": None,
            "g_scale_max": "G0",
            "s1_or_greater_pct": None,
            "r1_r2_pct": None,
            "r3_or_greater_pct": None,
            "geomagnetic_rationale": None,
            "radiation_rationale": None,
            "radio_rationale": None,
            "kp_blocks_json": json.dumps([]),
            "raw_sections_json": json.dumps({"forecast": compact_section}),
            "flare_watch": bool(flare_sentence),
            "cme_watch": False,
            "solar_wind_watch": False,
            "geomagnetic_severity_bucket": "low",
            "radiation_severity_bucket": "low",
            "radio_severity_bucket": "mild" if flare_sentence else "low",
            "updated_at": updated_at,
        }
        for day_key in forecast_days
    }

    for sentence in sentences:
        for match in SWPC_GEOMAG_EVENT_RE.finditer(sentence):
            g_scale_max = _max_g_scale_token(match.group(1))
            event_days = _parse_swpc_day_expr(match.group(2), issued_at)
            for day_key in event_days:
                payload = rows_by_day.get(day_key)
                if payload is None:
                    continue
                if _g_scale_int(g_scale_max) > _g_scale_int(payload.get("g_scale_max")):
                    payload["g_scale_max"] = g_scale_max
                    payload["geomagnetic_severity_bucket"] = _severity_from_g_scale(g_scale_max)
                if _watch_flag(sentence, "hss", "high speed stream", "coronal hole", "solar wind"):
                    payload["solar_wind_watch"] = True
                if _watch_flag(sentence, "cme"):
                    payload["cme_watch"] = True
                payload["geomagnetic_rationale"] = _compress_whitespace(sentence)

    if flare_sentence:
        rationale = _compress_whitespace(flare_sentence)
        for payload in rows_by_day.values():
            payload["radio_rationale"] = rationale

    return [rows_by_day[day_key] for day_key in forecast_days]


def summarize_local_forecast_days(
    hourly_payload: Mapping[str, Any],
    grid_payload: Mapping[str, Any] | None,
    *,
    allergen_payload: Mapping[str, Any] | None = None,
    location_key: str,
    zip_code: str | None,
    lat: float | None,
    lon: float | None,
    now: datetime | None = None,
    max_days: int = LOCAL_FORECAST_DAYS,
) -> list[dict[str, Any]]:
    props = hourly_payload.get("properties") if isinstance(hourly_payload, Mapping) else {}
    props = props if isinstance(props, Mapping) else {}
    periods = props.get("periods") if isinstance(props.get("periods"), list) else []

    now_ts = now or datetime.now(UTC)
    issued_at = _parse_iso_datetime(props.get("generatedAt")) or now_ts
    day_order: list[date] = []
    grouped: dict[date, dict[str, Any]] = {}

    for period in periods:
        if not isinstance(period, Mapping):
            continue
        start_time = _parse_iso_datetime(period.get("startTime"))
        if start_time is None or start_time < now_ts - timedelta(hours=1):
            continue
        local_day = start_time.date()
        if local_day not in grouped:
            if len(day_order) >= max_days:
                continue
            day_order.append(local_day)
            grouped[local_day] = {
                "temps": [],
                "humidity": [],
                "precip": [],
                "wind": [],
                "gust": [],
                "summaries": [],
                "raw_periods": 0,
            }
        bucket = grouped[local_day]
        temp_c = _coerce_temperature_c(period.get("temperature"), period.get("temperatureUnit"))
        humidity_value = None
        humidity_raw = period.get("relativeHumidity")
        if isinstance(humidity_raw, Mapping):
            humidity_value = _safe_float(humidity_raw.get("value"))
        precip_value = None
        precip_raw = period.get("probabilityOfPrecipitation")
        if isinstance(precip_raw, Mapping):
            precip_value = _safe_float(precip_raw.get("value"))
        wind_speed = _parse_wind_value(period.get("windSpeed"))
        wind_gust = _parse_wind_value(period.get("windGust"))
        summary = str(period.get("shortForecast") or "").strip()

        if temp_c is not None:
            bucket["temps"].append(temp_c)
        if humidity_value is not None:
            bucket["humidity"].append(humidity_value)
        if precip_value is not None:
            bucket["precip"].append(precip_value)
        if wind_speed is not None:
            bucket["wind"].append(wind_speed)
        if wind_gust is not None:
            bucket["gust"].append(wind_gust)
        if summary:
            bucket["summaries"].append(summary)
        bucket["raw_periods"] += 1

    pressure_by_day: dict[date, float | None] = {day_key: None for day_key in day_order}
    pollen_by_day = {
        row.get("day"): row
        for row in pollen.normalize_daily_forecast(allergen_payload)
        if isinstance(row.get("day"), date)
    }
    grid_props = grid_payload.get("properties") if isinstance(grid_payload, Mapping) else {}
    grid_props = grid_props if isinstance(grid_props, Mapping) else {}
    pressure_values = []
    for field_name in ("pressure", "barometricPressure", "seaLevelPressure"):
        field_block = grid_props.get(field_name)
        if isinstance(field_block, Mapping) and isinstance(field_block.get("values"), list):
            pressure_values = field_block.get("values") or []
            break
    weighted_values: dict[date, list[tuple[float, float]]] = defaultdict(list)
    for item in pressure_values:
        if not isinstance(item, Mapping):
            continue
        start_time = _parse_iso_datetime(str(item.get("validTime") or "").split("/", 1)[0])
        pressure_hpa = _coerce_pressure_hpa(item.get("value"))
        if start_time is None or pressure_hpa is None:
            continue
        local_day = start_time.date()
        if local_day not in pressure_by_day:
            continue
        weighted_values[local_day].append((pressure_hpa, _parse_duration_hours(item.get("validTime"))))
    for day_key in day_order:
        entries = weighted_values.get(day_key) or []
        if not entries:
            continue
        total_hours = sum(weight for _, weight in entries) or 1.0
        weighted_mean = sum(value * weight for value, weight in entries) / total_hours
        pressure_by_day[day_key] = round(weighted_mean, 1)

    rows: list[dict[str, Any]] = []
    prev_temp_mean: float | None = None
    prev_pressure: float | None = None
    updated_at = datetime.now(UTC)
    for day_key in day_order:
        bucket = grouped.get(day_key) or {}
        temps = [float(item) for item in bucket.get("temps") or []]
        humidity = [float(item) for item in bucket.get("humidity") or []]
        precip = [float(item) for item in bucket.get("precip") or []]
        wind = [float(item) for item in bucket.get("wind") or []]
        gust = [float(item) for item in bucket.get("gust") or []]
        summaries = [str(item) for item in bucket.get("summaries") or [] if str(item).strip()]

        temp_high = max(temps) if temps else None
        temp_low = min(temps) if temps else None
        temp_mean = (temp_high + temp_low) / 2.0 if temp_high is not None and temp_low is not None else (fmean(temps) if temps else None)
        pressure_hpa = pressure_by_day.get(day_key)
        summary = Counter(summaries).most_common(1)[0][0] if summaries else None
        pollen_row = pollen_by_day.get(day_key) or {}

        rows.append(
            {
                "location_key": location_key,
                "day": day_key,
                "source": "nws:forecast-hourly",
                "issued_at": issued_at,
                "location_zip": zip_code,
                "lat": lat,
                "lon": lon,
                "temp_high_c": _safe_round(temp_high, 1),
                "temp_low_c": _safe_round(temp_low, 1),
                "temp_delta_from_prior_day_c": _safe_round(temp_mean - prev_temp_mean, 1) if temp_mean is not None and prev_temp_mean is not None else None,
                "pressure_hpa": pressure_hpa,
                "pressure_delta_from_prior_day_hpa": _safe_round(pressure_hpa - prev_pressure, 1) if pressure_hpa is not None and prev_pressure is not None else None,
                "humidity_avg": _safe_round(fmean(humidity), 1) if humidity else None,
                "precip_probability": _safe_round(max(precip), 1) if precip else None,
                "wind_speed": _safe_round(fmean(wind), 1) if wind else None,
                "wind_gust": _safe_round(max(gust), 1) if gust else None,
                "condition_code": _slugify_condition(summary),
                "condition_summary": summary,
                "aqi_forecast": None,
                "pollen_tree_level": pollen_row.get("pollen_tree_level"),
                "pollen_grass_level": pollen_row.get("pollen_grass_level"),
                "pollen_weed_level": pollen_row.get("pollen_weed_level"),
                "pollen_mold_level": pollen_row.get("pollen_mold_level"),
                "pollen_overall_level": pollen_row.get("pollen_overall_level"),
                "pollen_primary_type": pollen_row.get("pollen_primary_type"),
                "pollen_source": pollen_row.get("pollen_source"),
                "pollen_updated_at": _parse_iso_datetime(pollen_row.get("pollen_updated_at")) or updated_at,
                "pollen_tree_index": _safe_float(pollen_row.get("pollen_tree_index")),
                "pollen_grass_index": _safe_float(pollen_row.get("pollen_grass_index")),
                "pollen_weed_index": _safe_float(pollen_row.get("pollen_weed_index")),
                "pollen_mold_index": _safe_float(pollen_row.get("pollen_mold_index")),
                "pollen_overall_index": _safe_float(pollen_row.get("pollen_overall_index")),
                "raw": json.dumps(
                    {
                        "period_count": bucket.get("raw_periods") or 0,
                        "pressure_points": len(weighted_values.get(day_key) or []),
                        "pollen_available": bool(pollen_row),
                        "pollen_primary_type": pollen_row.get("pollen_primary_type"),
                    }
                ),
                "updated_at": updated_at,
            }
        )
        prev_temp_mean = temp_mean if temp_mean is not None else prev_temp_mean
        prev_pressure = pressure_hpa if pressure_hpa is not None else prev_pressure

    return rows


async def _table_columns(conn, schema: str, table: str) -> list[str]:
    async with conn.cursor(**_cursor_kwargs()) as cur:
        await cur.execute(
            """
            select column_name
              from information_schema.columns
             where table_schema = %s
               and table_name = %s
             order by ordinal_position
            """,
            (schema, table),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [str(row.get("column_name")) for row in rows or [] if row.get("column_name")]


async def fetch_user_location_context(conn, user_id: str) -> dict[str, Any] | None:
    cols = await _table_columns(conn, "app", "user_locations")
    if not cols:
        return None

    user_col = _pick(cols, ["user_id"])
    zip_col = _pick(cols, ["zip", "postal_code"])
    lat_col = _pick(cols, ["lat", "latitude"])
    lon_col = _pick(cols, ["lon", "lng", "longitude"])
    primary_col = _pick(cols, ["is_primary", "primary", "is_default"])
    updated_col = _pick(cols, ["updated_at", "created_at"])
    if not user_col:
        return None

    select_parts = [
        f"{zip_col} as zip" if zip_col else "null::text as zip",
        f"{lat_col} as lat" if lat_col else "null::double precision as lat",
        f"{lon_col} as lon" if lon_col else "null::double precision as lon",
        "coalesce(local_insights_enabled, true) as local_insights_enabled"
        if "local_insights_enabled" in cols
        else "true as local_insights_enabled",
    ]
    order_parts = []
    if primary_col:
        order_parts.append(f"{primary_col} desc")
    if updated_col:
        order_parts.append(f"{updated_col} desc")
    order_sql = f" order by {', '.join(order_parts)}" if order_parts else ""
    sql = (
        f"select {', '.join(select_parts)} "
        f"from app.user_locations "
        f"where {user_col} = %s"
        f"{order_sql} "
        f"limit 1"
    )
    async with conn.cursor(**_cursor_kwargs()) as cur:
        await cur.execute(sql, (user_id,), prepare=False)
        row = await cur.fetchone()
    return dict(row) if row else None


def build_location_key(zip_code: str | None, lat: float | None, lon: float | None) -> str | None:
    if zip_code:
        return f"zip:{''.join(ch for ch in str(zip_code) if ch.isdigit())[:10]}"
    if lat is None or lon is None:
        return None
    return f"geo:{round(float(lat), 3):.3f},{round(float(lon), 3):.3f}"


async def _fetch_local_forecast_rows(conn, location_key: str, start_day: date, *, days: int = LOCAL_FORECAST_DAYS) -> list[dict[str, Any]]:
    async with conn.cursor(**_cursor_kwargs()) as cur:
        await cur.execute(
            """
            select location_key, day, source, issued_at, location_zip, lat, lon,
                   temp_high_c, temp_low_c, temp_delta_from_prior_day_c,
                   pressure_hpa, pressure_delta_from_prior_day_hpa,
                   humidity_avg, precip_probability, wind_speed, wind_gust,
                   condition_code, condition_summary, aqi_forecast,
                   pollen_tree_level, pollen_grass_level, pollen_weed_level, pollen_mold_level,
                   pollen_overall_level, pollen_primary_type, pollen_source, pollen_updated_at,
                   pollen_tree_index, pollen_grass_index, pollen_weed_index, pollen_mold_index, pollen_overall_index,
                   raw, updated_at
              from marts.local_forecast_daily
             where location_key = %s
               and day >= %s
             order by day asc
             limit %s
            """,
            (location_key, start_day, days),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows or []]


async def _upsert_local_forecast_rows(conn, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    async with conn.cursor() as cur:
        for row in rows:
            await cur.execute(
                """
                insert into marts.local_forecast_daily (
                    location_key, day, source, issued_at, location_zip, lat, lon,
                    temp_high_c, temp_low_c, temp_delta_from_prior_day_c,
                    pressure_hpa, pressure_delta_from_prior_day_hpa,
                    humidity_avg, precip_probability, wind_speed, wind_gust,
                    condition_code, condition_summary, aqi_forecast,
                    pollen_tree_level, pollen_grass_level, pollen_weed_level, pollen_mold_level,
                    pollen_overall_level, pollen_primary_type, pollen_source, pollen_updated_at,
                    pollen_tree_index, pollen_grass_index, pollen_weed_index, pollen_mold_index, pollen_overall_index,
                    raw, updated_at
                )
                values (
                    %(location_key)s, %(day)s, %(source)s, %(issued_at)s, %(location_zip)s, %(lat)s, %(lon)s,
                    %(temp_high_c)s, %(temp_low_c)s, %(temp_delta_from_prior_day_c)s,
                    %(pressure_hpa)s, %(pressure_delta_from_prior_day_hpa)s,
                    %(humidity_avg)s, %(precip_probability)s, %(wind_speed)s, %(wind_gust)s,
                    %(condition_code)s, %(condition_summary)s, %(aqi_forecast)s,
                    %(pollen_tree_level)s, %(pollen_grass_level)s, %(pollen_weed_level)s, %(pollen_mold_level)s,
                    %(pollen_overall_level)s, %(pollen_primary_type)s, %(pollen_source)s, %(pollen_updated_at)s,
                    %(pollen_tree_index)s, %(pollen_grass_index)s, %(pollen_weed_index)s, %(pollen_mold_index)s, %(pollen_overall_index)s,
                    %(raw)s::jsonb, %(updated_at)s
                )
                on conflict (location_key, day) do update
                set source = excluded.source,
                    issued_at = excluded.issued_at,
                    location_zip = excluded.location_zip,
                    lat = excluded.lat,
                    lon = excluded.lon,
                    temp_high_c = excluded.temp_high_c,
                    temp_low_c = excluded.temp_low_c,
                    temp_delta_from_prior_day_c = excluded.temp_delta_from_prior_day_c,
                    pressure_hpa = excluded.pressure_hpa,
                    pressure_delta_from_prior_day_hpa = excluded.pressure_delta_from_prior_day_hpa,
                    humidity_avg = excluded.humidity_avg,
                    precip_probability = excluded.precip_probability,
                    wind_speed = excluded.wind_speed,
                    wind_gust = excluded.wind_gust,
                    condition_code = excluded.condition_code,
                    condition_summary = excluded.condition_summary,
                    aqi_forecast = excluded.aqi_forecast,
                    pollen_tree_level = excluded.pollen_tree_level,
                    pollen_grass_level = excluded.pollen_grass_level,
                    pollen_weed_level = excluded.pollen_weed_level,
                    pollen_mold_level = excluded.pollen_mold_level,
                    pollen_overall_level = excluded.pollen_overall_level,
                    pollen_primary_type = excluded.pollen_primary_type,
                    pollen_source = excluded.pollen_source,
                    pollen_updated_at = excluded.pollen_updated_at,
                    pollen_tree_index = excluded.pollen_tree_index,
                    pollen_grass_index = excluded.pollen_grass_index,
                    pollen_weed_index = excluded.pollen_weed_index,
                    pollen_mold_index = excluded.pollen_mold_index,
                    pollen_overall_index = excluded.pollen_overall_index,
                    raw = excluded.raw,
                    updated_at = excluded.updated_at
                """,
                dict(row),
                prepare=False,
            )


async def ensure_local_forecast_daily(conn, *, zip_code: str | None, lat: float | None, lon: float | None) -> list[dict[str, Any]]:
    location_key = build_location_key(zip_code, lat, lon)
    if not location_key:
        return []

    today = datetime.now(UTC).date() - timedelta(days=1)
    existing = await _fetch_local_forecast_rows(conn, location_key, today, days=LOCAL_FORECAST_DAYS)
    if existing:
        newest = max((_parse_iso_datetime(row.get("updated_at")) for row in existing), default=None)
        if len(existing) >= LOCAL_FORECAST_DAYS and newest and newest >= datetime.now(UTC) - timedelta(hours=LOCAL_REFRESH_HOURS):
            return existing

    resolved_lat = lat
    resolved_lon = lon
    if (resolved_lat is None or resolved_lon is None) and zip_code:
        try:
            from services.geo.zip_lookup import zip_to_latlon

            resolved_lat, resolved_lon = await asyncio.to_thread(zip_to_latlon, zip_code)
        except Exception:
            resolved_lat = resolved_lon = None
    if resolved_lat is None or resolved_lon is None:
        return existing

    try:
        from services.external import nws

        hourly_payload, grid_payload, allergen_payload = await asyncio.gather(
            nws.forecast_hourly_by_latlon(float(resolved_lat), float(resolved_lon)),
            nws.gridpoints_by_latlon(float(resolved_lat), float(resolved_lon)),
            pollen.forecast_by_latlon(float(resolved_lat), float(resolved_lon), days=POLLEN_FORECAST_DAYS),
        )
        rows = summarize_local_forecast_days(
            hourly_payload,
            grid_payload,
            allergen_payload=allergen_payload,
            location_key=location_key,
            zip_code=zip_code,
            lat=float(resolved_lat),
            lon=float(resolved_lon),
            max_days=LOCAL_FORECAST_DAYS,
        )
    except Exception:
        return existing

    if rows:
        await _upsert_local_forecast_rows(conn, rows)
        try:
            await conn.commit()
        except Exception:
            pass
        return await _fetch_local_forecast_rows(conn, location_key, today, days=LOCAL_FORECAST_DAYS)
    return existing


async def _fetch_space_forecast_rows(conn, start_day: date, *, days: int = SPACE_FORECAST_DAYS) -> list[dict[str, Any]]:
    async with conn.cursor(**_cursor_kwargs()) as cur:
        await cur.execute(
            """
            with day_rows as (
                select *
                  from marts.space_forecast_daily
                 where forecast_day >= %s
            ),
            latest as (
                select distinct on (forecast_day)
                    forecast_day,
                    issued_at,
                    source_product_ts,
                    source_src
                  from day_rows
                 order by forecast_day, source_product_ts desc, updated_at desc
            ),
            merged as (
                select
                    forecast_day,
                    (array_agg(kp_max_forecast order by source_product_ts desc, updated_at desc)
                        filter (where kp_max_forecast is not null))[1] as kp_max_forecast,
                    coalesce(
                        (array_agg(g_scale_max order by source_product_ts desc, updated_at desc)
                            filter (where nullif(g_scale_max, '') is not null))[1],
                        'G0'
                    ) as g_scale_max,
                    (array_agg(s1_or_greater_pct order by source_product_ts desc, updated_at desc)
                        filter (where s1_or_greater_pct is not null))[1] as s1_or_greater_pct,
                    (array_agg(r1_r2_pct order by source_product_ts desc, updated_at desc)
                        filter (where r1_r2_pct is not null))[1] as r1_r2_pct,
                    (array_agg(r3_or_greater_pct order by source_product_ts desc, updated_at desc)
                        filter (where r3_or_greater_pct is not null))[1] as r3_or_greater_pct,
                    (array_agg(geomagnetic_rationale order by source_product_ts desc, updated_at desc)
                        filter (where nullif(geomagnetic_rationale, '') is not null))[1] as geomagnetic_rationale,
                    (array_agg(radiation_rationale order by source_product_ts desc, updated_at desc)
                        filter (where nullif(radiation_rationale, '') is not null))[1] as radiation_rationale,
                    (array_agg(radio_rationale order by source_product_ts desc, updated_at desc)
                        filter (where nullif(radio_rationale, '') is not null))[1] as radio_rationale,
                    coalesce(
                        (array_agg(kp_blocks_json order by source_product_ts desc, updated_at desc)
                            filter (where kp_blocks_json is not null and kp_blocks_json <> '[]'::jsonb))[1],
                        '[]'::jsonb
                    ) as kp_blocks_json,
                    (array_agg(raw_sections_json order by source_product_ts desc, updated_at desc)
                        filter (where raw_sections_json is not null))[1] as raw_sections_json,
                    bool_or(flare_watch) as flare_watch,
                    bool_or(cme_watch) as cme_watch,
                    bool_or(solar_wind_watch) as solar_wind_watch,
                    coalesce(
                        (array_agg(geomagnetic_severity_bucket order by source_product_ts desc, updated_at desc)
                            filter (where nullif(geomagnetic_severity_bucket, '') is not null))[1],
                        'low'
                    ) as geomagnetic_severity_bucket,
                    coalesce(
                        (array_agg(radiation_severity_bucket order by source_product_ts desc, updated_at desc)
                            filter (where nullif(radiation_severity_bucket, '') is not null))[1],
                        'low'
                    ) as radiation_severity_bucket,
                    coalesce(
                        (array_agg(radio_severity_bucket order by source_product_ts desc, updated_at desc)
                            filter (where nullif(radio_severity_bucket, '') is not null))[1],
                        'low'
                    ) as radio_severity_bucket,
                    max(updated_at) as updated_at
                  from day_rows
                 group by forecast_day
            )
            select
                latest.forecast_day,
                latest.issued_at,
                latest.source_product_ts,
                latest.source_src,
                merged.kp_max_forecast,
                merged.g_scale_max,
                merged.s1_or_greater_pct,
                merged.r1_r2_pct,
                merged.r3_or_greater_pct,
                merged.geomagnetic_rationale,
                merged.radiation_rationale,
                merged.radio_rationale,
                merged.kp_blocks_json,
                merged.raw_sections_json,
                merged.flare_watch,
                merged.cme_watch,
                merged.solar_wind_watch,
                merged.geomagnetic_severity_bucket,
                merged.radiation_severity_bucket,
                merged.radio_severity_bucket,
                merged.updated_at
              from latest
              join merged using (forecast_day)
             order by latest.forecast_day asc
             limit %s
            """,
            (start_day, days),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [dict(row) for row in rows or []]


async def _upsert_space_forecast_rows(conn, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    async with conn.cursor() as cur:
        for row in rows:
            await cur.execute(
                """
                insert into marts.space_forecast_daily (
                    forecast_day, issued_at, source_product_ts, source_src,
                    kp_max_forecast, g_scale_max,
                    s1_or_greater_pct, r1_r2_pct, r3_or_greater_pct,
                    geomagnetic_rationale, radiation_rationale, radio_rationale,
                    kp_blocks_json, raw_sections_json,
                    flare_watch, cme_watch, solar_wind_watch,
                    geomagnetic_severity_bucket, radiation_severity_bucket, radio_severity_bucket,
                    updated_at
                )
                values (
                    %(forecast_day)s, %(issued_at)s, %(source_product_ts)s, %(source_src)s,
                    %(kp_max_forecast)s, %(g_scale_max)s,
                    %(s1_or_greater_pct)s, %(r1_r2_pct)s, %(r3_or_greater_pct)s,
                    %(geomagnetic_rationale)s, %(radiation_rationale)s, %(radio_rationale)s,
                    %(kp_blocks_json)s::jsonb, %(raw_sections_json)s::jsonb,
                    %(flare_watch)s, %(cme_watch)s, %(solar_wind_watch)s,
                    %(geomagnetic_severity_bucket)s, %(radiation_severity_bucket)s, %(radio_severity_bucket)s,
                    %(updated_at)s
                )
                on conflict (forecast_day, source_product_ts) do update
                set issued_at = excluded.issued_at,
                    source_src = excluded.source_src,
                    kp_max_forecast = excluded.kp_max_forecast,
                    g_scale_max = excluded.g_scale_max,
                    s1_or_greater_pct = excluded.s1_or_greater_pct,
                    r1_r2_pct = excluded.r1_r2_pct,
                    r3_or_greater_pct = excluded.r3_or_greater_pct,
                    geomagnetic_rationale = excluded.geomagnetic_rationale,
                    radiation_rationale = excluded.radiation_rationale,
                    radio_rationale = excluded.radio_rationale,
                    kp_blocks_json = excluded.kp_blocks_json,
                    raw_sections_json = excluded.raw_sections_json,
                    flare_watch = excluded.flare_watch,
                    cme_watch = excluded.cme_watch,
                    solar_wind_watch = excluded.solar_wind_watch,
                    geomagnetic_severity_bucket = excluded.geomagnetic_severity_bucket,
                    radiation_severity_bucket = excluded.radiation_severity_bucket,
                    radio_severity_bucket = excluded.radio_severity_bucket,
                    updated_at = excluded.updated_at
                """,
                dict(row),
                prepare=False,
            )


async def ensure_space_forecast_daily(conn) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date() - timedelta(days=1)
    existing = await _fetch_space_forecast_rows(conn, today, days=SPACE_FORECAST_DAYS)
    if existing:
        newest = max((_parse_iso_datetime(row.get("updated_at")) for row in existing), default=None)
        if len(existing) >= SPACE_FORECAST_DAYS and newest and newest >= datetime.now(UTC) - timedelta(hours=LOCAL_REFRESH_HOURS):
            return existing
    async with conn.cursor(**_cursor_kwargs()) as cur:
        await cur.execute(
            """
            with latest as (
              select distinct on (src) fetched_at, src, body_text
                from ext.space_forecast
               where src in ('noaa-swpc:3-day-forecast', 'noaa-swpc:weekly', 'noaa-swpc:advisory-outlook')
               order by src, fetched_at desc
            )
            select fetched_at, src, body_text
              from latest
             order by fetched_at desc, src asc
            """,
            prepare=False,
        )
        source_rows = await cur.fetchall()
    if not source_rows:
        return existing

    parsed_rows: list[dict[str, Any]] = []
    for row in source_rows:
        src = str(row.get("src") or "")
        body_text = str(row.get("body_text") or "")
        fetched_at = row.get("fetched_at") or datetime.now(UTC)
        if src == "noaa-swpc:3-day-forecast":
            parsed_rows.extend(
                parse_swpc_three_day_forecast(
                    body_text,
                    source_product_ts=fetched_at,
                    src=src,
                )
            )
        elif src in {"noaa-swpc:weekly", "noaa-swpc:advisory-outlook"}:
            parsed_rows.extend(
                parse_swpc_range_forecast(
                    body_text,
                    source_product_ts=fetched_at,
                    src=src,
                    days=SPACE_FORECAST_DAYS,
                )
            )
    if parsed_rows:
        await _upsert_space_forecast_rows(conn, parsed_rows)
        try:
            await conn.commit()
        except Exception:
            pass
        return await _fetch_space_forecast_rows(conn, today, days=SPACE_FORECAST_DAYS)
    return existing


def _serialize_iso_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def serialize_local_forecast_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "location_key": row.get("location_key"),
                "day": _serialize_iso_value(row.get("day")),
                "source": row.get("source"),
                "issued_at": _serialize_iso_value(row.get("issued_at")),
                "location_zip": row.get("location_zip"),
                "lat": _safe_float(row.get("lat")),
                "lon": _safe_float(row.get("lon")),
                "temp_high_c": _safe_float(row.get("temp_high_c")),
                "temp_low_c": _safe_float(row.get("temp_low_c")),
                "temp_delta_from_prior_day_c": _safe_float(row.get("temp_delta_from_prior_day_c")),
                "pressure_hpa": _safe_float(row.get("pressure_hpa")),
                "pressure_delta_from_prior_day_hpa": _safe_float(row.get("pressure_delta_from_prior_day_hpa")),
                "humidity_avg": _safe_float(row.get("humidity_avg")),
                "precip_probability": _safe_float(row.get("precip_probability")),
                "wind_speed": _safe_float(row.get("wind_speed")),
                "wind_gust": _safe_float(row.get("wind_gust")),
                "condition_code": row.get("condition_code"),
                "condition_summary": row.get("condition_summary"),
                "aqi_forecast": _safe_float(row.get("aqi_forecast")),
                "pollen_tree_level": row.get("pollen_tree_level"),
                "pollen_grass_level": row.get("pollen_grass_level"),
                "pollen_weed_level": row.get("pollen_weed_level"),
                "pollen_mold_level": row.get("pollen_mold_level"),
                "pollen_overall_level": row.get("pollen_overall_level"),
                "pollen_primary_type": row.get("pollen_primary_type"),
                "pollen_source": row.get("pollen_source"),
                "pollen_updated_at": _serialize_iso_value(row.get("pollen_updated_at")),
                "pollen_tree_index": _safe_float(row.get("pollen_tree_index")),
                "pollen_grass_index": _safe_float(row.get("pollen_grass_index")),
                "pollen_weed_index": _safe_float(row.get("pollen_weed_index")),
                "pollen_mold_index": _safe_float(row.get("pollen_mold_index")),
                "pollen_overall_index": _safe_float(row.get("pollen_overall_index")),
                "updated_at": _serialize_iso_value(row.get("updated_at")),
            }
        )
    return payload


def serialize_space_forecast_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "forecast_day": _serialize_iso_value(row.get("forecast_day")),
                "issued_at": _serialize_iso_value(row.get("issued_at")),
                "source_product_ts": _serialize_iso_value(row.get("source_product_ts")),
                "source_src": row.get("source_src"),
                "kp_max_forecast": _safe_float(row.get("kp_max_forecast")),
                "g_scale_max": row.get("g_scale_max"),
                "s1_or_greater_pct": _safe_float(row.get("s1_or_greater_pct")),
                "r1_r2_pct": _safe_float(row.get("r1_r2_pct")),
                "r3_or_greater_pct": _safe_float(row.get("r3_or_greater_pct")),
                "geomagnetic_rationale": row.get("geomagnetic_rationale"),
                "radiation_rationale": row.get("radiation_rationale"),
                "radio_rationale": row.get("radio_rationale"),
                "flare_watch": bool(row.get("flare_watch")),
                "cme_watch": bool(row.get("cme_watch")),
                "solar_wind_watch": bool(row.get("solar_wind_watch")),
                "geomagnetic_severity_bucket": row.get("geomagnetic_severity_bucket"),
                "radiation_severity_bucket": row.get("radiation_severity_bucket"),
                "radio_severity_bucket": row.get("radio_severity_bucket"),
                "updated_at": _serialize_iso_value(row.get("updated_at")),
            }
        )
    return payload


async def fetch_latest_gauges(conn, user_id: str) -> dict[str, float | None]:
    async with conn.cursor(**_cursor_kwargs()) as cur:
        await cur.execute(
            """
            select pain, focus, heart, stamina, energy, sleep, mood, health_status
              from marts.user_gauges_day
             where user_id = %s
             order by day desc
             limit 1
            """,
            (user_id,),
            prepare=False,
        )
        row = await cur.fetchone()
    if not row:
        return {}
    return {
        "pain": _safe_float(row.get("pain")),
        "focus": _safe_float(row.get("focus")),
        "heart": _safe_float(row.get("heart")),
        "energy": _safe_float(row.get("energy")),
        "sleep": _safe_float(row.get("sleep")),
        "mood": _safe_float(row.get("mood")),
    }


def merge_daily_forecast_inputs(
    local_rows: Sequence[Mapping[str, Any]],
    space_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[date, dict[str, Any]] = {}
    for row in local_rows:
        day_key = row.get("day")
        if not isinstance(day_key, date):
            continue
        merged[day_key] = {
            "day": day_key,
            "temp_high_c": _safe_float(row.get("temp_high_c")),
            "temp_low_c": _safe_float(row.get("temp_low_c")),
            "temp_delta_from_prior_day_c": _safe_float(row.get("temp_delta_from_prior_day_c")),
            "pressure_hpa": _safe_float(row.get("pressure_hpa")),
            "pressure_delta_from_prior_day_hpa": _safe_float(row.get("pressure_delta_from_prior_day_hpa")),
            "humidity_avg": _safe_float(row.get("humidity_avg")),
            "precip_probability": _safe_float(row.get("precip_probability")),
            "wind_speed": _safe_float(row.get("wind_speed")),
            "wind_gust": _safe_float(row.get("wind_gust")),
            "condition_code": row.get("condition_code"),
            "condition_summary": row.get("condition_summary"),
            "aqi_forecast": _safe_float(row.get("aqi_forecast")),
            "pollen_tree_level": row.get("pollen_tree_level"),
            "pollen_grass_level": row.get("pollen_grass_level"),
            "pollen_weed_level": row.get("pollen_weed_level"),
            "pollen_mold_level": row.get("pollen_mold_level"),
            "pollen_overall_level": row.get("pollen_overall_level"),
            "pollen_primary_type": row.get("pollen_primary_type"),
            "pollen_tree_index": _safe_float(row.get("pollen_tree_index")),
            "pollen_grass_index": _safe_float(row.get("pollen_grass_index")),
            "pollen_weed_index": _safe_float(row.get("pollen_weed_index")),
            "pollen_mold_index": _safe_float(row.get("pollen_mold_index")),
            "pollen_overall_index": _safe_float(row.get("pollen_overall_index")),
        }
    for row in space_rows:
        day_key = row.get("forecast_day")
        if not isinstance(day_key, date):
            continue
        target = merged.setdefault(day_key, {"day": day_key})
        target.update(
            {
                "kp_max_forecast": _safe_float(row.get("kp_max_forecast")),
                "g_scale_max": row.get("g_scale_max"),
                "s1_or_greater_pct": _safe_float(row.get("s1_or_greater_pct")),
                "r1_r2_pct": _safe_float(row.get("r1_r2_pct")),
                "r3_or_greater_pct": _safe_float(row.get("r3_or_greater_pct")),
                "geomagnetic_rationale": row.get("geomagnetic_rationale"),
                "radiation_rationale": row.get("radiation_rationale"),
                "radio_rationale": row.get("radio_rationale"),
                "flare_watch": bool(row.get("flare_watch")),
                "cme_watch": bool(row.get("cme_watch")),
                "solar_wind_watch": bool(row.get("solar_wind_watch")),
                "geomagnetic_severity_bucket": row.get("geomagnetic_severity_bucket"),
                "radiation_severity_bucket": row.get("radiation_severity_bucket"),
                "radio_severity_bucket": row.get("radio_severity_bucket"),
            }
        )
    return [merged[key] for key in sorted(merged.keys())]


def derive_forecast_drivers(
    merged_rows: Sequence[Mapping[str, Any]],
    *,
    window_hours: int,
) -> list[dict[str, Any]]:
    row_limit = 2 if window_hours <= 24 else 3 if window_hours <= 72 else 7
    rows = list(merged_rows[:row_limit])
    if not rows:
        return []

    drivers: list[dict[str, Any]] = []

    def add_driver(
        key: str,
        *,
        severity: str,
        value: float | None,
        unit: str | None,
        day_key: date | None,
        detail: str,
        signal_key: str | None = None,
        label: str | None = None,
    ) -> None:
        if severity == "low":
            return
        drivers.append(
            {
                "key": key,
                "label": label or DRIVER_LABELS.get(key, key.replace("_", " ").title()),
                "severity": severity,
                "value": _safe_round(value, 1) if value is not None else None,
                "unit": unit,
                "day": day_key.isoformat() if isinstance(day_key, date) else None,
                "detail": detail,
                "signal_key": signal_key,
            }
        )

    pressure_candidates = [
        (row.get("day"), _safe_float(row.get("pressure_delta_from_prior_day_hpa")))
        for row in rows
        if _safe_float(row.get("pressure_delta_from_prior_day_hpa")) is not None
    ]
    if pressure_candidates:
        day_key, delta = max(pressure_candidates, key=lambda item: abs(item[1] or 0.0))
        add_driver(
            "pressure",
            severity=_severity_from_pressure(delta),
            value=delta,
            unit="hPa",
            day_key=day_key if isinstance(day_key, date) else None,
            detail=f"Pressure may swing about {abs(delta or 0.0):.1f} hPa day to day.",
            signal_key=DRIVER_TO_SIGNAL["pressure"],
        )

    temp_candidates = [
        (row.get("day"), _safe_float(row.get("temp_delta_from_prior_day_c")))
        for row in rows
        if _safe_float(row.get("temp_delta_from_prior_day_c")) is not None
    ]
    if temp_candidates:
        day_key, delta = max(temp_candidates, key=lambda item: abs(item[1] or 0.0))
        add_driver(
            "temp",
            severity=_severity_from_temp(delta),
            value=delta,
            unit="C",
            day_key=day_key if isinstance(day_key, date) else None,
            detail=f"Temperature may swing about {abs(delta or 0.0):.1f} C day to day.",
            signal_key=DRIVER_TO_SIGNAL["temp"],
        )

    humidity_candidates = [
        (row.get("day"), _safe_float(row.get("humidity_avg")))
        for row in rows
        if _safe_float(row.get("humidity_avg")) is not None
    ]
    if humidity_candidates:
        day_key, humidity_value = max(
            humidity_candidates,
            key=lambda item: (
                SEVERITY_RANK.get(_severity_from_humidity(item[1]), 0),
                _humidity_departure_score(item[1]),
            ),
        )
        add_driver(
            "humidity",
            severity=_severity_from_humidity(humidity_value),
            value=humidity_value,
            unit="%",
            day_key=day_key if isinstance(day_key, date) else None,
            detail=_humidity_detail(humidity_value or 0.0),
            signal_key=DRIVER_TO_SIGNAL.get("humidity"),
        )

    aqi_candidates = [
        (row.get("day"), _safe_float(row.get("aqi_forecast")))
        for row in rows
        if _safe_float(row.get("aqi_forecast")) is not None
    ]
    if aqi_candidates:
        day_key, aqi_value = max(aqi_candidates, key=lambda item: item[1] or 0.0)
        add_driver(
            "aqi",
            severity=_severity_from_aqi(aqi_value),
            value=aqi_value,
            unit="AQI",
            day_key=day_key if isinstance(day_key, date) else None,
            detail=f"AQI may drift up to around {aqi_value:.0f}.",
            signal_key=DRIVER_TO_SIGNAL["aqi"],
        )

    allergen_candidates = [
        (
            row.get("day"),
            str(row.get("pollen_overall_level") or ""),
            _safe_float(row.get("pollen_overall_index")),
            str(row.get("pollen_primary_type") or ""),
        )
        for row in rows
        if str(row.get("pollen_overall_level") or "").strip()
    ]
    if allergen_candidates:
        day_key, overall_level, overall_index, primary_type = max(
            allergen_candidates,
            key=lambda item: (
                pollen.LEVEL_RANK.get(item[1], 0),
                item[2] or 0.0,
            ),
        )
        primary_label = pollen.TYPE_LABELS.get(primary_type) if primary_type else None
        detail_subject = primary_label or "Allergen load"
        level_label = pollen.STATE_LABELS.get(overall_level, str(overall_level).replace("_", " ").title())
        add_driver(
            "allergens",
            label=primary_label or DRIVER_LABELS["allergens"],
            severity=_severity_from_allergen_level(overall_level),
            value=overall_index,
            unit="index",
            day_key=day_key if isinstance(day_key, date) else None,
            detail=f"{detail_subject} looks {level_label.lower()} over this period.",
            signal_key=DRIVER_TO_SIGNAL["allergens"],
        )

    kp_candidates = [
        (
            row.get("day"),
            _safe_float(row.get("kp_max_forecast")),
            str(row.get("g_scale_max") or ""),
        )
        for row in rows
        if _safe_float(row.get("kp_max_forecast")) is not None or row.get("g_scale_max")
    ]
    if kp_candidates:
        day_key, kp_value, g_scale = max(
            kp_candidates,
            key=lambda item: (_g_scale_int(item[2]), item[1] or 0.0),
        )
        severity = _severity_from_g_scale(g_scale or f"G{_g_from_kp(kp_value)}")
        add_driver(
            "kp",
            severity=severity,
            value=kp_value,
            unit="Kp",
            day_key=day_key if isinstance(day_key, date) else None,
            detail=f"SWPC expects {g_scale or 'elevated'} geomagnetic conditions in this window.",
            signal_key=DRIVER_TO_SIGNAL["kp"],
        )

    solar_wind_row = next((row for row in rows if row.get("solar_wind_watch")), None)
    if solar_wind_row:
        add_driver(
            "solar_wind",
            severity="watch" if str(solar_wind_row.get("geomagnetic_severity_bucket") or "") in {"watch", "high"} else "mild",
            value=None,
            unit=None,
            day_key=solar_wind_row.get("day") if isinstance(solar_wind_row.get("day"), date) else None,
            detail="SWPC is flagging a solar-wind watch.",
        )

    radio_row = next(
        (
            row
            for row in rows
            if (_safe_float(row.get("r1_r2_pct")) or 0.0) > 0 or (_safe_float(row.get("r3_or_greater_pct")) or 0.0) > 0
        ),
        None,
    )
    if radio_row:
        r1_pct = _safe_float(radio_row.get("r1_r2_pct"))
        r3_pct = _safe_float(radio_row.get("r3_or_greater_pct"))
        add_driver(
            "radio",
            severity=_severity_bucket_from_probability(r1_pct, r3_pct),
            value=max(r1_pct or 0.0, r3_pct or 0.0),
            unit="%",
            day_key=radio_row.get("day") if isinstance(radio_row.get("day"), date) else None,
            detail="SWPC is carrying a radio-blackout chance in this window.",
        )

    radiation_row = next((row for row in rows if (_safe_float(row.get("s1_or_greater_pct")) or 0.0) > 0), None)
    if radiation_row:
        s1_pct = _safe_float(radiation_row.get("s1_or_greater_pct"))
        add_driver(
            "radiation",
            severity=_severity_bucket_from_probability(s1_pct),
            value=s1_pct,
            unit="%",
            day_key=radiation_row.get("day") if isinstance(radiation_row.get("day"), date) else None,
            detail="SWPC is carrying a solar-radiation chance in this window.",
        )

    cme_row = next((row for row in rows if row.get("cme_watch")), None)
    if cme_row:
        add_driver(
            "cme",
            severity="watch",
            value=None,
            unit=None,
            day_key=cme_row.get("day") if isinstance(cme_row.get("day"), date) else None,
            detail="SWPC is watching for CME-driven activity.",
        )

    flare_row = next((row for row in rows if row.get("flare_watch")), None)
    if flare_row:
        add_driver(
            "flare",
            severity="watch",
            value=None,
            unit=None,
            day_key=flare_row.get("day") if isinstance(flare_row.get("day"), date) else None,
            detail="SWPC is flagging an elevated flare watch.",
        )

    drivers.sort(
        key=lambda item: (
            -SEVERITY_RANK.get(str(item.get("severity")), 0),
            int(DRIVER_ORDER.get(str(item.get("key")), 999)),
        )
    )
    return drivers


def _gauge_boost(domain_key: str, gauges: Mapping[str, Any]) -> float:
    gauge_key = GAUGE_BY_DOMAIN.get(domain_key)
    value = _safe_float(gauges.get(gauge_key)) if gauge_key else None
    if value is None:
        return 0.0
    if value >= 80:
        return 1.2
    if value >= 65:
        return 0.75
    if value >= 50:
        return 0.35
    return 0.0


def _likelihood_label(score: float) -> str:
    if score >= 5.0:
        return "watch"
    if score >= 3.5:
        return "elevated"
    return "mild"


def _support_line(driver_key: str) -> str:
    if driver_key == "pressure":
        return "Worth keeping pacing and hydration a little steadier if pressure changes feel easier to notice."
    if driver_key == "temp":
        return "Worth keeping hydration, layering, and recovery a little steadier if the temperature swing lands hard."
    if driver_key == "humidity":
        return "Worth keeping hydration, indoor air, and pacing a little steadier if humid or dry air is easier for you to notice."
    if driver_key == "aqi":
        return "Worth keeping the air around you a bit cleaner if the AQI drifts up."
    if driver_key == "allergens":
        return "Worth keeping windows, filters, rinses, and outdoor timing a little more deliberate if allergy-type days tend to hit you."
    if driver_key in {"kp", "solar_wind", "cme", "flare", "radio", "radiation"}:
        return "Worth keeping the next couple of evenings a little lower-stimulation if the space-weather watch becomes more noticeable for you."
    return "Worth keeping your baseline routines a little steadier while this window passes."


def _history_clause(pattern_row: Mapping[str, Any]) -> str:
    clause = pattern_anchor_statement(pattern_row, variant="clause")
    clause = clause.strip()
    if clause and clause.endswith("."):
        clause = clause[:-1]
    return clause


def _history_sentence(driver_label: str, pattern_row: Mapping[str, Any]) -> str:
    clause = _history_clause(pattern_row)
    if clause.startswith("it "):
        return f"{driver_label} {clause[3:]}"
    if clause.startswith("they "):
        return f"{driver_label} {clause[5:]}"
    return f"{driver_label} {clause}".strip()


def build_window_outlook(
    merged_rows: Sequence[Mapping[str, Any]],
    *,
    pattern_rows: Sequence[Mapping[str, Any]],
    gauges: Mapping[str, Any],
    window_hours: int,
) -> dict[str, Any] | None:
    if not merged_rows:
        return None

    semantic_day = next(
        (
            item
            for item in (
                row.get("day") if isinstance(row.get("day"), date) else None
                for row in merged_rows
            )
            if isinstance(item, date)
        ),
        date.today(),
    )

    window_label = "24 hours" if window_hours == 24 else "72 hours" if window_hours == 72 else "7 days" if window_hours == 168 else f"{window_hours} hours"

    drivers = derive_forecast_drivers(merged_rows, window_hours=window_hours)
    scoped_pattern_rows = [
        row
        for row in pattern_rows
        if int(row.get("lag_hours") or 0) <= window_hours
        and str(row.get("signal_key") or "") in SIGNAL_TO_DRIVER
    ]

    driver_map = {str(driver.get("signal_key")): driver for driver in drivers if driver.get("signal_key")}
    domain_scores: dict[str, dict[str, Any]] = {}
    for row in scoped_pattern_rows:
        signal_key = str(row.get("signal_key") or "")
        driver = driver_map.get(signal_key)
        if not driver:
            continue
        outcome_key = str(row.get("outcome_key") or "")
        domain_key = OUTCOME_TO_DOMAIN.get(outcome_key)
        if not domain_key:
            continue
        score = (
            SEVERITY_WEIGHT.get(str(driver.get("severity")), 0.0)
            + (confidence_rank(str(row.get("confidence") or "")) * 1.0)
            + min(float(row.get("relative_lift") or 0.0), 3.5) * 0.35
            + _gauge_boost(domain_key, gauges)
        )
        bucket = domain_scores.setdefault(
            domain_key,
            {"score": 0.0, "refs": [], "current_gauge": _safe_float(gauges.get(GAUGE_BY_DOMAIN.get(domain_key)))},
        )
        bucket["score"] += score
        bucket["refs"].append({"pattern_row": dict(row), "driver": dict(driver), "score": score})

    driver_scores: dict[str, float] = defaultdict(float)
    for payload in domain_scores.values():
        for ref in payload.get("refs") or []:
            driver_key = str(ref["driver"].get("key") or "")
            driver_scores[driver_key] += float(ref.get("score") or 0.0)

    top_drivers = sorted(
        drivers,
        key=lambda item: (
            -driver_scores.get(str(item.get("key") or ""), 0.0),
            -SEVERITY_RANK.get(str(item.get("severity")), 0),
            int(DRIVER_ORDER.get(str(item.get("key")), 999)),
        ),
    )[:3]
    visible_driver_keys = {
        str(item.get("key") or "").strip()
        for item in top_drivers
        if str(item.get("key") or "").strip()
    }

    likely_domains: list[dict[str, Any]] = []
    for domain_key, payload in domain_scores.items():
        refs = sorted(payload["refs"], key=lambda item: item["score"], reverse=True)
        if not refs:
            continue
        visible_refs = [
            ref for ref in refs if str(ref["driver"].get("key") or "").strip() in visible_driver_keys
        ]
        if visible_driver_keys and not visible_refs:
            continue
        chosen_refs = visible_refs or refs
        top_ref = chosen_refs[0]
        pattern_row = top_ref["pattern_row"]
        driver = top_ref["driver"]
        domain_score = sum(float(ref.get("score") or 0.0) for ref in chosen_refs) or float(payload["score"] or 0.0)
        explanation = (
            f"{driver['detail']} Over the next {window_label}, {_history_sentence(str(driver.get('label') or 'This signal'), pattern_row)}."
        )
        current_gauge = payload.get("current_gauge")
        if current_gauge is not None and current_gauge >= 65:
            explanation += f" {DOMAIN_LABELS[domain_key]} already looks a little elevated today, so it is worth watching."
        likely_domains.append(
            {
                "key": domain_key,
                "label": DOMAIN_LABELS[domain_key],
                "likelihood": _likelihood_label(domain_score),
                "current_gauge": current_gauge,
                "score": round(domain_score, 2),
                "explanation": explanation,
                "top_driver_key": driver.get("key"),
                "top_driver_label": driver.get("label"),
            }
        )

    likely_domains.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            int(DRIVER_ORDER.get(str(item.get("top_driver_key")), 999)),
        )
    )
    likely_domains = likely_domains[:4]
    top_domain = likely_domains[0] if likely_domains else None
    if top_domain and top_drivers:
        summary = (
            f"{top_drivers[0]['detail']} {top_domain['label']} may stand out more over this window based on your recent pattern history."
        )
        support_line = _support_line(str(top_drivers[0].get("key")))
    elif top_drivers:
        summary = f"{top_drivers[0]['detail']} No stronger personal pattern stands out yet, but this signal is still worth watching."
        support_line = _support_line(str(top_drivers[0].get("key")))
    else:
        summary = "No clearer short-range forecast driver stands out from the data available right now."
        support_line = "Worth sticking with your usual baseline routines while the next day or two settles out."

    payload = {
        "window_hours": window_hours,
        "likely_elevated_domains": [
            {key: value for key, value in item.items() if key != "score"}
            for item in likely_domains
        ],
        "top_drivers": top_drivers,
        "summary": summary,
        "support_line": support_line,
    }
    payload["voice_semantic"] = build_user_outlook_window_semantic(
        day=semantic_day,
        window_hours=window_hours,
        top_drivers=top_drivers,
        likely_domains=payload["likely_elevated_domains"],
        summary=summary,
        support_line=support_line,
    ).to_dict()
    return payload


def _daily_outlook_label(day: date, index: int) -> str:
    today = date.today()
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    if index == 0:
        return "Today"
    if index == 1:
        return "Tomorrow"
    return day.strftime("%a")


def build_daily_outlook(
    merged_rows: Sequence[Mapping[str, Any]],
    *,
    pattern_rows: Sequence[Mapping[str, Any]],
    gauges: Mapping[str, Any],
    days: int = 7,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(list(merged_rows)[:days]):
        day_value = row.get("day")
        if not isinstance(day_value, date):
            continue
        window = build_window_outlook(
            [row],
            pattern_rows=pattern_rows,
            gauges=gauges,
            window_hours=24,
        )
        if not window:
            continue
        top_drivers = window.get("top_drivers") or []
        likely_domains = window.get("likely_elevated_domains") or []
        primary = top_drivers[0] if top_drivers else None
        items.append(
            {
                "day": day_value.isoformat(),
                "label": _daily_outlook_label(day_value, index),
                "likely_elevated_domains": likely_domains,
                "top_drivers": top_drivers,
                "summary": window.get("summary"),
                "support_line": window.get("support_line"),
                "primary_state": primary.get("severity") if isinstance(primary, Mapping) else None,
                "voice_semantic": window.get("voice_semantic"),
            }
        )
    return items


async def build_user_outlook_payload(conn, user_id: str) -> dict[str, Any]:
    location = await fetch_user_location_context(conn, user_id)
    local_rows: list[dict[str, Any]] = []
    if location and bool(location.get("local_insights_enabled", True)):
        local_rows = await ensure_local_forecast_daily(
            conn,
            zip_code=str(location.get("zip") or "").strip() or None,
            lat=_safe_float(location.get("lat")),
            lon=_safe_float(location.get("lon")),
        )

    space_rows = await ensure_space_forecast_daily(conn)
    merged_rows = merge_daily_forecast_inputs(local_rows, space_rows)
    pattern_rows = await fetch_best_pattern_rows(conn, user_id)
    gauges = await fetch_latest_gauges(conn, user_id)
    daily_outlook = build_daily_outlook(
        merged_rows,
        pattern_rows=pattern_rows,
        gauges=gauges,
        days=7,
    )

    next_24h = None
    if local_rows and space_rows:
        next_24h = build_window_outlook(
            merged_rows,
            pattern_rows=pattern_rows,
            gauges=gauges,
            window_hours=24,
        )

    next_72h = None
    if len(local_rows) >= 3 and len(space_rows) >= 3:
        next_72h = build_window_outlook(
            merged_rows,
            pattern_rows=pattern_rows,
            gauges=gauges,
            window_hours=72,
        )

    next_7d = None
    if len(local_rows) >= LOCAL_FORECAST_DAYS and len(space_rows) >= SPACE_FORECAST_DAYS:
        next_7d = build_window_outlook(
            merged_rows,
            pattern_rows=pattern_rows,
            gauges=gauges,
            window_hours=168,
        )

    available_windows: list[str] = []
    if next_24h:
        available_windows.append("next_24h")
    if next_72h:
        available_windows.append("next_72h")
    if next_7d:
        available_windows.append("next_7d")

    generated_at = datetime.now(UTC).isoformat()
    overview_semantic = build_user_outlook_overview_semantic(
        day=datetime.now(UTC).date(),
        available_windows=available_windows,
        forecast_data_ready={
            "location_found": bool(location),
            "local_forecast_daily": bool(local_rows),
            "local_forecast_days": len(local_rows),
            "space_forecast_daily": bool(space_rows),
            "space_forecast_days": len(space_rows),
            "next_24h": bool(next_24h),
            "next_72h": bool(next_72h),
            "next_7d": bool(next_7d),
        },
        windows=[next_24h, next_72h, next_7d],
    )

    return {
        "generated_at": generated_at,
        "available_windows": available_windows,
        "daily_outlook": daily_outlook,
        "forecast_data_ready": {
            "location_found": bool(location),
            "local_forecast_daily": bool(local_rows),
            "local_forecast_days": len(local_rows),
            "space_forecast_daily": bool(space_rows),
            "space_forecast_days": len(space_rows),
            "next_24h": bool(next_24h),
            "next_72h": bool(next_72h),
            "next_7d": bool(next_7d),
        },
        "next_24h": next_24h,
        "next_72h": next_72h,
        "next_7d": next_7d,
        "voice_semantics": {
            "overview": overview_semantic.to_dict(),
        },
    }
