from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import HTTPException
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import ForeignKeyViolation, InsufficientPrivilege
from starlette.requests import Request

from app.routers import symptoms as symptoms_router
from app.routers.symptoms import SymptomFollowUpResponseIn
from app.db.migraine import (
    MigraineEpisodeNotFound,
    MigraineImportConflict,
    StaleMigraineRevision,
    commit_migraine_import_episode,
    create_migraine_import_run,
    load_migraine_follow_up_detail,
    persist_migraine_episode_detail,
    reverse_migraine_import_run,
    save_migraine_follow_up_detail,
)
from services.migraine.episode_contract import EarlySign, MedicineTaken
from services.migraine.episode_contract import MigraineEpisode


TEST_DATABASE_URL_ENV = "GAIA_MIGRAINE_TEST_DATABASE_URL"
USER_A = "90000000-0000-4000-8000-000000000001"
USER_B = "90000000-0000-4000-8000-000000000002"


def anyio_backend() -> str:
    return "asyncio"


def _database_url() -> str:
    value = os.getenv(TEST_DATABASE_URL_ENV)
    if not value:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is required for disposable PostgreSQL verification")
    params = conninfo_to_dict(value)
    expected_socket = os.path.expanduser("~/.codex/cache/gaia-migraine-postgres-17.11/socket")
    if params.get("dbname") != "gaia_migraine_test":
        raise RuntimeError("refusing non-test database name")
    if params.get("host") != expected_socket or params.get("hostaddr"):
        raise RuntimeError("refusing non-private or remote migraine test DSN")
    return value


def test_database_url_rejects_remote_target_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql://postgres:postgres@example.invalid:5432/gaia_migraine_test",
    )
    with pytest.raises(RuntimeError, match="refusing non-private or remote"):
        _database_url()


def test_database_url_rejects_wrong_database_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = os.path.expanduser("~/.codex/cache/gaia-migraine-postgres-17.11/socket")
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        f"postgresql://postgres:postgres@/postgres?host={socket}",
    )
    with pytest.raises(RuntimeError, match="refusing non-test database name"):
        _database_url()


async def _assert_disposable(conn: psycopg.AsyncConnection) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            select current_database(),
                   current_setting('gaia.migraine_disposable', true),
                   inet_server_addr(),
                   current_setting('unix_socket_directories')
            """
        )
        database, marker, server_addr, socket_dir = await cur.fetchone()
    assert database == "gaia_migraine_test"
    assert marker == "true"
    assert server_addr is None
    assert "/.codex/cache/gaia-migraine-postgres-17.11/socket" in socket_dir


async def _connect(*, autocommit: bool = True) -> psycopg.AsyncConnection:
    conn = await psycopg.AsyncConnection.connect(_database_url(), autocommit=autocommit)
    await _assert_disposable(conn)
    if not autocommit:
        await conn.commit()
    return conn


async def _reset(conn: psycopg.AsyncConnection) -> None:
    async with conn.cursor() as cur:
        await cur.execute("truncate raw.user_symptom_events cascade")
        await cur.execute("truncate raw.user_migraine_import_runs cascade")


def _episode(
    *,
    episode_id: UUID,
    event_id: UUID,
    start: datetime,
    revision: int = 1,
    source_type: str = "manual",
    run_id: UUID | None = None,
    provider: str = "synthetic_fixture",
    external_id: str = "provider-event",
    raw_row_ref: str = "row:1",
    notes: str | None = None,
) -> MigraineEpisode:
    provenance: dict[str, object] = {
        "source_type": source_type,
        "source_platform": "g009_postgres",
    }
    if source_type == "import":
        assert run_id is not None
        provenance.update(
            {
                "source_provider": provider,
                "external_event_id": external_id,
                "source_file_hash": "a" * 64,
                "import_run_id": str(run_id),
                "raw_row_ref": raw_row_ref,
                "mapping_version": "g009-1",
            }
        )
    return MigraineEpisode.model_validate(
        {
            "schema_version": "1.0",
            "episode_id": str(episode_id),
            "symptom_event_id": str(event_id),
            "symptom_code": "MIGRAINE",
            "state": "ongoing",
            "start": {
                "utc": start.isoformat(),
                "timezone_name": "America/Chicago",
                "timezone_source": "device" if source_type != "import" else "provider",
            },
            "severity": 5,
            "early_signs": [],
            "contexts": [],
            "medicines": [],
            "notes": notes,
            "provenance": provenance,
            "lifecycle": {
                "revision": revision,
                "created_at": start.isoformat(),
                "updated_at": start.isoformat(),
            },
        }
    )


async def _insert_parent(
    conn: psycopg.AsyncConnection,
    *,
    user_id: str,
    episode_id: UUID,
    event_id: UUID,
    start: datetime,
    source: str,
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            insert into raw.user_symptom_events
              (id, user_id, ts_utc, symptom_code, severity, source)
            values (%s, %s, %s, 'migraine', 5, %s)
            """,
            (event_id, user_id, start, source),
        )
        await cur.execute(
            """
            insert into raw.user_symptom_episodes
              (id, user_id, symptom_event_id, symptom_code, started_at,
               original_severity, current_severity, source)
            values (%s, %s, %s, 'migraine', %s, 5, 5, %s)
            """,
            (episode_id, user_id, event_id, start, source),
        )


async def _insert_prompt(
    conn: psycopg.AsyncConnection,
    *,
    prompt_id: UUID,
    user_id: str,
    episode_id: UUID,
    scheduled_for: datetime,
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            insert into raw.user_feedback_prompts
              (id, user_id, prompt_type, episode_id, symptom_code,
               question_key, question_text, scheduled_for, source)
            values (%s, %s, 'symptom_follow_up', %s, 'migraine',
                    'status_check', 'How is your migraine now?', %s, 'test')
            """,
            (prompt_id, user_id, episode_id, scheduled_for),
        )


def _request(user_id: str) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/symptoms/follow-ups/test/respond",
            "headers": [],
            "query_string": b"",
        }
    )
    request.state.user_id = user_id
    return request


def _structured_prompt_payload(
    *,
    expected_revision: int,
    responded_at: datetime,
    medicine_name: str = "User-entered medicine",
    note_text: str | None = "Resting in a dark room",
    nested_notes: object = ...,
) -> SymptomFollowUpResponseIn:
    migraine: dict[str, object] = {
        "expected_revision": expected_revision,
        "medicines": [
            {
                "name": medicine_name,
                "taken_at": {
                    "utc": responded_at.isoformat(),
                    "timezone_source": "user",
                },
            }
        ],
    }
    if nested_notes is not ...:
        migraine["notes"] = nested_notes
    return SymptomFollowUpResponseIn.model_validate(
        {
            "state": "improving",
            "detail_choice": "resting",
            "note_text": note_text,
            "time_bucket": "within_hours",
            "ts_utc": responded_at.isoformat(),
            "migraine": migraine,
        }
    )


async def _create_run(
    conn: psycopg.AsyncConnection,
    *,
    user_id: str,
    run_id: UUID,
    provider: str = "synthetic_fixture",
) -> None:
    await create_migraine_import_run(
        conn,
        user_id,
        import_run_id=str(run_id),
        source_provider=provider,
        source_file_hash="a" * 64,
        mapping_version="g009-1",
    )


async def _scalar(conn: psycopg.AsyncConnection, query: str, params=()):
    async with conn.cursor() as cur:
        await cur.execute(query, params)
        return (await cur.fetchone())[0]


async def _wait_for_backend_block(
    *,
    blocked_pid: int,
    blocker_pid: int,
    timeout_seconds: float = 5.0,
) -> None:
    """Wait until PostgreSQL confirms the intended lock dependency."""

    async def _poll() -> None:
        observer = await _connect()
        try:
            while True:
                blockers = await _scalar(
                    observer,
                    "select pg_blocking_pids(%s)",
                    (blocked_pid,),
                )
                if blocker_pid in blockers:
                    return
                await asyncio.sleep(0.02)
        finally:
            await observer.close()

    await asyncio.wait_for(_poll(), timeout=timeout_seconds)


@pytest.mark.anyio
async def test_real_postgres_rls_grants_and_owner_linkage() -> None:
    conn = await _connect()
    try:
        await _reset(conn)
        start = datetime(2026, 9, 8, 12, tzinfo=UTC)
        episode_a, event_a = uuid4(), uuid4()
        episode_b, event_b, unlinked_event_b = uuid4(), uuid4(), uuid4()
        await _insert_parent(
            conn, user_id=USER_A, episode_id=episode_a, event_id=event_a, start=start, source="ios"
        )
        await _insert_parent(
            conn, user_id=USER_B, episode_id=episode_b, event_id=event_b, start=start, source="ios"
        )
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into raw.user_symptom_events
                  (id, user_id, ts_utc, symptom_code, severity, source)
                values (%s, %s, %s, 'migraine', 5, 'ios')
                """,
                (unlinked_event_b, USER_B, start),
            )
        await persist_migraine_episode_detail(
            conn,
            USER_A,
            _episode(episode_id=episode_a, event_id=event_a, start=start),
            expected_revision=0,
            change_kind="created",
            source="ios",
        )

        import_run, import_episode, import_event = uuid4(), uuid4(), uuid4()
        await _create_run(conn, user_id=USER_A, run_id=import_run)
        await _commit_import(
            conn,
            user_id=USER_A,
            run_id=import_run,
            episode_id=import_episode,
            event_id=import_event,
            start=start.replace(hour=13),
            identity="rls-owner-a",
        )

        protected_tables = (
            "user_migraine_episode_details",
            "user_migraine_episode_detail_revisions",
            "user_migraine_import_runs",
            "user_migraine_import_identities",
            "user_migraine_episode_import_links",
        )

        async with conn.cursor() as cur:
            await cur.execute("set role authenticated")
            await cur.execute("select set_config('request.jwt.claim.sub', %s, false)", (USER_A,))
            for table in protected_tables:
                await cur.execute(
                    sql.SQL("select count(*) from raw.{}").format(sql.Identifier(table))
                )
                assert (await cur.fetchone())[0] >= 1
            await cur.execute("select set_config('request.jwt.claim.sub', %s, false)", (USER_B,))
            for table in protected_tables:
                await cur.execute(
                    sql.SQL("select count(*) from raw.{}").format(sql.Identifier(table))
                )
                assert (await cur.fetchone())[0] == 0
                with pytest.raises(InsufficientPrivilege):
                    await cur.execute(
                        sql.SQL("update raw.{} set user_id = user_id").format(
                            sql.Identifier(table)
                        )
                    )
            await cur.execute("reset role")
            await cur.execute("set role anon")
            for table in protected_tables:
                with pytest.raises(InsufficientPrivilege):
                    await cur.execute(
                        sql.SQL("select * from raw.{}").format(sql.Identifier(table))
                    )
            await cur.execute("reset role")

            with pytest.raises(ForeignKeyViolation):
                await cur.execute(
                    """
                    insert into raw.user_symptom_episodes
                      (id, user_id, symptom_event_id, symptom_code, started_at,
                       original_severity, current_severity, source)
                    values (%s, %s, %s, 'migraine', %s, 5, 5, 'ios')
                    """,
                    (uuid4(), USER_A, unlinked_event_b, start),
                )

            cross_payload = _episode(
                episode_id=episode_b, event_id=event_b, start=start
            ).model_dump(mode="json")
            with pytest.raises(ForeignKeyViolation):
                await cur.execute(
                    """
                    insert into raw.user_migraine_episode_details
                      (episode_id, user_id, symptom_event_id, revision, payload)
                    values (%s, %s, %s, 1, %s::jsonb)
                    """,
                    (episode_b, USER_A, event_b, psycopg.types.json.Jsonb(cross_payload)),
                )

            with pytest.raises(ForeignKeyViolation):
                await cur.execute(
                    """
                    insert into raw.user_migraine_import_identities
                      (user_id, source_provider, source_identity_key,
                       episode_id, symptom_event_id)
                    values (%s, 'synthetic_fixture', 'cross-owner', %s, %s)
                    """,
                    (USER_A, episode_b, event_b),
                )
    finally:
        await conn.close()


@pytest.mark.anyio
async def test_real_structured_follow_up_read_write_clear_retry_and_owner_isolation() -> None:
    conn = await _connect(autocommit=False)
    await _reset(conn)
    await conn.commit()
    start = datetime(2026, 9, 8, 12, tzinfo=UTC)
    episode_id, event_id = uuid4(), uuid4()
    await _insert_parent(
        conn,
        user_id=USER_A,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        source="siri",
    )
    await conn.commit()

    sign = EarlySign(label="Visual shimmer")
    medicine = MedicineTaken.model_validate(
        {
            "name": "User-entered medicine",
            "taken_at": {"utc": start, "timezone_source": "user"},
            "reported_relief": None,
        }
    )
    try:
        async with conn.transaction():
            created = await save_migraine_follow_up_detail(
                conn,
                USER_A,
                str(episode_id),
                expected_revision=0,
                changes={
                    "early_signs": [sign],
                    "medicines": [medicine],
                    "notes": "Lights became uncomfortable first",
                },
                supplied_fields={"early_signs", "medicines", "notes"},
                canonical_fields={"notes"},
                occurred_at=start,
            )
        assert created["changed"] is True
        assert created["revision"] == 1

        loaded = await load_migraine_follow_up_detail(conn, USER_A, str(episode_id))
        assert loaded["revision"] == 1
        assert len(loaded["episode"].medicines) == 1
        assert loaded["episode"].medicines[0].reported_relief is None

        async with conn.transaction():
            retried = await save_migraine_follow_up_detail(
                conn,
                USER_A,
                str(episode_id),
                expected_revision=0,
                changes={
                    "early_signs": [sign],
                    "medicines": [medicine],
                    "notes": "Lights became uncomfortable first",
                },
                supplied_fields={"early_signs", "medicines", "notes"},
                canonical_fields={"notes"},
                occurred_at=start,
            )
        assert retried["changed"] is False
        assert retried["revision"] == 1
        assert len(retried["episode"].medicines) == 1

        with pytest.raises(StaleMigraineRevision):
            async with conn.transaction():
                await save_migraine_follow_up_detail(
                    conn,
                    USER_A,
                    str(episode_id),
                    expected_revision=0,
                    changes={"notes": "Conflicting replacement"},
                    supplied_fields={"notes"},
                    canonical_fields={"notes"},
                )

        async with conn.transaction():
            cleared = await save_migraine_follow_up_detail(
                conn,
                USER_A,
                str(episode_id),
                expected_revision=1,
                changes={"medicines": [], "notes": None},
                supplied_fields={"medicines", "notes"},
                canonical_fields={"notes"},
            )
        assert cleared["revision"] == 2
        assert cleared["episode"].medicines == []
        assert cleared["episode"].notes is None
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_detail_revisions where episode_id = %s",
            (episode_id,),
        ) == 2
        assert await _scalar(
            conn,
            "select latest_note_text is null from raw.user_symptom_episodes where id = %s",
            (episode_id,),
        ) is True

        with pytest.raises(MigraineEpisodeNotFound):
            await load_migraine_follow_up_detail(conn, USER_B, str(episode_id))
    finally:
        await conn.close()


@pytest.mark.anyio
async def test_real_structured_follow_up_rolls_back_canonical_when_detail_audit_fails() -> None:
    conn = await _connect(autocommit=False)
    await _reset(conn)
    await conn.commit()
    start = datetime(2026, 9, 8, 14, tzinfo=UTC)
    episode_id, event_id = uuid4(), uuid4()
    await _insert_parent(
        conn,
        user_id=USER_A,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        source="ios",
    )
    await conn.commit()

    async with conn.cursor() as cur:
        await cur.execute(
            """
            create or replace function raw.fail_g010_detail_audit()
            returns trigger language plpgsql as $$
            begin
              raise exception 'synthetic G-010 audit failure';
            end
            $$;
            create trigger fail_g010_detail_audit
            before insert on raw.user_migraine_episode_detail_revisions
            for each row execute function raw.fail_g010_detail_audit();
            """
        )
    await conn.commit()

    try:
        with pytest.raises(Exception, match="synthetic G-010 audit failure"):
            async with conn.transaction():
                await save_migraine_follow_up_detail(
                    conn,
                    USER_A,
                    str(episode_id),
                    expected_revision=0,
                    changes={"state": "resolved", "notes": "Resolved note"},
                    supplied_fields={"state", "notes"},
                    canonical_fields={"state", "notes"},
                    occurred_at=start.replace(hour=16),
                )

        assert await _scalar(
            conn,
            "select current_state = 'new' and latest_note_text is null from raw.user_symptom_episodes where id = %s",
            (episode_id,),
        ) is True
        assert await _scalar(
            conn,
            "select count(*) from raw.user_symptom_episode_updates where episode_id = %s",
            (episode_id,),
        ) == 0
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_details where episode_id = %s",
            (episode_id,),
        ) == 0
    finally:
        async with conn.cursor() as cur:
            await cur.execute("drop trigger if exists fail_g010_detail_audit on raw.user_migraine_episode_detail_revisions")
            await cur.execute("drop function if exists raw.fail_g010_detail_audit()")
        await conn.commit()
        await conn.close()


@pytest.mark.anyio
async def test_real_prompt_route_commits_before_refresh_and_exact_retry_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = await _connect(autocommit=False)
    await _reset(conn)
    await conn.commit()
    start = datetime(2026, 9, 8, 15, tzinfo=UTC)
    responded_at = start.replace(hour=16)
    episode_id, event_id, prompt_id = uuid4(), uuid4(), uuid4()
    await _insert_parent(
        conn,
        user_id=USER_A,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        source="ios",
    )
    await _insert_prompt(
        conn,
        prompt_id=prompt_id,
        user_id=USER_A,
        episode_id=episode_id,
        scheduled_for=responded_at,
    )
    await conn.commit()

    refresh_observations: list[tuple[str, int, int]] = []

    async def _observe_committed_refresh(user_id: str, ts_utc: str) -> None:
        observer = await _connect()
        try:
            prompt_status = await _scalar(
                observer,
                "select status from raw.user_feedback_prompts where id = %s",
                (prompt_id,),
            )
            detail_count = await _scalar(
                observer,
                "select count(*) from raw.user_migraine_episode_details where episode_id = %s",
                (episode_id,),
            )
            update_count = await _scalar(
                observer,
                "select count(*) from raw.user_symptom_episode_updates where episode_id = %s",
                (episode_id,),
            )
            assert user_id == USER_A
            assert ts_utc
            assert prompt_status == "answered"
            refresh_observations.append((prompt_status, detail_count, update_count))
        finally:
            await observer.close()

    monkeypatch.setattr(
        symptoms_router,
        "_refresh_gauges_for_symptom",
        _observe_committed_refresh,
    )
    payload = _structured_prompt_payload(
        expected_revision=0,
        responded_at=responded_at,
    )

    try:
        await conn.execute("set statement_timeout = 5000")
        first = await symptoms_router.respond_symptom_follow_up(
            str(prompt_id),
            payload,
            _request(USER_A),
            conn,
        )
        assert first["ok"] is True
        assert first["data"]["migraine_detail"]["revision"] == 1
        assert first["data"]["migraine_detail"]["changed"] is True
        assert refresh_observations == [("answered", 1, 1)]

        prompt_updated_at = await _scalar(
            conn,
            "select updated_at from raw.user_feedback_prompts where id = %s",
            (prompt_id,),
        )
        await conn.execute("set statement_timeout = 5000")
        replay = await symptoms_router.respond_symptom_follow_up(
            str(prompt_id),
            payload,
            _request(USER_A),
            conn,
        )
        assert replay["ok"] is True
        assert replay["data"]["migraine_detail"]["revision"] == 1
        assert replay["data"]["migraine_detail"]["changed"] is False
        assert refresh_observations == [("answered", 1, 1)]

        assert await _scalar(
            conn,
            "select count(*) from raw.user_feedback_prompts where id = %s",
            (prompt_id,),
        ) == 1
        assert await _scalar(
            conn,
            "select updated_at = %s from raw.user_feedback_prompts where id = %s",
            (prompt_updated_at, prompt_id),
        ) is True
        assert await _scalar(
            conn,
            "select count(*) from raw.user_symptom_episode_updates where episode_id = %s",
            (episode_id,),
        ) == 1
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_detail_revisions where episode_id = %s",
            (episode_id,),
        ) == 1
        medicines = await _scalar(
            conn,
            "select payload -> 'medicines' from raw.user_migraine_episode_details where episode_id = %s",
            (episode_id,),
        )
        assert len(medicines) == 1
        assert medicines[0]["name"] == "User-entered medicine"
        prompt_answer = await _scalar(
            conn,
            """
            select jsonb_build_object(
                'status', status,
                'state', response_state,
                'detail_choice', response_detail_choice,
                'note', response_note_text,
                'time_bucket', response_time_bucket,
                'answered', answered_at is not null
            )
              from raw.user_feedback_prompts
             where id = %s
            """,
            (prompt_id,),
        )
        assert prompt_answer == {
            "status": "answered",
            "state": "improving",
            "detail_choice": "resting",
            "note": "Resting in a dark room",
            "time_bucket": "within_hours",
            "answered": True,
        }
        canonical = await _scalar(
            conn,
            """
            select jsonb_build_object(
                'state', current_state,
                'note', latest_note_text
            )
              from raw.user_symptom_episodes
             where id = %s
            """,
            (episode_id,),
        )
        assert canonical == {
            "state": "improving",
            "note": "Resting in a dark room",
        }
        canonical_update = await _scalar(
            conn,
            """
            select jsonb_build_object(
                'kind', update_kind,
                'state', state,
                'note', note_text,
                'source', source,
                'prompt_id', metadata ->> 'prompt_id'
            )
              from raw.user_symptom_episode_updates
             where episode_id = %s
            """,
            (episode_id,),
        )
        assert canonical_update == {
            "kind": "follow_up",
            "state": "improving",
            "note": "Resting in a dark room",
            "source": "follow_up",
            "prompt_id": str(prompt_id),
        }
        audit = await _scalar(
            conn,
            """
            select jsonb_build_object(
                'revision', revision,
                'kind', change_kind,
                'source', source,
                'medicine_count', jsonb_array_length(payload -> 'medicines'),
                'medicine_name', payload -> 'medicines' -> 0 ->> 'name'
            )
              from raw.user_migraine_episode_detail_revisions
             where episode_id = %s
            """,
            (episode_id,),
        )
        assert audit == {
            "revision": 1,
            "kind": "user_edit",
            "source": "follow_up",
            "medicine_count": 1,
            "medicine_name": "User-entered medicine",
        }

        conflicting = _structured_prompt_payload(
            expected_revision=0,
            responded_at=responded_at,
            medicine_name="Conflicting medicine",
            note_text="Conflicting retry",
        )
        await conn.execute("set statement_timeout = 5000")
        with pytest.raises(HTTPException) as stale:
            await symptoms_router.respond_symptom_follow_up(
                str(prompt_id),
                conflicting,
                _request(USER_A),
                conn,
            )
        assert stale.value.status_code == 409
        assert await _scalar(
            conn,
            "select count(*) from raw.user_symptom_episode_updates where episode_id = %s",
            (episode_id,),
        ) == 1
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_detail_revisions where episode_id = %s",
            (episode_id,),
        ) == 1
    finally:
        await conn.close()


@pytest.mark.anyio
async def test_real_prompt_route_concurrent_identical_requests_do_not_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = await _connect(autocommit=False)
    await _reset(setup)
    await setup.commit()
    start = datetime(2026, 9, 8, 17, tzinfo=UTC)
    responded_at = start.replace(hour=18)
    episode_id, event_id, prompt_id = uuid4(), uuid4(), uuid4()
    await _insert_parent(
        setup,
        user_id=USER_A,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        source="android",
    )
    await _insert_prompt(
        setup,
        prompt_id=prompt_id,
        user_id=USER_A,
        episode_id=episode_id,
        scheduled_for=responded_at,
    )
    await setup.commit()
    await setup.close()

    refreshes: list[str] = []

    async def _refresh(user_id: str, ts_utc: str) -> None:
        assert user_id == USER_A
        refreshes.append(ts_utc)

    monkeypatch.setattr(symptoms_router, "_refresh_gauges_for_symptom", _refresh)
    payload = _structured_prompt_payload(
        expected_revision=0,
        responded_at=responded_at,
    )
    conn_a = await _connect(autocommit=False)
    conn_b = await _connect(autocommit=False)

    async def _respond(conn: psycopg.AsyncConnection) -> dict:
        await conn.execute("set statement_timeout = 5000")
        return await symptoms_router.respond_symptom_follow_up(
            str(prompt_id),
            payload,
            _request(USER_A),
            conn,
        )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(_respond(conn_a), _respond(conn_b)),
            timeout=5.0,
        )
        assert all(result["ok"] is True for result in results)
        assert sorted(
            result["data"]["migraine_detail"]["changed"] for result in results
        ) == [False, True]
        assert len(refreshes) == 1

        observer = await _connect()
        try:
            assert await _scalar(
                observer,
                "select count(*) from raw.user_feedback_prompts where id = %s and status = 'answered'",
                (prompt_id,),
            ) == 1
            assert await _scalar(
                observer,
                "select count(*) from raw.user_symptom_episode_updates where episode_id = %s",
                (episode_id,),
            ) == 1
            assert await _scalar(
                observer,
                "select count(*) from raw.user_migraine_episode_detail_revisions where episode_id = %s",
                (episode_id,),
            ) == 1
            medicines = await _scalar(
                observer,
                "select payload -> 'medicines' from raw.user_migraine_episode_details where episode_id = %s",
                (episode_id,),
            )
            assert len(medicines) == 1
        finally:
            await observer.close()
    finally:
        await conn_a.close()
        await conn_b.close()


@pytest.mark.anyio
async def test_real_prompt_route_returns_projected_note_and_explicit_clear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = await _connect(autocommit=False)
    await _reset(conn)
    await conn.commit()
    start = datetime(2026, 9, 8, 19, tzinfo=UTC)
    responded_at = start.replace(hour=20)
    episode_id, event_id, prompt_id = uuid4(), uuid4(), uuid4()
    await _insert_parent(
        conn,
        user_id=USER_A,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        source="ios",
    )
    await _insert_prompt(
        conn,
        prompt_id=prompt_id,
        user_id=USER_A,
        episode_id=episode_id,
        scheduled_for=responded_at,
    )
    await conn.commit()

    async def _noop_refresh(user_id: str, ts_utc: str) -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(symptoms_router, "_refresh_gauges_for_symptom", _noop_refresh)
    try:
        save_payload = _structured_prompt_payload(
            expected_revision=0,
            responded_at=responded_at,
            note_text=None,
            nested_notes="Light sensitivity eased after resting",
        )
        await conn.execute("set statement_timeout = 5000")
        saved = await symptoms_router.respond_symptom_follow_up(
            str(prompt_id), save_payload, _request(USER_A), conn
        )
        assert saved["ok"] is True
        assert saved["data"]["episode"]["note_preview"] == "Light sensitivity eased after resting"
        assert saved["data"]["episode"]["note_count"] == 1
        assert saved["data"]["migraine_detail"]["episode"]["notes"] == "Light sensitivity eased after resting"

        clear_payload = _structured_prompt_payload(
            expected_revision=1,
            responded_at=responded_at,
            note_text=None,
            nested_notes=None,
        )
        await conn.execute("set statement_timeout = 5000")
        cleared = await symptoms_router.respond_symptom_follow_up(
            str(prompt_id), clear_payload, _request(USER_A), conn
        )
        assert cleared["ok"] is True
        assert cleared["data"]["episode"]["note_preview"] is None
        assert cleared["data"]["episode"]["note_count"] == 1
        assert cleared["data"]["migraine_detail"]["episode"]["notes"] is None
        assert cleared["data"]["migraine_detail"]["revision"] == 2
    finally:
        await conn.close()


@pytest.mark.anyio
async def test_real_prompt_route_commit_failure_rolls_back_without_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = await _connect(autocommit=False)
    await _reset(conn)
    await conn.commit()
    start = datetime(2026, 9, 8, 21, tzinfo=UTC)
    responded_at = start.replace(hour=22)
    episode_id, event_id, prompt_id = uuid4(), uuid4(), uuid4()
    await _insert_parent(
        conn,
        user_id=USER_A,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        source="android",
    )
    await _insert_prompt(
        conn,
        prompt_id=prompt_id,
        user_id=USER_A,
        episode_id=episode_id,
        scheduled_for=responded_at,
    )
    await conn.commit()

    async with conn.cursor() as cur:
        await cur.execute(
            """
            create or replace function raw.fail_g010_deferred_commit()
            returns trigger language plpgsql as $$
            begin
              raise exception 'synthetic G-010 deferred commit failure';
            end
            $$;
            create constraint trigger fail_g010_deferred_commit
            after insert on raw.user_migraine_episode_detail_revisions
            deferrable initially deferred
            for each row execute function raw.fail_g010_deferred_commit();
            """
        )
    await conn.commit()
    refreshes: list[str] = []

    async def _refresh(user_id: str, ts_utc: str) -> None:  # noqa: ARG001
        refreshes.append(ts_utc)

    monkeypatch.setattr(symptoms_router, "_refresh_gauges_for_symptom", _refresh)
    payload = _structured_prompt_payload(
        expected_revision=0,
        responded_at=responded_at,
    )
    try:
        await conn.execute("set statement_timeout = 5000")
        failed = await symptoms_router.respond_symptom_follow_up(
            str(prompt_id), payload, _request(USER_A), conn
        )
        assert failed.status_code == 200
        body = json.loads(failed.body)
        assert body["ok"] is False
        assert "synthetic G-010 deferred commit failure" in body["error"]
        assert refreshes == []
        assert await _scalar(
            conn,
            "select status from raw.user_feedback_prompts where id = %s",
            (prompt_id,),
        ) == "pending"
        assert await _scalar(
            conn,
            "select current_state = 'new' and latest_note_text is null from raw.user_symptom_episodes where id = %s",
            (episode_id,),
        ) is True
        assert await _scalar(
            conn,
            "select count(*) from raw.user_symptom_episode_updates where episode_id = %s",
            (episode_id,),
        ) == 0
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_details where episode_id = %s",
            (episode_id,),
        ) == 0
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_detail_revisions where episode_id = %s",
            (episode_id,),
        ) == 0
    finally:
        async with conn.cursor() as cur:
            await cur.execute(
                "drop trigger if exists fail_g010_deferred_commit on raw.user_migraine_episode_detail_revisions"
            )
            await cur.execute("drop function if exists raw.fail_g010_deferred_commit()")
        await conn.commit()
        await conn.close()


@pytest.mark.anyio
async def test_repository_revision_audit_and_failure_rollback() -> None:
    conn = await _connect()
    try:
        await _reset(conn)
        start = datetime(2026, 9, 8, 13, tzinfo=UTC)
        episode_id, event_id = uuid4(), uuid4()
        await _insert_parent(
            conn, user_id=USER_A, episode_id=episode_id, event_id=event_id, start=start, source="ios"
        )
        created = await persist_migraine_episode_detail(
            conn,
            USER_A,
            _episode(episode_id=episode_id, event_id=event_id, start=start),
            expected_revision=0,
            change_kind="created",
            source="ios",
        )
        assert created["revision"] == 1

        edited = await persist_migraine_episode_detail(
            conn,
            USER_A,
            _episode(
                episode_id=episode_id,
                event_id=event_id,
                start=start,
                revision=2,
                notes="User edit retained",
            ),
            expected_revision=1,
            change_kind="user_edit",
            source="ios",
            user_edit=True,
        )
        assert edited["revision"] == 2
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_detail_revisions where episode_id = %s",
            (episode_id,),
        ) == 2

        with pytest.raises(StaleMigraineRevision):
            await persist_migraine_episode_detail(
                conn,
                USER_A,
                _episode(episode_id=episode_id, event_id=event_id, start=start, revision=3),
                expected_revision=1,
                change_kind="user_edit",
                source="ios",
                user_edit=True,
            )

        async with conn.cursor() as cur:
            await cur.execute(
                """
                create or replace function raw.g009_fail_audit()
                returns trigger language plpgsql as $$
                begin
                  if new.source = 'g009-force-audit-failure' then
                    raise exception 'forced audit failure';
                  end if;
                  return new;
                end $$
                """
            )
            await cur.execute(
                """
                create trigger g009_fail_audit
                before insert on raw.user_migraine_episode_detail_revisions
                for each row execute function raw.g009_fail_audit()
                """
            )
        with pytest.raises(psycopg.DatabaseError, match="forced audit failure"):
            await persist_migraine_episode_detail(
                conn,
                USER_A,
                _episode(episode_id=episode_id, event_id=event_id, start=start, revision=3),
                expected_revision=2,
                change_kind="user_edit",
                source="g009-force-audit-failure",
                user_edit=True,
            )
        assert await _scalar(
            conn,
            "select revision from raw.user_migraine_episode_details where episode_id = %s",
            (episode_id,),
        ) == 2
        assert await _scalar(
            conn,
            "select count(*) from raw.user_migraine_episode_detail_revisions where episode_id = %s",
            (episode_id,),
        ) == 2
    finally:
        async with conn.cursor() as cur:
            await cur.execute("drop trigger if exists g009_fail_audit on raw.user_migraine_episode_detail_revisions")
            await cur.execute("drop function if exists raw.g009_fail_audit()")
        await conn.close()


async def _commit_import(
    conn: psycopg.AsyncConnection,
    *,
    user_id: str,
    run_id: UUID,
    episode_id: UUID,
    event_id: UUID,
    start: datetime,
    identity: str,
    source: str | None = None,
    raw_row_ref: str = "row:1",
) -> dict:
    canonical_source = source or f"import:{run_id}"
    await _insert_parent(
        conn,
        user_id=user_id,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        source=canonical_source,
    )
    return await commit_migraine_import_episode(
        conn,
        user_id,
        _episode(
            episode_id=episode_id,
            event_id=event_id,
            start=start,
            source_type="import",
            run_id=run_id,
            raw_row_ref=raw_row_ref,
        ),
        source_identity_key=identity,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("reverse_first", ["origin", "later"])
async def test_import_replay_two_run_reversal_orders_and_origin_deletion(reverse_first: str) -> None:
    conn = await _connect()
    try:
        await _reset(conn)
        start = datetime(2026, 9, 8, 14, tzinfo=UTC)
        run_1, run_2 = uuid4(), uuid4()
        episode_id, event_id = uuid4(), uuid4()
        await _create_run(conn, user_id=USER_A, run_id=run_1)
        first = await _commit_import(
            conn,
            user_id=USER_A,
            run_id=run_1,
            episode_id=episode_id,
            event_id=event_id,
            start=start,
            identity="stable-provider-event",
        )
        replay = await commit_migraine_import_episode(
            conn,
            USER_A,
            _episode(
                episode_id=episode_id,
                event_id=event_id,
                start=start,
                source_type="import",
                run_id=run_1,
            ),
            source_identity_key="stable-provider-event",
        )
        assert replay["detail"]["revision"] == first["detail"]["revision"] == 1

        await _create_run(conn, user_id=USER_A, run_id=run_2)
        later = await commit_migraine_import_episode(
            conn,
            USER_A,
            _episode(
                episode_id=episode_id,
                event_id=event_id,
                start=start,
                source_type="import",
                run_id=run_2,
                raw_row_ref="row:later",
                notes="Must not overwrite stored detail",
            ),
            source_identity_key="stable-provider-event",
        )
        assert later["detail"]["revision"] == 1
        assert await _scalar(
            conn,
            "select canonical_origin_import_run_id from raw.user_migraine_import_identities where episode_id = %s",
            (episode_id,),
        ) == run_1

        ordered = (run_1, run_2) if reverse_first == "origin" else (run_2, run_1)
        first_reversal = await reverse_migraine_import_run(conn, USER_A, str(ordered[0]))
        assert str(episode_id) in first_reversal.preserved_episode_ids
        second_reversal = await reverse_migraine_import_run(conn, USER_A, str(ordered[1]))
        assert str(episode_id) in second_reversal.deleted_episode_ids
        assert await _scalar(
            conn, "select count(*) from raw.user_symptom_events where id = %s", (event_id,)
        ) == 0
    finally:
        await conn.close()


@pytest.mark.anyio
async def test_manual_episode_and_backdated_user_history_survive_reversal() -> None:
    conn = await _connect()
    try:
        await _reset(conn)
        start = datetime(2026, 9, 8, 15, tzinfo=UTC)

        manual_run, manual_episode, manual_event = uuid4(), uuid4(), uuid4()
        await _create_run(conn, user_id=USER_A, run_id=manual_run)
        await _commit_import(
            conn,
            user_id=USER_A,
            run_id=manual_run,
            episode_id=manual_episode,
            event_id=manual_event,
            start=start,
            identity="manual-linked",
            source="ios",
        )
        manual_result = await reverse_migraine_import_run(conn, USER_A, str(manual_run))
        assert str(manual_episode) in manual_result.preserved_episode_ids
        assert await _scalar(
            conn, "select count(*) from raw.user_symptom_events where id = %s", (manual_event,)
        ) == 1

        for kind in ("note", "state_change", "follow_up"):
            run_id, episode_id, event_id = uuid4(), uuid4(), uuid4()
            await _create_run(conn, user_id=USER_A, run_id=run_id)
            await _commit_import(
                conn,
                user_id=USER_A,
                run_id=run_id,
                episode_id=episode_id,
                event_id=event_id,
                start=start,
                identity=f"backdated-{kind}",
            )
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    insert into raw.user_symptom_episode_updates
                      (episode_id, user_id, update_kind, state, note_text,
                       occurred_at, source, created_at)
                    values (%s, %s, %s, 'ongoing', %s, %s, 'ios', now())
                    """,
                    (episode_id, USER_A, kind, f"backdated {kind}", start.replace(year=2025)),
                )
            result = await reverse_migraine_import_run(conn, USER_A, str(run_id))
            assert str(episode_id) in result.preserved_episode_ids
            assert await _scalar(
                conn, "select count(*) from raw.user_symptom_events where id = %s", (event_id,)
            ) == 1
    finally:
        await conn.close()


@pytest.mark.anyio
async def test_import_link_failure_rolls_back_detail_identity_and_link() -> None:
    conn = await _connect()
    try:
        await _reset(conn)
        start = datetime(2026, 9, 8, 16, tzinfo=UTC)
        run_id, episode_id, event_id = uuid4(), uuid4(), uuid4()
        await _create_run(conn, user_id=USER_A, run_id=run_id)
        await _insert_parent(
            conn,
            user_id=USER_A,
            episode_id=episode_id,
            event_id=event_id,
            start=start,
            source=f"import:{run_id}",
        )
        async with conn.cursor() as cur:
            await cur.execute(
                """
                create or replace function raw.g009_fail_link()
                returns trigger language plpgsql as $$
                begin
                  if new.raw_row_ref = 'g009-fail-link' then
                    raise exception 'forced link failure';
                  end if;
                  return new;
                end $$
                """
            )
            await cur.execute(
                """
                create trigger g009_fail_link
                before insert on raw.user_migraine_episode_import_links
                for each row execute function raw.g009_fail_link()
                """
            )
        with pytest.raises(psycopg.DatabaseError, match="forced link failure"):
            await commit_migraine_import_episode(
                conn,
                USER_A,
                _episode(
                    episode_id=episode_id,
                    event_id=event_id,
                    start=start,
                    source_type="import",
                    run_id=run_id,
                    raw_row_ref="g009-fail-link",
                ),
                source_identity_key="link-failure",
            )
        for table in (
            "user_migraine_episode_details",
            "user_migraine_episode_detail_revisions",
            "user_migraine_import_identities",
            "user_migraine_episode_import_links",
        ):
            assert await _scalar(
                conn,
                sql.SQL("select count(*) from raw.{} where episode_id = %s").format(
                    sql.Identifier(table)
                ),
                (episode_id,),
            ) == 0
    finally:
        async with conn.cursor() as cur:
            await cur.execute("drop trigger if exists g009_fail_link on raw.user_migraine_episode_import_links")
            await cur.execute("drop function if exists raw.g009_fail_link()")
        await conn.close()


@pytest.mark.anyio
async def test_competing_imports_serialize_and_failed_candidate_is_not_orphaned() -> None:
    setup = await _connect()
    await _reset(setup)
    start = datetime(2026, 9, 8, 17, tzinfo=UTC)
    run_1, run_2 = uuid4(), uuid4()
    await _create_run(setup, user_id=USER_A, run_id=run_1)
    await _create_run(setup, user_id=USER_A, run_id=run_2)
    await setup.close()

    async def contender(run_id: UUID, row: str) -> tuple[str, UUID, UUID]:
        conn = await _connect()
        episode_id, event_id = uuid4(), uuid4()
        try:
            async with conn.transaction():
                await _insert_parent(
                    conn,
                    user_id=USER_A,
                    episode_id=episode_id,
                    event_id=event_id,
                    start=start,
                    source=f"import:{run_id}",
                )
                await commit_migraine_import_episode(
                    conn,
                    USER_A,
                    _episode(
                        episode_id=episode_id,
                        event_id=event_id,
                        start=start,
                        source_type="import",
                        run_id=run_id,
                        raw_row_ref=row,
                    ),
                    source_identity_key="concurrent-stable-identity",
                )
            return "committed", episode_id, event_id
        except MigraineImportConflict:
            return "conflict", episode_id, event_id
        finally:
            await conn.close()

    results = await asyncio.gather(contender(run_1, "row:a"), contender(run_2, "row:b"))
    assert sorted(result[0] for result in results) == ["committed", "conflict"]
    check = await _connect()
    try:
        assert await _scalar(
            check,
            "select count(*) from raw.user_migraine_import_identities where source_identity_key = 'concurrent-stable-identity'",
        ) == 1
        assert await _scalar(
            check, "select count(*) from raw.user_symptom_events where ts_utc = %s", (start,)
        ) == 1
        failed_event = next(result[2] for result in results if result[0] == "conflict")
        assert await _scalar(
            check, "select count(*) from raw.user_symptom_events where id = %s", (failed_event,)
        ) == 0
    finally:
        await check.close()


@pytest.mark.anyio
async def test_user_update_lock_precedes_reversal_and_prevents_data_loss() -> None:
    setup = await _connect()
    await _reset(setup)
    start = datetime(2026, 9, 8, 18, tzinfo=UTC)
    run_id, episode_id, event_id = uuid4(), uuid4(), uuid4()
    await _create_run(setup, user_id=USER_A, run_id=run_id)
    await _commit_import(
        setup,
        user_id=USER_A,
        run_id=run_id,
        episode_id=episode_id,
        event_id=event_id,
        start=start,
        identity="user-update-race",
    )
    await setup.close()

    update_locked = asyncio.Event()
    reversal_started = asyncio.Event()
    allow_commit = asyncio.Event()
    backend_pids: dict[str, int] = {}

    async def user_update() -> None:
        conn = await _connect(autocommit=False)
        try:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute("select pg_backend_pid()")
                    backend_pids["writer"] = int((await cur.fetchone())[0])
                    await cur.execute(
                        "select id from raw.user_symptom_episodes where id = %s for update",
                        (episode_id,),
                    )
                    update_locked.set()
                    await allow_commit.wait()
                    await cur.execute(
                        """
                        insert into raw.user_symptom_episode_updates
                          (episode_id, user_id, update_kind, note_text, occurred_at, source)
                        values (%s, %s, 'note', 'keep this user note', %s, 'ios')
                        """,
                        (episode_id, USER_A, start.replace(year=2025)),
                    )
        finally:
            await conn.close()

    async def reverse_after_lock():
        await update_locked.wait()
        conn = await _connect()
        try:
            backend_pids["reversal"] = int(await _scalar(conn, "select pg_backend_pid()"))
            reversal_started.set()
            return await reverse_migraine_import_run(conn, USER_A, str(run_id))
        finally:
            await conn.close()

    update_task = asyncio.create_task(user_update())
    reversal_task = asyncio.create_task(reverse_after_lock())
    await update_locked.wait()
    await reversal_started.wait()
    await _wait_for_backend_block(
        blocked_pid=backend_pids["reversal"],
        blocker_pid=backend_pids["writer"],
    )
    assert not reversal_task.done()
    allow_commit.set()
    await update_task
    reversal = await reversal_task
    assert str(episode_id) in reversal.preserved_episode_ids

    check = await _connect()
    try:
        assert await _scalar(
            check, "select count(*) from raw.user_symptom_events where id = %s", (event_id,)
        ) == 1
        assert await _scalar(
            check,
            "select count(*) from raw.user_symptom_episode_updates where episode_id = %s and note_text = 'keep this user note'",
            (episode_id,),
        ) == 1
    finally:
        await check.close()
