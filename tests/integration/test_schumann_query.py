"""Opt-in equivalence and API mapping checks against disposable PostgreSQL.

Set GAIA_TEST_POSTGRES_DSN to a disposable, numeric-loopback PostgreSQL admin
URL and run: python -m pytest tests/integration/test_schumann_query.py -q

The shared fixture creates and drops a unique database, rejects remote hosts,
and never obtains its connection target from DATABASE_URL. All source rows and
daily relations below are synthetic; these tests do not access production.
"""
from __future__ import annotations

import os
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg
import pytest

from services.schumann_daily import LATEST_SCHUMANN_SQL
from test_refresh_postgres import postgres_dsn  # noqa: F401 -- shared safe fixture

pytestmark = pytest.mark.skipif(
    not os.getenv("GAIA_TEST_POSTGRES_DSN"),
    reason="set GAIA_TEST_POSTGRES_DSN to opt into a disposable local database",
)

TIMEZONES = (
    "UTC",
    "Etc/UTC",
    "America/Los_Angeles",
    "Europe/Berlin",
    "Asia/Kathmandu",
    "Pacific/Auckland",
    "America/Havana",
    "America/Santiago",
    "Pacific/Apia",
)
ORIGINAL_SQL = """
    SELECT station_id, f0_avg_hz, f1_avg_hz, f2_avg_hz, f3_avg_hz, f4_avg_hz
    FROM marts.schumann_daily
    WHERE station_id IN ('tomsk', 'cumiana') AND day <= %(day)s
    ORDER BY day DESC,
             CASE WHEN station_id = 'tomsk' THEN 0
                  WHEN station_id = 'cumiana' THEN 1 ELSE 2 END
    LIMIT 1
"""
DAILY_SELECT = """
    SELECT station_id, date(ts_utc) AS day,
           avg(value_num) FILTER (WHERE channel = 'fundamental_hz') AS f0_avg_hz,
           avg(value_num) FILTER (WHERE channel = 'F1') AS f1_avg_hz,
           avg(value_num) FILTER (WHERE channel = 'F2') AS f2_avg_hz,
           avg(value_num) FILTER (WHERE channel = 'F3') AS f3_avg_hz,
           avg(value_num) FILTER (WHERE channel = 'F4') AS f4_avg_hz,
           avg(value_num) FILTER (WHERE channel = 'F5') AS f5_avg_hz
    FROM ext.schumann
    GROUP BY station_id, date(ts_utc)
"""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def schumann_db(postgres_dsn):
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        conn.execute("CREATE SCHEMA ext; CREATE SCHEMA marts")
        try:
            conn.execute(
                """
                CREATE TABLE ext.schumann (
                    station_id text NOT NULL,
                    ts_utc timestamptz NOT NULL,
                    channel text NOT NULL,
                    value_num numeric
                );
                CREATE INDEX fixture_station_ts
                    ON ext.schumann (station_id, ts_utc, channel);
                CREATE INDEX fixture_ts ON ext.schumann (ts_utc)
                """
            )
            conn.execute("CREATE VIEW marts.schumann_daily AS " + DAILY_SELECT)
            yield conn
        finally:
            conn.execute("DROP SCHEMA ext, marts CASCADE")


def replace_rows(conn, rows):
    conn.execute("TRUNCATE ext.schumann")
    if rows:
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO ext.schumann VALUES (%s, %s, %s, %s)", rows)


def equivalence_cases():
    """286 fixture/date pairs, each compared in nine timezones: 2,574 checks."""
    day = date(2026, 10, 10)
    yield pytest.param([], [day], id="empty")
    yield pytest.param(
        [("elsewhere", "2026-10-10T23:00:00Z", "fundamental_hz", 9)],
        [day],
        id="unselected-station",
    )
    yield pytest.param(
        [
            ("cumiana", "2026-10-09T23:00:00Z", "fundamental_hz", 9),
            ("tomsk", "2026-10-08T23:00:00Z", "fundamental_hz", 7),
            ("tomsk", "2026-10-09T00:00:00Z", "F1", None),
            ("cumiana", "2026-10-11T00:00:00Z", "F1", 15),
        ],
        [date(2026, 10, d) for d in (7, 8, 9, 10, 11)],
        id="latest-day-before-station-priority-and-null-winner",
    )
    rows = [
        (station, f"2026-10-10T{hour:02}:00:00Z", channel, value)
        for station in ("tomsk", "cumiana", "elsewhere", "Tomsk")
        for channel in ("fundamental_hz", "F1", "F2", "F3", "F4", "F5", "unrelated")
        for hour, value in (
            (0, Decimal("1.123456789")),
            (0, Decimal("1.123456789")),
            (1, Decimal("5.111111111")),
            (22, None),
        )
    ]
    yield pytest.param(
        rows,
        [day - timedelta(days=1), day, day + timedelta(days=1)],
        id="weighted-duplicates-decimal-precision-and-all-fields",
    )
    yield pytest.param(
        [
            ("tomsk", "-infinity", "F1", 11),
            ("cumiana", "-infinity", "F1", 12),
            ("tomsk", "infinity", "F1", 13),
        ],
        [day],
        id="nonfinite-timestamps",
    )
    for start in (
        "2026-03-07",
        "2026-03-28",
        "2026-10-24",
        "2026-10-31",
        "2026-04-04",
        "2026-09-05",
        "2011-12-29",
    ):
        begin = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        rows = [
            (station, begin + timedelta(minutes=15 * i), "fundamental_hz", Decimal(i))
            for i in range(96 * 4)
            for station in ("tomsk", "cumiana")
        ]
        yield pytest.param(
            rows,
            [(begin + timedelta(days=i)).date() for i in range(5)],
            id=f"dst-or-date-line-{start}",
        )
    rng = random.Random(487)
    for fixture in range(30):
        begin = datetime(2026, 10, 28, tzinfo=timezone.utc)
        rows = [
            (
                rng.choice(("tomsk", "cumiana", "elsewhere", "Tomsk")),
                begin + timedelta(minutes=rng.randrange(60 * 24 * 7)),
                rng.choice(("fundamental_hz", "F1", "F2", "F3", "F4", "F5", "unrelated")),
                rng.choice((None, Decimal(rng.randrange(1000)) / Decimal(17))),
            )
            for _ in range(rng.randrange(1, 800))
        ]
        rng.shuffle(rows)
        yield pytest.param(
            rows,
            [(begin + timedelta(days=i)).date() for i in range(8)],
            id=f"seeded-random-{fixture}",
        )


@pytest.mark.parametrize("rows, days", list(equivalence_cases()))
def test_query_matches_original_across_nine_timezones(schumann_db, rows, days):
    replace_rows(schumann_db, rows)
    for session_timezone in TIMEZONES:
        schumann_db.execute("SELECT set_config('TimeZone', %s, false)", (session_timezone,))
        for day in days:
            params = {"day": day}
            expected = schumann_db.execute(ORIGINAL_SQL, params).fetchall()
            actual = schumann_db.execute(LATEST_SCHUMANN_SQL, params).fetchall()
            assert actual == expected, (session_timezone, day, expected, actual)


@pytest.mark.parametrize("relation_kind", ["MATERIALIZED VIEW", "TABLE"])
def test_snapshot_relation_keeps_snapshot_instead_of_new_raw_rows(schumann_db, relation_kind):
    replace_rows(
        schumann_db,
        [("cumiana", "2026-10-09T12:00:00Z", "fundamental_hz", Decimal("8.25"))],
    )
    schumann_db.execute("DROP VIEW marts.schumann_daily")
    schumann_db.execute(f"CREATE {relation_kind} marts.schumann_daily AS " + DAILY_SELECT)
    # Deliberately make the raw winner disagree with the persisted daily snapshot.
    replace_rows(
        schumann_db,
        [("tomsk", "2026-10-10T12:00:00Z", "fundamental_hz", Decimal("99.5"))],
    )
    params = {"day": date(2026, 10, 10)}
    expected = [("cumiana", Decimal("8.25"), None, None, None, None)]
    assert schumann_db.execute(ORIGINAL_SQL, params).fetchall() == expected
    assert schumann_db.execute(LATEST_SCHUMANN_SQL, params).fetchall() == expected


def plan_nodes(node):
    yield node
    for child in node.get("Plans", []):
        yield from plan_nodes(child)


@pytest.mark.parametrize("session_timezone", ["UTC", "Etc/UTC", "America/Los_Angeles"])
def test_only_utc_view_bypasses_historical_daily_aggregate(schumann_db, session_timezone):
    begin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    replace_rows(
        schumann_db,
        [
            (station, begin + timedelta(hours=i), "fundamental_hz", Decimal(i))
            for i in range(24 * 120)
            for station in ("tomsk", "cumiana")
        ],
    )
    schumann_db.execute("ANALYZE ext.schumann")
    schumann_db.execute("SELECT set_config('TimeZone', %s, false)", (session_timezone,))
    plan = schumann_db.execute(
        "EXPLAIN (ANALYZE, FORMAT JSON) " + LATEST_SCHUMANN_SQL,
        {"day": date(2026, 4, 20)},
    ).fetchone()[0][0]["Plan"]
    daily_aggregates = [
        node
        for node in plan_nodes(plan)
        if node["Node Type"] == "Aggregate"
        and any("ts_utc" in key for key in node.get("Group Key", []))
    ]
    assert daily_aggregates, "expected the original view's historical daily aggregate"
    if session_timezone == "UTC":
        assert all(node["Actual Loops"] == 0 for node in daily_aggregates)
    else:
        assert any(node["Actual Loops"] > 0 for node in daily_aggregates)


@pytest.fixture
def summary_module(postgres_dsn, monkeypatch):
    # The import needs application settings, but it must not inherit real DSNs.
    for name in ("DATABASE_URL", "SUPABASE_DB_URL", "DIRECT_URL"):
        monkeypatch.setenv(name, postgres_dsn)
    from app.routers import summary

    return summary


@pytest.mark.anyio
@pytest.mark.parametrize("session_timezone", ["UTC", "America/Los_Angeles"])
@pytest.mark.parametrize("scenario", ["empty", "null-winner", "all-fields"])
async def test_summary_fetch_maps_real_async_cursor_rows(
    postgres_dsn, schumann_db, summary_module, session_timezone, scenario
):
    values = [None] * 5
    rows = []
    if scenario == "null-winner":
        rows = [
            ("cumiana", "2026-10-10T12:00:00Z", "fundamental_hz", Decimal("8.25")),
            ("tomsk", "2026-10-10T12:00:00Z", "unrelated", 99),
        ]
    elif scenario == "all-fields":
        values = list(map(Decimal, ("7.83", "14.2", "20.1", "26.0", "33.8")))
        rows = [
            ("tomsk", "2026-10-10T12:00:00Z", channel, value)
            for channel, value in zip(("fundamental_hz", "F1", "F2", "F3", "F4"), values)
        ]
    replace_rows(schumann_db, rows)
    async with await psycopg.AsyncConnection.connect(postgres_dsn) as conn:
        await conn.execute("SELECT set_config('TimeZone', %s, false)", (session_timezone,))
        actual = await summary_module._fetch_schumann_row(conn, date(2026, 10, 10))
    assert actual == {
        "sch_station": None if scenario == "empty" else "tomsk",
        "sch_f0_hz": values[0],
        "sch_f1_hz": values[1],
        "sch_f2_hz": values[2],
        "sch_f3_hz": values[3],
        "sch_f4_hz": values[4],
    }
    if scenario == "all-fields":
        assert all(isinstance(actual[f"sch_f{i}_hz"], Decimal) for i in range(5))
