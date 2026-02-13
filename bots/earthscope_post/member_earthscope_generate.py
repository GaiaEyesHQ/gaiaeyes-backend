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


def _health_status_line(value: Optional[Any]) -> str:
    if value is None:
        return "Health Status: calibrating"
    try:
        v = float(value)
    except Exception:
        return "Health Status: calibrating"
    label = "stable"
    if v >= 85:
        label = "high"
    elif v >= 70:
        label = "elevated"
    elif v >= 55:
        label = "moderate"
    return f"Health Status: {int(round(v, 0))} ({label})"


def _default_actions(alerts: List[Dict[str, Any]]) -> List[str]:
    actions = []
    for alert in alerts or []:
        for a in alert.get("suggested_actions") or []:
            if a not in actions:
                actions.append(a)
    if actions:
        return actions[:5]
    return [
        "hydrate and pace",
        "gentle movement",
        "protect your sleep window",
    ]


def _render_member_post(
    definition: Dict[str, Any],
    gauges_row: Dict[str, Any],
    active_states: List[Dict[str, Any]],
    tags: List[Dict[str, Any]],
    symptoms: Dict[str, Any],
) -> Dict[str, str]:
    day = gauges_row.get("day")
    day_str = day.isoformat() if isinstance(day, date) else str(day)

    highlights = _highlight_gauges(definition, gauges_row)
    drivers = active_states[:4]
    alerts = gauges_row.get("alerts_json") or []
    actions = _default_actions(alerts)

    hook = "Here is your EarthScope for today—focused on how conditions may feel for you."
    if highlights:
        top = highlights[0]
        hook = f"Your top sensitivity today: {top['label']} ({top['value']})."

    gauges_lines_parts = []
    gauges_lines_parts.append(f"- {_health_status_line(gauges_row.get('health_status'))}")
    gauges_lines_parts.extend(
        [f"- **{h['label']}**: {h['value']} ({h['severity']})" for h in highlights]
    )
    gauges_lines = "\n".join(gauges_lines_parts) or "- No gauge highlights yet."

    driver_lines = "\n".join(
        [
            f"- {d.get('signal_key')}: {d.get('state')} (value {d.get('value')})"
            for d in drivers
        ]
    ) or "- No dominant drivers detected."

    action_lines = "\n".join([f"- {a}" for a in actions])

    disclaimer = definition.get("global_disclaimer") or ""

    body = (
        f"## Today’s Check-in\n{hook}\n\n"
        f"## Your Gauges Today\n{gauges_lines}\n\n"
        f"## Drivers\n{driver_lines}\n\n"
        f"## Supportive Actions\n{action_lines}\n\n"
        f"## Disclaimer\n{disclaimer}\n"
    )

    title = f"Your EarthScope — {day_str}"
    caption = hook
    return {"title": title, "caption": caption, "body_markdown": body}


def _render_with_openai(
    definition: Dict[str, Any],
    gauges_row: Dict[str, Any],
    active_states: List[Dict[str, Any]],
    tags: List[Dict[str, Any]],
    symptoms: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not (HAVE_OPENAI and api_key):
        return None

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    def _jsonable(obj: Any) -> Any:
        try:
            json.dumps(obj)
            return obj
        except Exception:
            return json.loads(json.dumps(obj, default=str))
    prompt = {
        "task": "Write a personalized EarthScope member update.",
        "format": "Return strict JSON with keys: title, caption, body_markdown.",
        "voice": "calm, grounded, practical, never alarmist",
        "rules": [
            "Use conditional language (may/can/for some).",
            "Do not provide medical advice or diagnosis.",
            "Include 3–5 supportive actions.",
            "Include the disclaimer verbatim at the end.",
        ],
        "data": {
            "gauges": _jsonable(gauges_row),
            "active_states": active_states,
            "tags": tags,
            "symptoms": symptoms,
            "disclaimer": definition.get("global_disclaimer"),
        },
    }

    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are Gaia Eyes’ member EarthScope writer. Keep it concise and supportive.",
                },
                {"role": "user", "content": json.dumps(prompt, default=str)},
            ],
        )
        obj = json.loads(resp.choices[0].message.content)
        if not all(k in obj for k in ("title", "caption", "body_markdown")):
            return None
        health_line = _health_status_line(gauges_row.get("health_status"))
        body = str(obj.get("body_markdown") or "").strip()
        if health_line and "Health Status" not in body:
            body = f"{body}\n\n{health_line}"
        return {
            "title": str(obj.get("title") or "").strip(),
            "caption": str(obj.get("caption") or "").strip(),
            "body_markdown": body,
        }
    except Exception as exc:
        logger.warning("[member] OpenAI failed, using fallback: %s", exc)
        return None


def generate_member_post_for_user(
    user_id: str,
    day: str | date | None = None,
    *,
    force: bool = False,
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

    inputs_snapshot = {
        "definition_version": version,
        "day": day.isoformat(),
        "gauges": {k: gauges_row.get(k) for k in ["pain", "focus", "heart", "stamina", "energy", "sleep", "mood", "health_status"]},
        "alerts": gauges_row.get("alerts_json"),
        "active_states": active_states,
        "local_payload": local_payload,
        "tags": tags,
        "symptoms": symptoms,
    }
    inputs_hash = _hash_inputs(inputs_snapshot)

    existing_hash = _fetch_existing_inputs_hash(user_id, day)
    if existing_hash == inputs_hash and not force:
        return {"ok": True, "skipped": True}

    rendered = _render_with_openai(definition, gauges_row, active_states, tags, symptoms)
    if not rendered:
        rendered = _render_member_post(definition, gauges_row, active_states, tags, symptoms)

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
