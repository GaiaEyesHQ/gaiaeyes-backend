"""Synthetic-only publication fencing checks in the owned disposable database."""
from contextlib import contextmanager
from datetime import date
from uuid import uuid4
import psycopg
import pytest
from psycopg.rows import dict_row
from services.db import pg
from services.migraine import refresh_publication as fencing
from test_migraine_postgres_integration import _database_url

@pytest.fixture
def db(monkeypatch):
    dsn=_database_url()
    monkeypatch.setattr(pg,'_dsn',dsn)
    with psycopg.connect(dsn,autocommit=True,row_factory=dict_row) as conn:
        assert conn.execute("select current_setting('gaia.migraine_disposable',true) as value").fetchone()['value']=='true'
        conn.execute('create table if not exists public.synthetic_refresh_publications (user_id uuid primary key, value int not null)')
        yield conn


def new_user(conn, *, generation=1, lease=False):
    user=str(uuid4());token=str(uuid4())
    conn.execute('insert into raw.migraine_time_refresh_users(user_id,generation,writer_epoch,lease_token,lease_until) values(%s,%s,0,%s,case when %s then clock_timestamp()+interval \'5 minutes\' else null end)',(user,generation,token if lease else None,lease))
    return user,token

def publish(conn,user,snapshot,value):
    with fencing.publication_guard(conn,user,snapshot):
        conn.execute('insert into public.synthetic_refresh_publications values(%s,%s) on conflict(user_id) do update set value=excluded.value',(user,value))

def value(conn,user):
    row=conn.execute('select value from public.synthetic_refresh_publications where user_id=%s',(user,)).fetchone()
    return row['value'] if row else None

def test_new_correction_does_not_wait_for_compute_and_rejects_stale_publication(db):
    user,_=new_user(db)
    snapshot=fencing.capture_user_generation(user,db)
    # Capturing does not lock the row across computation. Another connection
    # can commit a new canonical generation while this calculation is paused.
    with psycopg.connect(_database_url(),autocommit=True) as other:
        other.execute("set lock_timeout='200ms'")
        other.execute('update raw.migraine_time_refresh_users set generation=generation+1 where user_id=%s',(user,))
    with pytest.raises(fencing.StaleRefreshPublication):publish(db,user,snapshot,1)
    assert value(db,user) is None

def test_first_correction_after_absent_row_capture_is_fenced(db):
    user=str(uuid4());snapshot=fencing.capture_user_generation(user,db)
    assert snapshot.generation==0
    db.execute('insert into raw.migraine_time_refresh_users(user_id,generation) values(%s,1)',(user,))
    with pytest.raises(fencing.StaleRefreshPublication):publish(db,user,snapshot,1)
    assert value(db,user) is None

def test_publication_epoch_prevents_same_generation_late_overwrite(db):
    user,_=new_user(db)
    older=fencing.capture_user_generation(user,db);newer=fencing.capture_user_generation(user,db)
    publish(db,user,newer,2)
    with pytest.raises(fencing.StaleRefreshPublication):publish(db,user,older,1)
    assert value(db,user)==2

def test_claim_then_completion_invalidates_preclaim_cron_snapshot(db):
    user,token=new_user(db);old=fencing.capture_user_generation(user,db)
    db.execute('update raw.migraine_time_refresh_users set writer_epoch=writer_epoch+1,lease_token=%s,lease_until=clock_timestamp()+interval \'1 minute\' where user_id=%s',(token,user))
    with pytest.raises(fencing.StaleRefreshPublication):fencing.capture_user_generation(user,db)
    db.execute('update raw.migraine_time_refresh_users set lease_token=null,lease_until=null where user_id=%s',(user,))
    with pytest.raises(fencing.StaleRefreshPublication):publish(db,user,old,1)

def test_expired_worker_cannot_publish_after_recovery_same_generation(db):
    user,token=new_user(db,lease=True)
    with fencing.worker_publication(user,1,token):snapshot=fencing.capture_user_generation(user,db)
    db.execute('update raw.migraine_time_refresh_users set lease_token=%s,writer_epoch=writer_epoch+1 where user_id=%s',(str(uuid4()),user))
    with fencing.worker_publication(user,1,token),pytest.raises(fencing.StaleRefreshPublication):publish(db,user,snapshot,1)
    assert value(db,user) is None

def test_worker_rejects_expiry_even_without_replacement(db):
    user,token=new_user(db,lease=True)
    with fencing.worker_publication(user,1,token):snapshot=fencing.capture_user_generation(user,db)
    db.execute('update raw.migraine_time_refresh_users set lease_until=clock_timestamp()-interval \'1 second\' where user_id=%s',(user,))
    with fencing.worker_publication(user,1,token),pytest.raises(fencing.StaleRefreshPublication):publish(db,user,snapshot,1)

def test_worker_may_publish_sequential_components_and_scope_cannot_escape(db):
    user,token=new_user(db,lease=True)
    with fencing.worker_publication(user,1,token):
        for expected in (1,2):
            snapshot=fencing.capture_user_generation(user,db);publish(db,user,snapshot,expected)
        with pytest.raises(fencing.StaleRefreshPublication):fencing.capture_user_generation(str(uuid4()),db)
        with pytest.raises(fencing.StaleRefreshPublication):fencing.capture_all_generations(db)
    assert value(db,user)==2
    assert db.execute('select writer_epoch from raw.migraine_time_refresh_users where user_id=%s',(user,)).fetchone()['writer_epoch']==2

def test_failed_publication_rolls_back_output_and_epoch(db):
    user,_=new_user(db);snapshot=fencing.capture_user_generation(user,db)
    with pytest.raises(RuntimeError):
        with fencing.publication_guard(db,user,snapshot):
            db.execute('insert into public.synthetic_refresh_publications values(%s,1)',(user,))
            raise RuntimeError('synthetic failure')
    assert value(db,user) is None
    assert fencing.capture_user_generation(user,db)==snapshot

def test_global_snapshot_fences_newly_corrected_user(db):
    snapshots=fencing.capture_all_generations(db);user,_=new_user(db)
    with pytest.raises(fencing.StaleRefreshPublication):publish(db,user,snapshots.get(user,fencing.PublicationSnapshot()),1)

def test_missing_storage_worker_fails_closed_ordinary_path_legacy(monkeypatch,db):
    monkeypatch.setattr(fencing,'_available',lambda conn:False)
    user=str(uuid4());snapshot=fencing.capture_user_generation(user,db)
    publish(db,user,snapshot,1);assert value(db,user)==1
    with fencing.worker_publication(user,1,str(uuid4())),pytest.raises(fencing.RefreshPublicationUnavailable):fencing.capture_user_generation(user,db)
    with pytest.raises(fencing.RefreshPublicationUnavailable):publish(db,user,fencing.PublicationSnapshot(1,0,True),2)


def test_actual_gauge_and_delta_publication_roll_back_together(db,monkeypatch):
    from bots.gauges import gauge_scorer as gauges
    from unittest.mock import Mock
    user,token=new_user(db,lease=True)
    for name,result in {
        'load_definition_base':({},'synthetic'),'fetch_local_payload':{'synthetic':True},'resolve_signals':[],
        'fetch_user_tags':[],'fetch_symptom_summary':{},'fetch_exposure_summary':{},'fetch_recent_daily_checkins':{},
        'fetch_local_health_summary':{},'fetch_daily_features':{},'fetch_daily_features_baseline':[],
        'fetch_hrv_fallback':(None,None,None),'compute_health_status':(None,{}),'_score_gauges':{},
        'apply_symptom_gauge_adjustments':({},{}),'apply_exposure_gauge_adjustments':({},{}),
        'apply_daily_check_in_energy_adjustment':({},{}),'_build_alerts':[],'_compute_trend':{},
    }.items():monkeypatch.setattr(gauges,name,Mock(return_value=result))
    monkeypatch.setattr(pg,'fetchrow',lambda *args:None)
    def upsert(*args,**kwargs):pg.execute('insert into public.synthetic_refresh_publications values(%s,7)',user)
    def delta(*args):raise RuntimeError('synthetic delta failure')
    monkeypatch.setattr(gauges,'upsert_row',upsert);monkeypatch.setattr(gauges,'_upsert_gauge_delta',delta)
    with fencing.worker_publication(user,1,token),pytest.raises(RuntimeError,match='delta failure'):
        gauges.score_user_day(user,date(2026,9,1),force=True,require_corrected_symptoms=True)
    assert value(db,user) is None
    assert db.execute('select writer_epoch from raw.migraine_time_refresh_users where user_id=%s',(user,)).fetchone()['writer_epoch']==0


def test_actual_global_pattern_prefetch_cannot_replace_later_generation(db,monkeypatch):
    from bots.patterns import pattern_engine_job as patterns
    from unittest.mock import Mock
    user,_=new_user(db);created=[]
    for table in ('marts.user_pattern_associations','marts.user_daily_outcomes','marts.user_daily_features'):
        if db.execute('select to_regclass(%s) as relation',(table,)).fetchone()['relation'] is None:
            db.execute('create table '+table+' (user_id uuid primary key)');created.append(table)
    def base(*args,**kwargs):
        # Generation changes after global fence snapshot but before prefetch.
        db.execute('update raw.migraine_time_refresh_users set generation=generation+1 where user_id=%s',(user,))
        return [{'user_id':user}]
    monkeypatch.setattr(patterns,'_fetch_base_daily_features',base)
    for name in ('_fetch_gauges','_fetch_gauge_deltas','_fetch_symptom_rows','_fetch_camera_rows','_fetch_daily_exposure_context','_fetch_tag_flags','_fetch_day_zip_map','_fetch_current_zip_map','_fetch_local_signals_daily','_fetch_schumann_variability_daily'):
        monkeypatch.setattr(patterns,name,Mock(return_value={}))
    monkeypatch.setattr(patterns,'_collect_relevant_zip_codes',Mock(return_value=set()))
    for name in ('build_user_daily_features','build_user_daily_outcomes','build_associations'):
        monkeypatch.setattr(patterns,name,Mock(return_value=[{'user_id':user}]))
    writes=[]
    monkeypatch.setattr(patterns,'_delete_scope',lambda *args,**kwargs:writes.append(('delete',kwargs)))
    monkeypatch.setattr(patterns,'_insert_rows',lambda *args,**kwargs:writes.append(('insert',args)))
    try:
        result=patterns._run_pattern_engine_once(as_of_day=date(2026,9,1),days_back=90,user_id=None,dsn=_database_url(),require_corrected_symptoms=True)
        assert result['stale_users']==1 and result['features']==0 and not writes
    finally:
        for table in created:db.execute('drop table '+table)


def test_actual_delta_job_captures_before_prefetch_and_skips_stale_user(db,monkeypatch):
    from bots.gauges import gauge_delta_job as delta
    user,_=new_user(db)
    monkeypatch.setattr('sys.argv',['gauge_delta_job','--day','2026-09-01'])
    def rows(*args):
        db.execute('update raw.migraine_time_refresh_users set generation=generation+1 where user_id=%s',(user,))
        return [{'user_id':user,'day':date(2026,9,1),'pain':10}]
    monkeypatch.setattr(delta,'_fetch_rows_for_day',rows)
    monkeypatch.setattr(delta,'_fetch_yesterday_row',lambda *args:{'pain':3})
    monkeypatch.setattr(delta,'upsert_row',lambda *args,**kwargs:pytest.fail('stale delta published'))
    delta.main()


def test_gauge_batch_marks_stale_as_expected_skip(db,monkeypatch):
    from bots.gauges import gauge_scoring_job as batch
    user,_=new_user(db)
    def stale(*args,**kwargs):raise fencing.StaleRefreshPublication('synthetic stale input')
    monkeypatch.setattr(batch,'score_user_day',stale)
    result=batch._score_chunk([(user,date(2026,9,1))],force=True)
    assert result==[((user,date(2026,9,1)),{'ok':True,'skipped':True,'skip_reason':'superseded_publication'},None,{})]


def test_worker_expiring_during_publication_rolls_back_output(db):
    user,token=new_user(db,lease=True)
    db.execute("update raw.migraine_time_refresh_users set lease_until=clock_timestamp()+interval '100 milliseconds' where user_id=%s",(user,))
    with fencing.worker_publication(user,1,token):
        snapshot=fencing.capture_user_generation(user,db)
        with pytest.raises(fencing.StaleRefreshPublication):
            with fencing.publication_guard(db,user,snapshot):
                db.execute('insert into public.synthetic_refresh_publications values(%s,1)',(user,))
                db.execute('select pg_sleep(0.15)')
    assert value(db,user) is None


def test_publication_cannot_relax_timeout_and_restores_context(db):
    user,_=new_user(db);snapshot=fencing.capture_user_generation(user,db)
    with pg.operation_timeouts(connect_timeout=20,statement_timeout_ms=30000):
        with fencing.publication_guard(db,user,snapshot):
            assert pg._operation_timeout_settings.get()==(5,5000)
        assert pg._operation_timeout_settings.get()==(20,30000)
    assert pg._operation_timeout_settings.get() is None
