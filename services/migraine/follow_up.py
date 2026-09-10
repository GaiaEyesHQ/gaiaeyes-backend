"""Pure helpers for structured migraine follow-up edits.

The existing symptom event and episode remain canonical.  These helpers only
build or merge the additive structured snapshot; database locking and writes
stay in ``app.db.migraine``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable

from services.migraine.episode_contract import MigraineEpisode


STRUCTURED_FIELDS = frozenset({"state", "early_signs", "contexts", "medicines", "notes"})


def _utc(value: datetime | None, *, fallback: datetime) -> datetime:
    if value is None:
        return fallback.astimezone(UTC)
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC)


def _timestamp(value: datetime, *, source: str = "unknown") -> dict[str, Any]:
    return {
        "utc": value.astimezone(UTC),
        "timezone_source": source,
    }


def _project_timestamp(existing: Any, value: datetime, *, fallback_source: str = "unknown") -> dict[str, Any]:
    projected = dict(existing or {})
    projected["utc"] = value.astimezone(UTC)
    projected.setdefault("timezone_source", fallback_source)
    return projected


def _canonical_state(value: Any) -> str:
    token = str(value or "new").strip().lower()
    if token not in {"new", "ongoing", "improving", "worse", "resolved"}:
        return "new"
    return token


def _source_type(value: Any) -> str:
    token = str(value or "manual").strip().lower()
    if token == "siri":
        return "siri"
    if token == "healthkit":
        return "healthkit"
    if token == "follow_up":
        return "follow_up"
    return "manual"


def episode_from_canonical(
    canonical: dict[str, Any],
    stored_payload: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> MigraineEpisode:
    """Return the structured view with canonical state/timing projected in.

    A missing stored row is represented as a revision-one candidate.  The API
    reports its stored revision separately as zero until the first edit saves
    it.
    """

    current_time = _utc(now, fallback=datetime.now(UTC))
    start = _utc(canonical.get("started_at"), fallback=current_time)
    state = _canonical_state(canonical.get("current_state"))
    resolution = canonical.get("resolution_ts")
    end = _utc(resolution, fallback=current_time) if state == "resolved" and resolution else None
    # Legacy missing/inconsistent ends remain unknown, never invented durations.
    if end is not None and end < start:
        end = None
    severity = canonical.get("current_severity")
    if severity is None:
        severity = canonical.get("original_severity")

    if stored_payload is None:
        source = str(canonical.get("source") or "manual")
        created = _utc(canonical.get("created_at"), fallback=start)
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "episode_id": str(canonical["id"]),
            "symptom_event_id": str(canonical["symptom_event_id"]),
            "symptom_code": "MIGRAINE",
            "state": state,
            "start": _timestamp(start),
            "end": _timestamp(end) if end else None,
            "severity": severity,
            "early_signs": [],
            "contexts": [],
            "medicines": [],
            "notes": canonical.get("latest_note_text"),
            "provenance": {
                "source_type": _source_type(source),
                "source_platform": source,
            },
            "lifecycle": {
                "revision": 1,
                "created_at": created,
                "updated_at": _utc(canonical.get("updated_at"), fallback=created),
            },
        }
    else:
        payload = dict(stored_payload)
        payload["episode_id"] = str(canonical["id"])
        payload["symptom_event_id"] = str(canonical["symptom_event_id"])
        payload["symptom_code"] = "MIGRAINE"
        payload["state"] = state
        payload["start"] = _project_timestamp(payload.get("start"), start)
        payload["end"] = _project_timestamp(payload.get("end"), end) if end else None
        payload["severity"] = severity
        payload["notes"] = canonical.get("latest_note_text")

    return MigraineEpisode.model_validate(payload)


def apply_follow_up_patch(
    base: MigraineEpisode,
    changes: dict[str, Any],
    supplied_fields: Iterable[str],
    *,
    revision: int,
    occurred_at: datetime | None = None,
    now: datetime | None = None,
) -> MigraineEpisode:
    fields = set(supplied_fields) & STRUCTURED_FIELDS
    current_time = _utc(now, fallback=datetime.now(UTC))
    event_time = _utc(occurred_at, fallback=current_time)
    payload = base.model_dump(mode="python")

    for field in ("early_signs", "contexts", "medicines", "notes"):
        if field in fields:
            value = changes.get(field)
            if isinstance(value, list):
                payload[field] = [
                    item.model_dump(mode="python") if hasattr(item, "model_dump") else item
                    for item in value
                ]
            else:
                payload[field] = value

    if "state" in fields:
        next_state = str(changes["state"])
        payload["state"] = next_state
        if next_state == "resolved":
            existing_end = base.end
            payload["end"] = existing_end.model_dump(mode="python") if existing_end else _timestamp(event_time)
        else:
            payload["end"] = None

    lifecycle = dict(payload["lifecycle"])
    lifecycle["revision"] = revision
    lifecycle["updated_at"] = current_time
    payload["lifecycle"] = lifecycle
    return MigraineEpisode.model_validate(payload)


def patch_matches_episode(
    episode: MigraineEpisode,
    changes: dict[str, Any],
    supplied_fields: Iterable[str],
) -> bool:
    """True when a one-revision-behind retry already produced this snapshot."""

    fields = set(supplied_fields) & STRUCTURED_FIELDS
    current = episode.model_dump(mode="json")
    for field in fields:
        value = changes.get(field)
        if isinstance(value, list):
            expected = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
        elif hasattr(value, "model_dump"):
            expected = value.model_dump(mode="json")
        else:
            expected = value
        if current.get(field) != expected:
            return False
    return True
