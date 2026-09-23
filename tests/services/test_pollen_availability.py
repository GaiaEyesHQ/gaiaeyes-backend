"""G048 pollen coverage/provenance checks. No external service or database calls."""
from datetime import UTC,date,datetime,timedelta
import pytest
import os
os.environ.setdefault("DATABASE_URL", "postgresql://127.0.0.1:1/g048_unused")
from services.external import pollen
from services.forecast_outlook import summarize_local_forecast_days
from services.local_signals import aggregator

DAY=date(2026,9,22)
def payload(index=None,category=None,day=DAY,empty=False):
    item={'code':'GRASS','inSeason':False}
    if not empty:item['indexInfo']={k:v for k,v in {'value':index,'category':category}.items() if v is not None}
    return {'dailyInfo':[{'date':day.isoformat(),'pollenTypeInfo':[item]}]}

@pytest.mark.parametrize('value',[None,-1,6,float('nan'),float('inf'),True])
def test_invalid_missing_indices_never_become_low_or_numeric_rank(value):
    rows=pollen.normalize_daily_forecast(payload(value))
    assert rows[0]['pollen_overall_index'] is None
    assert rows[0]['pollen_overall_level'] is None
    assert rows[0]['pollen_updated_at'] is None
    assert pollen.current_snapshot(payload(value),target_day=DAY)=={}

def test_explicit_zero_is_present_but_missing_or_out_of_season_alone_is_not():
    current=pollen.current_snapshot(payload(0,'NONE'),target_day=DAY)
    assert current['overall_index']==0 and current['grass_index']==0
    assert current['source']=='google-pollen:forecast' and current['forecast_day']==DAY.isoformat()
    assert pollen.current_snapshot(payload(empty=True),target_day=DAY)=={}

def test_category_only_remains_category_not_substituted_upi():
    current=pollen.current_snapshot(payload(category='HIGH'),target_day=DAY)
    assert current['overall_level']=='high' and current['grass_level']=='high'
    assert current['overall_index'] is None and current['grass_index'] is None
    # Relevance is explicitly a separate derived score, never a measurement.
    assert current['relevance_score'] is not None

@pytest.mark.parametrize('offset',[-1,1])
def test_stale_and_future_forecast_days_are_not_current(offset):
    source=payload(4,'HIGH',DAY+timedelta(days=offset))
    assert pollen.current_snapshot(source,target_day=DAY)=={}
    assert pollen.normalize_daily_forecast(source)[0]['day']==DAY+timedelta(days=offset)

def test_current_selects_utc_day_instead_of_first_returned_forecast():
    source={'dailyInfo':payload(5,'VERY_HIGH',DAY-timedelta(days=1))['dailyInfo']+payload(0,'NONE')['dailyInfo']}
    assert pollen.current_snapshot(source,target_day=DAY)['overall_index']==0

@pytest.mark.parametrize('source',[{}, {'dailyInfo':[{'date':DAY.isoformat()}]},payload(empty=True)])
def test_weather_issue_time_cannot_become_pollen_update_time(source):
    weather={'properties':{'generatedAt':'2026-09-22T01:00:00Z','periods':[{'startTime':'2026-09-22T02:00:00Z','temperature':70,'temperatureUnit':'F'}]}}
    rows=summarize_local_forecast_days(weather,{},allergen_payload=source,location_key='zip:78754',zip_code='78754',lat=30.35,lon=-97.65,now=datetime(2026,9,22,1,tzinfo=UTC))
    assert rows and rows[0]['issued_at'] is not None
    assert rows[0]['pollen_source'] is None and rows[0]['pollen_updated_at'] is None
    assert rows[0]['pollen_overall_index'] is None

@pytest.mark.anyio
async def test_metadata_only_response_does_not_stop_existing_coverage_search(monkeypatch):
    day=datetime.now(UTC).date();calls=[]
    async def fetch(lat,lon,**kwargs):
        calls.append((lat,lon))
        return {'dailyInfo':[{'date':day.isoformat()}]} if len(calls)==1 else payload(3,'MODERATE',day)
    monkeypatch.setattr(pollen,'forecast_by_latlon',fetch)
    actual=await aggregator._fetch_pollen_forecast('78754',30.35,-97.65)
    assert len(calls)==2 and pollen.current_snapshot(actual)['overall_index']==3

@pytest.mark.anyio
async def test_provider_failure_logging_does_not_copy_key_bearing_url(monkeypatch,capsys):
    async def fail(*args,**kwargs):raise RuntimeError('https://example.invalid/?key=SYNTHETIC-SECRET')
    monkeypatch.setattr(pollen,'forecast_by_latlon',fail)
    assert await aggregator._fetch_pollen_forecast('78754',30.35,-97.65)=={}
    log=capsys.readouterr().out
    assert 'RuntimeError' in log and 'SYNTHETIC-SECRET' not in log

@pytest.fixture
def anyio_backend():return 'asyncio'

@pytest.mark.anyio
async def test_missing_configuration_returns_no_data_without_provider_call(monkeypatch):
    monkeypatch.setattr(pollen,'API_KEY','')
    class NoHttp:
        def AsyncClient(self,*args,**kwargs):raise AssertionError('must not call provider')
    monkeypatch.setattr(pollen,'httpx',NoHttp())
    assert await pollen.forecast_by_latlon(30.35,-97.65)=={}
