"""Disposable PostgreSQL regression coverage; never accepts a network DSN."""
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
import pytest
from starlette.requests import Request
from fastapi import HTTPException
from app.db import symptoms as db
from app.routers import symptoms as router


def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def conn():
    dsn = os.getenv('GAIA_MIGRAINE_ACTIVE_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('requires the isolated migraine-active PostgreSQL runner')
    params = conninfo_to_dict(dsn)
    host = params.get('host', '')
    assert host.startswith('/tmp/gaia-migraine-active-') and host.endswith('/socket')
    assert params.get('dbname') == 'gaia_migraine_test' and not params.get('hostaddr')
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as connection:
        row = await (await connection.execute("select current_setting('gaia.migraine_disposable'), inet_server_addr() ")).fetchone()
        assert row == ('true', None)
        yield connection


async def episode(conn, user, code='migraine', age=40, severity=5):
    start = datetime.now(UTC) - timedelta(days=age)
    async with conn.transaction():
        event = await db.insert_symptom_event(conn, user, symptom_code=code, ts_utc=start, severity=severity, free_text=None, tags=None)
        result = await db.ensure_symptom_episode_for_event(conn, user, symptom_event_id=event['id'], symptom_code=code, ts_utc=start, severity=severity)
        await conn.execute('update raw.user_symptom_episodes set last_interaction_at = %s where id = %s', (start, result['id']))
    return result['id'], start


@pytest.mark.anyio
async def test_old_unresolved_migraines_survive_window_and_limit_then_end_explicitly(conn):
    user, other = str(uuid4()), str(uuid4())
    ids = [(await episode(conn, user))[0] for _ in range(23)]
    other_id, _ = await episode(conn, other)
    headache, _ = await episode(conn, user, 'headache')
    rows = await db.fetch_current_symptom_items(conn, user, window_hours=12, limit=20)
    assert {row['id'] for row in rows} == set(ids)
    assert other_id not in {r['id'] for r in rows} and headache not in {r['id'] for r in rows}
    now = datetime.now(UTC)
    async with conn.transaction():
        zero = await db.record_symptom_episode_update(conn, user, ids[0], severity=0, occurred_at=now)
        assert zero['current_severity'] == 0 and zero['current_state'] != 'resolved'
        note = await db.record_symptom_episode_update(conn, user, ids[0], note_text='Synthetic note', occurred_at=now+timedelta(seconds=1))
        assert note['current_severity'] == 0
        await db.record_symptom_episode_update(conn, user, ids[0], state='resolved', occurred_at=now+timedelta(seconds=2))
        await db.record_symptom_episode_update(conn, user, ids[0], severity=1, occurred_at=now+timedelta(seconds=3))
    ended = await (await conn.execute('select resolution_ts from raw.user_symptom_episodes where id = %s', (ids[0],))).fetchone()
    assert ended[0] == now+timedelta(seconds=2)
    rows = await db.fetch_current_symptom_items(conn, user, window_hours=12, limit=20)
    assert {r['id'] for r in rows} == set(ids[1:])


@pytest.mark.anyio
async def test_full_episode_timeline_is_owner_scoped_and_retry_does_not_overwrite(conn):
    user = str(uuid4()); identifier, start = await episode(conn, user)
    async with conn.transaction():
        await db.record_symptom_episode_update(conn, user, identifier, severity=8, occurred_at=start+timedelta(hours=1))
        await db.record_symptom_episode_update(conn, user, identifier, severity=0, occurred_at=start+timedelta(hours=2))
        retried = await db.record_symptom_episode_update(conn, user, identifier, severity=8, occurred_at=start+timedelta(hours=1))
    assert retried['current_severity'] == 0
    with pytest.raises(db.StaleSymptomUpdate):
        async with conn.transaction():
            # First arrival of a delayed request, not a replay of a committed one.
            await db.record_symptom_episode_update(conn, user, identifier, severity=6, occurred_at=start+timedelta(minutes=90))
    assert (await db.fetch_symptom_episode(conn,user,identifier))['current_severity'] == 0
    rows = await db.fetch_current_symptom_timeline(conn, user, days=1, episode_id=identifier)
    assert len(rows) == 3 and max(row['severity'] for row in rows) == 8
    assert await db.fetch_current_symptom_timeline(conn, str(uuid4()), days=1, episode_id=identifier) == []
    assert await db.fetch_current_symptom_timeline(conn, user, days=1) == []


@pytest.mark.anyio
async def test_raw_and_canonical_save_roll_back_together_and_retry_acknowledges_same_episode(conn, monkeypatch):
    user = str(uuid4())
    request = Request({'type':'http', 'state':{'user_id':user}})
    payload = router.SymptomEventIn(symptom_code='MIGRAINE', ts_utc=datetime.now(UTC)-timedelta(days=2))
    async def noop(*args, **kwargs): pass
    monkeypatch.setattr(router, '_refresh_gauges_for_symptom', noop)
    monkeypatch.setattr(router.feedback_db, 'maybe_schedule_symptom_follow_up', noop)
    original = db.ensure_symptom_episode_for_event
    async def failure(*args, **kwargs): raise RuntimeError('synthetic canonical failure')
    monkeypatch.setattr(db, 'ensure_symptom_episode_for_event', failure)
    with pytest.raises(HTTPException) as error:
        await router.create_symptom_event(payload, request, conn, strict=False)
    assert error.value.status_code == 503
    assert (await (await conn.execute('select count(*) from raw.user_symptom_events where user_id=%s',(user,))).fetchone())[0] == 0
    monkeypatch.setattr(db, 'ensure_symptom_episode_for_event', original)
    first = await router.create_symptom_event(payload, request, conn, strict=False)
    retry = await router.create_symptom_event(payload, request, conn, strict=False)
    assert first.data.episode_id == retry.data.episode_id and first.data.id == retry.data.id
    row = await (await conn.execute('select current_severity, last_interaction_at, started_at from raw.user_symptom_episodes where id=%s',(first.data.episode_id,))).fetchone()
    assert row[0] is None and row[1] > row[2]+timedelta(days=1)


@pytest.mark.anyio
async def test_calendar_overlap_midnight_dst_and_ended_episode_are_retained(conn):
    from zoneinfo import ZoneInfo
    user = str(uuid4()); identifier, _ = await episode(conn, user)
    zone = ZoneInfo('America/New_York')
    # DST fall-back makes this local day 25 hours long.
    start = datetime(2026, 11, 1, tzinfo=zone).astimezone(UTC)
    end = datetime(2026, 11, 2, tzinfo=zone).astimezone(UTC)
    assert end-start == timedelta(hours=25)
    onset = start-timedelta(hours=2)
    await conn.execute('update raw.user_symptom_episodes set started_at=%s where id=%s',(onset,identifier))
    async def calendar():
        return await db.fetch_migraine_episode_range(conn,user,start=start,end=end,as_of=end,limit=50)
    active = await calendar()
    assert [row['id'] for row in active['items']] == [identifier]
    assert active['items'][0]['end_status'] == 'open'
    ended_at = start+timedelta(hours=3)
    async with conn.transaction():
        await db.record_symptom_episode_update(conn,user,identifier,state='resolved',occurred_at=ended_at)
    ended = await calendar()
    assert ended['items'][0]['end_status'] == 'recorded'
    assert ended['snapshot'] != active['snapshot']
    other = await db.fetch_migraine_episode_range(conn,str(uuid4()),start=start,end=end,as_of=end,limit=50)
    assert other['items'] == []
    # A recorded end exactly at the next day's start does not spill into that day.
    next_day = await db.fetch_migraine_episode_range(conn,user,start=end,end=end+timedelta(days=1),as_of=end+timedelta(days=1),limit=50)
    assert next_day['items'] == []


@pytest.mark.anyio
async def test_simultaneous_retries_create_one_event_and_one_episode(conn, monkeypatch):
    import asyncio
    user = str(uuid4())
    request = Request({'type':'http', 'state':{'user_id':user}})
    payload = router.SymptomEventIn(symptom_code='MIGRAINE', ts_utc=datetime.now(UTC)-timedelta(days=1))
    async def noop(*args, **kwargs): pass
    monkeypatch.setattr(router, '_refresh_gauges_for_symptom', noop)
    monkeypatch.setattr(router.feedback_db, 'maybe_schedule_symptom_follow_up', noop)
    async def submit():
        # The fixture has already validated that this DSN is our owned socket.
        async with await psycopg.AsyncConnection.connect(conn.info.dsn, autocommit=True) as separate:
            return await router.create_symptom_event(payload,request,separate,strict=False)
    first, second = await asyncio.gather(submit(),submit())
    assert first.data.id == second.data.id and first.data.episode_id == second.data.episode_id
    assert (await (await conn.execute('select count(*) from raw.user_symptom_episodes where user_id=%s',(user,))).fetchone())[0] == 1
