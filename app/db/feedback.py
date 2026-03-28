from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row


UTC = timezone.utc
FOLLOW_UP_RESPONSE_STATES = {"ongoing", "improving", "worse", "resolved"}
CURRENT_SYMPTOM_STATES = {"new", "ongoing", "improving", "worse", "resolved"}
CADENCE_ALIASES = {
    "gentle": "minimal",
    "frequent": "detailed",
    "minimal": "minimal",
    "balanced": "balanced",
    "detailed": "detailed",
}

DEFAULT_FAMILIES: Dict[str, bool] = {
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

PAIN_CODES = {
    "headache",
    "migraine",
    "sinus_pressure",
    "pain",
    "joint_pain",
    "nerve_pain",
    "muscle_pain",
    "stiffness",
    "zaps",
}
ENERGY_CODES = {"fatigue", "drained", "low_energy", "wired_tired", "wired", "brain_fog"}
MOOD_CODES = {"anxious", "panic", "restless", "wired", "irritable", "low_mood"}
SLEEP_CODES = {"insomnia", "restless_sleep", "poor_sleep", "waking_unrefreshed"}

DEFAULT_PAIN_OPTIONS = [
    "sinus_pressure",
    "joint_pain",
    "nerve_pain",
    "muscle_pain",
    "head_pressure",
    "cycle_related_pain",
    "other",
]
DEFAULT_ENERGY_OPTIONS = ["tired", "drained", "heavy_body", "brain_fog", "crashed_later"]
DEFAULT_MOOD_OPTIONS = ["anxious", "wired", "irritable", "low_mood", "emotionally_sensitive"]
DEFAULT_SLEEP_OPTIONS = ["yes_strongly", "yes_somewhat", "not_much", "unsure"]


def _normalize_ts(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _serialize_ts(value: Optional[datetime]) -> Optional[str]:
    normalized = _normalize_ts(value)
    return normalized.isoformat() if normalized else None


def _serialize_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _normalize_state(value: Optional[str], *, fallback: str = "new") -> str:
    token = str(value or fallback).strip().lower()
    return token if token in CURRENT_SYMPTOM_STATES else fallback


def _normalize_follow_up_response_state(value: Optional[str]) -> str:
    token = str(value or "ongoing").strip().lower()
    if token not in FOLLOW_UP_RESPONSE_STATES:
        raise RuntimeError("invalid follow-up response state")
    return token


def _normalize_cadence(value: Optional[str], *, default: str = "balanced") -> str:
    token = str(value or default).strip().lower() or default
    return CADENCE_ALIASES.get(token, default)


def _normalize_codes(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for value in values:
        token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if token and token not in normalized:
            normalized.append(token)
    return normalized


def _label_from_code(value: Optional[str]) -> str:
    token = str(value or "other").strip().replace("-", "_").replace(" ", "_")
    return token.replace("_", " ").title()


def _symptom_category(code: Optional[str]) -> str:
    token = str(code or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token in PAIN_CODES:
        return "pain"
    if token in ENERGY_CODES:
        return "energy"
    if token in MOOD_CODES:
        return "mood"
    if token in SLEEP_CODES:
        return "sleep"
    return "general"


def _parse_hhmm(value: Optional[str], *, fallback: str) -> time:
    raw = (value or "").strip() or fallback
    hour, minute = raw.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def _clock_hhmm(value: Any, *, fallback: str) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    raw = str(value or "").strip()
    if not raw:
        return fallback
    parts = raw.split(":", 1)
    if len(parts) != 2:
        return fallback
    return f"{int(parts[0]):02d}:{int(parts[1][:2]):02d}"


def _time_zone(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "UTC").strip() or "UTC")
    except Exception:
        return ZoneInfo("UTC")


async def _table_columns(conn, schema: str, table: str) -> List[str]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select column_name
              from information_schema.columns
             where table_schema = %s
               and table_name = %s
             order by ordinal_position
            """,
            (schema, table),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [str(row.get("column_name")) for row in rows or [] if row.get("column_name")]


async def load_feedback_preferences(conn, user_id: str) -> Dict[str, Any]:
    defaults = {
        "notifications_enabled": False,
        "quiet_hours_enabled": False,
        "quiet_start": "22:00",
        "quiet_end": "08:00",
        "time_zone": "UTC",
        "families": dict(DEFAULT_FAMILIES),
        "symptom_followups_enabled": False,
        "symptom_followup_push_enabled": False,
        "symptom_followup_cadence": "balanced",
        "symptom_followup_states": ["new", "ongoing", "improving", "worse"],
        "symptom_followup_symptom_codes": [],
        "daily_checkins_enabled": False,
        "daily_checkin_push_enabled": False,
        "daily_checkin_cadence": "balanced",
        "daily_checkin_reminder_time": "20:00",
    }

    columns = await _table_columns(conn, "app", "user_notification_preferences")
    if not columns:
        return defaults

    select_parts = [
        "enabled" if "enabled" in columns else "false as enabled",
        "quiet_hours_enabled" if "quiet_hours_enabled" in columns else "false as quiet_hours_enabled",
        "to_char(quiet_start, 'HH24:MI') as quiet_start" if "quiet_start" in columns else "'22:00'::text as quiet_start",
        "to_char(quiet_end, 'HH24:MI') as quiet_end" if "quiet_end" in columns else "'08:00'::text as quiet_end",
        "time_zone" if "time_zone" in columns else "'UTC'::text as time_zone",
        "families" if "families" in columns else "'{}'::jsonb as families",
        "symptom_followups_enabled" if "symptom_followups_enabled" in columns else "false as symptom_followups_enabled",
        "symptom_followup_push_enabled" if "symptom_followup_push_enabled" in columns else "false as symptom_followup_push_enabled",
        "symptom_followup_cadence" if "symptom_followup_cadence" in columns else "'balanced'::text as symptom_followup_cadence",
        "symptom_followup_states" if "symptom_followup_states" in columns else "array['new','ongoing','improving','worse']::text[] as symptom_followup_states",
        "symptom_followup_symptom_codes" if "symptom_followup_symptom_codes" in columns else "array[]::text[] as symptom_followup_symptom_codes",
        "daily_checkins_enabled" if "daily_checkins_enabled" in columns else "false as daily_checkins_enabled",
        "daily_checkin_push_enabled" if "daily_checkin_push_enabled" in columns else "false as daily_checkin_push_enabled",
        "daily_checkin_cadence" if "daily_checkin_cadence" in columns else "'balanced'::text as daily_checkin_cadence",
        "to_char(daily_checkin_reminder_time, 'HH24:MI') as daily_checkin_reminder_time" if "daily_checkin_reminder_time" in columns else "'20:00'::text as daily_checkin_reminder_time",
    ]

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            select {", ".join(select_parts)}
              from app.user_notification_preferences
             where user_id = %s
             limit 1
            """,
            (user_id,),
            prepare=False,
        )
        row = await cur.fetchone()

    if not row:
        return defaults

    families = defaults["families"]
    raw_families = _serialize_json(row.get("families"))
    if isinstance(raw_families, dict):
        families = dict(families)
        for key in families:
            if key in raw_families:
                families[key] = bool(raw_families.get(key))

    states = []
    for value in row.get("symptom_followup_states") or []:
        state = _normalize_state(value)
        if state not in states:
            states.append(state)
    if "worse" not in states:
        states.append("worse")

    return {
        "notifications_enabled": bool(row.get("enabled")),
        "quiet_hours_enabled": bool(row.get("quiet_hours_enabled")),
        "quiet_start": _clock_hhmm(row.get("quiet_start"), fallback="22:00"),
        "quiet_end": _clock_hhmm(row.get("quiet_end"), fallback="08:00"),
        "time_zone": str(row.get("time_zone") or "UTC"),
        "families": families,
        "symptom_followups_enabled": bool(row.get("symptom_followups_enabled")),
        "symptom_followup_push_enabled": bool(row.get("symptom_followup_push_enabled")) or bool(families.get("symptom_followups")),
        "symptom_followup_cadence": _normalize_cadence(row.get("symptom_followup_cadence")),
        "symptom_followup_states": states or defaults["symptom_followup_states"],
        "symptom_followup_symptom_codes": _normalize_codes(row.get("symptom_followup_symptom_codes")),
        "daily_checkins_enabled": bool(row.get("daily_checkins_enabled")),
        "daily_checkin_push_enabled": bool(row.get("daily_checkin_push_enabled")) or bool(families.get("daily_checkins")),
        "daily_checkin_cadence": _normalize_cadence(row.get("daily_checkin_cadence")),
        "daily_checkin_reminder_time": _clock_hhmm(row.get("daily_checkin_reminder_time"), fallback="20:00"),
    }


async def _fetch_symptom_episode(conn, user_id: str, episode_id: str) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select ep.id,
                   ep.user_id,
                   ep.symptom_code,
                   coalesce(sc.label, initcap(replace(ep.symptom_code, '_', ' '))) as label,
                   ep.current_state,
                   ep.original_severity,
                   ep.current_severity,
                   ep.started_at,
                   ep.last_interaction_at,
                   ep.latest_note_text,
                   ep.follow_up_state
              from raw.user_symptom_episodes ep
              left join dim.symptom_codes sc
                on sc.symptom_code = ep.symptom_code
             where ep.id = %s
               and ep.user_id = %s
             limit 1
            """,
            (episode_id, user_id),
            prepare=False,
        )
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": str(row.get("id") or ""),
        "symptom_code": str(row.get("symptom_code") or ""),
        "label": str(row.get("label") or _label_from_code(row.get("symptom_code"))),
        "current_state": _normalize_state(row.get("current_state")),
        "original_severity": row.get("original_severity"),
        "current_severity": row.get("current_severity"),
        "started_at": _normalize_ts(row.get("started_at")),
        "last_interaction_at": _normalize_ts(row.get("last_interaction_at")),
        "latest_note_text": row.get("latest_note_text"),
        "follow_up_state": _serialize_json(row.get("follow_up_state")) or {},
    }


async def _set_episode_follow_up_state(conn, user_id: str, episode_id: str, payload: Dict[str, Any]) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            update raw.user_symptom_episodes
               set follow_up_state = %s::jsonb,
                   updated_at = now()
             where id = %s
               and user_id = %s
            """,
            (
                json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str),
                episode_id,
                user_id,
            ),
            prepare=False,
        )


async def _active_prompt_counts(conn, user_id: str, episode_id: str) -> Dict[str, int]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select count(*)::int as total_prompts,
                   count(*) filter (where status = 'dismissed')::int as dismissals
              from raw.user_feedback_prompts
             where user_id = %s
               and episode_id = %s
               and prompt_type = 'symptom_follow_up'
            """,
            (user_id, episode_id),
            prepare=False,
        )
        row = await cur.fetchone()
    return {
        "total_prompts": int((row or {}).get("total_prompts") or 0),
        "dismissals": int((row or {}).get("dismissals") or 0),
    }


async def _existing_prompt(conn, user_id: str, *, prompt_type: str, episode_id: Optional[str] = None, prompt_day: Optional[date] = None) -> Optional[Dict[str, Any]]:
    where_clauses = ["user_id = %s", "prompt_type = %s"]
    params: List[Any] = [user_id, prompt_type]
    if episode_id is not None:
        where_clauses.append("episode_id = %s")
        params.append(episode_id)
    if prompt_day is not None:
        where_clauses.append("prompt_day = %s")
        params.append(prompt_day)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            select *
              from raw.user_feedback_prompts
             where {" and ".join(where_clauses)}
             order by scheduled_for desc, created_at desc
             limit 1
            """,
            params,
            prepare=False,
        )
        row = await cur.fetchone()
    return dict(row or {}) if row else None


def _follow_up_delay_hours(*, cadence: str, cycle_index: int, state: str, severity: Optional[int]) -> float:
    if cycle_index <= 0:
        base = {"minimal": 4.0, "balanced": 3.0, "detailed": 2.0}[cadence]
    else:
        base = {"minimal": 18.0, "balanced": 10.0, "detailed": 6.0}[cadence]

    if state == "worse":
        base = min(base, 4.0 if cycle_index > 0 else 2.0)
    elif state == "improving" and cycle_index > 0:
        base += 4.0

    if severity is not None and severity >= 8:
        base = max(2.0, base - 1.0)
    elif severity is not None and severity <= 4 and cycle_index <= 0:
        base += 1.0

    return base


async def maybe_schedule_symptom_follow_up(
    conn,
    user_id: str,
    *,
    episode_id: str,
    trigger: str,
    reference_ts: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    preferences = await load_feedback_preferences(conn, user_id)
    if not preferences.get("symptom_followups_enabled"):
        return None

    episode = await _fetch_symptom_episode(conn, user_id, episode_id)
    if not episode:
        return None

    state = _normalize_state(episode.get("current_state"))
    if state == "resolved":
        return None
    if state not in set(preferences.get("symptom_followup_states") or []):
        return None

    allowed_codes = set(preferences.get("symptom_followup_symptom_codes") or [])
    if allowed_codes and str(episode.get("symptom_code") or "") not in allowed_codes:
        return None

    existing = await _existing_prompt(
        conn,
        user_id,
        prompt_type="symptom_follow_up",
        episode_id=episode_id,
    )
    if existing and str(existing.get("status") or "") in {"pending", "snoozed"}:
        return _serialize_prompt(existing, fallback_label=str(episode.get("label") or ""))

    counts = await _active_prompt_counts(conn, user_id, episode_id)
    if counts["total_prompts"] >= 3 or counts["dismissals"] >= 2:
        return None

    cadence = _normalize_cadence(preferences.get("symptom_followup_cadence"))
    severity = episode.get("current_severity") or episode.get("original_severity")
    delay_hours = _follow_up_delay_hours(
        cadence=cadence,
        cycle_index=counts["total_prompts"],
        state=state,
        severity=severity,
    )
    base_ts = _normalize_ts(reference_ts) or episode.get("last_interaction_at") or episode.get("started_at") or datetime.now(UTC)
    scheduled_for = base_ts + timedelta(hours=delay_hours)
    now_utc = datetime.now(UTC)
    if scheduled_for < now_utc:
        scheduled_for = now_utc

    category = _symptom_category(episode.get("symptom_code"))
    question_text = f"Still feeling that {str(episode.get('label') or _label_from_code(episode.get('symptom_code'))).lower()}?"
    payload = {
        "trigger": trigger,
        "detail_focus": category,
        "episode_state": state,
        "response_states": ["ongoing", "improving", "worse", "resolved"],
    }

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            insert into raw.user_feedback_prompts (
                user_id,
                prompt_type,
                episode_id,
                symptom_code,
                question_key,
                question_text,
                prompt_payload,
                status,
                scheduled_for,
                push_delivery_enabled,
                source,
                created_at,
                updated_at
            )
            values (
                %s,
                'symptom_follow_up',
                %s,
                %s,
                'status_check',
                %s,
                %s::jsonb,
                'pending',
                %s,
                %s,
                %s,
                now(),
                now()
            )
            returning *
            """,
            (
                user_id,
                episode_id,
                episode.get("symptom_code"),
                question_text,
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                scheduled_for,
                bool(preferences.get("symptom_followup_push_enabled")),
                "system",
            ),
            prepare=False,
        )
        row = await cur.fetchone()

    if row:
        await _set_episode_follow_up_state(
            conn,
            user_id,
            episode_id,
            {
                "latest_prompt_id": str(row.get("id") or ""),
                "status": "pending",
                "scheduled_for": _serialize_ts(row.get("scheduled_for")),
                "detail_focus": category,
                "trigger": trigger,
            },
        )
    return _serialize_prompt(row, fallback_label=str(episode.get("label") or "")) if row else None


def _serialize_prompt(row: Any, *, fallback_label: str = "") -> Dict[str, Any]:
    payload = _serialize_json((row or {}).get("prompt_payload")) or {}
    return {
        "id": str((row or {}).get("id") or ""),
        "prompt_type": str((row or {}).get("prompt_type") or ""),
        "episode_id": str((row or {}).get("episode_id") or "") or None,
        "symptom_code": str((row or {}).get("symptom_code") or "").upper() or None,
        "symptom_label": str(payload.get("symptom_label") or fallback_label or _label_from_code((row or {}).get("symptom_code"))),
        "question_key": str((row or {}).get("question_key") or ""),
        "question_text": str((row or {}).get("question_text") or ""),
        "detail_focus": str(payload.get("detail_focus") or ""),
        "trigger": str(payload.get("trigger") or ""),
        "status": str((row or {}).get("status") or ""),
        "scheduled_for": _serialize_ts((row or {}).get("scheduled_for")),
        "delivered_at": _serialize_ts((row or {}).get("delivered_at")),
        "push_delivery_enabled": bool((row or {}).get("push_delivery_enabled")),
        "response_state": (row or {}).get("response_state"),
        "response_detail_choice": (row or {}).get("response_detail_choice"),
        "response_note_text": (row or {}).get("response_note_text"),
        "response_time_bucket": (row or {}).get("response_time_bucket"),
        "prompt_day": str((row or {}).get("prompt_day") or "") or None,
        "prompt_payload": payload if isinstance(payload, dict) else {},
    }


async def fetch_due_symptom_follow_up_prompts(
    conn,
    user_id: str,
    *,
    episode_ids: Optional[List[str]] = None,
    mark_delivered: bool = True,
) -> List[Dict[str, Any]]:
    params: List[Any] = [user_id]
    where = [
        "user_id = %s",
        "prompt_type = 'symptom_follow_up'",
        "status in ('pending', 'snoozed')",
        "coalesce(snoozed_until, scheduled_for) <= now()",
    ]
    if episode_ids:
        where.append("episode_id = any(%s)")
        params.append(episode_ids)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            select *
              from raw.user_feedback_prompts
             where {" and ".join(where)}
             order by coalesce(snoozed_until, scheduled_for) asc, created_at asc
            """,
            params,
            prepare=False,
        )
        rows = await cur.fetchall()

        if mark_delivered and rows:
            prompt_ids = [str(row.get("id")) for row in rows if row.get("id")]
            if prompt_ids:
                await cur.execute(
                    """
                    update raw.user_feedback_prompts
                       set delivered_at = coalesce(delivered_at, now()),
                           updated_at = now()
                     where id = any(%s::uuid[])
                    """,
                    (prompt_ids,),
                    prepare=False,
                )

    serialized = [_serialize_prompt(row) for row in rows or []]
    for prompt in serialized:
        if prompt.get("episode_id"):
            await _set_episode_follow_up_state(
                conn,
                user_id,
                prompt["episode_id"],
                {
                    "latest_prompt_id": prompt["id"],
                    "status": prompt["status"],
                    "scheduled_for": prompt.get("scheduled_for"),
                    "delivered_at": prompt.get("delivered_at") or datetime.now(UTC).isoformat(),
                    "detail_focus": prompt.get("detail_focus"),
                    "trigger": prompt.get("trigger"),
                },
            )
    return serialized


async def _expire_episode_prompts(conn, user_id: str, episode_id: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            update raw.user_feedback_prompts
               set status = 'expired',
                   updated_at = now()
             where user_id = %s
               and episode_id = %s
               and prompt_type = 'symptom_follow_up'
               and status in ('pending', 'snoozed')
            """,
            (user_id, episode_id),
            prepare=False,
        )


async def respond_symptom_follow_up(
    conn,
    user_id: str,
    prompt_id: str,
    *,
    state: str,
    detail_choice: Optional[str] = None,
    detail_text: Optional[str] = None,
    note_text: Optional[str] = None,
    time_bucket: Optional[str] = None,
    responded_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    normalized_state = _normalize_follow_up_response_state(state)
    effective_ts = _normalize_ts(responded_at) or datetime.now(UTC)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select *
              from raw.user_feedback_prompts
             where id = %s
               and user_id = %s
               and prompt_type = 'symptom_follow_up'
             limit 1
            """,
            (prompt_id, user_id),
            prepare=False,
        )
        prompt = await cur.fetchone()

    if not prompt:
        raise RuntimeError("Follow-up prompt not found")

    current_status = str(prompt.get("status") or "")
    if current_status not in {"pending", "snoozed", "answered"}:
        raise RuntimeError("Follow-up prompt is no longer active")
    existing_state = str(prompt.get("response_state") or "").strip().lower()
    if current_status == "answered" and existing_state and existing_state != normalized_state:
        raise RuntimeError("Follow-up prompt was already answered")

    from app.db import symptoms as symptoms_db

    should_write_episode = current_status != "answered"
    if should_write_episode:
        episode_row = await symptoms_db.record_symptom_episode_update(
            conn,
            user_id,
            str(prompt.get("episode_id") or ""),
            state=normalized_state,
            severity=None,
            note_text=note_text,
            occurred_at=effective_ts,
            source="follow_up",
            update_kind="follow_up",
            metadata={
                "prompt_id": prompt_id,
                "detail_choice": detail_choice,
                "detail_text": detail_text,
                "time_bucket": time_bucket,
            },
        )
    else:
        episode_row = await _fetch_symptom_episode(conn, user_id, str(prompt.get("episode_id") or ""))
        if note_text:
            episode_row = await symptoms_db.record_symptom_episode_update(
                conn,
                user_id,
                str(prompt.get("episode_id") or ""),
                state=None,
                severity=None,
                note_text=note_text,
                occurred_at=effective_ts,
                source="follow_up",
                update_kind="follow_up",
                metadata={
                    "prompt_id": prompt_id,
                    "detail_choice": detail_choice,
                    "detail_text": detail_text,
                    "time_bucket": time_bucket,
                    "detail_only": True,
                },
            )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            update raw.user_feedback_prompts
               set status = 'answered',
                   delivered_at = coalesce(delivered_at, now()),
                   answered_at = coalesce(answered_at, %s),
                   response_state = coalesce(response_state, %s),
                   response_detail_choice = coalesce(%s::text, response_detail_choice),
                   response_detail_text = coalesce(%s::text, response_detail_text),
                   response_note_text = coalesce(%s::text, response_note_text),
                   response_time_bucket = coalesce(%s::text, response_time_bucket),
                   updated_at = now()
             where id = %s
               and user_id = %s
         returning *
            """,
            (
                effective_ts,
                normalized_state,
                detail_choice,
                detail_text,
                note_text,
                time_bucket,
                prompt_id,
                user_id,
            ),
            prepare=False,
        )
        updated_prompt = await cur.fetchone()

    episode_id = str(prompt.get("episode_id") or "")
    if normalized_state == "resolved":
        await _expire_episode_prompts(conn, user_id, episode_id)
    elif should_write_episode and episode_id:
        await maybe_schedule_symptom_follow_up(
            conn,
            user_id,
            episode_id=episode_id,
            trigger="follow_up_response",
            reference_ts=effective_ts,
        )

    await _set_episode_follow_up_state(
        conn,
        user_id,
        episode_id,
        {
            "latest_prompt_id": prompt_id,
            "status": "answered",
            "answered_at": _serialize_ts(effective_ts),
            "last_response_state": normalized_state,
            "detail_choice": detail_choice,
            "time_bucket": time_bucket,
        },
    )

    return {
        "prompt": _serialize_prompt(updated_prompt),
        "episode": episode_row,
    }


async def dismiss_symptom_follow_up(
    conn,
    user_id: str,
    prompt_id: str,
    *,
    action: str = "snooze",
    snooze_hours: Optional[int] = None,
) -> Dict[str, Any]:
    normalized_action = str(action or "snooze").strip().lower()
    if normalized_action not in {"dismiss", "snooze"}:
        raise RuntimeError("invalid follow-up dismissal action")

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select *
              from raw.user_feedback_prompts
             where id = %s
               and user_id = %s
               and prompt_type = 'symptom_follow_up'
             limit 1
            """,
            (prompt_id, user_id),
            prepare=False,
        )
        prompt = await cur.fetchone()

    if not prompt:
        raise RuntimeError("Follow-up prompt not found")

    episode_id = str(prompt.get("episode_id") or "")
    if normalized_action == "snooze":
        hours = snooze_hours or 4
        snoozed_until = datetime.now(UTC) + timedelta(hours=max(1, hours))
        new_status = "snoozed"
        dismissed_at = None
    else:
        snoozed_until = None
        new_status = "dismissed"
        dismissed_at = datetime.now(UTC)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            update raw.user_feedback_prompts
               set status = %s,
                   delivered_at = coalesce(delivered_at, now()),
                   dismissed_at = %s,
                   snoozed_until = %s,
                   updated_at = now()
             where id = %s
               and user_id = %s
         returning *
            """,
            (new_status, dismissed_at, snoozed_until, prompt_id, user_id),
            prepare=False,
        )
        updated_prompt = await cur.fetchone()

    if normalized_action == "dismiss" and episode_id:
        episode = await _fetch_symptom_episode(conn, user_id, episode_id)
        if episode and _normalize_state(episode.get("current_state")) != "resolved":
            await maybe_schedule_symptom_follow_up(
                conn,
                user_id,
                episode_id=episode_id,
                trigger="follow_up_dismissed",
                reference_ts=(dismissed_at or datetime.now(UTC)) + timedelta(hours=8),
            )

    await _set_episode_follow_up_state(
        conn,
        user_id,
        episode_id,
        {
            "latest_prompt_id": prompt_id,
            "status": new_status,
            "dismissed_at": _serialize_ts(dismissed_at),
            "snoozed_until": _serialize_ts(snoozed_until),
        },
    )
    return _serialize_prompt(updated_prompt)


def _daily_prompt_phase(local_now: datetime, reminder_time: time) -> str:
    if local_now.time() >= reminder_time:
        return "end_of_day"
    return "next_morning"


async def _completed_checkin_exists(conn, user_id: str, target_day: date) -> bool:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select 1
              from raw.user_daily_checkins
             where user_id = %s
               and day = %s
             limit 1
            """,
            (user_id, target_day),
            prepare=False,
        )
        row = await cur.fetchone()
    return bool(row)


def _daily_target_day(local_now: datetime, reminder_time: time) -> Optional[date]:
    if local_now.time() >= reminder_time:
        return local_now.date()
    if local_now.time() < time(hour=11, minute=0):
        return local_now.date() - timedelta(days=1)
    if local_now.time() >= time(hour=12, minute=0):
        return local_now.date() - timedelta(days=1)
    return None


async def _recent_symptom_context(conn, user_id: str) -> Dict[str, Any]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select ep.symptom_code,
                   coalesce(sc.label, initcap(replace(ep.symptom_code, '_', ' '))) as label,
                   ep.current_state,
                   ep.current_severity,
                   ep.last_interaction_at
              from raw.user_symptom_episodes ep
              left join dim.symptom_codes sc
                on sc.symptom_code = ep.symptom_code
             where ep.user_id = %s
               and (
                 ep.current_state <> 'resolved'
                 or ep.last_interaction_at >= now() - interval '36 hours'
               )
             order by ep.last_interaction_at desc
             limit 10
            """,
            (user_id,),
            prepare=False,
        )
        rows = await cur.fetchall()

    codes: List[str] = []
    labels: List[str] = []
    categories: set[str] = set()
    for row in rows or []:
        code = str(row.get("symptom_code") or "").strip().lower()
        if code and code not in codes:
            codes.append(code)
        label = str(row.get("label") or _label_from_code(code))
        if label and label not in labels:
            labels.append(label)
        categories.add(_symptom_category(code))

    return {
        "recent_symptom_codes": codes,
        "active_symptom_labels": labels[:4],
        "pain_logged_recently": "pain" in categories,
        "energy_logged_recently": "energy" in categories,
        "mood_logged_recently": "mood" in categories,
        "sleep_logged_recently": "sleep" in categories,
        "suggested_pain_types": DEFAULT_PAIN_OPTIONS,
        "suggested_energy_details": DEFAULT_ENERGY_OPTIONS,
        "suggested_mood_types": DEFAULT_MOOD_OPTIONS,
        "suggested_sleep_impacts": DEFAULT_SLEEP_OPTIONS,
    }


async def _ensure_daily_check_in_prompt(conn, user_id: str, *, now_utc: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    preferences = await load_feedback_preferences(conn, user_id)
    if not preferences.get("daily_checkins_enabled"):
        return None

    effective_now = _normalize_ts(now_utc) or datetime.now(UTC)
    tz = _time_zone(preferences.get("time_zone"))
    local_now = effective_now.astimezone(tz)
    reminder_time = _parse_hhmm(preferences.get("daily_checkin_reminder_time"), fallback="20:00")
    target_day = _daily_target_day(local_now, reminder_time)
    if target_day is None:
        return None

    if await _completed_checkin_exists(conn, user_id, target_day):
        return None

    existing = await _existing_prompt(
        conn,
        user_id,
        prompt_type="daily_check_in",
        prompt_day=target_day,
    )
    if existing and str(existing.get("status") or "") in {"pending", "snoozed", "dismissed", "answered"}:
        return _serialize_prompt(existing)

    phase = _daily_prompt_phase(local_now, reminder_time)
    if phase == "end_of_day":
        scheduled_local = datetime.combine(target_day, reminder_time, tzinfo=tz)
        question_text = "How did today feel?"
    else:
        scheduled_local = datetime.combine(local_now.date(), time(hour=9, minute=0), tzinfo=tz)
        question_text = "How did yesterday feel?"

    context_payload = await _recent_symptom_context(conn, user_id)
    payload = dict(context_payload)
    payload["phase"] = phase
    payload["target_day"] = target_day.isoformat()

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            insert into raw.user_feedback_prompts (
                user_id,
                prompt_type,
                prompt_day,
                question_key,
                question_text,
                prompt_payload,
                status,
                scheduled_for,
                push_delivery_enabled,
                source,
                created_at,
                updated_at
            )
            values (
                %s,
                'daily_check_in',
                %s,
                'daily_check_in',
                %s,
                %s::jsonb,
                'pending',
                %s,
                %s,
                'system',
                now(),
                now()
            )
            returning *
            """,
            (
                user_id,
                target_day,
                question_text,
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                scheduled_local.astimezone(UTC),
                bool(preferences.get("daily_checkin_push_enabled")),
            ),
            prepare=False,
        )
        row = await cur.fetchone()
    return _serialize_prompt(row) if row else None


async def fetch_latest_daily_check_in(conn, user_id: str) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select *
              from raw.user_daily_checkins
             where user_id = %s
             order by day desc
             limit 1
            """,
            (user_id,),
            prepare=False,
        )
        row = await cur.fetchone()
    if not row:
        return None
    payload = _serialize_json(row.get("context_payload")) or {}
    return {
        "day": str(row.get("day") or ""),
        "prompt_id": str(row.get("prompt_id") or "") or None,
        "compared_to_yesterday": row.get("compared_to_yesterday"),
        "energy_level": row.get("energy_level"),
        "usable_energy": row.get("usable_energy"),
        "system_load": row.get("system_load"),
        "pain_level": row.get("pain_level"),
        "pain_type": row.get("pain_type"),
        "energy_detail": row.get("energy_detail"),
        "mood_level": row.get("mood_level"),
        "mood_type": row.get("mood_type"),
        "sleep_impact": row.get("sleep_impact"),
        "prediction_match": row.get("prediction_match"),
        "note_text": row.get("note_text"),
        "completed_at": _serialize_ts(row.get("completed_at")),
        "context_payload": payload if isinstance(payload, dict) else {},
    }


async def fetch_feedback_calibration_summary(conn, user_id: str, *, days: int = 21) -> Dict[str, Any]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select count(*)::int as total_checkins,
                   count(*) filter (where prediction_match = 'mostly_right')::int as mostly_right,
                   count(*) filter (where prediction_match = 'partly_right')::int as partly_right,
                   count(*) filter (where prediction_match = 'not_really')::int as not_really
              from raw.user_daily_checkins
             where user_id = %s
               and completed_at >= now() - (%s * interval '1 day')
            """,
            (user_id, days),
            prepare=False,
        )
        daily_row = await cur.fetchone()
        await cur.execute(
            """
            select count(*) filter (where response_state = 'resolved')::int as resolved_count,
                   count(*) filter (where response_state = 'improving')::int as improving_count,
                   count(*) filter (where response_state = 'worse')::int as worse_count
              from raw.user_feedback_prompts
             where user_id = %s
               and prompt_type = 'symptom_follow_up'
               and answered_at >= now() - (%s * interval '1 day')
            """,
            (user_id, days),
            prepare=False,
        )
        follow_up_row = await cur.fetchone()

    total_checkins = int((daily_row or {}).get("total_checkins") or 0)
    mostly_right = int((daily_row or {}).get("mostly_right") or 0)
    return {
        "window_days": days,
        "total_checkins": total_checkins,
        "mostly_right": mostly_right,
        "partly_right": int((daily_row or {}).get("partly_right") or 0),
        "not_really": int((daily_row or {}).get("not_really") or 0),
        "match_rate": round(mostly_right / total_checkins, 3) if total_checkins else None,
        "resolved_count": int((follow_up_row or {}).get("resolved_count") or 0),
        "improving_count": int((follow_up_row or {}).get("improving_count") or 0),
        "worse_count": int((follow_up_row or {}).get("worse_count") or 0),
    }


async def fetch_daily_check_in_status(
    conn,
    user_id: str,
    *,
    now_utc: Optional[datetime] = None,
    mark_delivered: bool = True,
) -> Dict[str, Any]:
    prompt = await _ensure_daily_check_in_prompt(conn, user_id, now_utc=now_utc)
    latest_entry = await fetch_latest_daily_check_in(conn, user_id)
    calibration = await fetch_feedback_calibration_summary(conn, user_id)
    preferences = await load_feedback_preferences(conn, user_id)

    if prompt and mark_delivered:
        prompt_id = str(prompt.get("id") or "")
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                update raw.user_feedback_prompts
                   set delivered_at = coalesce(delivered_at, now()),
                       updated_at = now()
                 where id = %s
                   and user_id = %s
             returning *
                """,
                (prompt_id, user_id),
                prepare=False,
            )
            updated_prompt = await cur.fetchone()
        if updated_prompt:
            prompt = _serialize_prompt(updated_prompt)

    return {
        "prompt": prompt,
        "latest_entry": latest_entry,
        "calibration_summary": calibration,
        "settings": {
            "enabled": bool(preferences.get("daily_checkins_enabled")),
            "push_enabled": bool(preferences.get("daily_checkin_push_enabled")),
            "cadence": str(preferences.get("daily_checkin_cadence") or "balanced"),
            "reminder_time": str(preferences.get("daily_checkin_reminder_time") or "20:00"),
        },
    }


async def save_daily_check_in(
    conn,
    user_id: str,
    *,
    prompt_id: Optional[str],
    day: date,
    compared_to_yesterday: str,
    energy_level: str,
    usable_energy: str,
    system_load: str,
    pain_level: str,
    pain_type: Optional[str],
    energy_detail: Optional[str],
    mood_level: str,
    mood_type: Optional[str],
    sleep_impact: Optional[str],
    prediction_match: Optional[str],
    note_text: Optional[str],
    completed_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    effective_completed_at = _normalize_ts(completed_at) or datetime.now(UTC)
    prompt_payload: Dict[str, Any] = {}
    if prompt_id:
        prompt = await _existing_prompt(conn, user_id, prompt_type="daily_check_in", prompt_day=day)
        if prompt and str(prompt.get("id") or "") == prompt_id:
            prompt_payload = _serialize_json(prompt.get("prompt_payload")) or {}

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            insert into raw.user_daily_checkins (
                user_id,
                day,
                prompt_id,
                compared_to_yesterday,
                energy_level,
                usable_energy,
                system_load,
                pain_level,
                pain_type,
                energy_detail,
                mood_level,
                mood_type,
                sleep_impact,
                prediction_match,
                note_text,
                context_payload,
                completed_at,
                created_at,
                updated_at
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, now(), now()
            )
            on conflict (user_id, day) do update set
                prompt_id = excluded.prompt_id,
                compared_to_yesterday = excluded.compared_to_yesterday,
                energy_level = excluded.energy_level,
                usable_energy = excluded.usable_energy,
                system_load = excluded.system_load,
                pain_level = excluded.pain_level,
                pain_type = excluded.pain_type,
                energy_detail = excluded.energy_detail,
                mood_level = excluded.mood_level,
                mood_type = excluded.mood_type,
                sleep_impact = excluded.sleep_impact,
                prediction_match = excluded.prediction_match,
                note_text = excluded.note_text,
                context_payload = excluded.context_payload,
                completed_at = excluded.completed_at,
                updated_at = now()
            returning *
            """,
            (
                user_id,
                day,
                prompt_id,
                compared_to_yesterday,
                energy_level,
                usable_energy,
                system_load,
                pain_level,
                pain_type,
                energy_detail,
                mood_level,
                mood_type,
                sleep_impact,
                prediction_match,
                note_text,
                json.dumps(prompt_payload, separators=(",", ":"), sort_keys=True),
                effective_completed_at,
            ),
            prepare=False,
        )
        row = await cur.fetchone()

        if prompt_id:
            await cur.execute(
                """
                update raw.user_feedback_prompts
                   set status = 'answered',
                       delivered_at = coalesce(delivered_at, now()),
                       answered_at = coalesce(answered_at, %s),
                       updated_at = now()
                 where id = %s
                   and user_id = %s
                """,
                (effective_completed_at, prompt_id, user_id),
                prepare=False,
            )

    payload = _serialize_json((row or {}).get("context_payload")) or {}
    return {
        "day": str((row or {}).get("day") or day.isoformat()),
        "prompt_id": prompt_id,
        "compared_to_yesterday": compared_to_yesterday,
        "energy_level": energy_level,
        "usable_energy": usable_energy,
        "system_load": system_load,
        "pain_level": pain_level,
        "pain_type": pain_type,
        "energy_detail": energy_detail,
        "mood_level": mood_level,
        "mood_type": mood_type,
        "sleep_impact": sleep_impact,
        "prediction_match": prediction_match,
        "note_text": note_text,
        "completed_at": _serialize_ts((row or {}).get("completed_at") or effective_completed_at),
        "context_payload": payload if isinstance(payload, dict) else {},
    }


async def dismiss_daily_check_in(
    conn,
    user_id: str,
    prompt_id: str,
    *,
    action: str = "dismiss",
    snooze_hours: Optional[int] = None,
) -> Dict[str, Any]:
    normalized_action = str(action or "dismiss").strip().lower()
    if normalized_action not in {"dismiss", "snooze"}:
        raise RuntimeError("invalid daily check-in dismissal action")

    if normalized_action == "snooze":
        snoozed_until = datetime.now(UTC) + timedelta(hours=max(1, snooze_hours or 12))
        status = "snoozed"
        dismissed_at = None
    else:
        snoozed_until = None
        status = "dismissed"
        dismissed_at = datetime.now(UTC)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            update raw.user_feedback_prompts
               set status = %s,
                   delivered_at = coalesce(delivered_at, now()),
                   dismissed_at = %s,
                   snoozed_until = %s,
                   updated_at = now()
             where id = %s
               and user_id = %s
               and prompt_type = 'daily_check_in'
         returning *
            """,
            (status, dismissed_at, snoozed_until, prompt_id, user_id),
            prepare=False,
        )
        row = await cur.fetchone()
    if not row:
        raise RuntimeError("Daily check-in prompt not found")
    return _serialize_prompt(row)


async def fetch_due_push_prompts(
    conn,
    *,
    prompt_type: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if prompt_type not in {"symptom_follow_up", "daily_check_in"}:
        return []

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select *
              from raw.user_feedback_prompts
             where prompt_type = %s
               and status in ('pending', 'snoozed')
               and push_delivery_enabled = true
               and coalesce(snoozed_until, scheduled_for) <= now()
             order by coalesce(snoozed_until, scheduled_for) asc, created_at asc
             limit %s
            """,
            (prompt_type, limit),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [_serialize_prompt(row) for row in rows or []]
