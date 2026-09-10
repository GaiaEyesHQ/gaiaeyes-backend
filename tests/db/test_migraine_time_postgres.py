"""G-013 verification against the private disposable PostgreSQL runtime."""
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from psycopg.rows import dict_row
from pydantic import ValidationError
from app.db import migraine as db, symptoms, feedback
from app.routers import symptoms as router
from services.migraine.time_correction import TimeCorrectionIn
from services.migraine.episode_contract import MigraineEpisode
from test_migraine_postgres_integration import (_connect, _reset, _insert_parent, _insert_prompt, _episode, _request, USER_A, USER_B)

pytestmark = pytest.mark.anyio

def anyio_backend(): return 'asyncio'

def stamp(local, zone='America/Chicago', fold=0):
    value = datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(zone), fold=fold)
    return {'utc': value.astimezone(UTC).isoformat(), 'original_time': local,
            'timezone_name': zone, 'utc_offset_minutes': int(value.utcoffset().total_seconds()/60), 'timezone_source': 'user'}

async def seed(conn, *, episode_id=None, start='2026-09-01T04:30:00+00:00', detail=True):
    await _reset(conn)
    eid, event = episode_id or uuid4(), uuid4()
    start = datetime.fromisoformat(start)
    await _insert_parent(conn, user_id=USER_A, episode_id=eid, event_id=event, start=start, source='manual')
    await conn.execute("update raw.user_symptom_episodes set current_state='ongoing', last_interaction_at=%s, state_updated_at=%s, latest_note_text='Keep notes' where id=%s", (start,start,eid))
    if detail:
        payload=_episode(episode_id=eid,event_id=event,start=start,notes='Keep notes').model_dump(mode='json')
        payload['medicines']=[{'name':'Synthetic medicine','taken_at':stamp('2026-09-01T00:30:00'),'dose_amount':'2.5','dose_unit':'mg'}]
        await db.persist_migraine_episode_detail(conn,USER_A,MigraineEpisode.model_validate(payload),expected_revision=0,change_kind='created',source='synthetic')
    return str(eid), str(event)

async def request_for(conn,eid,**changes):
    context=await db.load_migraine_time_context(conn,USER_A,eid)
    return TimeCorrectionIn.model_validate({'request_id':str(uuid4()),'expected_revision':context['revision'],
        'expected_canonical_updated_at':context['canonical_updated_at'], **changes})

async def snapshot(conn,eid):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("""select row_to_json(ep) as canonical,
          (select payload from raw.user_migraine_episode_details where episode_id=ep.id) as detail,
          (select count(*) from raw.user_migraine_episode_detail_revisions where episode_id=ep.id) as revisions,
          (select jsonb_agg(row_to_json(p) order by p.id) from raw.user_feedback_prompts p where episode_id=ep.id) as prompts
          from raw.user_symptom_episodes ep where id=%s""",(eid,))
        return dict(await cur.fetchone())

async def save(conn,eid,request):
    async with conn.transaction(): return await db.save_migraine_time_correction(conn,USER_A,eid,request)

async def test_canonical_start_moves_daily_and_calendar_without_rewriting_events():
    async with await _connect() as conn:
        eid,event=await seed(conn)
        before=await snapshot(conn,eid)
        request=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
        result=await save(conn,eid,request)
        after=await snapshot(conn,eid)
        assert result['revision']==2 and result['episode'].start.utc==datetime(2026,8,31,4,30,tzinfo=UTC)
        assert after['detail']['medicines']==before['detail']['medicines'] and after['detail']['notes']=='Keep notes'
        assert after['revisions']==2
        async with conn.cursor() as cur:
            await cur.execute('select ts_utc from raw.user_symptom_events where id=%s',(event,));assert (await cur.fetchone())[0]==datetime(2026,9,1,4,30,tzinfo=UTC)
            await cur.execute('select day,events from marts.symptom_daily_effective where user_id=%s',(USER_A,));assert await cur.fetchall()==[(datetime(2026,8,31).date(),1)]
            await cur.execute('select time_correction from raw.user_migraine_episode_detail_revisions where correction_request_id=%s',(request.request_id,));audit=(await cur.fetchone())[0]
            assert audit['before']['started_at'].startswith('2026-09-01') and audit['before']['stored_start_provenance']
            await cur.execute('select count(*) from raw.user_symptom_episode_updates');assert (await cur.fetchone())[0]==0
        history=await symptoms.fetch_migraine_episode_range(conn,USER_A,start=datetime(2026,8,1,tzinfo=UTC),end=datetime(2026,9,1,tzinfo=UTC),as_of=datetime.now(UTC),limit=10)
        assert [x['id'] for x in history['items']]==[eid]

async def test_exact_retry_changed_retry_stale_tokens_and_owner_isolation():
    async with await _connect() as conn:
        eid,event=await seed(conn)
        request=await request_for(conn,eid,end=stamp('2026-09-01T02:00:00'),state='resolved')
        first=await save(conn,eid,request);before=await snapshot(conn,eid)
        retry=await save(conn,eid,request)
        assert retry['replayed'] and retry['request_id']==str(request.request_id) and retry['applied_revision']==first['revision']
        assert await snapshot(conn,eid)==before
        changed=request.model_copy(update={'state':'ongoing'})
        with pytest.raises(db.StaleMigraineRevision): await save(conn,eid,changed)
        other=request.model_copy(update={'request_id':uuid4()})
        with pytest.raises(db.StaleMigraineRevision): await save(conn,eid,other)
        with pytest.raises(db.MigraineEpisodeNotFound):
            async with conn.transaction(): await db.save_migraine_time_correction(conn,USER_B,eid,request)
        current=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
        await conn.execute("update raw.user_symptom_episodes set latest_note_text='Legacy edit',updated_at=clock_timestamp() where id=%s",(eid,))
        with pytest.raises(db.StaleMigraineRevision): await save(conn,eid,current)
        assert (await snapshot(conn,eid))['detail']==before['detail']

async def test_unknown_end_clear_and_explicit_reopen():
    async with await _connect() as conn:
        eid,_=await seed(conn,detail=False)
        await conn.execute("update raw.user_symptom_episodes set current_state='resolved',resolution_ts=null where id=%s",(eid,))
        context=await db.load_migraine_time_context(conn,USER_A,eid)
        assert context['revision']==0 and context['episode'].end is None
        request=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
        result=await save(conn,eid,request);assert result['episode'].state=='resolved' and result['episode'].end is None
        ended=await request_for(conn,eid,end=stamp('2026-09-01T02:00:00'));await save(conn,eid,ended)
        reopen=await request_for(conn,eid,state='ongoing')
        with pytest.raises(ValidationError): await save(conn,eid,reopen)
        clear=await request_for(conn,eid,end=None);cleared=await save(conn,eid,clear)
        assert cleared['episode'].state=='resolved' and cleared['episode'].end is None
        reopen=await request_for(conn,eid,state='ongoing',end=None);opened=await save(conn,eid,reopen)
        assert opened['episode'].state=='ongoing' and opened['episode'].end is None

async def test_invalid_legacy_end_can_be_repaired_without_inventing_before_value():
    async with await _connect() as conn:
        eid,_=await seed(conn)
        await conn.execute("update raw.user_symptom_episodes set current_state='resolved',resolution_ts=started_at-interval '1 hour' where id=%s",(eid,))
        context=await db.load_migraine_time_context(conn,USER_A,eid)
        assert context['inconsistent_end'] and context['episode'].end is None
        request=await request_for(conn,eid,start=stamp('2026-08-31T21:30:00'))
        result=await save(conn,eid,request)
        assert result['episode'].end.utc==datetime(2026,9,1,3,30,tzinfo=UTC)
        assert result['raw_end_utc']==context['raw_end_utc']

async def test_rollback_includes_canonical_revision_and_prompt(monkeypatch):
    async with await _connect() as conn:
        eid,_=await seed(conn)
        await _insert_prompt(conn,prompt_id=uuid4(),user_id=USER_A,episode_id=UUID(eid),scheduled_for=datetime.now(UTC)+timedelta(hours=1))
        request=await request_for(conn,eid,state='resolved',end=stamp('2026-09-01T02:00:00'))
        before=await snapshot(conn,eid)
        real=feedback.reconcile_migraine_time_correction
        async def fail(*args,**kwargs): await real(*args,**kwargs);raise RuntimeError('synthetic rollback')
        monkeypatch.setattr(feedback,'reconcile_migraine_time_correction',fail)
        with pytest.raises(RuntimeError): await save(conn,eid,request)
        assert await snapshot(conn,eid)==before

async def test_reminders_shift_once_preserve_snooze_and_expire_on_resolve():
    async with await _connect() as conn:
        eid,_=await seed(conn)
        pending,snoozed=uuid4(),uuid4();scheduled=datetime.now(UTC)+timedelta(days=2)
        for pid in [pending,snoozed]:
            await _insert_prompt(conn,prompt_id=pid,user_id=USER_A,episode_id=UUID(eid),scheduled_for=scheduled)
            await conn.execute('update raw.user_feedback_prompts set question_key=%s where id=%s',(str(pid),pid))
        await conn.execute("update raw.user_feedback_prompts set status='snoozed' where id=%s",(snoozed,))
        request=await request_for(conn,eid,start=stamp('2026-09-01T23:30:00'))
        await save(conn,eid,request);await save(conn,eid,request)
        async with conn.cursor() as cur:
            await cur.execute('select id,scheduled_for from raw.user_feedback_prompts');rows=dict(await cur.fetchall())
            assert rows[pending]==scheduled+timedelta(days=1) and rows[snoozed]==scheduled
        end=await request_for(conn,eid,state='resolved',end=stamp('2026-09-02T01:00:00'));await save(conn,eid,end)
        async with conn.cursor() as cur:
            await cur.execute('select status from raw.user_feedback_prompts');assert set(x[0] for x in await cur.fetchall())=={'expired'}

async def test_real_route_commit_then_refresh_receipt_survives_refresh_failure(monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    async with await _connect(autocommit=False) as conn:
        eid,_=await seed(conn,episode_id=UUID('33333333-3333-4333-8333-333333333333'),start='2026-09-09T04:30:00+00:00')
        await conn.execute("update raw.user_symptom_episodes set current_state='resolved',resolution_ts='2026-09-09T07:30:00Z' where id=%s",(eid,))
        await conn.commit()
        context=await router.get_migraine_time_context(eid,_request(USER_A),conn)
        request=await request_for(conn,eid,start=stamp('2026-08-31T23:30:00'),end=stamp('2026-09-01T02:30:00'))
        calls=[]
        async def refresh(uid,result):
            async with await _connect() as observer:
                observed=await snapshot(observer,eid)
                assert observed['detail']['lifecycle']['revision']==result['revision']
            calls.append((uid,result['refresh_days']))
            raise RuntimeError('synthetic downstream failure')
        monkeypatch.setattr(router,'_refresh_migraine_time_correction',refresh)
        response=await router.correct_migraine_episode_times(eid,request,_request(USER_A),conn)
        assert response['data']['refresh']['status']=='pending' and calls
        assert {'2026-09-08','2026-09-09','2026-08-31','2026-09-01'} <= set(calls[0][1])
        again=await router.correct_migraine_episode_times(eid,request,_request(USER_A),conn)
        assert again['data']['replayed'] and len(calls)==2
        path=os.getenv('GAIA_TIME_EVIDENCE_DIR')
        if path:
            out=Path(path);out.mkdir(parents=True,exist_ok=True)
            for name,value in [('backend-time-context.json',context),('backend-time-ack.json',response)]:
                (out/name).write_text(router.MigraineTimeResponse.model_validate(value).model_dump_json(indent=2)+'\n')
            (out/'backend-time-request.json').write_text(json.dumps(request.canonical_request(),indent=2)+'\n')

async def test_concurrent_exact_retry_creates_one_correction():
    import asyncio
    async with await _connect() as setup:
        eid,_=await seed(setup)
        request=await request_for(setup,eid,start=stamp('2026-08-30T23:30:00'))
    async def writer():
        async with await _connect() as conn: return await save(conn,eid,request)
    results=await asyncio.gather(writer(),writer())
    assert sorted(row['replayed'] for row in results)==[False,True]
    async with await _connect() as check: assert (await snapshot(check,eid))['revisions']==2

async def test_projection_owner_policies_and_actual_daily_pattern_readers():
    import psycopg
    from test_migraine_postgres_integration import _database_url
    from bots.patterns import pattern_engine_job
    async with await _connect() as conn:
        eid,_=await seed(conn)
        await _insert_parent(conn,user_id=USER_B,episode_id=uuid4(),event_id=uuid4(),start=datetime(2026,9,2,tzinfo=UTC),source='manual')
        request=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'));await save(conn,eid,request)
        daily=await symptoms.fetch_daily_summary(conn,USER_A,60)
        assert [row['day'] for row in daily]==['2026-08-31'] and daily[0]['events']==1
        with psycopg.connect(_database_url()) as sync:
            stats=pattern_engine_job._fetch_symptom_rows(sync,since_day=datetime(2026,8,1).date(),as_of_day=datetime(2026,9,30).date(),user_id=USER_A)
            assert list(stats)==[(USER_A,datetime(2026,8,31).date())]
        async with conn.transaction():
            await conn.execute("set local role authenticated")
            await conn.execute("select set_config('request.jwt.claim.sub',%s,true)",(USER_A,))
            async with conn.cursor() as cur:
                await cur.execute('select user_id from raw.user_symptom_events_effective');assert await cur.fetchall()==[(UUID(USER_A),)]
                await cur.execute('select user_id from marts.symptom_daily_effective');assert await cur.fetchall()==[(UUID(USER_A),)]
        async with conn.cursor() as cur:
            await cur.execute("select has_table_privilege('anon','raw.user_symptom_events_effective','SELECT'), has_table_privilege('authenticated','raw.user_symptom_events_effective','INSERT')")
            assert await cur.fetchone()==(False,False)

async def test_invalid_order_and_future_leave_all_storage_unchanged():
    async with await _connect() as conn:
        eid,_=await seed(conn);before=await snapshot(conn,eid)
        for fields in [{'state':'resolved','end':stamp('2026-08-30T01:00:00')}, {'start':stamp('2099-01-01T00:00:00')}]:
            request=await request_for(conn,eid,**fields)
            with pytest.raises(ValueError): await save(conn,eid,request)
            assert await snapshot(conn,eid)==before

async def test_midnight_end_and_explicit_dst_fold_reach_canonical_calendar():
    async with await _connect() as conn:
        eid,_=await seed(conn)
        await save(conn,eid,await request_for(conn,eid,start=stamp('2026-08-31T23:30:00'),end=stamp('2026-09-01T00:00:00'),state='resolved'))
        day=await symptoms.fetch_migraine_episode_range(conn,USER_A,start=datetime(2026,9,1,5,tzinfo=UTC),end=datetime(2026,9,2,5,tzinfo=UTC),as_of=datetime.now(UTC),limit=10)
        assert day['items']==[] # A midnight ending belongs only to the preceding local day.
        first=stamp('2025-11-02T01:30:00',fold=0);second=stamp('2025-11-02T01:30:00',fold=1)
        result=await save(conn,eid,await request_for(conn,eid,start=first,end=second))
        assert (result['episode'].end.utc-result['episode'].start.utc).total_seconds()==3600
        assert result['episode'].start.utc_offset_minutes==-300 and result['episode'].end.utc_offset_minutes==-360
        assert result['episode'].start.original_time==result['episode'].end.original_time

async def test_commit_failure_never_runs_refresh(monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    async with await _connect() as conn:
        eid,_=await seed(conn);before=await snapshot(conn,eid)
        request=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
        # A deferred constraint trigger fails after the function returns, at COMMIT.
        await conn.execute("""create function raw.synthetic_commit_rejection() returns trigger language plpgsql as $$
            begin raise exception 'synthetic commit rejected'; return new; end $$""")
        await conn.execute("""create constraint trigger synthetic_commit_rejection after update on raw.user_symptom_episodes
            deferrable initially deferred for each row execute function raw.synthetic_commit_rejection()""")
        async def no_refresh(*args): pytest.fail('refresh ran before successful commit')
        monkeypatch.setattr(router,'_refresh_migraine_time_correction',no_refresh)
        try:
            with pytest.raises(Exception,match='synthetic commit rejected'):
                await router.correct_migraine_episode_times(eid,request,_request(USER_A),conn)
            assert await snapshot(conn,eid)==before
        finally:
            await conn.execute('drop trigger synthetic_commit_rejection on raw.user_symptom_episodes')
            await conn.execute('drop function raw.synthetic_commit_rejection()')

async def test_actual_gauge_input_reader_moves_onset_without_duplicates(monkeypatch):
    import psycopg
    from test_migraine_postgres_integration import _database_url
    from bots.gauges import gauge_scorer
    async with await _connect() as conn:
        eid,_=await seed(conn)
        await save(conn,eid,await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'),state='resolved',end=None))
        with psycopg.connect(_database_url(),row_factory=dict_row) as sync:
            def fetch(query,*params): return sync.execute(query,params).fetchall()
            def columns(schema,table):
                return {r['column_name'] for r in sync.execute('select column_name from information_schema.columns where table_schema=%s and table_name=%s',(schema,table)).fetchall()}
            monkeypatch.setattr(gauge_scorer.pg,'fetch',fetch)
            monkeypatch.setattr(gauge_scorer.pg,'fetchrow',lambda query,*params:sync.execute(query,params).fetchone())
            monkeypatch.setattr(gauge_scorer,'table_columns',columns)
            # Observe actual selected inputs; full gauge scoring needs other synthetic datasets.
            monkeypatch.setattr(gauge_scorer,'_build_symptom_signal_summary',lambda rows:rows)
            assert gauge_scorer.fetch_symptom_summary(USER_A,datetime(2026,8,31).date())==[]
            rows=gauge_scorer.fetch_symptom_summary(USER_A,datetime(2026,8,30).date())
            assert len(rows)==1 and rows[0]['ts_utc']==datetime(2026,8,31,4,30,tzinfo=UTC)

async def test_additive_migration_switches_existing_lunar_input_and_is_repeatable():
    async with await _connect() as conn:
        eid,_=await seed(conn)
        # Small stand-in for the existing lunar view's unchanged calculation;
        # exercise pg_get_viewdef replacement, grants and invoker behavior itself.
        await conn.execute("""create view marts.symptom_daily as select (ts_utc at time zone 'UTC')::date as day,
            user_id,symptom_code,count(*) as events,avg(severity::float) as mean_severity,max(ts_utc) as last_ts
            from raw.user_symptom_events group by 1,2,3""")
        await conn.execute('create view marts.user_lunar_patterns as select user_id,day,events from marts.symptom_daily')
        migration=Path('supabase/migrations/20260910033343_add_migraine_time_corrections.sql').read_text()
        try:
            await conn.execute(migration,prepare=False);await conn.execute(migration,prepare=False)
            await save(conn,eid,await request_for(conn,eid,start=stamp('2026-08-30T23:30:00')))
            async with conn.cursor() as cur:
                await cur.execute('select day,events from marts.user_lunar_patterns where user_id=%s',(USER_A,))
                assert await cur.fetchall()==[(datetime(2026,8,31).date(),1)]
                await cur.execute("select reloptions from pg_class where oid='marts.user_lunar_patterns'::regclass")
                assert 'security_invoker=true' in (await cur.fetchone())[0]
        finally:
            await conn.execute('drop view marts.user_lunar_patterns')
            await conn.execute('drop view marts.symptom_daily')
