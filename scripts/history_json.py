"""Validation shared by history publication and the comparison builder."""

import datetime as dt
import json
import math
from pathlib import Path


QUAKE_DAILY = ("all_daily", "m5p_daily", "m6p_daily")
SPACE_DAILY = ("kp_daily_max", "bz_daily_min", "sw_daily_avg")
MAX_AGE = dt.timedelta(hours=48)


def load_json(path):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise ValueError(f"{Path(path).name}: missing or invalid JSON") from exc


def validate_history(data, name, daily_keys, *, now=None):
    """Require a recent build AND recent data, before replacing public output."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(data, dict):
        raise ValueError(f"{name}: expected a JSON object")
    try:
        stamp = dt.datetime.fromisoformat(data["timestamp_utc"].replace("Z", "+00:00"))
        # Older builders emitted UTC without an explicit offset.
        stamp = stamp.replace(tzinfo=dt.timezone.utc) if stamp.tzinfo is None else stamp
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{name}: invalid timestamp_utc") from exc
    if not -dt.timedelta(minutes=5) <= now - stamp <= MAX_AGE:
        raise ValueError(f"{name}: stale or future timestamp_utc ({stamp.isoformat()})")
    series = data.get("series")
    if not isinstance(series, dict):
        raise ValueError(f"{name}: missing series")
    for key in daily_keys:
        points = series.get(key)
        if not isinstance(points, list) or not points:
            raise ValueError(f"{name}: missing or empty {key}")
        previous = None
        for point in points:
            try:
                day, value = point
                date = dt.date.fromisoformat(day)
                valid = (day == date.isoformat() and type(value) in (int, float)
                         and math.isfinite(value) and (previous is None or date > previous))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name}: invalid {key} point") from exc
            if not valid:
                raise ValueError(f"{name}: invalid or unordered {key} point")
            previous = date
        if not now.date() - MAX_AGE <= previous <= now.date():
            raise ValueError(f"{name}: stale or future {key} data ({previous})")


def validate_quakes_history(data, *, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    validate_history(data, "quakes_history.json", QUAKE_DAILY, now=now)
    for key in QUAKE_DAILY:
        if any(type(value) is not int or value < 0 for _, value in data["series"][key]):
            raise ValueError(f"quakes_history.json: invalid count in {key}")
    # The generator pads daily bins through today. A fresh zero-filled endpoint
    # does not prove that USGS supplied recent events.
    event_days = [day for day, count in data["series"]["all_daily"] if count > 0]
    if not event_days or dt.date.fromisoformat(event_days[-1]) < now.date() - MAX_AGE:
        raise ValueError("quakes_history.json: no recent nonzero earthquake day")
