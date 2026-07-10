from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


_SPEED_URL = "https://services.swpc.noaa.gov/products/summary/solar-wind-speed.json"
_MAG_URL = "https://services.swpc.noaa.gov/products/summary/solar-wind-mag-field.json"
_CACHE_TTL_SECONDS = 60.0
_cache_lock = threading.Lock()
_cache_at = 0.0
_cache_value: Dict[str, Any] = {}


def _first_row(value: Any) -> Dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
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
    try:
        speed_row = _first_row(requests.get(_SPEED_URL, timeout=timeout).json())
    except Exception:
        pass
    try:
        mag_row = _first_row(requests.get(_MAG_URL, timeout=timeout).json())
    except Exception:
        pass

    speed_ts = _timestamp(speed_row.get("time_tag"))
    mag_ts = _timestamp(mag_row.get("time_tag"))
    timestamps = [item for item in (speed_ts, mag_ts) if item is not None]
    result = {
        "sw_speed_now_kms": _float(speed_row.get("proton_speed")),
        "bz_now": _float(mag_row.get("bz_gsm")),
        "bt_now": _float(mag_row.get("bt")),
        "updated_at": max(timestamps).isoformat() if timestamps else None,
        "source": "NOAA SWPC current summary",
    }
    if not any(result.get(key) is not None for key in ("sw_speed_now_kms", "bz_now")):
        return {}

    with _cache_lock:
        _cache_at = now
        _cache_value = dict(result)
    return result
