from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.db.migraine import (
    MigraineEpisodeNotFound,
    MigraineImportConflict,
    StaleMigraineRevision,
    commit_migraine_import_episode,
    find_migraine_episode_by_import_identity,
    persist_migraine_episode_detail,
    reverse_migraine_import_run,
)
from services.migraine.episode_contract import MigraineEpisode


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "migraine_episode_contract"
UTC = timezone.utc


class ScriptedTransaction:
    def __init__(self, connection: "ScriptedConnection") -> None:
        self.connection = connection

    async def __aenter__(self):
        self.connection.transaction_depth += 1
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.connection.transaction_depth -= 1
        self.connection.transaction_exits.append(exc_type)
        return False


class ScriptedCursor:
    def __init__(self, connection: "ScriptedConnection") -> None:
        self.connection = connection
        self.response: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, query, params=(), **kwargs):
        if not self.connection.script:
            raise AssertionError(f"unexpected SQL: {query}")
        self.response = self.connection.script.pop(0)
        self.connection.calls.append((" ".join(str(query).split()), tuple(params)))
        error = self.response.get("raise")
        if error is not None:
            raise error

    async def fetchone(self):
        return self.response.get("one")

    async def fetchall(self):
        return self.response.get("all", [])


class ScriptedConnection:
    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, tuple]] = []
        self.transaction_depth = 0
        self.transaction_exits: list[type[BaseException] | None] = []

    def transaction(self):
        return ScriptedTransaction(self)

    def cursor(self, **kwargs):
        return ScriptedCursor(self)


def load_episode(name: str = "live_siri_episode.json", *, revision: int | None = None) -> MigraineEpisode:
    payload = json.loads((FIXTURES / name).read_text())
    if revision is not None:
        payload["lifecycle"]["revision"] = revision
    return MigraineEpisode.model_validate(payload)


def parent_for(episode: MigraineEpisode) -> dict:
    return {
        "id": episode.episode_id,
        "user_id": "user-a",
        "symptom_event_id": episode.symptom_event_id,
        "symptom_code": "migraine",
        "started_at": episode.start.utc,
    }


@pytest.mark.anyio
async def test_persist_rejects_cross_account_or_wrong_parent_before_write() -> None:
    episode = load_episode()
    conn = ScriptedConnection([{"one": None}])

    with pytest.raises(MigraineEpisodeNotFound, match="not found for user"):
        await persist_migraine_episode_detail(
            conn,
            "user-b",
            episode,
            expected_revision=0,
            change_kind="created",
            source="ios",
        )

    assert len(conn.calls) == 1
    assert conn.calls[0][1][1] == "user-b"
    assert conn.transaction_exits == [MigraineEpisodeNotFound]


@pytest.mark.anyio
async def test_persist_rejects_stale_revision_without_update_or_audit() -> None:
    episode = load_episode(revision=3)
    conn = ScriptedConnection(
        [
            {"one": parent_for(episode)},
            {"one": {"revision": 4}},
        ]
    )

    with pytest.raises(StaleMigraineRevision, match="stored 4"):
        await persist_migraine_episode_detail(
            conn,
            "user-a",
            episode,
            expected_revision=2,
            change_kind="user_edit",
            source="ios",
            user_edit=True,
        )

    assert len(conn.calls) == 2
    assert conn.transaction_exits == [StaleMigraineRevision]


@pytest.mark.anyio
async def test_owner_edit_updates_exact_revision_and_appends_audit() -> None:
    episode = load_episode(revision=3)
    stored = {
        "episode_id": episode.episode_id,
        "user_id": "user-a",
        "symptom_event_id": episode.symptom_event_id,
        "revision": 3,
        "user_edited_at": datetime(2026, 9, 1, tzinfo=UTC),
    }
    conn = ScriptedConnection(
        [
            {"one": parent_for(episode)},
            {"one": {"revision": 2}},
            {"one": stored},
            {},
        ]
    )

    result = await persist_migraine_episode_detail(
        conn,
        "user-a",
        episode,
        expected_revision=2,
        change_kind="user_edit",
        source="ios",
        user_edit=True,
    )

    assert result["revision"] == 3
    update_call = next(call for call in conn.calls if "update raw.user_migraine_episode_details" in call[0])
    assert update_call[1][-3:] == ("user-a", str(episode.symptom_event_id), 2)
    assert any("insert into raw.user_migraine_episode_detail_revisions" in sql for sql, _ in conn.calls)
    assert conn.transaction_exits == [None]


@pytest.mark.anyio
async def test_detail_and_audit_share_one_atomic_transaction() -> None:
    episode = load_episode()
    stored = {
        "episode_id": episode.episode_id,
        "user_id": "user-a",
        "symptom_event_id": episode.symptom_event_id,
        "revision": episode.lifecycle.revision,
    }
    conn = ScriptedConnection(
        [
            {"one": parent_for(episode)},
            {"one": None},
            {"one": stored},
            {"raise": RuntimeError("audit unavailable")},
        ]
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await persist_migraine_episode_detail(
            conn,
            "user-a",
            episode,
            expected_revision=0,
            change_kind="created",
            source="ios",
        )

    assert conn.transaction_exits == [RuntimeError]
    assert any("insert into raw.user_migraine_episode_details" in sql for sql, _ in conn.calls)
    assert any("insert into raw.user_migraine_episode_detail_revisions" in sql for sql, _ in conn.calls)


@pytest.mark.anyio
async def test_import_identity_resolution_does_not_depend_on_run_or_file_hash() -> None:
    canonical = {
        "episode_id": "episode-1",
        "symptom_event_id": "event-1",
        "external_event_id": "provider-event-1",
        "started_at": datetime(2026, 8, 1, tzinfo=UTC),
    }
    conn = ScriptedConnection([{"one": canonical}])

    result = await find_migraine_episode_by_import_identity(
        conn,
        "user-a",
        source_provider="provider-a",
        source_identity_key="stable-event-key",
    )

    assert result == canonical
    assert conn.calls[0][1] == ("user-a", "provider-a", "stable-event-key")


@pytest.mark.anyio
async def test_import_commit_rejects_duplicate_clinical_identity() -> None:
    payload = json.loads((FIXTURES / "generic_import_episode.json").read_text())
    payload["symptom_event_id"] = "20000000-0000-4000-8000-000000000002"
    episode = MigraineEpisode.model_validate(payload)
    conn = ScriptedConnection(
        [
            {
                "one": {
                    "id": episode.provenance.import_run_id,
                    "user_id": "user-a",
                    "source_provider": episode.provenance.source_provider,
                    "source_file_hash": episode.provenance.source_file_hash,
                    "mapping_version": episode.provenance.mapping_version,
                    "status": "preview",
                }
            },
            {},
            {"one": {"episode_id": "different-episode", "symptom_event_id": "different-event"}},
        ]
    )

    with pytest.raises(MigraineImportConflict, match="another clinical episode"):
        await commit_migraine_import_episode(
            conn,
            "user-a",
            episode,
            source_identity_key="stable-event-key",
        )

    assert len(conn.calls) == 3
    assert "pg_advisory_xact_lock" in conn.calls[1][0]
    assert conn.transaction_exits == [MigraineImportConflict]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("run_status", "case"),
    [("committed", "same-run replay"), ("preview", "second import run")],
    ids=["same-run-replay", "second-run-link"],
)
async def test_import_replay_links_existing_detail_without_overwriting_user_edits(
    run_status: str,
    case: str,
) -> None:
    payload = json.loads((FIXTURES / "generic_import_episode.json").read_text())
    payload["symptom_event_id"] = "20000000-0000-4000-8000-000000000002"
    episode = MigraineEpisode.model_validate(payload)
    canonical_source = (
        f"import:{episode.provenance.import_run_id}"
        if case == "same-run replay"
        else "ios"
    )
    stored = {
        "episode_id": episode.episode_id,
        "user_id": "user-a",
        "symptom_event_id": episode.symptom_event_id,
        "schema_version": "1.0",
        "revision": 7,
        "payload": {"notes": "User-edited content must survive re-import."},
        "user_edited_at": datetime(2026, 9, 2, tzinfo=UTC),
        "retained_after_import_reversal_at": None,
        "created_at": datetime(2026, 9, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 2, tzinfo=UTC),
        "started_at": episode.start.utc,
    }
    conn = ScriptedConnection(
        [
            {
                "one": {
                    "id": episode.provenance.import_run_id,
                    "user_id": "user-a",
                    "source_provider": episode.provenance.source_provider,
                    "source_file_hash": episode.provenance.source_file_hash,
                    "mapping_version": episode.provenance.mapping_version,
                    "status": run_status,
                }
            },
            {},
            {
                "one": {
                    "episode_id": episode.episode_id,
                    "symptom_event_id": episode.symptom_event_id,
                }
            },
            {
                "one": {
                    "started_at": episode.start.utc,
                    "episode_source": canonical_source,
                    "event_source": canonical_source,
                }
            },
            {"one": stored},
            {
                "one": {
                    "id": "identity-1",
                    "episode_id": episode.episode_id,
                    "symptom_event_id": episode.symptom_event_id,
                }
            },
            {
                "one": {
                    "id": "link-1",
                    "import_run_id": episode.provenance.import_run_id,
                    "episode_id": episode.episode_id,
                    "symptom_event_id": episode.symptom_event_id,
                }
            },
            {},
        ]
    )

    result = await commit_migraine_import_episode(
        conn,
        "user-a",
        episode,
        source_identity_key="stable-event-key",
    )

    assert result["detail"]["episode_id"] == episode.episode_id
    assert result["detail"]["revision"] == 7
    assert result["detail"]["payload"]["notes"] == "User-edited content must survive re-import."
    assert result["link"]["episode_id"] == episode.episode_id
    assert conn.transaction_exits == [None]
    assert not any("insert into raw.user_migraine_episode_details" in sql for sql, _ in conn.calls), case
    assert not any("update raw.user_migraine_episode_details" in sql for sql, _ in conn.calls), case
    assert not any("user_migraine_episode_detail_revisions" in sql for sql, _ in conn.calls), case
    identity_call = next(call for call in conn.calls if "insert into raw.user_migraine_import_identities" in call[0])
    expected_origin = (
        str(episode.provenance.import_run_id)
        if case == "same-run replay"
        else None
    )
    expected_proof = "canonical_sources_match_run" if expected_origin else None
    assert identity_call[1][-2:] == (expected_origin, expected_proof)
    link_call = next(call for call in conn.calls if "insert into raw.user_migraine_episode_import_links" in call[0])
    assert link_call[1][6] == "stable-event-key"


@pytest.mark.anyio
async def test_reversal_preserves_user_edited_episode_and_returns_only_affected_user_times() -> None:
    started_at = datetime(2026, 8, 2, 14, 30, tzinfo=UTC)
    retained_payload = {
        "lifecycle": {"revision": 3, "updated_at": "2026-08-03T00:00:00Z"}
    }
    conn = ScriptedConnection(
        [
            {"one": {"id": "run-1", "status": "committed"}},
            {
                "all": [
                    {
                        "episode_id": "episode-1",
                        "symptom_event_id": "event-1",
                        "started_at": started_at,
                        "revision": 2,
                        "user_edited_at": datetime(2026, 8, 2, 15, tzinfo=UTC),
                        "canonical_origin_import_run_id": "run-1",
                        "has_user_history": False,
                    }
                ]
            },
            {},
            {
                "one": {
                    "revision": 2,
                    "user_edited_at": datetime(2026, 8, 2, 15, tzinfo=UTC),
                    "canonical_origin_import_run_id": "run-1",
                    "has_user_history": False,
                }
            },
            {"one": None},
            {"one": {"revision": 3, "payload": retained_payload}},
            {},
            {},
        ]
    )

    result = await reverse_migraine_import_run(conn, "user-a", "run-1")

    assert result.user_id == "user-a"
    assert result.deleted_episode_ids == ()
    assert result.preserved_episode_ids == ("episode-1",)
    assert result.affected_started_at == ("2026-08-02T14:30:00+00:00",)
    assert conn.transaction_exits == [None]
    assert all("user-b" not in params for _, params in conn.calls)
    assert not any("delete from raw.user_migraine_import_identities" in sql for sql, _ in conn.calls)

    conn.script.append(
        {
            "one": {
                "episode_id": "episode-1",
                "symptom_event_id": "event-1",
                "external_event_id": "provider-event-1",
                "started_at": started_at,
            }
        }
    )
    identity = await find_migraine_episode_by_import_identity(
        conn,
        "user-a",
        source_provider="provider-a",
        source_identity_key="stable-event-key",
    )
    assert identity["episode_id"] == "episode-1"


@pytest.mark.anyio
async def test_reversal_preserves_episode_changed_through_existing_follow_up_path() -> None:
    started_at = datetime(2026, 8, 2, 14, 30, tzinfo=UTC)
    conn = ScriptedConnection(
        [
            {"one": {"id": "run-1", "status": "committed"}},
            {
                "all": [
                    {
                        "episode_id": "episode-1",
                        "symptom_event_id": "event-1",
                        "started_at": started_at,
                        "revision": 2,
                        "user_edited_at": None,
                        "canonical_origin_import_run_id": "run-1",
                        "has_user_history": True,
                    }
                ]
            },
            {},
            {
                "one": {
                    "revision": 2,
                    "user_edited_at": None,
                    "canonical_origin_import_run_id": "run-1",
                    "has_user_history": True,
                }
            },
            {"one": None},
            {
                "one": {
                    "revision": 3,
                    "payload": {"lifecycle": {"revision": 3}},
                }
            },
            {},
            {},
        ]
    )

    result = await reverse_migraine_import_run(conn, "user-a", "run-1")

    assert result.deleted_episode_ids == ()
    assert result.preserved_episode_ids == ("episode-1",)
    assert not any("delete from raw.user_symptom_events" in sql for sql, _ in conn.calls)


@pytest.mark.anyio
async def test_reversal_deletes_only_unedited_episode_with_no_other_import_link() -> None:
    conn = ScriptedConnection(
        [
            {"one": {"id": "run-1", "status": "committed"}},
            {
                "all": [
                    {
                        "episode_id": "episode-1",
                        "symptom_event_id": "event-1",
                        "started_at": datetime(2026, 8, 2, 14, 30, tzinfo=UTC),
                        "revision": 1,
                        "user_edited_at": None,
                        "canonical_origin_import_run_id": "run-1",
                        "has_user_history": False,
                    }
                ]
            },
            {},
            {
                "one": {
                    "revision": 1,
                    "user_edited_at": None,
                    "canonical_origin_import_run_id": "run-1",
                    "has_user_history": False,
                }
            },
            {"one": None},
            {"one": {"id": "episode-1"}},
            {},
        ]
    )

    result = await reverse_migraine_import_run(conn, "user-a", "run-1")

    assert result.deleted_episode_ids == ("episode-1",)
    delete_call = next(call for call in conn.calls if "delete from raw.user_symptom_events" in call[0])
    assert delete_call[1] == ("episode-1", "user-a", "event-1")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("first_run", "second_run"),
    [("run-a", "run-b"), ("run-b", "run-a")],
    ids=["reverse-origin-first", "reverse-relink-first"],
)
async def test_reversal_orders_preserve_backdated_user_follow_up_without_detail_marker(
    first_run: str,
    second_run: str,
) -> None:
    started_at = datetime(2026, 8, 2, 14, 30, tzinfo=UTC)
    link = {
        "episode_id": "episode-1",
        "symptom_event_id": "event-1",
        "started_at": started_at,
        "revision": None,
        "user_edited_at": None,
        "canonical_origin_import_run_id": "run-a",
        # This represents a user note/state/follow-up whose occurred_at may be
        # earlier than either import link. The SQL must not time-bound it.
        "has_user_history": True,
    }
    conn = ScriptedConnection(
        [
            {"one": {"id": first_run, "status": "committed"}},
            {"all": [link]},
            {},
            {"one": link},
            {"one": {"present": 1}},
            {},
            {"one": {"id": second_run, "status": "committed"}},
            {"all": [link]},
            {},
            {"one": link},
            {"one": None},
            {},
        ]
    )

    first = await reverse_migraine_import_run(conn, "user-a", first_run)
    second = await reverse_migraine_import_run(conn, "user-a", second_run)

    assert first.preserved_episode_ids == ("episode-1",)
    assert second.preserved_episode_ids == ("episode-1",)
    assert first.deleted_episode_ids == second.deleted_episode_ids == ()
    assert not any("delete from raw.user_symptom_events" in sql for sql, _ in conn.calls)
    follow_up_query = next(
        sql for sql, _ in conn.calls if "from raw.user_symptom_episode_updates u" in sql
    )
    assert "u.occurred_at" not in follow_up_query
    assert "u.created_at" not in follow_up_query
    assert "u.update_kind <> 'logged'" in follow_up_query
    assert "u.update_kind = 'follow_up'" not in follow_up_query


@pytest.mark.anyio
async def test_reversal_preserves_manual_episode_without_positive_import_origin() -> None:
    conn = ScriptedConnection(
        [
            {"one": {"id": "run-1", "status": "committed"}},
            {
                "all": [
                    {
                        "episode_id": "episode-1",
                        "symptom_event_id": "event-1",
                        "started_at": datetime(2026, 8, 2, 14, 30, tzinfo=UTC),
                        "revision": None,
                        "user_edited_at": None,
                        "canonical_origin_import_run_id": None,
                        "has_user_history": False,
                    }
                ]
            },
            {},
            {
                "one": {
                    "revision": None,
                    "user_edited_at": None,
                    "canonical_origin_import_run_id": None,
                    "has_user_history": False,
                }
            },
            {"one": None},
            {},
        ]
    )

    result = await reverse_migraine_import_run(conn, "user-a", "run-1")

    assert result.deleted_episode_ids == ()
    assert result.preserved_episode_ids == ("episode-1",)
    assert not any("delete from raw.user_symptom_events" in sql for sql, _ in conn.calls)


@pytest.fixture
def anyio_backend():
    return "asyncio"
