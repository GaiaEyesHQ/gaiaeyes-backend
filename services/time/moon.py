from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import cos, floor, pi
from typing import Any, Dict, List

PHASES = [
    ("New Moon", 0.0),
    ("Waxing Crescent", 0.03),
    ("First Quarter", 0.23),
    ("Waxing Gibbous", 0.27),
    ("Full Moon", 0.47),
    ("Waning Gibbous", 0.52),
    ("Last Quarter", 0.73),
    ("Waning Crescent", 0.77),
]

KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
SYNODIC_MONTH_DAYS = 29.53058867
FULL_MOON_OFFSET_DAYS = SYNODIC_MONTH_DAYS / 2.0


def _ensure_utc_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time(12, 0), tzinfo=timezone.utc)


def _cycle_for_datetime(dt: datetime) -> float:
    days = (dt - KNOWN_NEW_MOON).total_seconds() / 86400.0
    raw_cycle = days / SYNODIC_MONTH_DAYS
    return raw_cycle - floor(raw_cycle)


def _phase_label_for_cycle(cycle: float) -> str:
    return next((name for name, threshold in reversed(PHASES) if cycle >= threshold), "New Moon")


def _nearest_event_offset_days(dt: datetime, *, base: datetime) -> float:
    days_since_base = (dt - base).total_seconds() / 86400.0
    nearest_index = round(days_since_base / SYNODIC_MONTH_DAYS)
    nearest_event = base + timedelta(days=nearest_index * SYNODIC_MONTH_DAYS)
    return (dt - nearest_event).total_seconds() / 86400.0


def moon_phase(dt: datetime) -> dict:
    dt = _ensure_utc_datetime(dt)
    cycle = _cycle_for_datetime(dt)
    illum_fraction = 0.5 * (1 - cos(2 * pi * cycle))
    phase_label = _phase_label_for_cycle(cycle)
    known_full_moon = KNOWN_NEW_MOON + timedelta(days=FULL_MOON_OFFSET_DAYS)
    days_from_full = _nearest_event_offset_days(dt, base=known_full_moon)
    days_from_new = _nearest_event_offset_days(dt, base=KNOWN_NEW_MOON)

    return {
        "phase": phase_label,
        "illum": round(illum_fraction, 3),
        "cycle": round(cycle, 3),
        "moon_phase_fraction": round(cycle, 6),
        "moon_illumination_pct": round(illum_fraction * 100.0, 3),
        "moon_phase_label": phase_label,
        "days_from_full_moon": int(round(days_from_full)),
        "days_from_new_moon": int(round(days_from_new)),
    }


def moon_context_for_day(day: date) -> Dict[str, Any]:
    context = moon_phase(datetime.combine(day, time(12, 0), tzinfo=timezone.utc))
    context["utc_date"] = day.isoformat()
    return context


def lunar_overlay_windows(start_day: date, end_day: date) -> List[Dict[str, str]]:
    if end_day < start_day:
        start_day, end_day = end_day, start_day

    windows: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _collect(kind: str, *, base: datetime) -> None:
        range_start = datetime.combine(start_day, time.min, tzinfo=timezone.utc) - timedelta(days=1)
        range_end = datetime.combine(end_day, time.max, tzinfo=timezone.utc) + timedelta(days=1)
        start_index = floor(((range_start - base).total_seconds() / 86400.0) / SYNODIC_MONTH_DAYS) - 1
        end_index = floor(((range_end - base).total_seconds() / 86400.0) / SYNODIC_MONTH_DAYS) + 1
        label = "Full moon" if kind == "full" else "New moon"

        for index in range(start_index, end_index + 1):
            event_dt = base + timedelta(days=index * SYNODIC_MONTH_DAYS)
            event_day = event_dt.astimezone(timezone.utc).date()
            if event_day < start_day or event_day > end_day:
                continue
            key = (kind, event_day.isoformat())
            if key in seen:
                continue
            seen.add(key)
            windows.append(
                {
                    "date": event_day.isoformat(),
                    "type": kind,
                    "label": label,
                }
            )

    _collect("full", base=KNOWN_NEW_MOON + timedelta(days=FULL_MOON_OFFSET_DAYS))
    _collect("new", base=KNOWN_NEW_MOON)

    return sorted(windows, key=lambda item: (item["date"], item["type"]))
