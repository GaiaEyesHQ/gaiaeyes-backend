"""Opt-in stored-function parity and safety checks on disposable PostgreSQL.

Set GAIA_TEST_POSTGRES_DSN to a numeric-loopback PostgreSQL admin URL and run:
    python -m pytest tests/integration/test_summary_materialization.py -q

The imported fixture creates/drops a unique database and never reads a service
DSN. The migration's pinned original definition is the fixture, avoiding another
copy that could drift. Only samples and daily_summary are synthesized. The
actual PL/pgSQL function, migration, and rollback execute against PostgreSQL.
Set GAIA_TEST_SUMMARY_LARGE_PLAN=1 to include the 53,000-sample plan regression.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg import errors, sql
from psycopg.pq import TransactionStatus

from test_refresh_postgres import postgres_dsn  # noqa: F401 -- shared safe fixture

pytestmark = pytest.mark.skipif(
    not os.getenv("GAIA_TEST_POSTGRES_DSN"),
    reason="set GAIA_TEST_POSTGRES_DSN to opt into a disposable local database",
)

ROOT = Path(__file__).resolve().parents[2]
FILENAME = "20261010171000_materialize_summary_resp_rows.sql"
MIGRATION = ROOT / "supabase" / "migrations" / FILENAME
ROLLBACK = ROOT / "supabase" / "rollbacks" / FILENAME
SIGNATURE = "gaia.refresh_daily_summary_user(uuid,date,text,integer)"
USER = "00000000-0000-4000-8000-000000000001"
OTHER_USER = "00000000-0000-4000-8000-000000000002"
ORIGINAL_CTE = "resp_rows as ("
MATERIALIZED_CTE = "resp_rows as materialized ("


@pytest.fixture(scope="module")
def original_definition():
    matches = re.findall(r"\$expected\$(.*?)\$expected\$", MIGRATION.read_text(), re.S)
    assert len(matches) == 1, "migration must pin exactly one original definition"
    definition = matches[0]
    assert definition.startswith("CREATE OR REPLACE FUNCTION gaia.refresh_daily_summary_user(")
    assert definition.count(ORIGINAL_CTE) == 1
    assert MATERIALIZED_CTE not in definition
    return definition


def extracted_select(conn, definition, day=date(2026, 10, 10), days_back=45, tz="UTC"):
    """Extract the unchanged SELECT only for schema inference and EXPLAIN.

    Parity tests below call the stored function; they never substitute this
    query for its INSERT/ON CONFLICT or transaction behavior.
    """
    insert = re.search(
        r"  insert into gaia\.daily_summary\s*\((.*?)\)\s*(select.*?)(?=  on conflict)",
        definition,
        re.S,
    )
    assert insert is not None
    columns = [column.strip() for column in insert.group(1).split(",")]
    query = definition[definition.index("  with raw as ("):insert.start()]
    query += insert.group(2)
    start = day - timedelta(days=days_back - 1)
    replacements = {
        "p_user_id": sql.Literal(USER).as_string(conn) + "::uuid",
        "v_tz": sql.Literal(tz).as_string(conn) + "::text",
        "v_window_end": sql.Literal(day).as_string(conn),
        "v_window_start": sql.Literal(start).as_string(conn),
        "v_history_start": sql.Literal(start - timedelta(days=60)).as_string(conn),
        "v_cycle_start": sql.Literal(start - timedelta(days=180)).as_string(conn),
    }
    for name, value in replacements.items():
        query = re.sub(r"\b" + name + r"\b", lambda _: value, query)
    return columns, query


@pytest.fixture
def summary_db(postgres_dsn, original_definition):
    with psycopg.connect(postgres_dsn) as conn:
        try:
            # One outer transaction freezes now() for old/new comparisons,
            # including updated_at. Each fixture is rolled back, even on failure.
            conn.execute("SET LOCAL TIME ZONE 'UTC'")
            conn.execute("SET LOCAL statement_timeout = '30s'")
            conn.execute("SET LOCAL jit = off")
            conn.execute("""
                CREATE SCHEMA gaia;
                CREATE TABLE gaia.samples (
                    user_id uuid NOT NULL,
                    type text NOT NULL,
                    start_time timestamptz NOT NULL,
                    end_time timestamptz,
                    value double precision,
                    value_text text
                );
                CREATE INDEX idx_samples_user_ts ON gaia.samples(user_id, start_time)
            """)
            columns, query = extracted_select(conn, original_definition)
            conn.execute(
                sql.SQL("CREATE TABLE gaia.daily_summary ({}) AS {} WITH NO DATA").format(
                    sql.SQL(", ").join(map(sql.Identifier, columns)), sql.SQL(query)
                )
            )
            conn.execute("ALTER TABLE gaia.daily_summary ADD PRIMARY KEY (user_id, date)")
            conn.execute(original_definition)
            assert function_definition(conn) == original_definition
            yield conn
        finally:
            conn.rollback()


def apply_guard(conn, path):
    # Execute the complete checked-in script in the caller's transaction. The
    # migration deliberately contains no BEGIN/COMMIT of its own.
    conn.execute(path.read_text())


def function_definition(conn):
    return conn.execute("SELECT pg_get_functiondef(%s::regprocedure)", (SIGNATURE,)).fetchone()[0]


def function_catalog(conn):
    # Includes OID, owner, ACL, security, configuration, defaults, return type,
    # argument metadata, volatility, parallelism, cost, support, and language.
    return conn.execute(
        "SELECT to_jsonb(p) FROM pg_proc p WHERE oid = %s::regprocedure", (SIGNATURE,)
    ).fetchone()[0]



def snapshot(conn):
    return conn.execute("SELECT * FROM gaia.daily_summary ORDER BY user_id, date").fetchall()


def call_summary(conn, day, tz="UTC", days_back=3, user=USER):
    assert conn.execute(
        "SELECT gaia.refresh_daily_summary_user(%s::uuid, %s::date, %s::text, %s::integer)",
        (user, day, tz, days_back),
    ).fetchone() == ("",)


def insert_samples(conn, rows):
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO gaia.samples(user_id, type, start_time, end_time, value, value_text) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            rows,
        )


def rich_samples(day, tz):
    """History, overlaps, strict boundary contacts, nulls, and all output inputs."""
    zone = ZoneInfo(tz)
    rows = []
    for offset in range(-17, 2):
        local_day = day + timedelta(days=offset)

        def sample(kind, start_minutes, end_minutes, value=None, text=None, user=USER):
            midnight = datetime.combine(local_day, time(), zone)
            start = (midnight + timedelta(minutes=start_minutes)).astimezone(timezone.utc)
            end = None if end_minutes is None else (
                midnight + timedelta(minutes=end_minutes)
            ).astimezone(timezone.utc)
            rows.append((user, kind, start, end, value, text))

        sample("sleep_stage", 0, 120, text="CORE")
        sample("sleep_rem", 60, 180)
        sample("sleep_deep", 180, 240)
        sample("sleep_awake", 240, 300)
        sample("sleep_in_bed", 0, 360)
        sample("sleep_asleep", 300, 360)
        sample("sleep_light", 400, None)
        # The overlap at 01:30 must not double count a respiratory measurement.
        for start, end, value in (
            (30, 45, 12), (90, 105, 14), (179, 181, 16), (240, 300, 30),
            (300, 315, 18), (420, 435, 22), (0, None, 24), (60, None, 20),
            (180, 180, 26), (30, 45, None), (60, None, None),
        ):
            sample("Respiratory_Rate", start, end, value)
        for kind, value, text in (
            ("heart_rate", 50 + offset, None), ("heart_rate", 90 + offset, None),
            ("hrv_rmssd", 40 + offset, None), ("steps", 100, None),
            ("step_count", 200, None), ("spo2", 0.98, None),
            ("bp_sys", 120, None), ("bp_dia", 80, None),
            ("resting_heart_rate", 60 + offset, None),
            ("temperature_deviation", offset / 8, "sensor"),
        ):
            sample(kind, 720, None, value, text)
        if offset in {-16, -15, -2}:
            sample("menstrual_flow", 720, 780, 1)
        sample("respiratory_rate", 30, 45, 999, user=OTHER_USER)
    # Far outside both the output and lookback windows.
    old = datetime.combine(day - timedelta(days=400), time(12), zone)
    rows.append((USER, "respiratory_rate", old, old + timedelta(minutes=1), 9999, None))
    return rows


def seed_sentinels(conn, day):
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO gaia.daily_summary(user_id, date, hr_min, updated_at) "
            "VALUES (%s, %s, -999, '2000-01-01 00:00:00+00')",
            [(USER, day - timedelta(days=5)), (USER, day + timedelta(days=1)), (OTHER_USER, day)],
        )


@pytest.mark.parametrize("tz, day", [
    ("America/Chicago", date(2026, 3, 9)),
    ("America/Chicago", date(2026, 11, 2)),
    ("America/Havana", date(2026, 3, 9)),
    ("America/Havana", date(2026, 11, 2)),
    ("Pacific/Apia", date(2011, 12, 31)),
])
def test_actual_function_preserves_all_columns_across_dst_and_date_line(summary_db, tz, day):
    conn = summary_db
    # A different session zone must not silently substitute for p_tz.
    conn.execute("SET LOCAL TIME ZONE 'Asia/Kathmandu'")
    insert_samples(conn, rich_samples(day, tz))
    seed_sentinels(conn, day)
    untouched = snapshot(conn)
    call_summary(conn, day, tz)
    expected = snapshot(conn)
    assert len(expected) > len(untouched)
    assert all(row in expected for row in untouched)
    assert conn.execute(
        "SELECT count(*) FROM gaia.daily_summary WHERE user_id = %s AND date BETWEEN %s AND %s",
        (USER, day - timedelta(days=2), day),
    ).fetchone()[0] == (2 if tz == "Pacific/Apia" else 3)
    # No baseline columns should be silently omitted from the comparison.
    assert len(expected[0]) == 33
    assert conn.execute(
        "SELECT respiratory_rate_baseline_delta IS NOT NULL, "
        "temperature_deviation_baseline_delta IS NOT NULL, "
        "resting_hr_baseline_delta IS NOT NULL, bedtime_consistency_score IS NOT NULL, "
        "waketime_consistency_score IS NOT NULL, sleep_vs_14d_baseline_delta IS NOT NULL "
        "FROM gaia.daily_summary WHERE user_id = %s AND date = %s", (USER, day),
    ).fetchone() == (True,) * 6
    conn.execute("TRUNCATE gaia.daily_summary")
    seed_sentinels(conn, day)
    apply_guard(conn, MIGRATION)
    call_summary(conn, day, tz)
    assert snapshot(conn) == expected


@pytest.mark.parametrize("case", ["empty", "no-respiration", "null-respiration", "overlap-and-null-end"])
def test_actual_function_preserves_empty_null_and_overlap_behavior(summary_db, case):
    conn = summary_db
    day = date(2026, 1, 2)
    rows = rich_samples(day, "UTC")
    if case == "empty":
        rows = []
    elif case == "no-respiration":
        rows = [row for row in rows if row[1].lower() != "respiratory_rate"]
    elif case == "null-respiration":
        rows = [(*row[:4], None, row[5]) if row[1].lower() == "respiratory_rate" else row for row in rows]
    insert_samples(conn, rows)
    call_summary(conn, day, days_back=1)
    expected = snapshot(conn)
    if case == "empty":
        assert expected == []
    else:
        resp = conn.execute(
            "SELECT respiratory_rate_avg, respiratory_rate_sleep_avg FROM gaia.daily_summary"
        ).fetchone()
        if case == "overlap-and-null-end":
            assert resp == (182 / 9, 16.0)
        else:
            assert resp == (None, None)
    conn.execute("TRUNCATE gaia.daily_summary")
    apply_guard(conn, MIGRATION)
    call_summary(conn, day, days_back=1)
    assert snapshot(conn) == expected


def test_actual_function_upsert_and_default_arguments_preserve_every_column(summary_db):
    conn = summary_db
    day = conn.execute("SELECT current_date").fetchone()[0]
    insert_samples(conn, rich_samples(day, "America/Chicago"))

    def run_versions():
        # Omitted defaults and explicit null/blank values take their real paths.
        conn.execute("SELECT gaia.refresh_daily_summary_user(%s::uuid, %s::date)", (USER, day))
        first = snapshot(conn)
        conn.execute(
            "UPDATE gaia.samples SET value = value + 4 "
            "WHERE user_id = %s AND lower(type) = 'respiratory_rate'", (USER,),
        )
        call_summary(conn, None, tz="  ", days_back=None)
        second = snapshot(conn)
        call_summary(conn, day, tz=None, days_back=0)
        assert snapshot(conn) == second
        assert len(first) == len(second) and first != second
        return first, second

    expected = run_versions()
    conn.execute("TRUNCATE gaia.daily_summary")
    conn.execute(
        "UPDATE gaia.samples SET value = value - 4 "
        "WHERE user_id = %s AND lower(type) = 'respiratory_rate'", (USER,),
    )
    apply_guard(conn, MIGRATION)
    assert run_versions() == expected


def test_migration_changes_one_phrase_preserves_entire_catalog_and_rolls_back_exactly(summary_db):
    conn = summary_db
    # Exercise a nondefault ACL without creating cluster-wide roles.
    conn.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    before = function_catalog(conn)
    before_definition = function_definition(conn)
    assert before["proacl"] is not None
    apply_guard(conn, MIGRATION)
    after = function_catalog(conn)
    assert after["prosrc"] == before["prosrc"].replace(ORIGINAL_CTE, MATERIALIZED_CTE)
    assert function_definition(conn) == before_definition.replace(ORIGINAL_CTE, MATERIALIZED_CTE)
    assert {k: v for k, v in after.items() if k != "prosrc"} == {
        k: v for k, v in before.items() if k != "prosrc"
    }
    apply_guard(conn, ROLLBACK)
    assert function_catalog(conn) == before
    assert function_definition(conn) == before_definition


@pytest.mark.parametrize("drift", ["body", "config", "security", "default"])
@pytest.mark.parametrize("direction", ["migration", "rollback"])
def test_migration_and_rollback_reject_definition_drift_without_mutation(summary_db, drift, direction):
    conn = summary_db
    if direction == "rollback":
        apply_guard(conn, MIGRATION)
    if drift == "body":
        definition = function_definition(conn)
        assert definition.count("v_window_start - 60") == 1
        conn.execute(definition.replace("v_window_start - 60", "v_window_start - 59"))
    elif drift == "config":
        conn.execute(f"ALTER FUNCTION {SIGNATURE} SET statement_timeout = '15s'")
    elif drift == "security":
        conn.execute(f"ALTER FUNCTION {SIGNATURE} SECURITY DEFINER")
    else:
        definition = function_definition(conn)
        assert definition.count("DEFAULT 45") == 1
        conn.execute(definition.replace("DEFAULT 45", "DEFAULT 44"))
    before = function_catalog(conn)
    with pytest.raises(errors.RaiseException):
        with conn.transaction():
            apply_guard(conn, MIGRATION if direction == "migration" else ROLLBACK)
    assert function_catalog(conn) == before


def test_second_application_and_second_rollback_fail_closed(summary_db):
    conn = summary_db
    apply_guard(conn, MIGRATION)
    applied = function_catalog(conn)
    with pytest.raises(errors.RaiseException):
        with conn.transaction():
            apply_guard(conn, MIGRATION)
    assert function_catalog(conn) == applied
    apply_guard(conn, ROLLBACK)
    reverted = function_catalog(conn)
    with pytest.raises(errors.RaiseException):
        with conn.transaction():
            apply_guard(conn, ROLLBACK)
    assert function_catalog(conn) == reverted


def test_multiline_original_declaration_preserves_default_semantics(summary_db, original_definition):
    conn = summary_db
    historical = (ROOT / "supabase" / "migrations" / "20260319113000_expand_healthkit_phase2_context.sql").read_text()
    match = re.search(
        r"create or replace function gaia\.refresh_daily_summary_user\(.*?\n\$\$;",
        historical,
        re.S,
    )
    assert match is not None
    conn.execute(match.group())
    assert function_definition(conn) == original_definition
    before = function_catalog(conn)
    apply_guard(conn, MIGRATION)
    after = function_catalog(conn)
    assert {k: v for k, v in before.items() if k != "prosrc"} == {
        k: v for k, v in after.items() if k != "prosrc"
    }
    apply_guard(conn, ROLLBACK)
    assert function_catalog(conn) == before
    assert function_definition(conn) == original_definition


def test_complete_scripts_are_atomic_restore_timeouts_and_rollback_exactly(postgres_dsn, original_definition):
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA gaia")
        try:
            conn.execute(original_definition)
            before = function_catalog(conn)
            conn.execute("SET lock_timeout = '2s'; SET statement_timeout = '30s'")
            conn.execute(MIGRATION.read_text())
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert conn.execute("SHOW lock_timeout").fetchone() == ("2s",)
            assert conn.execute("SHOW statement_timeout").fetchone() == ("30s",)
            assert function_definition(conn) == original_definition.replace(ORIGINAL_CTE, MATERIALIZED_CTE)
            conn.execute(ROLLBACK.read_text())
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert function_catalog(conn) == before
            assert function_definition(conn) == original_definition
            conn.execute(f"ALTER FUNCTION {SIGNATURE} SET statement_timeout = '15s'")
            drifted = function_catalog(conn)
            with pytest.raises(errors.RaiseException, match="definition drift"):
                conn.execute(MIGRATION.read_text())
            assert conn.info.transaction_status == TransactionStatus.IDLE
            assert function_catalog(conn) == drifted
        finally:
            conn.rollback()
            conn.execute("DROP SCHEMA gaia CASCADE")


@pytest.mark.parametrize("script", [MIGRATION, ROLLBACK], ids=["migration", "rollback"])
def test_complete_scripts_reject_missing_function_without_creating_it(postgres_dsn, script):
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        with pytest.raises(errors.RaiseException, match="missing"):
            conn.execute(script.read_text())
        conn.rollback()
        assert conn.execute("SELECT to_regprocedure(%s)", (SIGNATURE,)).fetchone() == (None,)


def test_migration_and_rollback_obey_outer_transaction_rollback(postgres_dsn, original_definition):
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA gaia")
        try:
            conn.execute(original_definition)
            original = function_catalog(conn)
            with conn.transaction(force_rollback=True):
                conn.execute(MIGRATION.read_text())
                assert function_definition(conn) == original_definition.replace(ORIGINAL_CTE, MATERIALIZED_CTE)
            assert function_catalog(conn) == original
            conn.execute(MIGRATION.read_text())
            patched = function_catalog(conn)
            with conn.transaction(force_rollback=True):
                conn.execute(ROLLBACK.read_text())
                assert function_definition(conn) == original_definition
            assert function_catalog(conn) == patched
        finally:
            conn.execute("DROP SCHEMA gaia CASCADE")


def test_migration_lock_timeout_leaves_original_function_unchanged(postgres_dsn, original_definition):
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA gaia")
        try:
            conn.execute(original_definition)
            conn.execute("SET lock_timeout = '0'; SET statement_timeout = '5s'")
            before = function_catalog(conn)
            with psycopg.connect(postgres_dsn) as holder:
                try:
                    holder.execute(f"ALTER FUNCTION {SIGNATURE} COST 101")
                    # The uncommitted ALTER holds the catalog lock while the
                    # migration still sees the pinned original definition.
                    with pytest.raises(errors.LockNotAvailable):
                        conn.execute(MIGRATION.read_text())
                    assert conn.info.transaction_status == TransactionStatus.IDLE
                    assert conn.execute("SHOW lock_timeout").fetchone() == ("0",)
                finally:
                    holder.rollback()
            assert function_catalog(conn) == before
            assert function_definition(conn) == original_definition
            conn.execute(MIGRATION.read_text())
            assert function_definition(conn) == original_definition.replace(ORIGINAL_CTE, MATERIALIZED_CTE)
        finally:
            conn.execute("DROP SCHEMA gaia CASCADE")


def plan_nodes(node):
    yield node
    for child in node.get("Plans", []):
        yield from plan_nodes(child)


@pytest.mark.skipif(
    os.getenv("GAIA_TEST_SUMMARY_LARGE_PLAN") != "1",
    reason="set GAIA_TEST_SUMMARY_LARGE_PLAN=1 for the 53,000-sample plan regression",
)
def test_large_history_executes_real_function_and_materializes_respiration_once(summary_db, record_property):
    conn = summary_db
    day = date(2026, 10, 10)
    conn.execute("SET LOCAL work_mem = '5MB'")
    conn.execute("""
        INSERT INTO gaia.samples
        SELECT %s::uuid,
            CASE WHEN k < 20 THEN 'sleep_stage'
                 WHEN k < 60 THEN 'respiratory_rate'
                 WHEN k < 190 THEN 'heart_rate'
                 WHEN k < 195 THEN 'resting_heart_rate'
                 WHEN k < 198 THEN 'temperature_deviation' ELSE 'step_count' END,
            ((%s::date - d)::timestamp AT TIME ZONE 'America/Chicago')
                + make_interval(mins => k * 6),
            ((%s::date - d)::timestamp AT TIME ZONE 'America/Chicago')
                + make_interval(mins => k * 6 + 20),
            (k %% 30 + 10)::double precision,
            CASE WHEN k < 20 THEN 'core' ELSE '' END
        FROM generate_series(0, 264) d CROSS JOIN generate_series(0, 199) k
    """, (USER, day, day))
    conn.execute("ANALYZE gaia.samples")
    assert conn.execute("SELECT count(*) FROM gaia.samples").fetchone() == (53000,)
    apply_guard(conn, MIGRATION)
    conn.execute("SET LOCAL statement_timeout = '60s'")
    started = monotonic()
    call_summary(conn, day, "America/Chicago", days_back=45)
    record_property("stored_function_seconds", round(monotonic() - started, 3))
    assert conn.execute(
        "SELECT count(*), min(date), max(date), "
        "bool_and(user_id = %s::uuid), bool_and(respiratory_rate_avg = 27), "
        "bool_and(respiratory_rate_sleep_avg = 31) FROM gaia.daily_summary", (USER,)
    ).fetchone() == (45, day - timedelta(days=44), day, True, True, True)
    _, query = extracted_select(conn, function_definition(conn), day, 45, "America/Chicago")
    explain = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query).fetchone()[0][0]
    record_property("select_execution_ms", explain["Execution Time"])
    plan = explain["Plan"]
    respiration = [node for node in plan_nodes(plan) if node.get("Subplan Name") == "CTE resp_rows"]
    assert len(respiration) == 1
    assert respiration[0]["Parent Relationship"] == "InitPlan"
    assert respiration[0]["Actual Loops"] == 1
    assert respiration[0]["Actual Rows"] > 0
    # Plan shape and actual execution counts are stable assertions; elapsed
    # milliseconds are intentionally not treated as a portable SLA.
