from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from services.migraine.episode_contract import EarlySign, MedicineTaken
from services.migraine.follow_up import (
    apply_follow_up_patch,
    episode_from_canonical,
    patch_matches_episode,
)


START = datetime(2026, 9, 8, 12, tzinfo=UTC)


def canonical(**overrides):
    value = {
        "id": uuid4(),
        "user_id": uuid4(),
        "symptom_event_id": uuid4(),
        "symptom_code": "migraine",
        "started_at": START,
        "current_state": "ongoing",
        "original_severity": 5,
        "current_severity": 5,
        "resolution_ts": None,
        "latest_note_text": "Initial note",
        "source": "siri",
        "created_at": START,
        "updated_at": START,
    }
    value.update(overrides)
    return value


def test_missing_detail_builds_candidate_without_turning_missing_medicine_into_none_taken() -> None:
    episode = episode_from_canonical(canonical(), None, now=START)

    assert episode.lifecycle.revision == 1
    assert episode.medicines == []
    assert episode.notes == "Initial note"
    assert episode.provenance.source_type == "siri"


def test_partial_patch_retains_unsupplied_fields_and_empty_list_clears() -> None:
    base = episode_from_canonical(canonical(), None, now=START)
    first_sign = EarlySign(label="Visual shimmer")
    medicine = MedicineTaken.model_validate(
        {
            "name": "User-entered medicine",
            "taken_at": {"utc": START, "timezone_source": "user"},
            "reported_relief": None,
        }
    )
    enriched = apply_follow_up_patch(
        base,
        {"early_signs": [first_sign], "medicines": [medicine]},
        {"early_signs", "medicines"},
        revision=1,
        now=START,
    )
    cleared = apply_follow_up_patch(
        enriched,
        {"early_signs": []},
        {"early_signs"},
        revision=2,
        now=START,
    )

    assert cleared.early_signs == []
    assert len(cleared.medicines) == 1
    assert cleared.medicines[0].reported_relief is None


def test_explicit_null_clears_notes_and_resolved_state_sets_end() -> None:
    base = episode_from_canonical(canonical(), None, now=START)
    resolved_at = datetime(2026, 9, 8, 15, tzinfo=UTC)
    result = apply_follow_up_patch(
        base,
        {"notes": None, "state": "resolved"},
        {"notes", "state"},
        revision=1,
        occurred_at=resolved_at,
        now=resolved_at,
    )

    assert result.notes is None
    assert result.state == "resolved"
    assert result.end is not None
    assert result.end.utc == resolved_at


def test_retry_match_compares_user_fields_without_duplicating_medicines() -> None:
    base = episode_from_canonical(canonical(), None, now=START)
    medicine = MedicineTaken.model_validate(
        {
            "name": "User-entered medicine",
            "taken_at": {"utc": START, "timezone_source": "user"},
            "reported_relief": "none",
        }
    )
    saved = apply_follow_up_patch(
        base,
        {"medicines": [medicine]},
        {"medicines"},
        revision=1,
        now=START,
    )

    assert patch_matches_episode(saved, {"medicines": [medicine]}, {"medicines"}) is True
    assert len(saved.medicines) == 1
    assert saved.medicines[0].reported_relief == "none"


def test_worse_remains_a_valid_existing_lifecycle_state() -> None:
    episode = episode_from_canonical(canonical(current_state="worse"), None, now=START)
    assert episode.state == "worse"
