#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from services.db import pg
from services.openai_models import resolve_openai_model
from bots.definitions.load_definition_base import load_definition_base
from bots.gauges.gauge_scorer import (
    fetch_local_payload,
    fetch_symptom_summary,
    fetch_user_tags,
    score_user_day,
)
from bots.gauges.signal_resolver import resolve_signals
from bots.gauges.db_utils import upsert_row
from services.mc_modals.modal_builder import earthscope_condition_note, earthscope_ranked_symptoms
from services.voice.earthscope_posts import build_member_earthscope_semantic, render_member_earthscope_post

try:
    from openai import OpenAI
    HAVE_OPENAI = True
except Exception:
    HAVE_OPENAI = False


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def _coerce_day(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date()


def _hash_inputs(snapshot: Dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _refresh_bucket_key(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    minute_bucket = (current.minute // 15) * 15
    snapped = current.replace(minute=minute_bucket, second=0, microsecond=0)
    return snapped.isoformat()


def _rotating_template(options: List[str], *, user_id: str, bucket_key: str, driver_family: str, slot: str) -> str:
    values = [item for item in options if item]
    if not values:
        return ""
    seed = f"{user_id}|{bucket_key}|{driver_family}|{slot}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    index = int(digest[:8], 16) % len(values)
    return values[index]


def _parse_json_value(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _fetch_paid_users() -> List[str]:
    keys = [k.strip() for k in os.getenv("ENTITLEMENT_KEYS", "plus,pro").split(",") if k.strip()]
    try:
        rows = pg.fetch(
            """
            select distinct user_id
              from public.app_user_entitlements_active
             where is_active = true
               and entitlement_key = any(%s)
            """,
            keys,
        )
        return [r["user_id"] for r in rows if r.get("user_id")]
    except Exception as exc:
        logger.warning("[member] entitlements lookup failed: %s", exc)
        return []


def _fetch_gauges_row(user_id: str, day: date) -> Optional[Dict[str, Any]]:
    return pg.fetchrow(
        """
        select *
          from marts.user_gauges_day
         where user_id = %s and day = %s
         limit 1
        """,
        user_id,
        day,
    )


def _fetch_existing_inputs_hash(user_id: str, day: date) -> Optional[str]:
    row = pg.fetchrow(
        """
        select inputs_hash
          from content.daily_posts_user
         where user_id = %s and day = %s and platform = 'member'
         limit 1
        """,
        user_id,
        day,
    )
    return row.get("inputs_hash") if row else None


def _fetch_existing_member_post(user_id: str, day: date) -> Optional[Dict[str, Any]]:
    return pg.fetchrow(
        """
        select title, caption, body_markdown, updated_at
          from content.daily_posts_user
         where user_id = %s and day = %s and platform = 'member'
         limit 1
        """,
        user_id,
        day,
    )


def _highlight_gauges(definition: Dict[str, Any], gauges: Dict[str, Any]) -> List[Dict[str, Any]]:
    thresholds = (definition.get("normalization") or {}).get("alert_thresholds") or {}
    info = float(thresholds.get("info", 55))
    watch = float(thresholds.get("watch", 70))
    high = float(thresholds.get("high", 85))

    labeled = []
    for g in definition.get("gauges") or []:
        key = g.get("key")
        if not key:
            continue
        value = gauges.get(key)
        if value is None:
            continue
        severity = "info"
        if value >= high:
            severity = "high"
        elif value >= watch:
            severity = "watch"
        elif value >= info:
            severity = "info"
        labeled.append({"key": key, "label": g.get("label") or key, "value": value, "severity": severity})

    labeled.sort(key=lambda x: x["value"], reverse=True)
    return labeled[:4]


def _health_status_line(value: Optional[Any], *, include_value: bool = False) -> str:
    if value is None:
        return "Health Status: calibrating"
    try:
        v = float(value)
    except Exception:
        return "Health Status: calibrating"
    label = "very low strain"
    if v >= 86:
        label = "very high strain"
    elif v >= 71:
        label = "high strain"
    elif v >= 41:
        label = "moderate strain"
    elif v >= 21:
        label = "low strain"
    if include_value:
        return f"Health Status: {int(round(v, 0))} ({label})"
    return f"Health Status: {label}"


def _default_actions(alerts: List[Dict[str, Any]]) -> List[str]:
    actions = []
    for alert in alerts or []:
        for a in alert.get("suggested_actions") or []:
            if a not in actions:
                actions.append(a)
    if actions:
        return actions[:5]
    return [
        "hydrate steadily and pace your workload",
        "work in short focused blocks with brief resets",
        "add gentle movement every 60–90 minutes",
        "protect your evening wind-down and sleep window",
        "keep late caffeine and extra stimulation lighter",
    ]


def _state_rank(state: str) -> int:
    ranks = {
        "watch": 1,
        "moderate": 2,
        "elevated": 2,
        "active": 2,
        "high": 3,
        "strong": 3,
        "storm": 3,
        "usg": 3,
        "very_high": 4,
        "unhealthy": 4,
    }
    return ranks.get(state.lower().strip(), 0)


def _state_label(state: str) -> str:
    labels = {
        "watch": "Watch",
        "moderate": "Moderate",
        "elevated": "Elevated",
        "active": "Active",
        "high": "High",
        "strong": "Strong",
        "storm": "Storm",
        "very_high": "Very high",
        "usg": "USG",
        "unhealthy": "Unhealthy",
    }
    key = state.lower().strip()
    if key in labels:
        return labels[key]
    cleaned = key.replace("_", " ").strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "Active"


def _active_state_lines(active_states: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    seen: set[str] = set()

    pressure_windows: List[str] = []
    pressure_state = ""
    pressure_delta_12h: Optional[float] = None
    pressure_delta_24h: Optional[float] = None

    solar_state = ""
    solar_speed: Optional[float] = None

    aqi_state = ""
    aqi_value: Optional[float] = None

    def _push(line: str) -> None:
        clean = line.strip()
        if not clean:
            return
        key = clean.lower()
        if key in seen:
            return
        seen.add(key)
        lines.append(clean)

    for state in active_states[:8]:
        signal_key = str(state.get("signal_key") or "").strip()
        state_name = str(state.get("state") or "active").strip()
        value = state.get("value")

        if signal_key == "earthweather.pressure_swing_12h":
            pressure_windows.append("12h")
            if _state_rank(state_name) > _state_rank(pressure_state):
                pressure_state = state_name
            try:
                parsed = float(value) if value is not None else None
            except Exception:
                parsed = None
            if parsed is not None:
                pressure_delta_12h = parsed
            continue
        if signal_key == "earthweather.pressure_swing_24h_big":
            pressure_windows.append("24h")
            if _state_rank(state_name) > _state_rank(pressure_state):
                pressure_state = state_name
            try:
                parsed = float(value) if value is not None else None
            except Exception:
                parsed = None
            if parsed is not None:
                pressure_delta_24h = parsed
            continue
        if signal_key == "spaceweather.sw_speed":
            if _state_rank(state_name) > _state_rank(solar_state):
                solar_state = state_name
            try:
                parsed = float(value) if value is not None else None
            except Exception:
                parsed = None
            if parsed is not None:
                solar_speed = max(solar_speed or parsed, parsed)
            continue
        if signal_key == "earthweather.air_quality":
            if _state_rank(state_name) > _state_rank(aqi_state):
                aqi_state = state_name
            try:
                parsed = float(value) if value is not None else None
            except Exception:
                parsed = None
            if parsed is not None:
                aqi_value = parsed
            continue
        if signal_key == "earthweather.temp_swing_24h":
            if value is None:
                _push(f"Temperature swing: {_state_label(state_name)} (24h)")
            else:
                try:
                    _push(f"Temperature swing: {_state_label(state_name)} (24h, {float(value):+.1f} C)")
                except Exception:
                    _push(f"Temperature swing: {_state_label(state_name)} (24h, {value})")
            continue
        if signal_key == "earthweather.pressure_drop_3h":
            _push(f"Rapid pressure drop: {_state_label(state_name)} (3h)")
            continue
        if signal_key == "schumann.variability_24h":
            _push("Schumann variability: Elevated (24h)")
            continue

        signal = signal_key.replace("_", " ").replace(".", " ").strip().title() or "Signal"
        if value is None:
            _push(f"{signal}: {_state_label(state_name)}")
        else:
            try:
                _push(f"{signal}: {_state_label(state_name)} ({float(value):.1f})")
            except Exception:
                _push(f"{signal}: {_state_label(state_name)} ({value})")

    if pressure_windows:
        ordered = sorted(set(pressure_windows), key=lambda window: 0 if window == "12h" else 1)
        pressure_line = f"Pressure swing: {_state_label(pressure_state or 'elevated')} ({', '.join(ordered)})"
        delta_value = pressure_delta_24h if pressure_delta_24h is not None else pressure_delta_12h
        if delta_value is not None:
            delta_label = "Δ24h" if pressure_delta_24h is not None else "Δ12h"
            pressure_line += f" ({delta_label} {delta_value:+.1f} hPa)"
        _push(pressure_line)

    if solar_state:
        if solar_speed is None:
            _push(f"Solar wind: {_state_label(solar_state)}")
        else:
            _push(f"Solar wind: {_state_label(solar_state)} ({int(round(solar_speed, 0))} km/s)")

    if aqi_state:
        aqi_label = "Moderate" if aqi_state.lower() == "moderate" else _state_label(aqi_state)
        if aqi_value is None:
            _push(f"AQI: {aqi_label}")
        else:
            _push(f"AQI: {aqi_label} ({int(round(aqi_value, 0))})")

    return lines


def _local_context_lines(local_payload: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(local_payload, dict):
        return []
    lines: List[str] = []
    health = local_payload.get("health") if isinstance(local_payload.get("health"), dict) else {}
    flags = health.get("flags") if isinstance(health.get("flags"), dict) else {}

    messages = health.get("messages") if isinstance(health.get("messages"), list) else []
    for msg in messages[:2]:
        if isinstance(msg, str) and msg.strip():
            lines.append(msg.strip())
    moon_sensitivity = flags.get("moon_sensitivity")
    if isinstance(moon_sensitivity, str) and moon_sensitivity.strip():
        lines.append(f"Lunar context: {moon_sensitivity.strip()} phase sensitivity window.")

    return lines


def _observed_driver_lines(
    active_states: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    local_payload: Optional[Dict[str, Any]],
) -> List[str]:
    lines: List[str] = []
    seen: set[str] = set()

    def _normalize_phrase(value: str) -> str:
        text = str(value or "").lower()
        text = re.sub(r"\([^)]*\)", " ", text)
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _append(line: str) -> None:
        clean = line.strip()
        if not clean:
            return
        key = clean.lower()
        if key in seen:
            return
        seen.add(key)
        lines.append(clean)

    for line in _active_state_lines(active_states):
        _append(line)
    for line in _local_context_lines(local_payload):
        _append(line)

    for alert in alerts[:3]:
        title = str(alert.get("title") or alert.get("key") or "").strip()
        severity = str(alert.get("severity") or "").strip()
        if not title:
            continue
        normalized_title = _normalize_phrase(title)
        if any(
            normalized_title and normalized_title in _normalize_phrase(existing)
            for existing in lines
        ):
            continue
        if severity:
            _append(f"{title} ({severity}).")
        else:
            _append(f"{title}.")

    if not lines:
        lines.append("No major external drivers are flagged right now.")
    return lines[:5]


def _join_labels(labels: List[str]) -> str:
    cleaned = [str(x).strip() for x in labels if str(x).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _member_post_requires_refresh(post: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(post, dict):
        return False
    body = str(post.get("body_markdown") or "")
    title = str(post.get("title") or "")
    legacy_markers = [
        "## Today’s Check-in",
        "## Summary Note",
        "Cosmic note:",
        "most noticeable changes since yesterday",
        "today's drivers",
    ]
    if any(marker.lower() in body.lower() for marker in legacy_markers):
        return True
    return bool(re.search(r"\s+—\s+\d{4}-\d{2}-\d{2}$", title))


_MEMBER_DRIVER_LABELS = {
    "pressure": "Pressure Swing",
    "temp": "Temperature Swing",
    "aqi": "Air Quality",
    "kp": "Kp Index",
    "bz": "Bz Coupling",
    "sw": "Solar Wind",
    "schumann": "Schumann Variability",
}


def _member_driver_key_from_signal(signal_key: str) -> str:
    key = str(signal_key or "").strip().lower()
    if key in {"earthweather.pressure_swing_12h", "earthweather.pressure_swing_24h_big", "earthweather.pressure_drop_3h"}:
        return "pressure"
    if key == "earthweather.temp_swing_24h":
        return "temp"
    if key == "earthweather.air_quality":
        return "aqi"
    if key == "spaceweather.kp":
        return "kp"
    if key == "spaceweather.bz_coupling":
        return "bz"
    if key == "spaceweather.sw_speed":
        return "sw"
    if key == "schumann.variability_24h":
        return "schumann"
    return ""


def _member_driver_key_from_alert(title: str) -> str:
    text = str(title or "").strip().lower()
    if "pressure" in text:
        return "pressure"
    if "temperature" in text or "temp" in text:
        return "temp"
    if "air quality" in text or "aqi" in text:
        return "aqi"
    if "solar wind" in text:
        return "sw"
    if "bz" in text:
        return "bz"
    if "kp" in text or "geomagnetic" in text:
        return "kp"
    if "schumann" in text:
        return "schumann"
    return ""


def _normalized_member_drivers(active_states: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    family_priority = {"pressure": 0, "sw": 1, "aqi": 2, "kp": 3, "bz": 4, "temp": 5, "schumann": 6}
    best_by_key: Dict[str, Dict[str, Any]] = {}

    def _score(key: str, severity: str, has_value: bool) -> tuple[int, int, int]:
        return (_state_rank(severity), 1 if has_value else 0, -family_priority.get(key, 99))

    for state in active_states or []:
        key = _member_driver_key_from_signal(str(state.get("signal_key") or ""))
        if not key:
            continue
        severity = str(state.get("state") or "active").strip() or "active"
        candidate = {
            "key": key,
            "label": _MEMBER_DRIVER_LABELS.get(key, key.replace("_", " ").title()),
            "severity": severity.lower(),
            "state": _state_label(severity),
            "score": _score(key, severity, state.get("value") is not None),
        }
        existing = best_by_key.get(key)
        if not existing or candidate["score"] > existing["score"]:
            best_by_key[key] = candidate

    for alert in alerts or []:
        key = _member_driver_key_from_alert(str(alert.get("title") or alert.get("key") or ""))
        if not key:
            continue
        severity = str(alert.get("severity") or "active").strip() or "active"
        candidate = {
            "key": key,
            "label": _MEMBER_DRIVER_LABELS.get(key, key.replace("_", " ").title()),
            "severity": severity.lower(),
            "state": _state_label(severity),
            "score": _score(key, severity, False),
        }
        existing = best_by_key.get(key)
        if not existing or candidate["score"] > existing["score"]:
            best_by_key[key] = candidate

    return sorted(best_by_key.values(), key=lambda item: item["score"], reverse=True)


def _lead_state_text(driver: Dict[str, Any]) -> str:
    state = str(driver.get("state") or "").strip().lower()
    if not state:
        return "still active"
    if str(driver.get("key") or "") == "aqi":
        return f"at {state} levels"
    return f"still {state}"


def _lead_now_line(*, user_id: str, bucket_key: str, drivers: List[Dict[str, Any]]) -> str:
    if not drivers:
        return _rotating_template(
            [
                "Right now, the outside signal mix looks fairly even, with no single driver taking over.",
                "At the moment, the environmental mix is quieter, with no strong leader.",
                "Currently, the broader signal picture looks mixed and relatively light.",
                "For now, no single outside driver is pulling especially hard.",
                "Right now, the external context looks balanced, without one clear lead.",
            ],
            user_id=user_id,
            bucket_key=bucket_key,
            driver_family="mixed",
            slot="lead-fallback",
        )

    primary = drivers[0]
    secondary_clause = ""
    if len(drivers) > 1:
        secondary = drivers[1]
        secondary_clause = f", while {secondary['label']} stays {str(secondary.get('state') or '').strip().lower() or 'active'}"

    template = _rotating_template(
        [
            "{label} is setting the pace right now, {state_text}{secondary_clause}.",
            "Right now, {label} is carrying the most weight, {state_text}{secondary_clause}.",
            "At the moment, {label} is the clearest influence, {state_text}{secondary_clause}.",
            "Currently, {label} is leading the mix, {state_text}{secondary_clause}.",
            "For now, {label} is doing more of the talking, {state_text}{secondary_clause}.",
            "Right now, {label} is out front, {state_text}{secondary_clause}.",
            "At the moment, {label} is the main thing to watch, {state_text}{secondary_clause}.",
            "Currently, {label} is the strongest external pull, {state_text}{secondary_clause}.",
        ],
        user_id=user_id,
        bucket_key=bucket_key,
        driver_family=str(primary.get("key") or "mixed"),
        slot="lead",
    )
    return template.format(label=primary["label"], state_text=_lead_state_text(primary), secondary_clause=secondary_clause)


def _health_status_now_sentence(value: Optional[Any], highlights: List[Dict[str, Any]]) -> str:
    try:
        strain = float(value) if value is not None else None
    except Exception:
        strain = None

    if strain is None:
        base = "Body load is still calibrating right now."
    elif strain >= 86:
        base = "Body load looks very high right now."
    elif strain >= 71:
        base = "Body load looks high right now."
    elif strain >= 41:
        base = "Body load looks moderate right now."
    elif strain >= 21:
        base = "Body load looks low right now."
    else:
        base = "Body load looks very low right now."

    labels = [str(item.get("label") or "").strip() for item in highlights[:2] if str(item.get("label") or "").strip()]
    if len(labels) == 1:
        return f"{base} {labels[0]} is the gauge worth watching most closely."
    if len(labels) >= 2:
        return f"{base} {_join_labels(labels)} are the gauges worth watching most closely."
    return f"{base} Most gauges are still sitting in lower zones."


def _what_you_may_feel(
    *,
    ranked_symptoms: List[Dict[str, Any]],
    condition_note: Optional[str],
) -> str:
    phrases = [str(item.get("phrase") or "").strip() for item in ranked_symptoms if str(item.get("phrase") or "").strip()]
    lines: List[str] = []
    if phrases:
        lines.append(
            f"Based on the current drivers and your gauges, the strongest possibilities right now are {_join_labels(phrases)}."
        )
    else:
        lines.append("Based on the current drivers and your gauges, the main shifts still look fairly light right now.")
    if condition_note:
        lines.append(condition_note)
    lines.append(
        "These are possibilities, not certainties. If something stands out, log it in the symptom tracker so your personal pattern gets sharper over time."
    )
    return " ".join(lines)


def _render_trigger_advisory(trigger_events: List[Dict[str, Any]], health_status: Optional[Any]) -> str:
    lines = []
    if health_status is not None:
        lines.append(_health_status_line(health_status, include_value=True))
    lines.append("Recent trigger(s):")
    for ev in trigger_events:
        title = ev.get("title") or ev.get("key")
        sev = ev.get("severity")
        lines.append(f"- {title} ({sev})")
    actions = []
    for ev in trigger_events:
        for a in ev.get("suggested_actions") or []:
            if a not in actions:
                actions.append(a)
    if actions:
        lines.append("")
        lines.append("Supportive actions:")
        for a in actions[:5]:
            lines.append(f"- {a}")
    return "\n".join(lines)


def _render_member_post(
    user_id: str,
    bucket_key: str,
    definition: Dict[str, Any],
    gauges_row: Dict[str, Any],
    active_states: List[Dict[str, Any]],
    local_payload: Optional[Dict[str, Any]],
    tags: List[Dict[str, Any]],
    symptoms: Dict[str, Any],
    trend: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    highlights = _highlight_gauges(definition, gauges_row)
    alerts = gauges_row.get("alerts_json") or []
    normalized_drivers = _normalized_member_drivers(active_states, alerts)
    actions = _default_actions(alerts)
    ranked_symptoms = earthscope_ranked_symptoms(
        gauge_keys=[item.get("key") for item in highlights],
        drivers=normalized_drivers,
        user_tags=tags,
        limit=3,
    )
    condition_note = earthscope_condition_note(ranked_symptoms=ranked_symptoms, user_tags=tags)

    hook = _lead_now_line(
        user_id=user_id,
        bucket_key=bucket_key,
        drivers=normalized_drivers,
    )
    now_text = f"{hook} {_health_status_now_sentence(gauges_row.get('health_status'), highlights)}".strip()

    all_driver_lines = _observed_driver_lines(active_states, alerts, local_payload)
    summary = _what_you_may_feel(ranked_symptoms=ranked_symptoms, condition_note=condition_note)

    disclaimer = definition.get("global_disclaimer") or ""
    semantic = build_member_earthscope_semantic(
        day=_coerce_day(gauges_row.get("day")),
        health_status=gauges_row.get("health_status"),
        highlights=highlights,
        drivers=normalized_drivers,
        driver_lines=all_driver_lines,
        ranked_symptoms=ranked_symptoms,
        condition_note=condition_note,
        actions=actions,
        disclaimer=disclaimer,
        seed_now_text=now_text,
        seed_summary=summary,
        title="Your EarthScope",
        caption=None,
    )
    rendered = render_member_earthscope_post(semantic)
    rendered["voice_semantic"] = semantic.to_dict()
    return rendered


def _render_with_openai(
    definition: Dict[str, Any],
    gauges_row: Dict[str, Any],
    active_states: List[Dict[str, Any]],
    trend: Optional[Dict[str, Any]],
    deterministic: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not (HAVE_OPENAI and api_key):
        return None

    client = OpenAI(api_key=api_key)
    model = resolve_openai_model("member_writer")
    if not model:
        logger.warning("[member] model not configured; using deterministic fallback.")
        return None

    def _trend_for_prompt(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not raw:
            return {}
        gauges = raw.get("gauges") or {}
        deltas: Dict[str, Any] = {}
        for key, item in gauges.items():
            if not isinstance(item, dict):
                continue
            if "delta" in item:
                deltas[key] = item.get("delta")
        out: Dict[str, Any] = {"deltas": deltas}
        if raw.get("baseline_day"):
            out["baseline_day"] = raw.get("baseline_day")
        return out

    trend_for_prompt = _trend_for_prompt(trend)
    has_trend = bool(trend_for_prompt.get("deltas"))

    def _mentions_comparison(text: str) -> bool:
        lowered = (text or "").lower()
        phrases = [
            "up from",
            "down from",
            "compared to",
            "higher than",
            "lower than",
            "rose from",
            "fell from",
        ]
        return any(p in lowered for p in phrases)

    def _word_count(text: str) -> int:
        return len([w for w in str(text or "").strip().split() if w])

    def _ensure_health_line(body: str, health_line: str) -> str:
        if not health_line:
            return body
        lines = body.splitlines()
        for idx, line in enumerate(lines):
            if "health status" in line.lower():
                stripped = line.lstrip()
                prefix = ""
                if stripped.startswith(("-", "*", "•")):
                    prefix = f"{line[:len(line) - len(stripped)]}{stripped[0]} "
                lines[idx] = f"{prefix}{health_line}"
                if idx + 1 < len(lines) and lines[idx + 1].strip() != "":
                    lines.insert(idx + 1, "")
                return "\n".join(lines)
        health_bullet = f"- {health_line}"
        if "## Today’s Check-in" in body:
            before, after = body.split("## Today’s Check-in", 1)
            after = after.lstrip("\n")
            return f"{before}## Today’s Check-in\n{health_bullet}\n\n{after}"
        if "## Disclaimer" in body:
            return body.replace("## Disclaimer", f"{health_bullet}\n\n## Disclaimer", 1)
        return f"{body}\n\n{health_bullet}"

    def _extract_section(body: str, heading: str) -> str:
        marker = f"## {heading}"
        idx = body.find(marker)
        if idx < 0:
            return ""
        rest = body[idx + len(marker):]
        next_idx = rest.find("\n## ")
        if next_idx >= 0:
            rest = rest[:next_idx]
        return rest.strip().lower()

    def _drivers_reference_observed_signals(body: str, states: List[Dict[str, Any]]) -> bool:
        drivers = _extract_section(body, "Drivers")
        if not drivers:
            return False
        token_map = {
            "earthweather.air_quality": ["aqi", "air quality"],
            "spaceweather.sw_speed": ["solar wind", "km/s", "wind speed"],
            "earthweather.temp_swing_24h": ["temperature", "24-hour", "24h", "swing"],
            "schumann.variability_24h": ["schumann"],
            "spaceweather.kp": ["kp", "geomagnetic"],
            "spaceweather.bz_coupling": ["bz", "magnetic field"],
        }
        wanted: List[List[str]] = []
        for st in states[:4]:
            key = str(st.get("signal_key") or "")
            if key in token_map:
                wanted.append(token_map[key])
        if not wanted:
            return True
        hits = 0
        for options in wanted:
            if any(tok in drivers for tok in options):
                hits += 1
        needed = 1 if len(wanted) == 1 else min(2, len(wanted))
        return hits >= needed

    def _has_required_sections(body: str) -> bool:
        if "## Today’s Check-in" not in body:
            return False
        if "## Drivers" not in body:
            return False
        if "## Summary Note" not in body:
            return False
        if "## Supportive Actions" not in body:
            return False
        if "## Disclaimer" not in body:
            return False
        return "## Your Gauges Today" not in body

    def _drivers_within_allowed(body: str, allowed_lines: List[str]) -> bool:
        drivers = _extract_section(body, "Drivers")
        if not drivers:
            return False
        allowed_text = " ".join((allowed_lines or [])).lower()
        domain_terms = [
            "temperature",
            "temp",
            "barometric",
            "pressure",
            "aqi",
            "air quality",
            "solar wind",
            "km/s",
            "schumann",
            "kp",
            "geomagnetic",
            "bz",
            "aurora",
            "lunar",
            "moon",
        ]
        for term in domain_terms:
            if term in drivers and term not in allowed_text:
                return False
        if "no major external drivers are flagged right now" in allowed_text:
            if any(term in drivers for term in domain_terms):
                return False
        return True

    health_line = _health_status_line(gauges_row.get("health_status"))
    draft_body = str(deterministic.get("body_markdown") or "").strip()
    driver_lines = deterministic.get("driver_lines") or []
    actions = deterministic.get("actions") or []

    for attempt in range(2):
        strict = attempt == 1
        prompt = {
            "task": "Rewrite this deterministic EarthScope draft in a human, warm tone.",
            "format": "Return strict JSON with keys: title, caption, body_markdown.",
            "voice": "grounded, practical, lightly witty, never alarmist",
            "rules": [
                "Preserve facts exactly. Do not add any new facts.",
                "Keep headings: ## Today’s Check-in, ## Drivers, ## Summary Note, ## Supportive Actions, ## Disclaimer.",
                "Keep the Health Status line and leave a blank line after it.",
                "Use at most one light, non-sarcastic humor line.",
                "Do not invent environmental drivers.",
                "Only mention changes if trend.deltas includes that gauge.",
                "If trend.deltas is empty, avoid comparisons.",
                "Use only the provided drivers and actions; no extra driver claims.",
                "Keep content substantial (roughly 120-220 words total) and do not collapse into one-liners.",
            ] + (["STRICT MODE: If unsure, keep original draft wording."] if strict else []),
            "data": {
                "trend": trend_for_prompt,
                "active_states": active_states,
                "allowed_driver_lines": driver_lines,
                "allowed_actions": actions,
                "health_line": health_line,
                "disclaimer": definition.get("global_disclaimer"),
                "draft_title": deterministic.get("title"),
                "draft_caption": deterministic.get("caption"),
                "draft_body_markdown": draft_body,
            },
        }

        try:
            resp = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "You are Gaia Eyes’ member EarthScope editor. Rewrite for tone only; preserve facts.",
                    },
                    {"role": "user", "content": json.dumps(prompt, default=str)},
                ],
            )
            obj = json.loads(resp.choices[0].message.content)
            if not all(k in obj for k in ("title", "caption", "body_markdown")):
                continue
            body = str(obj.get("body_markdown") or "").strip()
            if _word_count(body) < 110:
                logger.warning("[member] OpenAI rewrite too short; retrying (attempt %s).", attempt + 1)
                continue
            if not has_trend and _mentions_comparison(body):
                logger.warning("[member] OpenAI rewrite used comparisons without trend data (attempt %s).", attempt + 1)
                continue
            if not _has_required_sections(body):
                logger.warning("[member] OpenAI rewrite missing required sections (attempt %s).", attempt + 1)
                continue
            if not _drivers_reference_observed_signals(body, active_states):
                logger.warning("[member] OpenAI rewrite drivers do not reference observed signals (attempt %s).", attempt + 1)
                continue
            if not _drivers_within_allowed(body, driver_lines):
                logger.warning("[member] OpenAI rewrite introduced non-allowed driver claims (attempt %s).", attempt + 1)
                continue
            body = _ensure_health_line(body, health_line)
            return {
                "title": str(obj.get("title") or deterministic.get("title") or "").strip(),
                "caption": str(obj.get("caption") or deterministic.get("caption") or "").strip(),
                "body_markdown": body,
            }
        except Exception as exc:
            logger.warning("[member] OpenAI rewrite failed (attempt %s): %s", attempt + 1, exc)

    return None


def generate_member_post_for_user(
    user_id: str,
    day: str | date | None = None,
    *,
    force: bool = False,
    trigger_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    definition, version = load_definition_base()
    day = _coerce_day(day)

    gauges_row = _fetch_gauges_row(user_id, day)
    if not gauges_row:
        score_user_day(user_id, day, force=True)
        gauges_row = _fetch_gauges_row(user_id, day)
        if not gauges_row:
            return {"ok": False, "error": "gauges unavailable"}

    local_payload = fetch_local_payload(user_id, day)
    active_states = resolve_signals(user_id, day, local_payload=local_payload, definition=definition)
    tags = fetch_user_tags(user_id)
    symptoms = fetch_symptom_summary(user_id, day)
    trend = _parse_json_value(gauges_row.get("trend_json"))

    inputs_snapshot = {
        "definition_version": version,
        "day": day.isoformat(),
        "gauges": {k: gauges_row.get(k) for k in ["pain", "focus", "heart", "stamina", "energy", "sleep", "mood", "health_status"]},
        "alerts": gauges_row.get("alerts_json"),
        "trend": trend or {},
        "active_states": active_states,
        "local_payload": local_payload,
        "tags": tags,
        "symptoms": symptoms,
        "trigger_events": trigger_events or [],
    }
    refresh_bucket = _refresh_bucket_key()
    inputs_snapshot["refresh_bucket"] = refresh_bucket
    inputs_hash = _hash_inputs(inputs_snapshot)

    existing = _fetch_existing_member_post(user_id, day)
    existing_hash = _fetch_existing_inputs_hash(user_id, day)
    if existing_hash == inputs_hash and not force and not _member_post_requires_refresh(existing):
        return {"ok": True, "skipped": True}

    if _member_post_requires_refresh(existing):
        existing = None

    deterministic = _render_member_post(
        user_id,
        refresh_bucket,
        definition,
        gauges_row,
        active_states,
        local_payload,
        tags,
        symptoms,
        trend,
    )
    rendered: Optional[Dict[str, Any]] = None
    if not trigger_events:
        rendered = deterministic
    else:
        # Triggered advisory: append to existing post if present
        if existing and existing.get("body_markdown"):
            rendered = {
                "title": deterministic.get("title"),
                "caption": deterministic.get("caption"),
                "body_markdown": existing.get("body_markdown"),
            }
        else:
            rendered = deterministic

        advisory = _render_trigger_advisory(trigger_events, gauges_row.get("health_status"))
        rendered["body_markdown"] = f"{rendered.get('body_markdown')}\n\n## Triggered Advisory\n{advisory}\n"

    metrics_payload = dict(inputs_snapshot)
    if rendered.get("voice_semantic"):
        metrics_payload["voice_semantic"] = rendered.get("voice_semantic")

    payload = {
        "user_id": user_id,
        "day": day,
        "platform": "member",
        "title": rendered.get("title"),
        "caption": rendered.get("caption"),
        "body_markdown": rendered.get("body_markdown"),
        "metrics_json": json.dumps(metrics_payload),
        "sources_json": json.dumps({}),
        "inputs_hash": inputs_hash,
        "updated_at": datetime.now(timezone.utc),
    }

    upsert_row("content", "daily_posts_user", payload, ["user_id", "day", "platform"])
    return {"ok": True, "skipped": False}


def run_for_user(
    user_id: str,
    day: str | date | None = None,
    *,
    trigger_events: Optional[List[Dict[str, Any]]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    return generate_member_post_for_user(user_id, day, force=force, trigger_events=trigger_events)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate member EarthScope posts.")
    parser.add_argument("--day", default=None, help="Day in YYYY-MM-DD (UTC).")
    parser.add_argument("--user-id", default=None, help="Single user_id override.")
    parser.add_argument("--limit", type=int, default=None, help="Limit user count.")
    parser.add_argument("--force", action="store_true", help="Recompute even if inputs_hash matches.")
    args = parser.parse_args()

    day = _coerce_day(args.day)
    if args.user_id:
        users = [args.user_id]
    else:
        users = _fetch_paid_users()

    if args.limit:
        users = users[: args.limit]

    logger.info("[member] users=%d day=%s", len(users), day)
    for uid in users:
        try:
            result = generate_member_post_for_user(uid, day, force=args.force)
            logger.info("[member] user=%s ok=%s skipped=%s", uid, result.get("ok"), result.get("skipped"))
        except Exception as exc:
            logger.exception("[member] user=%s failed: %s", uid, exc)


if __name__ == "__main__":
    main()
