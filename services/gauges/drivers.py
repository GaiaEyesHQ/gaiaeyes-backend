from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple


_HEADER_RE = re.compile(r"^\s*#+\s*(.+?)\s*$")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*•]\s+|\d+\.\s+)")
_HPA_RE = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*hpa", re.IGNORECASE)
_KM_S_RE = re.compile(r"(\d+(?:\.\d+)?)\s*km\s*/?\s*s", re.IGNORECASE)
_AQI_RE = re.compile(r"aqi[^0-9]{0,8}(\d{1,3})", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")

_STATE_ORDER = [
    ("very high", 5, "Very high"),
    ("unhealthy", 5, "Unhealthy"),
    ("storm", 5, "Storm"),
    ("strong", 4, "Strong"),
    ("high", 4, "High"),
    ("usg", 4, "USG"),
    ("moderate", 3, "Moderate"),
    ("elevated", 3, "Elevated"),
    ("active", 3, "Active"),
    ("watch", 2, "Watch"),
    ("mild", 2, "Mild"),
    ("low", 1, "Low"),
    ("good", 1, "Good"),
]


def _clean_line(value: str) -> str:
    line = str(value or "").strip()
    if not line:
        return ""
    line = _LIST_PREFIX_RE.sub("", line)
    line = line.replace("**", "").replace("__", "")
    return _WS_RE.sub(" ", line).strip()


def _normalized_key(value: str) -> str:
    lowered = _clean_line(value).lower()
    lowered = re.sub(r"\([^)]*\)", " ", lowered)
    lowered = _NON_ALNUM_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", lowered).strip()


def _extract_state(text: str) -> Tuple[int, str]:
    lowered = text.lower()
    for token, rank, label in _STATE_ORDER:
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return rank, label
    return 0, ""


def _label_for_rank(rank: int, *, default: str = "Elevated") -> str:
    if rank >= 5:
        return "Very high"
    if rank >= 4:
        return "High"
    if rank >= 3:
        return "Moderate"
    if rank >= 2:
        return "Watch"
    if rank >= 1:
        return "Low"
    return default


def _extract_pressure_deltas(text: str) -> Tuple[Optional[float], Optional[float]]:
    lowered = text.lower()
    delta_24h: Optional[float] = None
    delta_12h: Optional[float] = None
    fallback: Optional[float] = None

    for match in _HPA_RE.finditer(text):
        try:
            value = float(match.group(1))
        except Exception:
            continue
        start, end = match.span()
        context = lowered[max(0, start - 24): min(len(lowered), end + 24)]
        if "24h" in context:
            delta_24h = value
        elif "12h" in context:
            delta_12h = value
        elif fallback is None:
            fallback = value

    if delta_24h is None and delta_12h is None and fallback is not None:
        delta_24h = fallback
    return delta_24h, delta_12h


def _state_from_aqi(aqi: Optional[int]) -> str:
    if aqi is None:
        return "Moderate"
    if aqi >= 151:
        return "Unhealthy"
    if aqi >= 101:
        return "USG"
    if aqi >= 51:
        return "Moderate"
    return "Good"


def extract_drivers_from_markdown(markdown: Optional[str]) -> List[str]:
    if not markdown or not str(markdown).strip():
        return []

    lines = str(markdown).replace("\r\n", "\n").split("\n")
    in_drivers = False
    out: List[str] = []

    for raw in lines:
        trimmed = str(raw or "").strip()
        if not trimmed:
            continue

        header = _HEADER_RE.match(trimmed)
        if header:
            heading = header.group(1).strip().lower()
            if "driver" in heading:
                in_drivers = True
            elif in_drivers:
                break
            continue

        if not in_drivers:
            if trimmed.lower().startswith("drivers:"):
                candidate = _clean_line(trimmed.split(":", 1)[1])
                if candidate:
                    out.append(candidate)
            continue

        cleaned = _clean_line(trimmed)
        if cleaned:
            out.append(cleaned)

    return out


def normalize_drivers(raw_drivers: Iterable[str]) -> List[str]:
    pressure_rank = 0
    pressure_label = ""
    pressure_windows: set[str] = set()
    pressure_delta_24h: Optional[float] = None
    pressure_delta_12h: Optional[float] = None

    solar_rank = 0
    solar_label = ""
    solar_speed: Optional[float] = None

    aqi_rank = 0
    aqi_label = ""
    aqi_value: Optional[int] = None

    seen_other: set[str] = set()
    ranked_lines: List[Tuple[int, int, str]] = []
    order = 0

    for raw in list(raw_drivers or []):
        line = _clean_line(str(raw or ""))
        if not line:
            continue
        lower = line.lower()

        if "pressure swing" in lower:
            rank, label = _extract_state(line)
            if rank > pressure_rank:
                pressure_rank = rank
                pressure_label = label
            if "12h" in lower:
                pressure_windows.add("12h")
            if "24h" in lower:
                pressure_windows.add("24h")
            delta_24h, delta_12h = _extract_pressure_deltas(line)
            if delta_24h is not None:
                pressure_delta_24h = delta_24h
            if delta_12h is not None:
                pressure_delta_12h = delta_12h
            continue

        if "solar wind" in lower:
            rank, label = _extract_state(line)
            if rank > solar_rank:
                solar_rank = rank
                solar_label = label
            speed_match = _KM_S_RE.search(line)
            if speed_match:
                try:
                    speed = float(speed_match.group(1))
                    solar_speed = max(solar_speed or speed, speed)
                except Exception:
                    pass
            continue

        if "aqi" in lower or "air quality" in lower:
            rank, label = _extract_state(line)
            if rank > aqi_rank:
                aqi_rank = rank
                aqi_label = label
            aqi_match = _AQI_RE.search(line)
            if aqi_match:
                try:
                    aqi_value = int(aqi_match.group(1))
                except Exception:
                    pass
            continue

        key = _normalized_key(line)
        if not key or key in seen_other:
            continue
        seen_other.add(key)
        rank, _ = _extract_state(line)
        ranked_lines.append((rank, order, line))
        order += 1

    if pressure_rank > 0 or pressure_windows or pressure_delta_24h is not None or pressure_delta_12h is not None:
        windows = sorted(pressure_windows, key=lambda w: 0 if w == "12h" else 1)
        line = f"Pressure swing: {pressure_label or _label_for_rank(pressure_rank, default='Moderate')}"
        if windows:
            line += f" ({', '.join(windows)})"
        delta = pressure_delta_24h if pressure_delta_24h is not None else pressure_delta_12h
        if delta is not None:
            tag = "Δ24h" if pressure_delta_24h is not None else "Δ12h"
            line += f" ({tag} {delta:+.1f} hPa)"
        ranked_lines.append((max(pressure_rank, 1), order, line))
        order += 1

    if solar_rank > 0 or solar_speed is not None:
        line = f"Solar wind: {solar_label or _label_for_rank(solar_rank, default='Elevated')}"
        if solar_speed is not None:
            line += f" ({int(round(solar_speed, 0))} km/s)"
        ranked_lines.append((max(solar_rank, 1), order, line))
        order += 1

    if aqi_rank > 0 or aqi_value is not None:
        category = aqi_label or _state_from_aqi(aqi_value)
        line = f"AQI: {category}"
        if aqi_value is not None:
            line += f" ({int(round(aqi_value, 0))})"
        ranked_lines.append((max(aqi_rank, 1), order, line))

    ranked_lines.sort(key=lambda item: (-item[0], item[1]))
    out = [line for _, _, line in ranked_lines]
    return out[:5]
