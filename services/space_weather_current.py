from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


_SPEED_URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
_MAG_URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json"
_SPEED_FALLBACK_URL = "https://services.swpc.noaa.gov/products/summary/solar-wind-speed.json"
_MAG_FALLBACK_URL = "https://services.swpc.noaa.gov/products/summary/solar-wind-mag-field.json"
_CACHE_TTL_SECONDS = 60.0
_MAX_SOURCE_AGE_SECONDS = 90 * 60
_cache_lock = threading.Lock()
_cache_at = 0.0
_cache_value: Dict[str, Any] = {}


def _first_active_row(value: Any, *, required_field: str) -> Dict[str, Any]:
    if isinstance(value, list):
        rows = [row for row in value if isinstance(row, dict) and row.get(required_field) is not None]
        active_rows = [
            row for row in rows
            if row.get("active") is True or str(row.get("active")).strip().lower() in {"1", "true", "yes"}
        ]
        if active_rows:
            return max(active_rows, key=lambda row: _timestamp(row.get("time_tag")) or datetime.min.replace(tzinfo=timezone.utc))
        if rows:
            return max(rows, key=lambda row: _timestamp(row.get("time_tag")) or datetime.min.replace(tzinfo=timezone.utc))
    if isinstance(value, dict):
        return value
    return {}


def _fetch_row(url: str, fallback_url: str, *, required_field: str, timeout: float) -> Dict[str, Any]:
    for candidate in (url, fallback_url):
        try:
            row = _first_active_row(requests.get(candidate, timeout=timeout).json(), required_field=required_field)
        except Exception:
            row = {}
        timestamp = _timestamp(row.get("time_tag")) if row else None
        is_fresh = timestamp is not None and (
            datetime.now(timezone.utc) - timestamp
        ).total_seconds() <= _MAX_SOURCE_AGE_SECONDS
        if row and is_fresh:
            row = dict(row)
            row["_url"] = candidate
            return row
    return {}


def _float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_current_space_weather(*, timeout: float = 2.0, force: bool = False) -> Dict[str, Any]:
    global _cache_at, _cache_value

    now = time.monotonic()
    with _cache_lock:
        if not force and _cache_value and now - _cache_at < _CACHE_TTL_SECONDS:
            return dict(_cache_value)

    speed_row: Dict[str, Any] = {}
    mag_row: Dict[str, Any] = {}
    speed_row = _fetch_row(
        _SPEED_URL,
        _SPEED_FALLBACK_URL,
        required_field="proton_speed",
        timeout=timeout,
    )
    mag_row = _fetch_row(
        _MAG_URL,
        _MAG_FALLBACK_URL,
        required_field="bz_gsm",
        timeout=timeout,
    )

    speed_ts = _timestamp(speed_row.get("time_tag"))
    mag_ts = _timestamp(mag_row.get("time_tag"))
    timestamps = [item for item in (speed_ts, mag_ts) if item is not None]
    result = {
        "sw_speed_now_kms": _float(speed_row.get("proton_speed")),
        "bz_now": _float(mag_row.get("bz_gsm")),
        "bt_now": _float(mag_row.get("bt")),
        "updated_at": max(timestamps).isoformat() if timestamps else None,
        "source": "NOAA SWPC RTSW",
        "speed_spacecraft": speed_row.get("source"),
        "mag_spacecraft": mag_row.get("source"),
        "speed_source_url": speed_row.get("_url"),
        "mag_source_url": mag_row.get("_url"),
    }
    if not any(result.get(key) is not None for key in ("sw_speed_now_kms", "bz_now")):
        return {}

    with _cache_lock:
        _cache_at = now
        _cache_value = dict(result)
    return result
