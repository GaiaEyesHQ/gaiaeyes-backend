import pytest
from app.routers import symptoms as router
from test_symptoms import client, override_db_dependency, override_dev_bearer

HEADERS={'Authorization':'Bearer test-token','X-Dev-UserId':'90000000-0000-4000-8000-000000000001'}
PATH='/v1/symptoms/current/33333333-3333-4333-8333-333333333333/migraine-times'
BODY={'request_id':'55555555-5555-4555-8555-555555555555','expected_revision':1,'expected_canonical_updated_at':'2026-01-01T00:00:00Z','end':None}

def anyio_backend(): return 'asyncio'

@pytest.mark.anyio
async def test_default_off_auth_and_explicit_shape(client,monkeypatch):
    monkeypatch.delenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED',raising=False)
    assert (await client.get(PATH,headers=HEADERS)).status_code==503
    assert (await client.post(PATH,headers=HEADERS,json=BODY)).status_code==503
    assert (await client.get(PATH)).status_code in (401,403)
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    for body in [{**BODY,'start':None},{**BODY,'state':None},{**BODY,'expected_revision':-1},{**BODY,'expected_canonical_updated_at':'2026-01-01'},{**BODY,'other':1}]:
        assert (await client.post(PATH,headers=HEADERS,json=body)).status_code==422

@pytest.mark.anyio
@pytest.mark.parametrize('error,status',[(router.migraine_db.MigraineDetailUnavailable('missing'),503),(router.migraine_db.MigraineEpisodeNotFound('missing'),404),(router.migraine_db.StaleMigraineRevision('stale'),409),(ValueError('invalid order'),422)])
async def test_errors_do_not_refresh_or_claim_a_save(client,monkeypatch,error,status):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    async def fail(conn,user_id,episode_id,payload):
        assert user_id==HEADERS['X-Dev-UserId'];raise error
    async def no_refresh(*args): pytest.fail('No refresh after failed transaction')
    monkeypatch.setattr(router.migraine_db,'save_migraine_time_correction',fail)
    monkeypatch.setattr(router,'_refresh_migraine_time_correction',no_refresh)
    response=await client.post(PATH,headers=HEADERS,json=BODY)
    assert response.status_code==status and 'data' not in response.json()

@pytest.mark.anyio
async def test_invalid_path_id_is_validation_failure(client,monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED','1')
    path='/v1/symptoms/current/not-a-uuid/migraine-times'
    assert (await client.get(path,headers=HEADERS)).status_code==422
    assert (await client.post(path,headers=HEADERS,json=BODY)).status_code==422

@pytest.mark.anyio
async def test_refresh_orchestration_is_user_scoped_and_covers_every_affected_day(monkeypatch):
    from datetime import date,datetime,timezone
    from bots.gauges import gauge_scorer
    from bots.patterns import pattern_engine_job
    gauges=[];patterns=[]
    def score(uid,day,force,require_corrected_symptoms):
        assert require_corrected_symptoms
        gauges.append((uid,day,force))
        if day==date(2026,8,31): raise RuntimeError('synthetic gauge failure')
    def pattern(**kwargs): patterns.append(kwargs)
    monkeypatch.setattr(gauge_scorer,'score_user_day',score)
    monkeypatch.setattr(pattern_engine_job,'run_pattern_engine',pattern)
    result=await router._refresh_migraine_time_correction(HEADERS['X-Dev-UserId'],{
        'refresh_days':['2026-08-31','2026-09-01','2026-09-08','2026-09-09'],'pattern_since_day':'2026-06-13'})
    assert gauges==[(HEADERS['X-Dev-UserId'],date.fromisoformat(d),True) for d in ['2026-08-31','2026-09-01','2026-09-08','2026-09-09']]
    today=datetime.now(timezone.utc).date()
    assert patterns==[{'as_of_day':today,'days_back':(today-date(2026,6,13)).days+1,'user_id':HEADERS['X-Dev-UserId'],'require_corrected_symptoms':True}]
    assert result=={'status':'pending','pending_components':['daily_gauges']}
