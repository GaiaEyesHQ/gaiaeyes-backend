"""Synthetic owned PostgreSQL durability/latency regression tests."""
import asyncio
from datetime import date,datetime,UTC,timedelta
from uuid import uuid4
import pytest,psycopg
from fastapi import HTTPException
from services.migraine import refresh_queue as queue
from services.db import pg
from test_migraine_postgres_integration import _database_url,_connect,_request,USER_A
from test_migraine_time_postgres import seed,request_for,stamp,save,snapshot
from app.routers import symptoms as router

@pytest.fixture
def anyio_backend():return 'asyncio'
@pytest.fixture(autouse=True)
def clean_queue():
    with psycopg.connect(_database_url(),autocommit=True) as c:
        c.execute('truncate raw.migraine_time_refresh_jobs,raw.migraine_time_refresh_users cascade')
    yield

def query(sql,*args):
    with psycopg.connect(_database_url(),autocommit=True,row_factory=psycopg.rows.dict_row) as c:
        cur=c.execute(sql,args)
        return cur.fetchall() if cur.description else []
async def create_correction(conn):
    eid,_=await seed(conn)
    req=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
    await save(conn,eid,req)
    return eid,req

def job_status():return query('select status,attempts from raw.migraine_time_refresh_jobs')[0]

@pytest.mark.anyio
async def test_atomic_enqueue_failure_rolls_back_canonical_and_audit(monkeypatch):
    async with await _connect() as conn:
        eid,_=await seed(conn);before=await snapshot(conn,eid)
        request=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
        real=queue.enqueue
        async def fail(*args):await real(*args);raise RuntimeError('synthetic enqueue failure')
        monkeypatch.setattr(queue,'enqueue',fail)
        with pytest.raises(RuntimeError):await save(conn,eid,request)
        assert await snapshot(conn,eid)==before
        assert query('select * from raw.migraine_time_refresh_jobs')==[]
        assert query('select * from raw.migraine_time_refresh_users')==[]

@pytest.mark.anyio
async def test_prompt_receipt_replay_and_background_never_awaited(monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    async def forbidden(*a):pytest.fail('HTTP path must not wait for refresh')
    monkeypatch.setattr(router,'_refresh_migraine_time_correction',forbidden)
    async with await _connect(autocommit=False) as conn:
        eid,_=await seed(conn);await conn.commit()
        req=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
        response=await asyncio.wait_for(router.correct_migraine_episode_times(eid,req,_request(USER_A),conn),2)
        assert response['data']['refresh']['status']=='pending'
        before=await snapshot(conn,eid);await conn.commit()
        retry=await router.correct_migraine_episode_times(eid,req,_request(USER_A),conn)
        assert retry['data']['replayed'] and retry['data']['refresh']['status']=='pending'
        assert await snapshot(conn,eid)==before
        assert len(query('select * from raw.migraine_time_refresh_jobs'))==1
        assert query('select generation from raw.migraine_time_refresh_users')[0]['generation']==1

@pytest.mark.anyio
async def test_new_correction_retains_both_work_targets_and_supersedes_completion():
    async with await _connect() as conn:
        eid,_=await create_correction(conn);old=queue.claim()
        second=await request_for(conn,eid,start=stamp('2026-08-29T23:30:00'))
        await save(conn,eid,second)
        with pytest.raises(queue.RefreshLeaseLost):queue.complete(old)
        assert queue.retry(old,queue.RefreshLeaseLost())
        latest=queue.claim();assert latest['generation']==2 and len(latest['request_ids'])==2
        assert set(latest['refresh_days'])>={date(2026,8,29),date(2026,8,30),date(2026,8,31)}
        assert len(query('select * from raw.migraine_time_refresh_jobs'))==2

@pytest.mark.anyio
async def test_expired_worker_cannot_finish_or_release_successor():
    async with await _connect() as conn:await create_correction(conn)
    first=queue.claim();assert queue.claim() is None
    query("update raw.migraine_time_refresh_users set lease_until=clock_timestamp()-interval '1 second'")
    second=queue.claim();assert first['lease_token']!=second['lease_token']
    with pytest.raises(queue.RefreshLeaseLost):queue.complete(first)
    assert queue.retry(first,RuntimeError()) is False
    assert query('select lease_token::text as token from raw.migraine_time_refresh_users')[0]['token']==second['lease_token']

@pytest.mark.anyio
async def test_claim_concurrency_serializes_user():
    async with await _connect() as conn:await create_correction(conn)
    claims=await asyncio.gather(asyncio.to_thread(queue.claim),asyncio.to_thread(queue.claim))
    assert sum(c is not None for c in claims)==1

@pytest.mark.anyio
async def test_independent_worker_drain_completion_and_exact_retry_status(monkeypatch):
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    calls=[]
    monkeypatch.setattr(gauge_scorer,'score_user_day',lambda user,day,**kw:calls.append((user,day,kw)))
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',lambda **kw:calls.append(kw))
    async with await _connect() as conn:
        eid,req=await create_correction(conn)
        before=await snapshot(conn,eid)
        batch=queue.claim();assert queue.process(batch)
        assert job_status()['status']=='complete'
        response=await queue.receipt_refresh(conn,USER_A,req.request_id);assert response=={'status':'complete','pending_components':[]}
        retry=await save(conn,eid,req);assert retry['replayed']
        assert await snapshot(conn,eid)==before
        assert queue.claim() is None and len(calls)==len(batch['refresh_days'])+1

@pytest.mark.anyio
async def test_partial_progress_resumes_across_budget_limited_drains(monkeypatch):
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    elapsed=[0.0];days=[];patterns=[]
    monkeypatch.setattr(queue,'monotonic',lambda:elapsed[0])
    def score(user,day,**kw):days.append(day);elapsed[0]+=2.0
    monkeypatch.setattr(gauge_scorer,'score_user_day',score)
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',lambda **kw:patterns.append(kw))
    async with await _connect() as conn:await create_correction(conn)
    first=queue.claim();assert len(first['refresh_days'])>=2
    assert queue.process(first,max_seconds=1) is False
    assert len(days)==1 and patterns==[]
    query('update raw.migraine_time_refresh_jobs set available_at=clock_timestamp()')
    second=queue.claim();assert second['completed_days']==days
    assert queue.process(second,max_seconds=10)
    assert days==first['refresh_days'] and len(patterns)==1 and job_status()['status']=='complete'

@pytest.mark.anyio
async def test_new_generation_resets_partial_progress():
    async with await _connect() as conn:
        eid,_=await create_correction(conn);first=queue.claim();queue.mark_day(first,first['refresh_days'][0])
        req=await request_for(conn,eid,start=stamp('2026-08-29T23:30:00'));await save(conn,eid,req)
        queue.retry(first,queue.RefreshLeaseLost())
        next_batch=queue.claim();assert next_batch['completed_days']==[]

@pytest.mark.anyio
async def test_failure_backoff_retains_jobs_and_does_not_touch_canonical(monkeypatch):
    from bots.gauges import gauge_scorer
    def fail(*a,**k):raise RuntimeError('secret should never be stored')
    monkeypatch.setattr(gauge_scorer,'score_user_day',fail)
    async with await _connect() as conn:
        eid,_=await create_correction(conn);before=await snapshot(conn,eid)
        assert queue.process(queue.claim()) is False
        row=query('select status,last_error_class,available_at>clock_timestamp() as future from raw.migraine_time_refresh_jobs')[0]
        assert row=={'status':'pending','last_error_class':'RuntimeError','future':True}
        assert await snapshot(conn,eid)==before and queue.claim() is None

@pytest.mark.anyio
async def test_publication_lock_returns_retryable_error_without_partial_save(monkeypatch):
    import time
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    async with await _connect() as conn:
        eid,_=await create_correction(conn);before=await snapshot(conn,eid)
        req=await request_for(conn,eid,start=stamp('2026-08-29T23:30:00'))
        with psycopg.connect(_database_url()) as blocker:
            blocker.execute('select * from raw.migraine_time_refresh_users where user_id=%s for update',(USER_A,))
            start=time.perf_counter()
            with pytest.raises(HTTPException) as caught:await router.correct_migraine_episode_times(eid,req,_request(USER_A),conn)
            elapsed=time.perf_counter()-start
            assert caught.value.status_code==503 and 1.5<elapsed<4
            blocker.rollback()
        assert await snapshot(conn,eid)==before
        assert len(query('select * from raw.migraine_time_refresh_jobs'))==1

def test_real_loopback_response_precedes_blocked_worker(monkeypatch):
    import json,socket,threading,time,uvicorn,httpx
    from fastapi import FastAPI,Depends
    from app.security.auth import require_write_auth,settings
    from app.db import get_db
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    monkeypatch.setattr(settings,'DEV_BEARER','synthetic-only-test-token')
    async def setup():
        async with await _connect() as conn:
            eid,_=await seed(conn)
            req=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
            return eid,req.canonical_request()
    eid,body=asyncio.run(setup())
    async def dependency():
        async with await _connect(autocommit=False) as conn:yield conn
    app=FastAPI();app.include_router(router.router,prefix='/v1',dependencies=[Depends(require_write_auth)])
    app.dependency_overrides[get_db]=dependency
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',lifespan='off',access_log=False))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    waiting=threading.Event();release=threading.Event();worker_errors=[]
    def worker():
        try:
            limit=time.monotonic()+5
            while time.monotonic()<limit:
                batch=queue.claim()
                if batch:
                    waiting.set();release.wait(timeout=10)
                    queue.retry(batch,RuntimeError('synthetic worker deliberately paused'))
                    return
                time.sleep(.005)
            raise AssertionError('job was not committed')
        except BaseException as exc:worker_errors.append(type(exc).__name__)
    worker_thread=threading.Thread(target=worker,daemon=True)
    thread.start()
    try:
        limit=time.monotonic()+5
        while not server.started and time.monotonic()<limit:time.sleep(.005)
        assert server.started
        worker_thread.start()
        url=f'http://127.0.0.1:{sock.getsockname()[1]}/v1/symptoms/current/{eid}/migraine-times'
        headers={'Authorization':'Bearer synthetic-only-test-token','X-Dev-UserId':USER_A}
        with httpx.Client(timeout=2,trust_env=False) as client:
            start=time.perf_counter();first=client.post(url,headers=headers,json=body);first_elapsed=time.perf_counter()-start
            assert first.status_code==200 and first.json()['data']['refresh']['status']=='pending'
            assert waiting.wait(2) and not release.is_set()
            assert query('select count(*) as n from raw.migraine_time_refresh_jobs')[0]['n']==1
            audits=query('select count(*) as n from raw.user_migraine_episode_detail_revisions where user_id=%s',USER_A)[0]['n']
            start=time.perf_counter();second=client.post(url,headers=headers,json=body);retry_elapsed=time.perf_counter()-start
            assert second.status_code==200 and second.json()['data']['replayed']
            assert second.json()['data']['refresh']['status']=='pending' and not release.is_set()
            assert query('select count(*) as n from raw.user_migraine_episode_detail_revisions where user_id=%s',USER_A)[0]['n']==audits
            assert first_elapsed<1 and retry_elapsed<1
            print('REAL_HTTP_TIMING '+json.dumps({'save_seconds':first_elapsed,'retry_seconds':retry_elapsed,'worker_blocked_at_receipt':True,'audit_unchanged_on_retry':True}))
    finally:
        release.set();worker_thread.join(timeout=5);server.should_exit=True;thread.join(timeout=5);sock.close()
    assert not worker_errors and not thread.is_alive() and not worker_thread.is_alive()

@pytest.mark.anyio
async def test_additive_migration_repeat_preserves_receipts_and_queue():
    from pathlib import Path
    async with await _connect() as conn:
        eid,_=await create_correction(conn);before=await snapshot(conn,eid)
        state=query('select generation,writer_epoch from raw.migraine_time_refresh_users')
        jobs=query('select * from raw.migraine_time_refresh_jobs')
        sql=Path('supabase/migrations/20261110032646_add_migraine_time_refresh_queue.sql').read_text()
        await conn.execute(sql,prepare=False);await conn.execute(sql,prepare=False)
        assert await snapshot(conn,eid)==before
        assert query('select generation,writer_epoch from raw.migraine_time_refresh_users')==state
        assert query('select * from raw.migraine_time_refresh_jobs')==jobs
        for role in ('anon','authenticated'):
            assert query("select has_table_privilege(%s,'raw.migraine_time_refresh_jobs','SELECT') as allowed",role)==[{'allowed':False}]

@pytest.mark.anyio
async def test_missing_queue_capability_rejects_save_without_changes(monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    async with await _connect() as conn:
        eid,_=await seed(conn);before=await snapshot(conn,eid)
        request=await request_for(conn,eid,start=stamp('2026-08-30T23:30:00'))
        await conn.execute('alter table raw.migraine_time_refresh_jobs rename to synthetic_hidden_refresh_jobs')
        try:
            with pytest.raises(HTTPException) as caught:await router.correct_migraine_episode_times(eid,request,_request(USER_A),conn)
            assert caught.value.status_code==503 and await snapshot(conn,eid)==before
        finally:await conn.execute('alter table raw.synthetic_hidden_refresh_jobs rename to migraine_time_refresh_jobs')

@pytest.mark.anyio
async def test_pattern_longer_than_initial_lease_completes_with_renewal(monkeypatch):
    import time
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    from services.migraine.refresh_publication import capture_user_generation,publication_guard
    monkeypatch.setattr(gauge_scorer,'score_user_day',lambda *a,**kw:None)
    def pattern(**kw):
        captured=capture_user_generation(kw['user_id'])
        time.sleep(6)  # Initial lease5 seconds; at least3 renewal opportunities.
        with queue.connection() as c:
            with publication_guard(c,kw['user_id'],captured):pass
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',pattern)
    async with await _connect() as conn:await create_correction(conn)
    batch=queue.claim(lease_seconds=5)
    assert queue.process(batch,lease_seconds=5,hard_seconds=20,max_seconds=15)
    assert job_status()['status']=='complete'

@pytest.mark.anyio
async def test_heartbeat_supersession_prevents_pattern_publication_and_completion(monkeypatch):
    import time
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    from services.migraine.refresh_publication import capture_user_generation,publication_guard
    monkeypatch.setattr(gauge_scorer,'score_user_day',lambda *a,**kw:None)
    def pattern(**kw):
        captured=capture_user_generation(kw['user_id'])
        query('update raw.migraine_time_refresh_users set generation=generation+1 where user_id=%s',USER_A)
        time.sleep(2)  # Lease5 -> heartbeat1.67s notices supersession.
        with queue.connection() as c:
            with publication_guard(c,kw['user_id'],captured):pytest.fail('superseded worker published')
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',pattern)
    async with await _connect() as conn:await create_correction(conn)
    assert queue.process(queue.claim(lease_seconds=5),lease_seconds=5,hard_seconds=15) is False
    assert job_status()['status']=='pending' and queue.claim() is not None

@pytest.mark.anyio
async def test_hard_deadline_revokes_running_worker_before_compute_returns(monkeypatch):
    import time
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    monkeypatch.setattr(gauge_scorer,'score_user_day',lambda *a,**kw:None)
    observed=[]
    def pattern(**kw):
        time.sleep(1.3)
        observed.append(query('select lease_token from raw.migraine_time_refresh_users')[0]['lease_token'])
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',pattern)
    async with await _connect() as conn:await create_correction(conn)
    assert queue.process(queue.claim(lease_seconds=5),lease_seconds=5,hard_seconds=1) is False
    assert observed==[None] and job_status()['status']=='pending'

@pytest.mark.anyio
async def test_repeated_no_progress_failure_becomes_visible_blocked_and_new_correction_recovers(monkeypatch):
    from bots.gauges import gauge_scorer
    def fail(*a,**kw):raise RuntimeError('synthetic repeat failure')
    monkeypatch.setattr(gauge_scorer,'score_user_day',fail)
    async with await _connect() as conn:
        eid,req=await create_correction(conn)
        for _ in range(5):
            query('update raw.migraine_time_refresh_jobs set available_at=clock_timestamp()')
            assert queue.process(queue.claim()) is False
        assert job_status()['status']=='blocked' and queue.claim() is None
        assert queue.health()['blocked_jobs']==1
        assert (await queue.receipt_refresh(conn,USER_A,req.request_id))['status']=='blocked'
        next_req=await request_for(conn,eid,start=stamp('2026-08-29T23:30:00'));await save(conn,eid,next_req)
        assert queue.health()['blocked_jobs']==0 and len(queue.claim()['request_ids'])==2

@pytest.mark.anyio
async def test_more_than_five_productive_budget_drains_do_not_block(monkeypatch):
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    elapsed=[0.0];seen=[]
    monkeypatch.setattr(queue,'monotonic',lambda:elapsed[0])
    def score(user,day,**kw):seen.append(day);elapsed[0]+=2
    monkeypatch.setattr(gauge_scorer,'score_user_day',score)
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',lambda **kw:None)
    async with await _connect() as conn:await create_correction(conn)
    targets=[date(2026,8,20)+timedelta(days=i) for i in range(7)]
    query('update raw.migraine_time_refresh_jobs set refresh_days=%s::date[]',targets)
    for _ in targets:
        batch=queue.claim();assert batch is not None
        assert queue.process(batch,max_seconds=1) is False
        assert job_status()['status']=='pending'
    assert queue.process(queue.claim(),max_seconds=1)
    assert seen==targets and job_status()['status']=='complete' and queue.health()['blocked_jobs']==0

@pytest.mark.anyio
async def test_heartbeat_database_failure_revokes_and_retains_work(monkeypatch):
    import time,threading
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    real=queue.renew
    def renew(*a,**kw):
        if threading.current_thread().name=='migraine-refresh-lease':raise psycopg.OperationalError('synthetic unavailable heartbeat')
        return real(*a,**kw)
    monkeypatch.setattr(queue,'renew',renew)
    monkeypatch.setattr(gauge_scorer,'score_user_day',lambda *a,**kw:None)
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',lambda **kw:time.sleep(2))
    async with await _connect() as conn:await create_correction(conn)
    assert queue.process(queue.claim(lease_seconds=5),lease_seconds=5,hard_seconds=15) is False
    assert job_status()['status']=='pending'
    assert query('select lease_token from raw.migraine_time_refresh_users')[0]['lease_token'] is None

def test_cli_passes_only_remaining_absolute_budget(monkeypatch):
    from scripts import run_migraine_time_refresh as cli
    import sys
    ticks=iter([0,200,210,220]);calls=[]
    monkeypatch.setattr(cli.time,'monotonic',lambda:next(ticks))
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED','1')
    monkeypatch.setattr(sys,'argv',['worker','--max-users','1','--max-seconds','240'])
    monkeypatch.setattr(cli,'claim',lambda:{'synthetic':True})
    monkeypatch.setattr(cli,'process',lambda batch,**kwargs:calls.append(kwargs) or True)
    monkeypatch.setattr(cli,'health',lambda:{'blocked_jobs':0,'pending_jobs':0})
    cli.main();assert calls==[{'max_seconds':20,'hard_seconds':20}]

@pytest.mark.anyio
async def test_repeated_process_loss_without_retry_becomes_blocked():
    async with await _connect() as conn:await create_correction(conn)
    for expected in range(1,6):
        batch=queue.claim();assert batch is not None and job_status()['attempts']==expected
        query("update raw.migraine_time_refresh_users set lease_until=clock_timestamp()-interval '1 second'")
    assert queue.claim() is None
    assert job_status()['status']=='blocked'
    assert queue.health()['blocked_jobs']==1
    assert query('select last_error_class from raw.migraine_time_refresh_jobs')[0]['last_error_class']=='WorkerProcessLost'

@pytest.mark.anyio
async def test_new_generation_recovers_fifth_crashed_attempt_targets():
    async with await _connect() as conn:
        eid,first=await create_correction(conn)
        for _ in range(5):
            batch=queue.claim();assert batch is not None
            query("update raw.migraine_time_refresh_users set lease_until=clock_timestamp()-interval '1 second'")
        second=await request_for(conn,eid,start=stamp('2026-08-29T23:30:00'))
        await save(conn,eid,second)
    batch=queue.claim()
    assert set(batch['request_ids'])=={str(first.request_id),str(second.request_id)}
    assert queue.health()['blocked_jobs']==0
    assert all(r['attempts']==1 for r in query('select attempts from raw.migraine_time_refresh_jobs'))

@pytest.mark.anyio
async def test_heartbeat_tolerates_own_publication_row_lock(monkeypatch):
    import time
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    from services.migraine.refresh_publication import capture_user_generation,publication_guard
    monkeypatch.setattr(gauge_scorer,'score_user_day',lambda *a,**kw:None)
    def pattern(**kw):
        with psycopg.connect(_database_url()) as c:
            captured=capture_user_generation(kw['user_id'],c)
            with publication_guard(c,kw['user_id'],captured):time.sleep(4)
        time.sleep(.3)
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',pattern)
    async with await _connect() as conn:await create_correction(conn)
    assert queue.process(queue.claim(lease_seconds=5),lease_seconds=5,hard_seconds=15)
    assert job_status()['status']=='complete'
