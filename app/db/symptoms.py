from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, List, Optional
from uuid import UUID

from psycopg.rows import dict_row

UTC = timezone.utc
CURRENT_SYMPTOM_STATES = ("new", "ongoing", "improving", "resolved")


def _normalize_ts(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _serialize_ts(ts: Optional[datetime]) -> Optional[str]:
    value = _normalize_ts(ts)
    return value.isoformat() if value else None


def _serialize_uuid(value: UUID | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return value


def _to_float(value: Decimal | float | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _prepare_tags(tags: Optional[Iterable[str]]) -> Optional[List[str]]:
    if tags is None:
        return None
    tags_list = [str(t) for t in tags if t]
    return tags_list or None


def _normalize_state(value: Optional[str]) -> str:
    token = str(value or "new").strip().lower()
    return token if token in CURRENT_SYMPTOM_STATES else "new"


def _normalize_note(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _serialize_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


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


async def insert_symptom_event(
    conn,
    user_id: str,
    *,
    symptom_code: str,
    ts_utc: Optional[datetime] = None,
    severity: Optional[int] = None,
    free_text: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
) -> dict:
    sql = """
    insert into raw.user_symptom_events (
        user_id,
        symptom_code,
        ts_utc,
        severity,
        free_text,
        tags
    ) values (%s, %s, coalesce(%s, now()), %s, %s, %s)
    returning id, ts_utc
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            sql,
            (
                user_id,
                symptom_code,
                _normalize_ts(ts_utc),
                severity,
                free_text,
                _prepare_tags(tags),
            ),
        )
        row = await cur.fetchone()

    if not row:
        raise RuntimeError("Failed to insert symptom event")

    return {
        "id": _serialize_uuid(row.get("id")),
        "ts_utc": _serialize_ts(row.get("ts_utc")),
    }


async def ensure_symptom_episode_for_event(
    conn,
    user_id: str,
    *,
    symptom_event_id: str,
    symptom_code: str,
    ts_utc: Optional[datetime] = None,
    severity: Optional[int] = None,
    note_text: Optional[str] = None,
    source: str = "ios",
) -> Optional[dict]:
    started_at = _normalize_ts(ts_utc) or datetime.now(UTC)
    normalized_note = _normalize_note(note_text)
    sql = """
    insert into raw.user_symptom_episodes (
        user_id,
        symptom_event_id,
        symptom_code,
        started_at,
        original_severity,
        current_severity,
        current_state,
        state_updated_at,
        last_interaction_at,
        latest_note_text,
        latest_note_at,
        source,
        created_at,
        updated_at
    ) values (
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        'new',
        %s,
        %s,
        %s,
        %s,
        %s,
        now(),
        now()
    )
    on conflict (symptom_event_id) do update
       set updated_at = now()
    returning id,
              current_state,
              state_updated_at,
              last_interaction_at,
              (xmax = 0) as inserted
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            sql,
            (
                user_id,
                symptom_event_id,
                symptom_code,
                started_at,
                severity,
                severity,
                started_at,
                started_at,
                normalized_note,
                started_at if normalized_note else None,
                source,
            ),
            prepare=False,
        )
        row = await cur.fetchone()

        if row and bool(row.get("inserted")):
            await cur.execute(
                """
                insert into raw.user_symptom_episode_updates (
                    episode_id,
                    user_id,
                    update_kind,
                    state,
                    severity,
                    note_text,
                    occurred_at,
                    metadata,
                    source
                ) values (
                    %s,
                    %s,
                    'logged',
                    'new',
                    %s,
                    %s,
                    %s,
                    %s::jsonb,
                    %s
                )
                """,
                (
                    row.get("id"),
                    user_id,
                    severity,
                    normalized_note,
                    started_at,
                    json.dumps({"symptom_event_id": symptom_event_id}, separators=(",", ":"), sort_keys=True),
                    source,
                ),
                prepare=False,
            )

    if not row:
        return None

    return {
        "id": _serialize_uuid(row.get("id")),
        "current_state": _normalize_state(row.get("current_state")),
        "state_updated_at": _serialize_ts(row.get("state_updated_at")),
        "last_interaction_at": _serialize_ts(row.get("last_interaction_at")),
        "inserted": bool(row.get("inserted")),
    }


async def record_symptom_episode_update(
    conn,
    user_id: str,
    episode_id: str,
    *,
    state: Optional[str] = None,
    severity: Optional[int] = None,
    note_text: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    source: str = "ios",
) -> dict:
    normalized_state = _normalize_state(state) if state is not None else None
    normalized_note = _normalize_note(note_text)
    effective_ts = _normalize_ts(occurred_at) or datetime.now(UTC)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select id,
                   user_id,
                   current_state,
                   current_severity,
                   original_severity,
                   started_at
              from raw.user_symptom_episodes
             where id = %s
               and user_id = %s
             limit 1
            """,
            (episode_id, user_id),
            prepare=False,
        )
        existing = await cur.fetchone()

        if not existing:
            raise RuntimeError("Symptom episode not found")

        next_state = normalized_state or _normalize_state(existing.get("current_state"))
        next_severity = severity if severity is not None else existing.get("current_severity") or existing.get("original_severity")
        update_kind = "state_change" if normalized_state is not None else ("note" if normalized_note else "severity_update")

        await cur.execute(
            """
            update raw.user_symptom_episodes
               set current_state = %s,
                   current_severity = %s,
                   state_updated_at = case when %s::text is null then state_updated_at else %s end,
                   last_interaction_at = %s,
                   improvement_ts = case
                       when %s = 'improving' and improvement_ts is null then %s
                       when %s = 'resolved' and improvement_ts is null then %s
                       else improvement_ts
                   end,
                   resolution_ts = case
                       when %s = 'resolved' then %s
                       when %s::text is not null then null
                       else resolution_ts
                   end,
                   latest_note_text = coalesce(%s, latest_note_text),
                   latest_note_at = case when %s is null then latest_note_at else %s end,
                   updated_at = now()
             where id = %s
               and user_id = %s
         returning id,
                   symptom_code,
                   current_state,
                   original_severity,
                   current_severity,
                   started_at,
                   state_updated_at,
                   last_interaction_at,
                   latest_note_text,
                   latest_note_at
            """,
            (
                next_state,
                next_severity,
                normalized_state,
                effective_ts,
                effective_ts,
                next_state,
                effective_ts,
                next_state,
                effective_ts,
                next_state,
                effective_ts,
                normalized_state,
                normalized_note,
                normalized_note,
                effective_ts,
                episode_id,
                user_id,
            ),
            prepare=False,
        )
        updated = await cur.fetchone()

        await cur.execute(
            """
            insert into raw.user_symptom_episode_updates (
                episode_id,
                user_id,
                update_kind,
                state,
                severity,
                note_text,
                occurred_at,
                source
            ) values (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                episode_id,
                user_id,
                update_kind,
                normalized_state,
                next_severity,
                normalized_note,
                effective_ts,
                source,
            ),
            prepare=False,
        )

    if not updated:
        raise RuntimeError("Failed to update symptom episode")

    return {
        "id": _serialize_uuid(updated.get("id")),
        "symptom_code": updated.get("symptom_code"),
        "current_state": _normalize_state(updated.get("current_state")),
        "original_severity": updated.get("original_severity"),
        "current_severity": updated.get("current_severity"),
        "started_at": _serialize_ts(updated.get("started_at")),
        "state_updated_at": _serialize_ts(updated.get("state_updated_at")),
        "last_interaction_at": _serialize_ts(updated.get("last_interaction_at")),
        "latest_note_text": updated.get("latest_note_text"),
        "latest_note_at": _serialize_ts(updated.get("latest_note_at")),
    }


async def delete_symptom_episode(conn, user_id: str, episode_id: str) -> dict:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            delete from raw.user_symptom_events e
                  using raw.user_symptom_episodes ep
             where ep.id = %s
               and ep.user_id = %s
               and e.id = ep.symptom_event_id
               and e.user_id = %s
         returning ep.id as episode_id,
                   ep.symptom_code,
                   ep.started_at,
                   ep.last_interaction_at,
                   e.id as symptom_event_id,
                   e.ts_utc
            """,
            (episode_id, user_id, user_id),
            prepare=False,
        )
        deleted = await cur.fetchone()

    if not deleted:
        raise RuntimeError("Symptom episode not found")

    return {
        "episode_id": _serialize_uuid(deleted.get("episode_id")),
        "symptom_event_id": _serialize_uuid(deleted.get("symptom_event_id")),
        "symptom_code": deleted.get("symptom_code"),
        "started_at": _serialize_ts(deleted.get("started_at")),
        "last_interaction_at": _serialize_ts(deleted.get("last_interaction_at")),
        "ts_utc": _serialize_ts(deleted.get("ts_utc")),
    }


async def fetch_symptom_codes(conn, *, include_inactive: bool = True) -> List[dict]:
    sql = """
    select
        symptom_code,
        label,
        description,
        is_active
    from dim.symptom_codes
    {where_clause}
    order by label
    """

    where_clause = ""
    if not include_inactive:
        where_clause = "where is_active"

    query = sql.format(where_clause=where_clause)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query)
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "symptom_code": row.get("symptom_code"),
                "label": row.get("label"),
                "description": row.get("description"),
                "is_active": bool(row.get("is_active", False)),
            }
        )
    return result


async def fetch_symptoms_today(conn, user_id: str) -> List[dict]:
    sql = """
    select
        symptom_code,
        ts_utc,
        severity,
        free_text
    from raw.user_symptom_events
    where user_id = %s
      and (ts_utc at time zone 'utc')::date = (now() at time zone 'utc')::date
    order by ts_utc desc
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id,))
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "symptom_code": row.get("symptom_code"),
                "ts_utc": _serialize_ts(row.get("ts_utc")),
                "severity": row.get("severity"),
                "free_text": row.get("free_text"),
            }
        )
    return result


async def fetch_daily_summary(conn, user_id: str, days: int) -> List[dict]:
    sql = """
    select
        (ts_utc at time zone 'utc')::date as day,
        symptom_code,
        count(*) as events,
        avg(severity) filter (where severity is not null) as mean_severity,
        max(ts_utc) as last_ts
    from raw.user_symptom_events
    where user_id = %s
      and ts_utc >= (now() at time zone 'utc') - (%s * interval '1 day')
    group by 1, 2
    order by day desc, symptom_code
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, days))
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        day_value = row.get("day")
        result.append(
            {
                "day": day_value.isoformat() if day_value else None,
                "symptom_code": row.get("symptom_code"),
                "events": int(row.get("events") or 0),
                "mean_severity": _to_float(row.get("mean_severity")),
                "last_ts": _serialize_ts(row.get("last_ts")),
            }
        )
    return result


async def fetch_diagnostics(conn, user_id: str, days: int) -> List[dict]:
    sql = """
    select
        symptom_code,
        count(*) as events,
        max(ts_utc) as last_ts
    from raw.user_symptom_events
    where user_id = %s
      and ts_utc >= (now() at time zone 'utc') - (%s * interval '1 day')
    group by 1
    order by symptom_code
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, days))
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "symptom_code": row.get("symptom_code"),
                "events": int(row.get("events") or 0),
                "last_ts": _serialize_ts(row.get("last_ts")),
            }
        )
    return result


async def fetch_current_symptom_items(
    conn,
    user_id: str,
    *,
    window_hours: int,
    limit: int = 20,
) -> List[dict]:
    sql = """
    with notes as (
        select episode_id,
               count(*) filter (where note_text is not null and btrim(note_text) <> '') as note_count
          from raw.user_symptom_episode_updates
         where user_id = %s
         group by episode_id
    )
    select
        ep.id,
        ep.symptom_code,
        coalesce(sc.label, initcap(replace(ep.symptom_code, '_', ' '))) as label,
        ep.original_severity,
        ep.current_severity,
        ep.started_at,
        ep.current_state,
        ep.state_updated_at,
        ep.last_interaction_at,
        ep.latest_note_text,
        ep.latest_note_at,
        ep.improvement_ts,
        ep.resolution_ts,
        ep.follow_up_state,
        coalesce(notes.note_count, 0) as note_count
      from raw.user_symptom_episodes ep
      left join dim.symptom_codes sc
        on sc.symptom_code = ep.symptom_code
      left join notes
        on notes.episode_id = ep.id
     where ep.user_id = %s
       and ep.current_state <> 'resolved'
       and ep.last_interaction_at >= now() - (%s * interval '1 hour')
     order by ep.last_interaction_at desc, ep.started_at desc
     limit %s
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, user_id, window_hours, limit), prepare=False)
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "id": _serialize_uuid(row.get("id")),
                "symptom_code": row.get("symptom_code"),
                "label": row.get("label"),
                "original_severity": row.get("original_severity"),
                "current_severity": row.get("current_severity"),
                "started_at": _serialize_ts(row.get("started_at")),
                "current_state": _normalize_state(row.get("current_state")),
                "state_updated_at": _serialize_ts(row.get("state_updated_at")),
                "last_interaction_at": _serialize_ts(row.get("last_interaction_at")),
                "latest_note_text": row.get("latest_note_text"),
                "latest_note_at": _serialize_ts(row.get("latest_note_at")),
                "improvement_ts": _serialize_ts(row.get("improvement_ts")),
                "resolution_ts": _serialize_ts(row.get("resolution_ts")),
                "follow_up_state": _serialize_json(row.get("follow_up_state")) or {},
                "note_count": int(row.get("note_count") or 0),
            }
        )
    return result


async def fetch_current_symptom_items_fallback(
    conn,
    user_id: str,
    *,
    window_hours: int,
    limit: int = 20,
) -> List[dict]:
    sql = """
    select
        e.id,
        e.symptom_code,
        coalesce(sc.label, initcap(replace(e.symptom_code, '_', ' '))) as label,
        e.severity,
        e.ts_utc,
        e.free_text
      from raw.user_symptom_events e
      left join dim.symptom_codes sc
        on sc.symptom_code = e.symptom_code
     where e.user_id = %s
       and e.ts_utc >= now() - (%s * interval '1 hour')
     order by e.ts_utc desc
     limit %s
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, window_hours, limit), prepare=False)
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        note_text = _normalize_note(row.get("free_text"))
        result.append(
            {
                "id": _serialize_uuid(row.get("id")),
                "symptom_code": row.get("symptom_code"),
                "label": row.get("label"),
                "original_severity": row.get("severity"),
                "current_severity": row.get("severity"),
                "started_at": _serialize_ts(row.get("ts_utc")),
                "current_state": "new",
                "state_updated_at": _serialize_ts(row.get("ts_utc")),
                "last_interaction_at": _serialize_ts(row.get("ts_utc")),
                "latest_note_text": note_text,
                "latest_note_at": _serialize_ts(row.get("ts_utc")) if note_text else None,
                "improvement_ts": None,
                "resolution_ts": None,
                "follow_up_state": {},
                "note_count": 1 if note_text else 0,
            }
        )
    return result


async def fetch_current_symptom_timeline(
    conn,
    user_id: str,
    *,
    days: int,
    limit: int = 80,
) -> List[dict]:
    sql = """
    select
        u.id,
        u.episode_id,
        ep.symptom_code,
        coalesce(sc.label, initcap(replace(ep.symptom_code, '_', ' '))) as label,
        u.update_kind,
        u.state,
        u.severity,
        u.note_text,
        u.occurred_at
      from raw.user_symptom_episode_updates u
      join raw.user_symptom_episodes ep
        on ep.id = u.episode_id
      left join dim.symptom_codes sc
        on sc.symptom_code = ep.symptom_code
     where u.user_id = %s
       and u.occurred_at >= now() - (%s * interval '1 day')
     order by u.occurred_at desc
     limit %s
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, days, limit), prepare=False)
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        result.append(
            {
                "id": _serialize_uuid(row.get("id")),
                "episode_id": _serialize_uuid(row.get("episode_id")),
                "symptom_code": row.get("symptom_code"),
                "label": row.get("label"),
                "update_kind": row.get("update_kind"),
                "state": _normalize_state(row.get("state")) if row.get("state") is not None else None,
                "severity": row.get("severity"),
                "note_text": row.get("note_text"),
                "occurred_at": _serialize_ts(row.get("occurred_at")),
            }
        )
    return result


async def fetch_current_symptom_timeline_fallback(
    conn,
    user_id: str,
    *,
    days: int,
    limit: int = 80,
) -> List[dict]:
    sql = """
    select
        e.id,
        e.symptom_code,
        coalesce(sc.label, initcap(replace(e.symptom_code, '_', ' '))) as label,
        e.severity,
        e.free_text,
        e.ts_utc
      from raw.user_symptom_events e
      left join dim.symptom_codes sc
        on sc.symptom_code = e.symptom_code
     where e.user_id = %s
       and e.ts_utc >= now() - (%s * interval '1 day')
     order by e.ts_utc desc
     limit %s
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (user_id, days, limit), prepare=False)
        rows = await cur.fetchall()

    result: List[dict] = []
    for row in rows or []:
        note_text = _normalize_note(row.get("free_text"))
        result.append(
            {
                "id": _serialize_uuid(row.get("id")),
                "episode_id": _serialize_uuid(row.get("id")),
                "symptom_code": row.get("symptom_code"),
                "label": row.get("label"),
                "update_kind": "logged",
                "state": "new",
                "severity": row.get("severity"),
                "note_text": note_text,
                "occurred_at": _serialize_ts(row.get("ts_utc")),
            }
        )
    return result


async def fetch_symptom_follow_up_settings(conn, user_id: str) -> dict:
    defaults = {
        "notifications_enabled": False,
        "enabled": False,
        "notification_family_enabled": False,
        "cadence": "balanced",
        "states": ["new", "ongoing", "improving"],
        "symptom_codes": [],
    }

    columns = await _table_columns(conn, "app", "user_notification_preferences")
    if not columns:
        return defaults

    select_parts = [
        "enabled" if "enabled" in columns else "false as enabled",
        "families" if "families" in columns else "'{}'::jsonb as families",
        (
            "symptom_followups_enabled"
            if "symptom_followups_enabled" in columns
            else "false as symptom_followups_enabled"
        ),
        (
            "symptom_followup_cadence"
            if "symptom_followup_cadence" in columns
            else "'balanced'::text as symptom_followup_cadence"
        ),
        (
            "symptom_followup_states"
            if "symptom_followup_states" in columns
            else "array['new','ongoing','improving']::text[] as symptom_followup_states"
        ),
        (
            "symptom_followup_symptom_codes"
            if "symptom_followup_symptom_codes" in columns
            else "array[]::text[] as symptom_followup_symptom_codes"
        ),
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

    families = _serialize_json(row.get("families"))
    family_enabled = False
    if isinstance(families, dict):
        family_enabled = bool(families.get("symptom_followups"))

    states = [state for state in (row.get("symptom_followup_states") or []) if state]
    symptom_codes = [code for code in (row.get("symptom_followup_symptom_codes") or []) if code]

    return {
        "notifications_enabled": bool(row.get("enabled")),
        "enabled": bool(row.get("symptom_followups_enabled")),
        "notification_family_enabled": family_enabled,
        "cadence": str(row.get("symptom_followup_cadence") or "balanced"),
        "states": states or defaults["states"],
        "symptom_codes": symptom_codes,
    }
