from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict
from urllib.parse import urlencode
from zoneinfo import ZoneInfo


DEFAULT_NOTIFICATION_FAMILIES: Dict[str, bool] = {
    "geomagnetic": True,
    "solar_wind": True,
    "flare_cme_sep": True,
    "schumann": True,
    "pressure": True,
    "aqi": True,
    "temp": True,
    "gauge_spikes": True,
    "symptom_followups": False,
    "daily_checkins": False,
}

DEFAULT_NOTIFICATION_PREFERENCES: Dict[str, Any] = {
    "enabled": False,
    "signal_alerts_enabled": True,
    "local_condition_alerts_enabled": True,
    "personalized_gauge_alerts_enabled": True,
    "quiet_hours_enabled": False,
    "quiet_start": "22:00",
    "quiet_end": "08:00",
    "time_zone": "UTC",
    "sensitivity": "normal",
    "symptom_followups_enabled": False,
    "symptom_followup_push_enabled": False,
    "daily_checkins_enabled": False,
    "daily_checkin_push_enabled": False,
    "families": dict(DEFAULT_NOTIFICATION_FAMILIES),
}

FAMILY_COOLDOWN_HOURS: Dict[str, int] = {
    "geomagnetic": 6,
    "solar_wind": 4,
    "flare_cme_sep": 6,
    "schumann": 6,
    "pressure": 4,
    "aqi": 6,
    "temp": 6,
    "pain": 6,
    "energy": 6,
    "sleep": 6,
    "heart": 6,
    "health_status": 6,
    "symptom_followups": 6,
    "daily_checkins": 24,
    "digest": 6,
}

SEVERITY_RANK = {"info": 0, "watch": 1, "high": 2}


@dataclass(frozen=True)
class NotificationCandidate:
    family: str
    event_key: str
    severity: str
    title: str
    body: str
    target_type: str
    target_key: str
    asof: str | None = None
    payload: Dict[str, Any] | None = None

    def event_payload(self) -> Dict[str, Any]:
        payload = dict(self.payload or {})
        payload.setdefault("family", self.family)
        payload.setdefault("event_key", self.event_key)
        payload.setdefault("target_type", self.target_type)
        payload.setdefault("target_key", self.target_key)
        payload.setdefault("asof", self.asof)
        payload.setdefault(
            "deep_link",
            build_deep_link(
                family=self.family,
                event_key=self.event_key,
                target_type=self.target_type,
                target_key=self.target_key,
                asof=self.asof,
            ),
        )
        return payload


def normalize_preferences(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    raw = dict(raw or {})
    merged["enabled"] = bool(raw.get("enabled", merged["enabled"]))
    merged["signal_alerts_enabled"] = bool(raw.get("signal_alerts_enabled", merged["signal_alerts_enabled"]))
    merged["local_condition_alerts_enabled"] = bool(raw.get("local_condition_alerts_enabled", merged["local_condition_alerts_enabled"]))
    merged["personalized_gauge_alerts_enabled"] = bool(
        raw.get("personalized_gauge_alerts_enabled", merged["personalized_gauge_alerts_enabled"])
    )
    merged["quiet_hours_enabled"] = bool(raw.get("quiet_hours_enabled", merged["quiet_hours_enabled"]))
    merged["quiet_start"] = str(raw.get("quiet_start") or merged["quiet_start"])
    merged["quiet_end"] = str(raw.get("quiet_end") or merged["quiet_end"])
    merged["time_zone"] = str(raw.get("time_zone") or merged["time_zone"])
    sensitivity = str(raw.get("sensitivity") or merged["sensitivity"]).strip().lower() or "normal"
    merged["sensitivity"] = sensitivity if sensitivity in {"minimal", "normal", "detailed"} else "normal"
    merged["symptom_followups_enabled"] = bool(raw.get("symptom_followups_enabled", merged["symptom_followups_enabled"]))
    merged["symptom_followup_push_enabled"] = bool(raw.get("symptom_followup_push_enabled", merged["symptom_followup_push_enabled"]))
    merged["daily_checkins_enabled"] = bool(raw.get("daily_checkins_enabled", merged["daily_checkins_enabled"]))
    merged["daily_checkin_push_enabled"] = bool(raw.get("daily_checkin_push_enabled", merged["daily_checkin_push_enabled"]))
    merged["families"] = normalize_families(raw.get("families"))
    return merged


def normalize_families(raw: Any) -> Dict[str, bool]:
    merged = dict(DEFAULT_NOTIFICATION_FAMILIES)
    if isinstance(raw, dict):
        for key in DEFAULT_NOTIFICATION_FAMILIES:
            if key in raw:
                merged[key] = bool(raw.get(key))
    return merged


def allows_severity(sensitivity: str, severity: str) -> bool:
    normalized = (sensitivity or "normal").strip().lower() or "normal"
    if normalized == "minimal":
        return severity == "high"
    return severity in {"watch", "high"}


def cooldown_hours_for_family(family: str) -> int:
    return FAMILY_COOLDOWN_HOURS.get(family, 6)


def cooldown_active(previous_created_at: datetime | None, family: str, now_utc: datetime) -> bool:
    if previous_created_at is None:
        return False
    previous_utc = previous_created_at.astimezone(timezone.utc)
    return now_utc < previous_utc + timedelta(hours=cooldown_hours_for_family(family))


def parse_hhmm(value: str | None, *, fallback: str) -> time:
    raw = (value or "").strip() or fallback
    hour, minute = raw.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def is_within_quiet_hours(
    now_utc: datetime,
    *,
    enabled: bool,
    time_zone_name: str,
    quiet_start: str,
    quiet_end: str,
) -> bool:
    if not enabled:
        return False

    try:
        tz = ZoneInfo(time_zone_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    local_time = now_utc.astimezone(tz).timetz().replace(tzinfo=None)
    start = parse_hhmm(quiet_start, fallback="22:00")
    end = parse_hhmm(quiet_end, fallback="08:00")

    if start == end:
        return True
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def dedupe_bucket_start(now_utc: datetime, family: str) -> datetime:
    hours = max(1, cooldown_hours_for_family(family))
    hour_bucket = (now_utc.hour // hours) * hours
    return now_utc.astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
        hour=hour_bucket,
    )


def build_dedupe_key(user_id: str, family: str, event_key: str, now_utc: datetime) -> str:
    bucket = dedupe_bucket_start(now_utc, family)
    return f"{user_id}:{family}:{event_key}:{bucket.strftime('%Y-%m-%dT%H')}"


def build_deep_link(
    *,
    family: str,
    event_key: str,
    target_type: str,
    target_key: str,
    asof: str | None,
) -> str:
    query = urlencode(
        {
            "family": family,
            "event_key": event_key,
            "target_type": target_type,
            "target_key": target_key,
            "asof": asof or "",
        }
    )
    return f"gaiaeyes://mission-control?{query}"


def flare_class_rank(value: str | None) -> tuple[int, float]:
    if not value:
        return (-1, 0.0)
    text = value.strip().upper()
    if not text:
        return (-1, 0.0)
    band = text[:1]
    scale = {"A": 0, "B": 1, "C": 2, "M": 3, "X": 4}
    try:
        magnitude = float(text[1:] or "0")
    except Exception:
        magnitude = 0.0
    return (scale.get(band, -1), magnitude)


def gauge_zone(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 80:
        return "high"
    if value >= 60:
        return "elevated"
    if value >= 30:
        return "mild"
    return "low"


def previous_gauge_value(current: float | None, delta: int | float | None) -> float | None:
    if current is None or delta is None:
        return None
    return float(current) - float(delta)


def severity_escalated(previous: str | None, current: str) -> bool:
    return SEVERITY_RANK.get(current, 0) > SEVERITY_RANK.get(previous or "", 0)


def can_emit_with_cooldown(
    *,
    previous_created_at: datetime | None,
    previous_severity: str | None,
    family: str,
    current_severity: str,
    now_utc: datetime,
) -> bool:
    if not cooldown_active(previous_created_at, family, now_utc):
        return True
    return severity_escalated(previous_severity, current_severity)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
