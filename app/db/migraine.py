from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from psycopg.rows import dict_row

from services.migraine.episode_contract import MigraineEpisode
from services.migraine.follow_up import (
    apply_follow_up_patch,
    episode_from_canonical,
    patch_matches_episode,
)


UTC = timezone.utc


class MigrainePersistenceError(RuntimeError):
    """Base error for migraine episode-detail persistence."""


class MigraineEpisodeNotFound(MigrainePersistenceError):
    pass


class MigraineDetailUnavailable(MigrainePersistenceError):
    pass


class StaleMigraineRevision(MigrainePersistenceError):
    pass


class MigraineImportConflict(MigrainePersistenceError):
    pass


@dataclass(frozen=True)
class ImportReversalResult:
    import_run_id: str
    user_id: str
    deleted_episode_ids: tuple[str, ...]
    preserved_episode_ids: tuple[str, ...]
    affected_started_at: tuple[str, ...]


def _uuid_text(value: UUID | str) -> str:
    return str(value)


def _utc_iso(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()


def _payload_json(episode: MigraineEpisode) -> str:
    return json.dumps(episode.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)


def _stored_payload(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    payload = row.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise MigrainePersistenceError("stored migraine detail payload is invalid")
    return payload


def _validate_committed_episode(episode: MigraineEpisode) -> None:
    if episode.symptom_event_id is None:
        raise MigrainePersistenceError("committed migraine details require symptom_event_id")


async def fetch_migraine_episode_detail(conn, user_id: str, episode_id: str) -> Optional[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select episode_id,
                   user_id,
                   symptom_event_id,
                   schema_version,
                   revision,
                   payload,
                   user_edited_at,
                   retained_after_import_reversal_at,
                   created_at,
                   updated_at
              from raw.user_migraine_episode_details
             where episode_id = %s
               and user_id = %s
             limit 1
            """,
            (episode_id, user_id),
            prepare=False,
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def migraine_detail_capability_available(conn) -> bool:
    """Return whether the additive detail + audit tables are installed.

    Old symptom and follow-up routes do not call this check, so they remain
    independent while the additive migration is unapplied.
    """

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select to_regclass('raw.user_migraine_episode_details') is not null
                   and to_regclass('raw.user_migraine_episode_detail_revisions') is not null
                   as available
            """,
            prepare=False,
        )
        row = await cur.fetchone()
    return bool(row and row.get("available"))


async def _fetch_canonical_migraine_episode(
    conn,
    user_id: str,
    episode_id: str,
    *,
    for_update: bool = False,
) -> dict[str, Any]:
    lock_clause = "for update" if for_update else ""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            select id,
                   user_id,
                   symptom_event_id,
                   symptom_code,
                   started_at,
                   current_state,
                   original_severity,
                   current_severity,
                   resolution_ts,
                   last_interaction_at,
                   state_updated_at,
                   latest_note_text,
                   source,
                   created_at,
                   updated_at
              from raw.user_symptom_episodes
             where id = %s
               and user_id = %s
               and lower(symptom_code) = 'migraine'
             limit 1
             {lock_clause}
            """,
            (episode_id, user_id),
            prepare=False,
        )
        row = await cur.fetchone()
    if not row:
        raise MigraineEpisodeNotFound("migraine episode not found for user")
    return dict(row)


async def _fetch_locked_migraine_detail(conn, user_id: str, episode_id: str) -> Optional[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select episode_id,
                   user_id,
                   symptom_event_id,
                   schema_version,
                   revision,
                   payload,
                   user_edited_at,
                   retained_after_import_reversal_at,
                   created_at,
                   updated_at
              from raw.user_migraine_episode_details
             where episode_id = %s
               and user_id = %s
             limit 1
             for update
            """,
            (episode_id, user_id),
            prepare=False,
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def load_migraine_follow_up_detail(conn, user_id: str, episode_id: str) -> dict[str, Any]:
    if not await migraine_detail_capability_available(conn):
        raise MigraineDetailUnavailable("structured migraine detail storage is not installed")
    canonical = await _fetch_canonical_migraine_episode(conn, user_id, episode_id)
    stored = await fetch_migraine_episode_detail(conn, user_id, episode_id)
    episode = episode_from_canonical(canonical, _stored_payload(stored))
    return {
        "episode": episode,
        "revision": int(stored.get("revision") or 0) if stored else 0,
        "changed": False,
    }


async def prepare_migraine_follow_up_detail(
    conn,
    user_id: str,
    episode_id: str,
    *,
    expected_revision: int,
    changes: dict[str, Any],
    supplied_fields: set[str],
) -> dict[str, Any]:
    """Lock and validate a structured edit before adjacent prompt writes."""

    if expected_revision < 0:
        raise ValueError("expected_revision cannot be negative")
    if not await migraine_detail_capability_available(conn):
        raise MigraineDetailUnavailable("structured migraine detail storage is not installed")

    canonical = await _fetch_canonical_migraine_episode(
        conn,
        user_id,
        episode_id,
        for_update=True,
    )
    stored = await _fetch_locked_migraine_detail(conn, user_id, episode_id)
    current_revision = int(stored.get("revision") or 0) if stored else 0
    base = episode_from_canonical(canonical, _stored_payload(stored))

    if current_revision != expected_revision:
        if current_revision == expected_revision + 1 and patch_matches_episode(
            base,
            changes,
            supplied_fields,
        ):
            return {
                "episode": base,
                "revision": current_revision,
                "changed": False,
            }
        raise StaleMigraineRevision(
            f"stale migraine detail revision: expected {expected_revision}, stored {current_revision}"
        )

    return {
        "episode": base,
        "revision": current_revision,
        "changed": True,
    }


async def save_migraine_follow_up_detail(
    conn,
    user_id: str,
    episode_id: str,
    *,
    expected_revision: int,
    changes: dict[str, Any],
    supplied_fields: set[str],
    canonical_fields: set[str],
    occurred_at: Optional[datetime] = None,
    source: str = "follow_up",
) -> dict[str, Any]:
    """Save a structured edit while preserving canonical identity and onset.

    Callers must provide an outer transaction when this write is combined with
    prompt response/scheduling work.  ``persist_migraine_episode_detail`` uses
    a nested transaction/savepoint for the detail + audit pair.
    """

    prepared = await prepare_migraine_follow_up_detail(
        conn,
        user_id,
        episode_id,
        expected_revision=expected_revision,
        changes=changes,
        supplied_fields=supplied_fields,
    )
    current_revision = int(prepared["revision"])
    base = prepared["episode"]
    if not prepared["changed"]:
        return prepared

    next_episode = apply_follow_up_patch(
        base,
        changes,
        supplied_fields,
        revision=current_revision + 1,
        occurred_at=occurred_at,
    )

    fields_to_project = set(canonical_fields) & {"state", "notes"}
    if fields_to_project:
        from app.db import symptoms as symptoms_db

        await symptoms_db.record_symptom_episode_update(
            conn,
            user_id,
            episode_id,
            state=str(changes["state"]) if "state" in fields_to_project else None,
            note_text=changes.get("notes") if "notes" in fields_to_project else None,
            clear_note="notes" in fields_to_project and changes.get("notes") is None,
            occurred_at=occurred_at,
            source=source,
            metadata={
                "structured_migraine_revision": current_revision + 1,
                "structured_fields": sorted(supplied_fields),
            },
        )

    stored_result = await persist_migraine_episode_detail(
        conn,
        user_id,
        next_episode,
        expected_revision=current_revision,
        change_kind="user_edit",
        source=source,
        user_edit=True,
    )
    return {
        "episode": next_episode,
        "revision": int(stored_result.get("revision") or next_episode.lifecycle.revision),
        "changed": True,
    }


async def persist_migraine_episode_detail(
    conn,
    user_id: str,
    episode: MigraineEpisode,
    *,
    expected_revision: int,
    change_kind: str,
    source: str,
    user_edit: bool = False,
) -> dict[str, Any]:
    """Insert or update a detail snapshot and its audit row atomically.

    ``expected_revision`` is zero for the first stored snapshot. Updates must
    submit exactly the next contract lifecycle revision.
    """

    _validate_committed_episode(episode)
    if expected_revision < 0:
        raise ValueError("expected_revision cannot be negative")
    if change_kind not in {"created", "user_edit", "import_commit"}:
        raise ValueError("unsupported migraine detail change_kind")
    if user_edit and change_kind != "user_edit":
        raise ValueError("user_edit requires change_kind='user_edit'")

    episode_id = _uuid_text(episode.episode_id)
    symptom_event_id = _uuid_text(episode.symptom_event_id)
    supplied_revision = episode.lifecycle.revision
    if expected_revision == 0:
        if supplied_revision < 1:
            raise StaleMigraineRevision("initial migraine detail revision must be positive")
    elif supplied_revision != expected_revision + 1:
        raise StaleMigraineRevision(
            f"expected contract revision {expected_revision + 1}, received {supplied_revision}"
        )

    payload_json = _payload_json(episode)

    async with conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select id, user_id, symptom_event_id, symptom_code, started_at
                  from raw.user_symptom_episodes
                 where id = %s
                   and user_id = %s
                   and symptom_event_id = %s
                   and lower(symptom_code) = 'migraine'
                 for update
                """,
                (episode_id, user_id, symptom_event_id),
                prepare=False,
            )
            parent = await cur.fetchone()
            if not parent:
                raise MigraineEpisodeNotFound("migraine episode not found for user")

            parent_started_at = parent.get("started_at")
            if parent_started_at is None or _utc_iso(parent_started_at) != _utc_iso(episode.start.utc):
                raise MigrainePersistenceError("contract start must match canonical episode onset")

            await cur.execute(
                """
                select revision
                  from raw.user_migraine_episode_details
                 where episode_id = %s
                   and user_id = %s
                 for update
                """,
                (episode_id, user_id),
                prepare=False,
            )
            current = await cur.fetchone()

            if current is None:
                if expected_revision != 0:
                    raise StaleMigraineRevision("migraine detail does not exist at expected revision")
                await cur.execute(
                    """
                    insert into raw.user_migraine_episode_details (
                        episode_id,
                        user_id,
                        symptom_event_id,
                        schema_version,
                        revision,
                        payload,
                        user_edited_at
                    ) values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                    returning episode_id, user_id, symptom_event_id, schema_version,
                              revision, payload, user_edited_at,
                              retained_after_import_reversal_at, created_at, updated_at
                    """,
                    (
                        episode_id,
                        user_id,
                        symptom_event_id,
                        episode.schema_version,
                        supplied_revision,
                        payload_json,
                        datetime.now(UTC) if user_edit else None,
                    ),
                    prepare=False,
                )
            else:
                current_revision = int(current.get("revision") or 0)
                if current_revision != expected_revision:
                    raise StaleMigraineRevision(
                        f"stale migraine detail revision: expected {expected_revision}, stored {current_revision}"
                    )
                await cur.execute(
                    """
                    update raw.user_migraine_episode_details
                       set schema_version = %s,
                           revision = %s,
                           payload = %s::jsonb,
                           user_edited_at = case when %s then now() else user_edited_at end
                     where episode_id = %s
                       and user_id = %s
                       and symptom_event_id = %s
                       and revision = %s
                 returning episode_id, user_id, symptom_event_id, schema_version,
                           revision, payload, user_edited_at,
                           retained_after_import_reversal_at, created_at, updated_at
                    """,
                    (
                        episode.schema_version,
                        supplied_revision,
                        payload_json,
                        user_edit,
                        episode_id,
                        user_id,
                        symptom_event_id,
                        expected_revision,
                    ),
                    prepare=False,
                )

            stored = await cur.fetchone()
            if not stored:
                raise StaleMigraineRevision("migraine detail changed during update")

            await cur.execute(
                """
                insert into raw.user_migraine_episode_detail_revisions (
                    episode_id,
                    user_id,
                    symptom_event_id,
                    revision,
                    payload,
                    change_kind,
                    source
                ) values (%s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    episode_id,
                    user_id,
                    symptom_event_id,
                    supplied_revision,
                    payload_json,
                    change_kind,
                    source,
                ),
                prepare=False,
            )

    return dict(stored)


async def _require_time_correction_capability(conn) -> None:
    if not await migraine_detail_capability_available(conn):
        raise MigraineDetailUnavailable("structured migraine detail storage is not installed")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("""select count(*) = 2
              and to_regclass('raw.user_symptom_events_effective') is not null
              and to_regclass('marts.symptom_daily_effective') is not null as available
            from information_schema.columns
            where table_schema = 'raw' and table_name = 'user_migraine_episode_detail_revisions'
              and column_name in ('correction_request_id', 'time_correction')""", prepare=False)
        row = await cur.fetchone()
    if not row or not row["available"]:
        raise MigraineDetailUnavailable("migraine time correction storage is not installed")


def _time_context(canonical, episode, revision):
    end = canonical.get("resolution_ts")
    invalid = end is not None and (canonical["current_state"] != "resolved" or end < canonical["started_at"])
    return {"episode": episode, "revision": revision,
            "canonical_updated_at": _utc_iso(canonical["updated_at"]),
            "raw_end_utc": _utc_iso(end) if end else None,
            "inconsistent_end": invalid}


async def load_migraine_time_context(conn, user_id: str, episode_id: str) -> dict:
    await _require_time_correction_capability(conn)
    canonical = await _fetch_canonical_migraine_episode(conn, user_id, episode_id, for_update=True)
    stored = await fetch_migraine_episode_detail(conn, user_id, episode_id)
    return _time_context(canonical, episode_from_canonical(canonical, _stored_payload(stored)),
                         int(stored["revision"]) if stored else 0)


async def save_migraine_time_correction(conn, user_id: str, episode_id: str, correction) -> dict:
    """Caller owns the outer transaction, including reminder reconciliation."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from services.migraine.episode_contract import EpisodeTimestamp
    from app.db import feedback as feedback_db

    await _require_time_correction_capability(conn)
    canonical = await _fetch_canonical_migraine_episode(conn, user_id, episode_id, for_update=True)
    stored = await _fetch_locked_migraine_detail(conn, user_id, episode_id)
    current_revision = int(stored["revision"]) if stored else 0
    request = correction.canonical_request()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("""select episode_id, revision, payload, time_correction
            from raw.user_migraine_episode_detail_revisions
            where user_id = %s and correction_request_id = %s""",
            (user_id, correction.request_id), prepare=False)
        receipt = await cur.fetchone()
    if receipt:
        metadata = receipt["time_correction"]
        if str(receipt["episode_id"]) != episode_id or metadata["request"] != request:
            raise StaleMigraineRevision("Correction request ID was already used with different content")
        return {**metadata["acknowledgement"], "episode": MigraineEpisode.model_validate(receipt["payload"]),
                "current_revision": current_revision, "current_canonical_updated_at": _utc_iso(canonical["updated_at"]), "replayed": True,
                "refresh_days": metadata["refresh_days"], "pattern_since_day": metadata["pattern_since_day"]}
    if current_revision != correction.expected_revision or canonical["updated_at"] != correction.expected_canonical_updated_at:
        raise StaleMigraineRevision("The saved episode changed. Reload its saved version before applying your correction")

    stored_payload = _stored_payload(stored)
    base = episode_from_canonical(canonical, stored_payload)
    payload = base.model_dump(mode="python")
    fields = correction.model_fields_set
    if "start" in fields:
        payload["start"] = correction.start.model_dump(mode="python")
    if "state" in fields:
        payload["state"] = correction.state
    if "end" in fields:
        payload["end"] = correction.end.model_dump(mode="python") if correction.end else None
    elif canonical.get("resolution_ts") is not None:
        # Preserve the actual retained end even if the old detail had to display
        # it as unknown. A corrected onset may repair its chronological order.
        original_end = dict((stored_payload or {}).get("end") or {})
        original_end.update(utc=canonical["resolution_ts"])
        original_end.setdefault("timezone_source", "unknown")
        payload["end"] = EpisodeTimestamp.model_validate(original_end).model_dump(mode="python")
    now = datetime.now(UTC)
    payload["lifecycle"].update(revision=current_revision + 1, updated_at=now)
    episode = MigraineEpisode.model_validate(payload)
    if episode.start.utc > now + timedelta(minutes=5) or (episode.end and episode.end.utc > now + timedelta(minutes=5)):
        raise ValueError("Corrected start/end cannot be in the future")
    old_timing = {"start": base.start.model_dump(mode="json"),
                  "end": base.end.model_dump(mode="json") if base.end else None, "state": base.state}
    new_timing = {"start": episode.start.model_dump(mode="json"),
                  "end": episode.end.model_dump(mode="json") if episode.end else None, "state": episode.state}
    if old_timing == new_timing and not _time_context(canonical, base, current_revision)["inconsistent_end"]:
        raise ValueError("No time or state changes to save")

    before = {key: _utc_iso(value) if isinstance(value, datetime) else value
              for key, value in canonical.items() if key in
              {"started_at", "resolution_ts", "current_state", "updated_at", "state_updated_at", "last_interaction_at"}}
    before["stored_start_provenance"] = (stored_payload or {}).get("start")
    before["stored_end_provenance"] = (stored_payload or {}).get("end")
    state_changed = episode.state != canonical["current_state"]
    interaction = now if state_changed else canonical["last_interaction_at"]
    state_time = now if state_changed else canonical["state_updated_at"]
    if not state_changed and interaction == canonical["started_at"]:
        interaction = episode.start.utc
    if not state_changed and state_time == canonical["started_at"]:
        state_time = episode.start.utc
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("""update raw.user_symptom_episodes
            set started_at = %s, resolution_ts = %s, current_state = %s,
                state_updated_at = %s, last_interaction_at = %s, updated_at = now()
            where id = %s and user_id = %s returning *""",
            (episode.start.utc, episode.end.utc if episode.end else None, episode.state,
             state_time, interaction, episode_id, user_id), prepare=False)
        after = dict(await cur.fetchone())
    await persist_migraine_episode_detail(conn, user_id, episode, expected_revision=current_revision,
                                          change_kind="user_edit", source="time_correction", user_edit=True)
    await feedback_db.reconcile_migraine_time_correction(conn, user_id, before=canonical, after=after, now=now)
    instants = [canonical["started_at"], canonical.get("resolution_ts"), canonical["last_interaction_at"],
                episode.start.utc, episode.end.utc if episode.end else None, interaction]
    # Future inconsistent source times have no computed current-day history.
    instants = [value for value in instants if value is not None and value <= now]
    days = sorted({value.astimezone(ZoneInfo("America/Chicago")).date().isoformat() for value in instants})
    pattern_since = min([value.astimezone(UTC).date() for value in instants] + [(now - timedelta(days=89)).date()]).isoformat()
    ack = {**_time_context(after, episode, current_revision + 1), "request_id": str(correction.request_id),
           "applied_revision": current_revision + 1, "current_revision": current_revision + 1,
           "current_canonical_updated_at": _utc_iso(after["updated_at"]), "replayed": False}
    metadata = {"request": request, "before": before, "after": new_timing,
                "acknowledgement": {k: v for k, v in ack.items() if k != "episode"},
                "refresh_days": days, "pattern_since_day": pattern_since}
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("""update raw.user_migraine_episode_detail_revisions
            set correction_request_id = %s, time_correction = %s::jsonb
            where episode_id = %s and user_id = %s and revision = %s""",
            (correction.request_id, json.dumps(metadata), episode_id, user_id, current_revision + 1), prepare=False)
    return {**ack, "refresh_days": days, "pattern_since_day": pattern_since}


async def create_migraine_import_run(
    conn,
    user_id: str,
    *,
    import_run_id: str,
    source_provider: str,
    source_file_hash: str,
    mapping_version: str,
) -> dict[str, Any]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            insert into raw.user_migraine_import_runs (
                id, user_id, source_provider, source_file_hash, mapping_version
            ) values (%s, %s, %s, lower(%s), %s)
            on conflict (id) do nothing
            returning id, user_id, source_provider, source_file_hash,
                      mapping_version, status, created_at, committed_at, reversed_at
            """,
            (import_run_id, user_id, source_provider, source_file_hash, mapping_version),
            prepare=False,
        )
        row = await cur.fetchone()
    if not row:
        raise MigraineImportConflict("import run ID already exists")
    return dict(row)


async def find_migraine_episode_by_import_identity(
    conn,
    user_id: str,
    *,
    source_provider: str,
    source_identity_key: str,
) -> Optional[dict[str, Any]]:
    """Resolve a clinical episode independently of file hash or run ID."""

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select i.episode_id,
                   i.symptom_event_id,
                   i.first_external_event_id as external_event_id,
                   i.first_seen_at,
                   i.last_seen_at,
                   ep.started_at
              from raw.user_migraine_import_identities i
              join raw.user_symptom_episodes ep
                on ep.id = i.episode_id
               and ep.user_id = i.user_id
               and ep.symptom_event_id = i.symptom_event_id
             where i.user_id = %s
               and i.source_provider = %s
               and i.source_identity_key = %s
             limit 1
            """,
            (user_id, source_provider, source_identity_key),
            prepare=False,
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def commit_migraine_import_episode(
    conn,
    user_id: str,
    episode: MigraineEpisode,
    *,
    source_identity_key: str,
    expected_revision: int = 0,
) -> dict[str, Any]:
    """Commit details + provenance link for an already-created canonical episode.

    Import adapters must call ``find_migraine_episode_by_import_identity`` before
    creating an onset event. This method rechecks that identity under a
    transaction and rejects a different candidate rather than duplicating it.
    """

    _validate_committed_episode(episode)
    provenance = episode.provenance
    if provenance.source_type != "import":
        raise MigrainePersistenceError("import commit requires import provenance")

    run_id = _uuid_text(provenance.import_run_id)
    episode_id = _uuid_text(episode.episode_id)
    event_id = _uuid_text(episode.symptom_event_id)

    async with conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select id, user_id, source_provider, source_file_hash,
                       mapping_version, status
                  from raw.user_migraine_import_runs
                 where id = %s
                   and user_id = %s
                 for update
                """,
                (run_id, user_id),
                prepare=False,
            )
            run = await cur.fetchone()
            if not run:
                raise MigraineImportConflict("import run not found for user")
            if run.get("status") == "reversed":
                raise MigraineImportConflict("reversed import run cannot be committed")
            if (
                run.get("source_provider") != provenance.source_provider
                or run.get("source_file_hash") != provenance.source_file_hash
                or run.get("mapping_version") != provenance.mapping_version
            ):
                raise MigraineImportConflict("import provenance does not match its run")

            identity_lock_key = "\x1f".join(
                (user_id, str(provenance.source_provider), source_identity_key)
            )
            await cur.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (identity_lock_key,),
                prepare=False,
            )

            await cur.execute(
                """
                select episode_id, symptom_event_id
                  from raw.user_migraine_import_identities
                 where user_id = %s
                   and source_provider = %s
                   and source_identity_key = %s
                 limit 1
                 for update
                """,
                (user_id, provenance.source_provider, source_identity_key),
                prepare=False,
            )
            existing_identity = await cur.fetchone()
            if existing_identity and (
                str(existing_identity.get("episode_id")) != episode_id
                or str(existing_identity.get("symptom_event_id")) != event_id
            ):
                raise MigraineImportConflict(
                    "import identity already belongs to another clinical episode"
                )

            await cur.execute(
                """
                select ep.started_at,
                       ep.source as episode_source,
                       e.source as event_source
                  from raw.user_symptom_episodes ep
                  join raw.user_symptom_events e
                    on e.id = ep.symptom_event_id
                   and e.user_id = ep.user_id
                 where ep.id = %s
                   and ep.user_id = %s
                   and ep.symptom_event_id = %s
                 for update of ep, e
                """,
                (episode_id, user_id, event_id),
                prepare=False,
            )
            canonical_parent = await cur.fetchone()
            if not canonical_parent:
                raise MigraineEpisodeNotFound("migraine episode not found for user")
            if _utc_iso(canonical_parent.get("started_at")) != _utc_iso(episode.start.utc):
                raise MigraineImportConflict("import onset does not match the canonical episode")

            origin_source = f"import:{run_id}"
            canonical_origin_run_id = (
                run_id
                if canonical_parent.get("episode_source") == origin_source
                and canonical_parent.get("event_source") == origin_source
                else None
            )

            await cur.execute(
                """
                select d.episode_id,
                       d.user_id,
                       d.symptom_event_id,
                       d.schema_version,
                       d.revision,
                       d.payload,
                       d.user_edited_at,
                       d.retained_after_import_reversal_at,
                       d.created_at,
                       d.updated_at
                  from raw.user_migraine_episode_details d
                 where d.episode_id = %s
                   and d.user_id = %s
                   and d.symptom_event_id = %s
                 for update
                """,
                (episode_id, user_id, event_id),
                prepare=False,
            )
            existing_detail = await cur.fetchone()

        if existing_detail:
            stored = dict(existing_detail)
        else:
            stored = await persist_migraine_episode_detail(
                conn,
                user_id,
                episode,
                expected_revision=expected_revision,
                change_kind="import_commit",
                source=f"import:{provenance.source_provider}",
            )

        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                insert into raw.user_migraine_import_identities (
                    user_id,
                    source_provider,
                    source_identity_key,
                    episode_id,
                    symptom_event_id,
                    first_external_event_id,
                    canonical_origin_import_run_id,
                    canonical_origin_proof
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (user_id, source_provider, source_identity_key)
                do update set last_seen_at = now()
                  where raw.user_migraine_import_identities.episode_id = excluded.episode_id
                    and raw.user_migraine_import_identities.symptom_event_id = excluded.symptom_event_id
                returning id, episode_id, symptom_event_id, first_seen_at, last_seen_at
                """,
                (
                    user_id,
                    provenance.source_provider,
                    source_identity_key,
                    episode_id,
                    event_id,
                    provenance.external_event_id,
                    canonical_origin_run_id,
                    "canonical_sources_match_run" if canonical_origin_run_id else None,
                ),
                prepare=False,
            )
            identity = await cur.fetchone()
            if not identity:
                raise MigraineImportConflict(
                    "import identity changed during commit"
                )

            await cur.execute(
                """
                insert into raw.user_migraine_episode_import_links (
                    import_run_id,
                    user_id,
                    episode_id,
                    symptom_event_id,
                    source_provider,
                    external_event_id,
                    source_identity_key,
                    source_file_hash,
                    raw_row_ref,
                    mapping_version
                ) values (%s, %s, %s, %s, %s, %s, %s, lower(%s), %s, %s)
                on conflict (user_id, import_run_id, source_provider, source_identity_key)
                do update set source_identity_key = excluded.source_identity_key
                returning id, import_run_id, episode_id, symptom_event_id, linked_at
                """,
                (
                    run_id,
                    user_id,
                    episode_id,
                    event_id,
                    provenance.source_provider,
                    provenance.external_event_id,
                    source_identity_key,
                    provenance.source_file_hash,
                    provenance.raw_row_ref,
                    provenance.mapping_version,
                ),
                prepare=False,
            )
            link = await cur.fetchone()
            await cur.execute(
                """
                update raw.user_migraine_import_runs
                   set status = 'committed',
                       committed_at = coalesce(committed_at, now())
                 where id = %s
                   and user_id = %s
                   and status in ('preview', 'committed')
                """,
                (run_id, user_id),
                prepare=False,
            )

    return {
        "detail": stored,
        "identity": dict(identity),
        "link": dict(link) if link else None,
    }


async def reverse_migraine_import_run(conn, user_id: str, import_run_id: str) -> ImportReversalResult:
    """Reverse one committed run without deleting user-edited episodes."""

    deleted_ids: list[str] = []
    preserved_ids: list[str] = []
    affected_times: list[str] = []

    async with conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select id, status
                  from raw.user_migraine_import_runs
                 where id = %s
                   and user_id = %s
                 for update
                """,
                (import_run_id, user_id),
                prepare=False,
            )
            run = await cur.fetchone()
            if not run:
                raise MigraineImportConflict("import run not found for user")
            if run.get("status") == "reversed":
                return ImportReversalResult(import_run_id, user_id, (), (), ())
            if run.get("status") != "committed":
                raise MigraineImportConflict("only a committed import run can be reversed")

            await cur.execute(
                """
                select l.episode_id,
                       l.symptom_event_id,
                       ep.started_at,
                       d.revision,
                       d.user_edited_at,
                       (
                         select origin.canonical_origin_import_run_id
                           from raw.user_migraine_import_identities origin
                          where origin.user_id = l.user_id
                            and origin.episode_id = l.episode_id
                            and origin.symptom_event_id = l.symptom_event_id
                            and origin.canonical_origin_import_run_id is not null
                          order by origin.first_seen_at
                          limit 1
                       ) as canonical_origin_import_run_id,
                       exists (
                         select 1
                           from raw.user_symptom_episode_updates u
                          where u.episode_id = l.episode_id
                            and u.user_id = l.user_id
                            and u.update_kind <> 'logged'
                            and lower(coalesce(u.source, '')) not like 'import:%%'
                       ) as has_user_history
                  from raw.user_migraine_episode_import_links l
                  join raw.user_symptom_episodes ep
                    on ep.id = l.episode_id
                   and ep.user_id = l.user_id
                   and ep.symptom_event_id = l.symptom_event_id
                  join raw.user_migraine_import_identities i
                    on i.user_id = l.user_id
                   and i.source_provider = l.source_provider
                   and i.source_identity_key = l.source_identity_key
                   and i.episode_id = l.episode_id
                   and i.symptom_event_id = l.symptom_event_id
                  left join raw.user_migraine_episode_details d
                    on d.episode_id = l.episode_id
                   and d.user_id = l.user_id
                   and d.symptom_event_id = l.symptom_event_id
                 where l.import_run_id = %s
                   and l.user_id = %s
                 order by l.episode_id
                 for update of l, ep
                """,
                (import_run_id, user_id),
                prepare=False,
            )
            links = list(await cur.fetchall())

            await cur.execute(
                """
                delete from raw.user_migraine_episode_import_links
                 where import_run_id = %s
                   and user_id = %s
                """,
                (import_run_id, user_id),
                prepare=False,
            )

            for link in links:
                episode_id = str(link.get("episode_id"))
                event_id = str(link.get("symptom_event_id"))
                started_at = link.get("started_at")
                if started_at is not None:
                    affected_times.append(_utc_iso(started_at))

                # The link/episode lock above can wait behind a user edit. Under
                # READ COMMITTED, the statement that waited keeps its original
                # snapshot, so re-read protection state after the lock is held.
                # This prevents a just-committed note/state/follow-up or detail
                # edit from being missed by reversal.
                await cur.execute(
                    """
                    select d.revision,
                           d.user_edited_at,
                           (
                             select origin.canonical_origin_import_run_id
                               from raw.user_migraine_import_identities origin
                              where origin.user_id = ep.user_id
                                and origin.episode_id = ep.id
                                and origin.symptom_event_id = ep.symptom_event_id
                                and origin.canonical_origin_import_run_id is not null
                              order by origin.first_seen_at
                              limit 1
                           ) as canonical_origin_import_run_id,
                           exists (
                             select 1
                               from raw.user_symptom_episode_updates u
                              where u.episode_id = ep.id
                                and u.user_id = ep.user_id
                                and u.update_kind <> 'logged'
                                and lower(coalesce(u.source, '')) not like 'import:%%'
                           ) as has_user_history
                      from raw.user_symptom_episodes ep
                      left join raw.user_migraine_episode_details d
                        on d.episode_id = ep.id
                       and d.user_id = ep.user_id
                       and d.symptom_event_id = ep.symptom_event_id
                     where ep.id = %s
                       and ep.user_id = %s
                       and ep.symptom_event_id = %s
                    """,
                    (episode_id, user_id, event_id),
                    prepare=False,
                )
                protection = await cur.fetchone() or {}

                await cur.execute(
                    """
                    select 1
                      from raw.user_migraine_episode_import_links
                     where user_id = %s
                       and episode_id = %s
                     limit 1
                    """,
                    (user_id, episode_id),
                    prepare=False,
                )
                has_other_import = await cur.fetchone() is not None

                if (
                    has_other_import
                    or protection.get("user_edited_at") is not None
                    or bool(protection.get("has_user_history"))
                    or protection.get("canonical_origin_import_run_id") is None
                ):
                    preserved_ids.append(episode_id)
                    if protection.get("revision") is not None and not has_other_import:
                        await cur.execute(
                            """
                            update raw.user_migraine_episode_details
                               set revision = revision + 1,
                                   payload = jsonb_set(
                                     jsonb_set(
                                       payload,
                                       '{lifecycle,revision}',
                                       to_jsonb(revision + 1),
                                       false
                                     ),
                                     '{lifecycle,updated_at}',
                                     to_jsonb(to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
                                     false
                                   ),
                                   retained_after_import_reversal_at = now()
                             where episode_id = %s
                               and user_id = %s
                               and symptom_event_id = %s
                         returning revision, payload
                            """,
                            (episode_id, user_id, event_id),
                            prepare=False,
                        )
                        retained = await cur.fetchone()
                        if retained:
                            await cur.execute(
                                """
                                insert into raw.user_migraine_episode_detail_revisions (
                                    episode_id, user_id, symptom_event_id, revision,
                                    payload, change_kind, source
                                ) values (%s, %s, %s, %s, %s::jsonb,
                                          'import_reversal_retained', 'import_reversal')
                                """,
                                (
                                    episode_id,
                                    user_id,
                                    event_id,
                                    retained.get("revision"),
                                    json.dumps(retained.get("payload"), separators=(",", ":"), sort_keys=True),
                                ),
                                prepare=False,
                            )
                    continue

                await cur.execute(
                    """
                    delete from raw.user_symptom_events e
                          using raw.user_symptom_episodes ep
                     where ep.id = %s
                       and ep.user_id = %s
                       and ep.symptom_event_id = %s
                       and e.id = ep.symptom_event_id
                       and e.user_id = ep.user_id
                 returning ep.id
                    """,
                    (episode_id, user_id, event_id),
                    prepare=False,
                )
                if await cur.fetchone():
                    deleted_ids.append(episode_id)

            await cur.execute(
                """
                update raw.user_migraine_import_runs
                   set status = 'reversed',
                       reversed_at = now()
                 where id = %s
                   and user_id = %s
                   and status = 'committed'
                """,
                (import_run_id, user_id),
                prepare=False,
            )

    return ImportReversalResult(
        import_run_id=import_run_id,
        user_id=user_id,
        deleted_episode_ids=tuple(deleted_ids),
        preserved_episode_ids=tuple(preserved_ids),
        affected_started_at=tuple(dict.fromkeys(affected_times)),
    )
