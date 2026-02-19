#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
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


def _light_wit_line(alerts: List[Dict[str, Any]]) -> str:
    if alerts:
        return "Cosmic note: today is a trim-tabs day, not a full-throttle day."
    return "Cosmic note: even calm days run better with a little maintenance."


def _active_state_lines(active_states: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for state in active_states[:4]:
        signal_key = str(state.get("signal_key") or "")
        state_name = str(state.get("state") or "active")
        value = state.get("value")
        if signal_key == "earthweather.air_quality":
            if value is None:
                lines.append(f"Air quality is {state_name}.")
            else:
                try:
                    lines.append(f"Air quality is {state_name} (AQI {int(round(float(value), 0))}).")
                except Exception:
                    lines.append(f"Air quality is {state_name} (AQI {value}).")
            continue
        if signal_key == "spaceweather.sw_speed":
            if value is None:
                lines.append(f"Solar wind speed is {state_name}.")
            else:
                try:
                    lines.append(f"Solar wind speed is {state_name} ({int(round(float(value), 0))} km/s).")
                except Exception:
                    lines.append(f"Solar wind speed is {state_name} ({value}).")
            continue
        if signal_key == "earthweather.temp_swing_24h":
            if value is None:
                lines.append(f"24-hour temperature swing is {state_name}.")
            else:
                try:
                    lines.append(f"24-hour temperature swing is {state_name} ({float(value):+.1f} C).")
                except Exception:
                    lines.append(f"24-hour temperature swing is {state_name} ({value}).")
            continue
        if signal_key == "schumann.variability_24h":
            lines.append("Schumann variability is elevated compared with recent baseline.")
            continue

        signal = signal_key.replace("_", " ").replace(".", " ").strip()
        if value is None:
            lines.append(f"{signal.title() or 'Signal'} is {state_name}.")
        else:
            try:
                numeric = float(value)
                lines.append(f"{signal.title() or 'Signal'} is {state_name} ({numeric:.1f}).")
            except Exception:
                lines.append(f"{signal.title() or 'Signal'} is {state_name} ({value}).")
    return lines


def _local_context_lines(local_payload: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(local_payload, dict):
        return []
    lines: List[str] = []
    weather = local_payload.get("weather") if isinstance(local_payload.get("weather"), dict) else {}
    air = local_payload.get("air") if isinstance(local_payload.get("air"), dict) else {}

    health = local_payload.get("health") if isinstance(local_payload.get("health"), dict) else {}
    flags = health.get("flags") if isinstance(health.get("flags"), dict) else {}

    # Only include local weather/air in drivers when flagged as elevated.
    temp_delta = weather.get("temp_delta_24h_c")
    if flags.get("big_temp_shift_24h") and isinstance(temp_delta, (int, float)):
        lines.append(f"24-hour temperature swing is notable ({float(temp_delta):+.1f} C).")

    baro_delta = weather.get("baro_delta_24h_hpa")
    if flags.get("pressure_rapid_drop") and isinstance(baro_delta, (int, float)):
        lines.append(f"Barometric pressure is dropping quickly ({float(baro_delta):+.1f} hPa / 24h).")

    aqi = air.get("aqi")
    category = air.get("category")
    try:
        aqi_value = float(aqi) if aqi is not None else None
    except Exception:
        aqi_value = None
    if aqi_value is not None and aqi_value >= 101:
        if category:
            lines.append(f"Air quality is elevated (AQI {int(round(aqi_value, 0))}, {category}).")
        else:
            lines.append(f"Air quality is elevated (AQI {int(round(aqi_value, 0))}).")

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
    for alert in alerts[:3]:
        title = str(alert.get("title") or alert.get("key") or "").strip()
        severity = str(alert.get("severity") or "").strip()
        if not title:
            continue
        if severity:
            lines.append(f"{title} ({severity}).")
        else:
            lines.append(f"{title}.")

    for line in _active_state_lines(active_states):
        if line not in lines:
            lines.append(line)
    for line in _local_context_lines(local_payload):
        if line not in lines:
            lines.append(line)

    if not lines:
        lines.append("No major external drivers are flagged right now.")
    return lines


def _join_labels(labels: List[str]) -> str:
    cleaned = [str(x).strip() for x in labels if str(x).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _trend_insight(trend: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(trend, dict):
        return {"deltas": {}, "mean": 0.0, "notable": []}
    raw = trend.get("gauges") if isinstance(trend.get("gauges"), dict) else {}
    deltas: Dict[str, float] = {}
    for key, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        try:
            delta = float(payload.get("delta"))
        except Exception:
            continue
        deltas[str(key)] = delta
    if not deltas:
        return {"deltas": {}, "mean": 0.0, "notable": []}
    mean_delta = sum(deltas.values()) / max(len(deltas), 1)
    ranked = sorted(deltas.items(), key=lambda kv: abs(kv[1]), reverse=True)
    notable = [k for k, v in ranked if abs(v) >= 5][:3]
    return {"deltas": deltas, "mean": mean_delta, "notable": notable}


def _checkin_hook(trend: Optional[Dict[str, Any]]) -> str:
    insight = _trend_insight(trend)
    mean_delta = float(insight.get("mean") or 0.0)
    if mean_delta <= -6:
        return "Today may feel lower-voltage than yesterday, so shorter sprints and extra resets may help."
    if mean_delta >= 6:
        return "Today may carry more momentum than yesterday; steady pacing can help you use it well."
    if insight.get("notable"):
        return "Today looks mixed versus yesterday, so keep your plan flexible and adjust in small steps."
    return "Today looks relatively steady, so consistency should carry most of the load."


def _summary_note(trend: Optional[Dict[str, Any]], drivers: List[str]) -> str:
    insight = _trend_insight(trend)
    label_map = {
        "energy": "energy",
        "sleep": "sleep",
        "focus": "focus",
        "mood": "mood",
        "stamina": "stamina",
        "pain": "pain",
        "heart": "heart",
        "health_status": "health status",
    }
    notable_labels = [label_map.get(k, k.replace("_", " ")) for k in insight.get("notable") or []]
    lines: List[str] = []
    if notable_labels:
        lines.append(f"The clearest shifts since yesterday are in {_join_labels(notable_labels)}.")
    else:
        lines.append("Compared with yesterday, your gauges are mostly steady.")

    if drivers and drivers[0] != "No major external drivers are flagged right now.":
        lines.append("Use today’s drivers as context, not destiny; small course-corrections usually matter most.")
    else:
        lines.append("With no major external drivers flagged, routine and recovery habits should carry extra weight today.")
    return " ".join(lines).strip()


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
    definition: Dict[str, Any],
    gauges_row: Dict[str, Any],
    active_states: List[Dict[str, Any]],
    local_payload: Optional[Dict[str, Any]],
    tags: List[Dict[str, Any]],
    symptoms: Dict[str, Any],
    trend: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    day = gauges_row.get("day")
    day_str = day.isoformat() if isinstance(day, date) else str(day)

    highlights = _highlight_gauges(definition, gauges_row)
    alerts = gauges_row.get("alerts_json") or []
    actions = _default_actions(alerts)
    wit_line = _light_wit_line(alerts)

    hook = _checkin_hook(trend)
    if highlights:
        top = highlights[0]
        try:
            if float(top.get("value") or 0) >= 45:
                hook = f"The gauge to watch most today is {top['label'].lower()}."
        except Exception:
            pass

    health_line = _health_status_line(gauges_row.get("health_status"), include_value=False)

    all_driver_lines = _observed_driver_lines(active_states, alerts, local_payload)
    driver_lines = "\n".join([f"- {line}" for line in all_driver_lines])

    action_lines = "\n".join([f"- {a}" for a in actions])
    summary = _summary_note(trend, all_driver_lines)

    disclaimer = definition.get("global_disclaimer") or ""

    checkin_parts = [health_line, "", hook]
    if wit_line:
        checkin_parts.extend(["", wit_line])
    checkin_block = "\n".join(checkin_parts)

    body = (
        f"## Today’s Check-in\n{checkin_block}\n\n"
        f"## Drivers\n{driver_lines}\n\n"
        f"## Summary Note\n{summary}\n\n"
        f"## Supportive Actions\n{action_lines}\n\n"
        f"## Disclaimer\n{disclaimer}\n"
    )

    title = f"Your EarthScope — {day_str}"
    caption = hook
    return {
        "title": title,
        "caption": caption,
        "body_markdown": body,
        "driver_lines": all_driver_lines,
        "actions": actions,
        "health_line": health_line,
    }


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
    inputs_hash = _hash_inputs(inputs_snapshot)

    existing_hash = _fetch_existing_inputs_hash(user_id, day)
    if existing_hash == inputs_hash and not force:
        return {"ok": True, "skipped": True}

    existing = _fetch_existing_member_post(user_id, day)

    deterministic = _render_member_post(definition, gauges_row, active_states, local_payload, tags, symptoms, trend)
    rendered: Optional[Dict[str, Any]] = None
    if not trigger_events:
        rendered = _render_with_openai(definition, gauges_row, active_states, trend, deterministic)
        if not rendered:
            rendered = deterministic
    else:
        # Triggered advisory: append to existing post if present
        if existing and existing.get("body_markdown"):
            rendered = {
                "title": existing.get("title") or f"Your EarthScope — {day.isoformat()}",
                "caption": existing.get("caption") or "Triggered advisory",
                "body_markdown": existing.get("body_markdown"),
            }
        else:
            rendered = deterministic

        advisory = _render_trigger_advisory(trigger_events, gauges_row.get("health_status"))
        rendered["body_markdown"] = f"{rendered.get('body_markdown')}\n\n## Triggered Advisory\n{advisory}\n"

    payload = {
        "user_id": user_id,
        "day": day,
        "platform": "member",
        "title": rendered.get("title"),
        "caption": rendered.get("caption"),
        "body_markdown": rendered.get("body_markdown"),
        "metrics_json": json.dumps(inputs_snapshot),
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
