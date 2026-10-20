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
async def test_legacy_quick_log_receipt_matches_committed_event_and_active_episode(conn, monkeypatch):
    user = str(uuid4())
    request = Request({'type': 'http', 'state': {'user_id': user}})
    payload = router.SymptomEventIn.model_validate({'symptom_code': 'MIGRAINE'})
    async def noop(*args, **kwargs): pass
    monkeypatch.setattr(router, '_refresh_gauges_for_symptom', noop)
    monkeypatch.setattr(router.feedback_db, 'maybe_schedule_symptom_follow_up', noop)
    before = datetime.now(UTC)
    result = await router.create_symptom_event(payload, request, conn, strict=False)
    after = datetime.now(UTC)
    receipt = result.model_dump(mode='json')['data']
    logged_at = datetime.fromisoformat(receipt['ts_utc'])
    assert before <= logged_at <= after
    row = await (await conn.execute('''
        select e.ts_utc, ep.started_at, e.severity, ep.original_severity,
               ep.current_severity, ep.current_state, ep.resolution_ts, e.free_text
          from raw.user_symptom_events e
          join raw.user_symptom_episodes ep on ep.symptom_event_id=e.id and ep.user_id=e.user_id
         where e.id=%s and ep.id=%s and e.user_id=%s
    ''', (receipt['id'], receipt['episode_id'], user))).fetchone()
    assert row == (logged_at, logged_at, None, None, None, 'new', None, None)
    assert [item['id'] for item in await db.fetch_current_symptom_items(conn, user, window_hours=12)] == [receipt['episode_id']]
    history = await db.fetch_symptom_episode_range(conn, user, start=before-timedelta(seconds=1),
        end=after+timedelta(seconds=1), as_of=after, limit=50)
    assert [item['id'] for item in history['items']] == [receipt['episode_id']]


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
    assert datetime.fromisoformat(first.data.ts_utc) == payload.ts_utc
    assert retry.data.ts_utc == first.data.ts_utc
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


@pytest.mark.anyio
async def test_shared_calendar_mixed_legacy_records_and_day_spans_without_duplication(conn):
    from zoneinfo import ZoneInfo
    user, other = str(uuid4()), str(uuid4())
    zone = ZoneInfo('America/New_York')
    start = datetime(2026,11,1,tzinfo=zone).astimezone(UTC)
    end = datetime(2026,11,2,tzinfo=zone).astimezone(UTC)
    assert end-start == timedelta(hours=25)
    async def canonical(code, onset, state='new', ended=None):
        identifier, _ = await episode(conn,user,code)
        await conn.execute('update raw.user_symptom_episodes set started_at=%s,current_state=%s,resolution_ts=%s where id=%s',
            (onset,state,ended,identifier))
        return identifier
    migraine = await canonical('migraine',start-timedelta(days=3))
    headache = await canonical('headache',start+timedelta(hours=1))
    ongoing = await canonical('headache',start-timedelta(days=1),'ongoing')
    ended = await canonical('headache',start-timedelta(hours=1),'resolved',start+timedelta(hours=1))
    await canonical('headache',start-timedelta(hours=1)) # Point on prior day only.
    await canonical('headache',start-timedelta(hours=1),'resolved',start) # Exclusive end boundary.
    await canonical('headache',end) # Exclusive onset boundary.
    await conn.execute("insert into dim.symptom_codes(symptom_code,label) values('fatigue','Fatigue') on conflict do nothing")
    raw = await db.insert_symptom_event(conn,user,symptom_code='fatigue',ts_utc=start,severity=2,free_text='Synthetic legacy note',tags=None)
    await db.insert_symptom_event(conn,other,symptom_code='fatigue',ts_utc=start,severity=2,free_text=None,tags=None)
    for _ in range(3):
        await conn.execute("insert into raw.user_symptom_episode_updates(episode_id,user_id,update_kind) values(%s,%s,'note')",(headache,user))
    page = await db.fetch_symptom_episode_range(conn,user,start=start,end=end,as_of=end,limit=100)
    rows = {r['id']:r for r in page['items']}
    assert set(rows) == {migraine,headache,ongoing,ended,raw['id']}
    assert len(page['items']) == 5
    assert rows[raw['id']]['record_kind'] == 'event' and rows[raw['id']]['end_status'] == 'instant'
    assert rows[headache]['symptom_code'] == 'HEADACHE' and rows[headache]['end_status'] == 'instant'
    assert rows[migraine]['end_status'] == rows[ongoing]['end_status'] == 'open'
    assert rows[ended]['end_status'] == 'recorded'
    assert {r['symptom_code'] for r in page['items']} == {'MIGRAINE','HEADACHE','FATIGUE'}


@pytest.mark.anyio
async def test_shared_calendar_cursor_kind_owner_and_snapshot_are_stable(conn):
    from services.migraine.history import read_history, HistoryChanged
    user = str(uuid4()); identifier,onset = await episode(conn,user,age=1)
    # UUIDs may coincide across tables. Both distinct records must survive paging.
    await conn.execute("insert into raw.user_symptom_events(id,user_id,ts_utc,symptom_code,severity) values(%s,%s,%s,'headache',2)",
        (identifier,user,onset))
    args = dict(start=onset-timedelta(hours=1),end=onset+timedelta(days=1),limit=1,all_symptoms=True)
    page = await read_history(conn,user,**args)
    assert page['next_cursor'] and page['items'][0]['record_kind'] == 'event'
    await conn.execute("set time zone 'Asia/Tokyo'")
    last = await read_history(conn,user,cursor=page['next_cursor'],**args)
    assert last['complete'] and last['items'][0]['record_kind'] == 'episode'
    assert last['snapshot'] == page['snapshot']
    with pytest.raises(ValueError):
        await read_history(conn,str(uuid4()),cursor=page['next_cursor'],**args)
    with pytest.raises(ValueError):
        await read_history(conn,user,cursor=page['next_cursor'],**{**args,'all_symptoms':False})
    await conn.execute("update raw.user_symptom_events set free_text='Synthetic revised note' where id=%s",(identifier,))
    with pytest.raises(HistoryChanged):
        await read_history(conn,user,cursor=page['next_cursor'],**args)


@pytest.mark.anyio
async def test_existing_migraine_cursor_without_new_calendar_fields_still_works(conn):
    import base64, json
    from services.migraine.history import read_history
    user = str(uuid4())
    _, onset = await episode(conn,user,age=1)
    await episode(conn,user,age=1)
    args = dict(start=onset-timedelta(hours=1),end=onset+timedelta(days=1),limit=1)
    page = await read_history(conn,user,**args)
    value = json.loads(base64.urlsafe_b64decode(page['next_cursor']+'==='))
    value.pop('calendar'); value.pop('last_kind')
    legacy = base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
    last = await read_history(conn,user,cursor=legacy,**args)
    assert last['complete'] and len(last['items']) == 1


@pytest.mark.anyio
async def test_legacy_unknown_is_read_only_separate_from_new_confirmed_and_point_logs(conn):
    user = str(uuid4())
    legacy = []
    for state in ('new', 'ongoing', 'improving', 'worse'):
        identifier, onset = await episode(conn, user)
        await conn.execute("update raw.user_symptom_episode_updates set metadata=metadata-'activity_contract' where episode_id=%s", (identifier,))
        await conn.execute('update raw.user_symptom_episodes set current_state=%s where id=%s', (state, identifier))
        legacy.append(identifier)
    headache, _ = await episode(conn, user, 'headache')
    await conn.execute("update raw.user_symptom_episode_updates set metadata=metadata-'activity_contract' where episode_id=%s", (headache,))
    fresh, _ = await episode(conn, user)
    before = await (await conn.execute('select id,current_state,resolution_ts,updated_at from raw.user_symptom_episodes where user_id=%s order by id', (user,))).fetchall()
    current = await db.fetch_current_symptom_items(conn, user, window_hours=12)
    assert {r['id'] for r in current if r['activity_status']=='needs_review'} == set(legacy)
    assert {r['id'] for r in current if r['activity_status']=='active'} == {fresh}
    now = datetime.now(UTC)
    page = await db.fetch_symptom_episode_range(conn,user,start=now-timedelta(days=1),end=now+timedelta(days=1),as_of=now,limit=100)
    assert {r['id'] for r in page['items']} == {fresh}
    history = await db.fetch_symptom_episode_range(conn,user,start=onset-timedelta(days=1),end=onset+timedelta(days=1),as_of=now,limit=100)
    rows = {r['id']:r for r in history['items']}
    assert all(rows[i]['activity_status']=='needs_review' and rows[i]['end_status']=='unknown' for i in legacy)
    assert rows[headache]['end_status']=='instant' and rows[headache]['activity_status']=='recorded'
    after = await (await conn.execute('select id,current_state,resolution_ts,updated_at from raw.user_symptom_episodes where user_id=%s order by id', (user,))).fetchall()
    assert before == after


@pytest.mark.anyio
async def test_retry_old_log_and_note_or_severity_never_confirm_activity(conn):
    user=str(uuid4()); identifier,onset=await episode(conn,user)
    await conn.execute("update raw.user_symptom_episode_updates set metadata=metadata-'activity_contract' where episode_id=%s", (identifier,))
    event_id = (await (await conn.execute('select symptom_event_id from raw.user_symptom_episodes where id=%s',(identifier,))).fetchone())[0]
    await db.ensure_symptom_episode_for_event(conn,user,symptom_event_id=str(event_id),symptom_code='migraine',ts_utc=onset)
    for values in ({'note_text':'Synthetic edit'}, {'severity':0}):
        saved=await db.record_symptom_episode_update(conn,user,identifier,**values)
        assert saved['activity_status']=='needs_review'
    assert (await (await conn.execute("select count(*) from raw.user_symptom_episode_updates where episode_id=%s and metadata->>'activity_contract'='persistent_v1'",(identifier,))).fetchone())[0]==0


@pytest.mark.anyio
async def test_explicit_review_preserves_unknown_end_and_is_replay_safe(conn):
    user=str(uuid4()); identifier,onset=await episode(conn,user)
    await conn.execute("update raw.user_symptom_episode_updates set metadata=metadata-'activity_contract' where episode_id=%s", (identifier,))
    initial=await db.fetch_symptom_episode(conn,user,identifier)
    review_at=datetime.now(UTC); request_id=str(uuid4())
    args=dict(state='resolved',occurred_at=review_at,resolution_time_unknown=True,
              expected_updated_at=datetime.fromisoformat(initial['updated_at']),metadata={'status_review_request_id':request_id})
    saved=await db.record_symptom_episode_update(conn,user,identifier,**args)
    replay=await db.record_symptom_episode_update(conn,user,identifier,**args)
    assert saved['activity_status']==replay['activity_status']=='resolved'
    row=await (await conn.execute('select resolution_ts,improvement_ts from raw.user_symptom_episodes where id=%s',(identifier,))).fetchone()
    assert row == (None, None)
    assert (await (await conn.execute("select count(*) from raw.user_symptom_episode_updates where episode_id=%s and metadata->>'status_review_request_id'=%s",(identifier,request_id))).fetchone())[0]==1
    page=await db.fetch_symptom_episode_range(conn,user,start=onset-timedelta(hours=1),end=onset+timedelta(hours=1),as_of=review_at,limit=100)
    assert page['items'][0]['end_status']=='unknown' and page['items'][0]['state']=='resolved'
    with pytest.raises(db.StaleSymptomUpdate):
        await db.record_symptom_episode_update(conn,user,identifier,state='ongoing',expected_updated_at=datetime.fromisoformat(initial['updated_at']))
    with pytest.raises(RuntimeError):
        await db.record_symptom_episode_update(conn,str(uuid4()),identifier,**args)


@pytest.mark.anyio
async def test_confirmed_legacy_ongoing_survives_age_and_multiple_records_stay_independent(conn):
    user=str(uuid4()); first,onset=await episode(conn,user,age=90); second,_=await episode(conn,user,age=91)
    for identifier in (first,second):
        await conn.execute("update raw.user_symptom_episode_updates set metadata=metadata-'activity_contract' where episode_id=%s",(identifier,))
    confirmed=await db.record_symptom_episode_update(conn,user,first,state='ongoing')
    assert confirmed['activity_status']=='active'
    await conn.execute("update raw.user_symptom_episodes set last_interaction_at=started_at where id=%s",(first,))
    rows=await db.fetch_current_symptom_items(conn,user,window_hours=1,limit=1)
    assert {r['id']:r['activity_status'] for r in rows}=={first:'active',second:'needs_review'}
    end=datetime.now(UTC)-timedelta(days=1)
    await db.record_symptom_episode_update(conn,user,first,state='resolved',occurred_at=end)
    page=await db.fetch_symptom_episode_range(conn,user,start=end-timedelta(hours=1),end=end+timedelta(hours=1),as_of=datetime.now(UTC),limit=100)
    assert page['items'][0]['ended_at']==end.isoformat()
    assert (await db.fetch_symptom_episode(conn,user,second))['activity_status']=='needs_review'


@pytest.mark.anyio
async def test_reconciliation_cannot_erase_or_change_an_already_recorded_end(conn):
    user=str(uuid4()); identifier,start=await episode(conn,user)
    end=start+timedelta(hours=3)
    async with conn.transaction():
        await db.record_symptom_episode_update(conn,user,identifier,state='resolved',occurred_at=end)
    current=await db.fetch_symptom_episode(conn,user,identifier)
    for unknown in (True,False):
        with pytest.raises(ValueError,match='already resolved'):
            async with conn.transaction():
                await db.record_symptom_episode_update(conn,user,identifier,state='resolved',occurred_at=datetime.now(UTC),
                    expected_updated_at=datetime.fromisoformat(current['updated_at']), resolution_time_unknown=unknown,
                    metadata={'status_review_request_id':str(uuid4())})
    row=await (await conn.execute('select resolution_ts from raw.user_symptom_episodes where id=%s',(identifier,))).fetchone()
    assert row[0]==end


@pytest.mark.anyio
async def test_gauge_uses_report_time_deduplicates_and_preserves_historical_latest(conn,monkeypatch):
    from bots.gauges import gauge_scorer as scorer
    from zoneinfo import ZoneInfo
    user=str(uuid4()); identifier,start=await episode(conn,user,age=2,severity=5)
    # sync reader shares only the disposable local socket, never a network DSN.
    with psycopg.connect(os.environ['GAIA_MIGRAINE_ACTIVE_TEST_DATABASE_URL'],autocommit=True,row_factory=psycopg.rows.dict_row) as reader:
        monkeypatch.setattr(scorer.pg,'fetch',lambda sql,*params:list(reader.execute(sql,params).fetchall()))
        monkeypatch.setattr(scorer.pg,'fetchrow',lambda sql,*params:reader.execute(sql,params).fetchone())
        monkeypatch.setattr(scorer,'table_columns',lambda *a:{'id'})
        monkeypatch.setattr(scorer,'LOCAL_TZ',ZoneInfo('UTC'))
        async with conn.transaction():
            await db.record_symptom_episode_update(conn,user,identifier,severity=2,occurred_at=datetime.now(UTC)-timedelta(minutes=5))
        historical=scorer.fetch_symptom_summary(user,start.date())
        assert historical['total_24h']==1 and historical['max_severity']==5
        current=scorer.fetch_symptom_summary(user,datetime.now(UTC).date())
        assert current['total_24h']==1 and current['max_severity']==2
        async with conn.transaction():
            await db.record_symptom_episode_update(conn,user,identifier,note_text='Synthetic note',occurred_at=datetime.now(UTC))
        assert scorer.fetch_symptom_summary(user,datetime.now(UTC).date())['last_symptom_update_at']==current['last_symptom_update_at']
        async with conn.transaction():
            await db.record_symptom_episode_update(conn,user,identifier,severity=0,occurred_at=datetime.now(UTC))
        assert scorer.fetch_symptom_summary(user,datetime.now(UTC).date())['gauge_boosts']=={}

        async with conn.transaction():
            await db.record_symptom_episode_update(conn,user,identifier,state='resolved',occurred_at=datetime.now(UTC))
        assert scorer.fetch_symptom_summary(user,datetime.now(UTC).date())['total_24h']==0
        assert scorer.fetch_symptom_summary(user,start.date())['max_severity']==5
