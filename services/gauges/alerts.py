from __future__ import annotations

from typing import Any, Dict, List


_SEVERITY_RANK = {"info": 1, "watch": 2, "high": 3}


def _family_for_alert(alert: Dict[str, Any]) -> str:
    key = str(alert.get("key") or "").lower()
    title = str(alert.get("title") or "").lower()
    merged = f"{key} {title}"

    if "pressure" in merged:
        return "pressure"
    if "solar_wind" in merged or "solar wind" in merged or "sw_speed" in merged:
        return "solar_wind"
    if "air_quality" in merged or "air quality" in merged or "aqi" in merged:
        return "aqi"
    if "geomagnetic" in merged or "bz_coupling" in merged or "bz " in merged:
        return "geomagnetic"
    return key or title or "misc"


def _specificity(alert: Dict[str, Any]) -> int:
    score = 0
    triggered = alert.get("triggered_by")
    if isinstance(triggered, list):
        score += len(triggered) + (2 if triggered else 0)
        for item in triggered:
            if isinstance(item, dict) and item.get("value") is not None:
                score += 1
    actions = alert.get("suggested_actions")
    if isinstance(actions, list) and actions:
        score += 1
    return score


def dedupe_alert_pills(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(alerts, list):
        return []

    winners: Dict[str, tuple[int, int, int, Dict[str, Any]]] = {}
    for index, alert in enumerate(alerts):
        if not isinstance(alert, dict):
            continue
        family = _family_for_alert(alert)
        severity = _SEVERITY_RANK.get(str(alert.get("severity") or "").lower(), 0)
        specificity = _specificity(alert)
        candidate = (severity, specificity, -index, alert)
        current = winners.get(family)
        if current is None or candidate[:3] > current[:3]:
            winners[family] = candidate

    selected = list(winners.values())
    selected.sort(key=lambda item: (-item[0], item[2]))
    return [item[3] for item in selected]
