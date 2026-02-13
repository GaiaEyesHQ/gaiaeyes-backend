from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.db import pg
from bots.triggers.config import COOLDOWNS, ESCALATION_ONLY, SEVERITY_RANK


logger = logging.getLogger(__name__)


def _coerce_day(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date()


def _parse_alerts(alerts_json: Any) -> List[Dict[str, Any]]:
    if alerts_json is None:
        return []
    if isinstance(alerts_json, str):
        try:
            alerts_json = json.loads(alerts_json)
        except Exception:
            return []
    if isinstance(alerts_json, list):
        return alerts_json
    return []


def _normalize_severity(value: Optional[str]) -> str:
    if not value:
        return "info"
    v = value.lower()
    if v in ("warn", "warning"):
        return "watch"
    if v in ("high", "critical"):
        return "high"
    if v in ("watch", "info"):
        return v
    return "info"


def _max_severity(alerts: List[Dict[str, Any]]) -> Optional[str]:
    if not alerts:
        return None
    best = "info"
    for a in alerts:
        sev = _normalize_severity(a.get("severity"))
        if SEVERITY_RANK.get(sev, 0) > SEVERITY_RANK.get(best, 0):
            best = sev
    return best


def _fetch_gauges_row(user_id: str, day: date) -> Optional[Dict[str, Any]]:
    return pg.fetchrow(
        """
        select alerts_json, health_status
          from marts.user_gauges_day
         where user_id = %s and day = %s
         limit 1
        """,
        user_id,
        day,
    )


def _fetch_trigger_state(user_id: str, trigger_key: str) -> Optional[Dict[str, Any]]:
    return pg.fetchrow(
        """
        select trigger_key, last_sent_at, last_severity
          from app.user_trigger_state
         where user_id = %s and trigger_key = %s
         limit 1
        """,
        user_id,
        trigger_key,
    )


def _should_send(state: Optional[Dict[str, Any]], severity: str, now: datetime) -> bool:
    if not state:
        return True
    prev_sev = _normalize_severity(state.get("last_severity"))
    if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(prev_sev, 0):
        return True
    last_sent = state.get("last_sent_at")
    if not last_sent:
        return True
    cooldown = COOLDOWNS.get(severity, timedelta(hours=6))
    if isinstance(last_sent, datetime):
        if now - last_sent >= cooldown:
            return True
    return not ESCALATION_ONLY


def _upsert_trigger_state(user_id: str, trigger_key: str, severity: str, now: datetime) -> None:
    pg.execute(
        """
        insert into app.user_trigger_state (user_id, trigger_key, last_sent_at, last_severity, updated_at)
        values (%s, %s, %s, %s, %s)
        on conflict (user_id, trigger_key) do update
           set last_sent_at = excluded.last_sent_at,
               last_severity = excluded.last_severity,
               updated_at = excluded.updated_at
        """,
        user_id,
        trigger_key,
        now,
        severity,
        now,
    )


def _dedupe_candidates(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for a in alerts:
        key = a.get("key")
        if not key:
            continue
        sev = _normalize_severity(a.get("severity"))
        existing = deduped.get(key)
        if not existing:
            deduped[key] = {**a, "severity": sev}
            continue
        if SEVERITY_RANK.get(sev, 0) > SEVERITY_RANK.get(existing.get("severity"), 0):
            deduped[key] = {**a, "severity": sev}
    return list(deduped.values())


def evaluate_user_triggers(user_id: str, day: str | date | None = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    day = _coerce_day(day)
    row = _fetch_gauges_row(user_id, day)
    if not row:
        return [], []
    alerts = _parse_alerts(row.get("alerts_json"))
    alerts = _dedupe_candidates(alerts)

    candidates = list(alerts)

    # Health + environment combo
    health_status = row.get("health_status")
    try:
        health_val = float(health_status) if health_status is not None else None
    except Exception:
        health_val = None

    env_alerts = [a for a in alerts if _normalize_severity(a.get("severity")) in ("watch", "high") and a.get("key") != "alert.health_calibrating"]
    if health_val is not None and health_val >= 70 and env_alerts:
        severity = "high" if health_val >= 85 else "watch"
        candidates.append(
            {
                "key": "alert.health_combo",
                "title": "Health + environment load",
                "severity": severity,
                "triggered_by": [{"signal_key": "health_status", "state": "elevated"}],
                "suggested_actions": ["slow down", "protect sleep window", "hydrate and pace"],
            }
        )

    now = datetime.now(timezone.utc)
    to_notify: List[Dict[str, Any]] = []
    for c in _dedupe_candidates(candidates):
        severity = _normalize_severity(c.get("severity"))
        if severity not in ("watch", "high"):
            continue
        state = _fetch_trigger_state(user_id, c.get("key"))
        if _should_send(state, severity, now):
            to_notify.append(c)
            _upsert_trigger_state(user_id, c.get("key"), severity, now)

    return alerts, to_notify
