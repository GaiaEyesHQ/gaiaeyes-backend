"""G044 changed-behavior checks: synthetic projections and an owned local DB."""
import copy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import ast

import psycopg
import pytest
from psycopg.types.json import Jsonb

from services.earthscope_public_facts import (
    prepare_public_packet, collect_public_inputs, PUBLIC_SOURCES, utc,
)
from services.earthscope_writer_contract import DraftError, sha256, validate_facts, job_envelope
from scripts import earthscope_draft_shadow as shadow
# Reuse the owned local fixture setup, not any accepted G043 test cases.
from test_earthscope_writer import postgres, anyio_backend

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests/fixtures/earthscope_public_facts.json'


def inputs():
    f = json.loads(FIXTURE.read_text())
    return date.fromisoformat(f['day']), utc(f['now']), f['inputs']


def packet(values=None, *, synthetic=True):
    day, now, data = inputs()
    return prepare_public_packet(day, now=now, synthetic=synthetic, **(values if values is not None else data))


def test_current_context_provenance_and_aggregate_meaning():
    p, q = packet()
    assert p['facts']['kp_now'] == 4 and p['facts']['solar_wind_kms'] == 520
    assert p['facts']['schumann_value_hz'] == 7.9
    assert p['facts']['aurora_headline'] == 'G1 aurora possible'
    assert 'not a forecast' in p['facts']['aurora_window']
    assert p['facts']['quakes_count'] is None and p['facts']['severe_summary'] is None
    assert p['facts_as_of'] == '2026-09-21T21:50:00+00:00'
    assert q['aggregate_time_is_observation_time'] is False
    assert q['facts_sha256'] == sha256(p)
    for entry in p['source_manifest']:
        item = next(v for v in q['sources'].values() if v['source_id'] == entry['source_id'])
        assert sha256(item['projection']) == entry['source_sha256']


@pytest.mark.parametrize('key,value', [
    ('day', '2026-09-20'), ('day', '2026-09-22'),
    ('updated_at', '2026-09-20T23:59:00Z'), ('updated_at', '2026-09-21T22:01:00Z'),
    ('updated_at', '2026-09-21T21:50:00'), ('now_ts', '2026-09-20T23:59:00Z'),
    ('now_ts', '2026-09-21T22:01:00Z'),
])
def test_conflicting_core_day_or_time_rejects(key, value):
    _, _, data = inputs(); data['space'][key] = value
    with pytest.raises(DraftError) as exc:
        packet(data)
    assert exc.value.code in {'facts_stale', 'public_source_conflict'}


def test_missing_aggregate_cannot_be_dated_from_request_clock():
    _, _, data = inputs(); data['space'] = None
    with pytest.raises(DraftError, match='public_facts_unavailable'):
        packet(data)


def test_unknown_counts_are_not_zero_and_zero_bz_is_retained():
    _, _, data = inputs(); data['space'].update(flares_count=None, cmes_count=0, bz_min=0)
    p, _ = packet(data)
    assert p['facts']['flares_24h'] is None and p['facts']['cmes_24h'] == 0 and p['facts']['bz_min'] == 0


@pytest.mark.parametrize('value', ['2026-09-20T23:00:00Z', '2026-09-21T01:00:00Z',
                                  '2026-09-21T22:01:00Z', None])
def test_kp_rejects_stale_future_undated_without_latest_overall_fallback(value):
    _, _, data = inputs()
    data['kp']['kp_time'] = value
    data['space']['kp_now'] = None; data['kp_fallback'] = data['pulse'] = None
    p, q = packet(data)
    assert p['facts']['kp_now'] is None
    assert q['sources']['kp']['status'] != 'current'


@pytest.mark.parametrize('remove,expected,origin', [
    (['kp'], 3, 'space.kp_now'),
    (['kp', 'daily_kp'], 3, 'kp_fallback.kp_index'),
    (['kp', 'daily_kp', 'kp_fallback'], 2, 'pulse.kp_latest'),
])
def test_active_outlook_kp_fallbacks_without_calling_side_effectful_route(remove, expected, origin):
    _, _, data = inputs()
    for k in remove:
        if k == 'daily_kp': data['space']['kp_now'] = None
        else: data[k] = None
    p, q = packet(data)
    assert p['facts']['kp_now'] == expected and q['fields']['kp_now']['source'] == origin


def test_schumann_does_not_average_prior_day_into_today():
    _, _, data = inputs()
    data['schumann'][0]['day'] = '2026-09-20'
    p, q = packet(data)
    assert p['facts']['schumann_value_hz'] == 8
    assert q['sources']['schumann']['rejected'][0]['status'] == 'different_aggregate_day'
    data['schumann'][1]['last_fundamental_ts'] = None
    assert packet(data)[0]['facts']['schumann_value_hz'] is None


@pytest.mark.parametrize('now_value,old_value,time_value,expected', [
    (None, None, None, 410), (3000, 0, '2026-09-21T21:45:00Z', 410),
    (500, None, None, 410), (None, 480, '2026-09-21T21:45:00Z', 480),
])
def test_wind_range_and_observation_provenance(now_value, old_value, time_value, expected):
    _, _, data = inputs()
    data['space'].update(sw_speed_now_kms=now_value, sw_speed_now=old_value, now_ts=time_value)
    assert packet(data)[0]['facts']['solar_wind_kms'] == expected


def test_missing_core_is_not_quiet_and_invalid_numbers_are_unknown():
    _, _, data = inputs(); data['space'].update(kp_max=float('nan'), bz_min=True)
    data['kp'] = None; data['space']['kp_now'] = None; data['kp_fallback'] = data['pulse'] = None
    p, q = packet(data)
    assert p['sample_kind'] == 'missing_data'
    assert p['facts']['kp_max_24h'] is None and p['facts']['bz_min'] is None
    assert q['missing_core_fields'] == ['kp_max_24h', 'bz_min']


def test_historical_copy_is_separate_from_recent_signal_evidence():
    p, _ = packet()
    assert len(p['recent_public_copy']) == 6
    assert [x['day'] for x in p['facts']['recent_signal_history']] == ['2026-09-20']
    _, _, data = inputs()
    data['public_copy'][0]['day'] = '2026-09-21'
    data['public_copy'][1]['updated_at'] = '2026-09-21T23:00:00Z'
    p, q = packet(data)
    assert p['recent_public_copy'] == [] and p['facts']['recent_signal_history'] == []
    assert len(q['omissions']) == 2


def test_title_memory_extends_beyond_five_caption_sets():
    day, _, data = inputs()
    row = data['public_copy'][0]
    data['public_copy'] = [dict(row, day=(day-timedelta(days=i)).isoformat(), title=f'Fixture Title {i}') for i in range(1,22)]
    p, _ = packet(data)
    assert len(p['recent_public_copy']) == 5*3+21
    assert len(p['facts']['recent_signal_history']) == 3
    assert len(json.dumps(p).encode()) < 65536


def test_public_projections_drop_unselected_keys_and_bound_text():
    _, _, data = inputs()
    for key in ('space', 'kp', 'kp_fallback', 'pulse'):
        data[key]['private'] = 'PRIVATE-CANARY'
    data['public_copy'][0]['caption'] = 'x' * 5000
    p, q = packet(data)
    assert 'PRIVATE-CANARY' not in json.dumps([p, q])
    assert max(len(i['text']) for i in p['recent_public_copy']) <= 2048


def test_timezone_normalization_is_stable():
    _, _, data = inputs(); original, _ = packet(data)
    for row in [data['space'], data['kp'], *data['schumann'], data['kp_fallback'], data['pulse'], *data['public_copy']]:
        for key, value in row.items():
            if key in {'updated_at', 'now_ts', 'kp_time', 'last_fundamental_ts', 'ts_utc', 'ts'}:
                row[key] = utc(value).astimezone(timezone(timedelta(hours=-10)))
    assert packet(data)[0] == original


def test_exact_wire_source_policy_and_production_day():
    p, _ = packet(synthetic=False)
    _, now, _ = inputs()
    validate_facts(p, 'dated_production_facts', now)
    p['source_manifest'][0]['source_path'] = 'raw.user_symptoms'
    with pytest.raises(DraftError): validate_facts(p, 'dated_production_facts', now)
    day, now, data = inputs()
    with pytest.raises(DraftError, match='facts_stale'):
        prepare_public_packet(day, now=now+timedelta(days=1), **data)


def test_trace_unused_loaders_and_api_shape_without_import_or_network():
    tree = ast.parse((ROOT/'bots/earthscope_post/earthscope_generate.py').read_text())
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not calls.intersection({'_load_pulse_cards', '_load_space_weather', '_load_earthscope_card'})
    route = next(n for n in ast.parse((ROOT/'app/routers/space.py').read_text()).body
                 if isinstance(n, ast.AsyncFunctionDef) and n.name == 'space_forecast_outlook')
    final_return = route.body[-1].value
    keys = {k.value for k in final_return.keys}
    assert not keys.intersection({'bz_now', 'sw_speed_now_kms', 'earth_directed_cme_count_24h', 'cme'})


@pytest.mark.anyio
async def test_restricted_collect_view_and_no_private_table_grant(postgres, tmp_path):
    params, _, cluster = postgres
    day, now, data = inputs()
    async with await psycopg.AsyncConnection.connect(**params) as conn:
        await conn.execute('truncate marts.space_weather_daily,marts.kp_obs,ext.schumann,ext.space_weather,ext.magnetosphere_pulse')
        s = data['space']
        await conn.execute('insert into marts.space_weather_daily(day,updated_at,kp_max,bz_min,sw_speed_avg,flares_count,cmes_count,sw_speed_now_kms,sw_speed_now,now_ts,kp_now) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', tuple(s[k] for k in ('day','updated_at','kp_max','bz_min','sw_speed_avg','flares_count','cmes_count','sw_speed_now_kms','sw_speed_now','now_ts','kp_now')))
        await conn.execute('insert into marts.kp_obs values (%s,%s)', tuple(data['kp'].values()))
        for r in data['schumann']:
            await conn.execute('insert into ext.schumann values (%s,%s,%s,%s)', (r['station_id'],r['last_fundamental_ts'],'fundamental_hz',r['f0_avg_hz']))
        for r in data['public_copy']:
            metrics = {k:r[k] for k in ('kp_max_24h','bz_min','solar_wind_kms')}
            metrics.update(private_canary='DO-NOT-PROJECT',social_variants={'ig':{'caption':r['ig_caption']},'fb':{'caption':r['fb_caption']}})
            await conn.execute('insert into content.daily_posts(title,day,updated_at,platform,caption,metrics_json) values (%s,%s,%s,%s,%s,%s)', (r['title'],r['day'],r['updated_at'],'default',r['caption'],Jsonb(metrics)))
        await conn.execute("""insert into content.daily_posts(title,day,updated_at,user_id,platform,caption)
            values ('PRIVATE MEMBER',%s,%s,'00000000-0000-0000-0000-000000000044','default','PRIVATE-ROW'),
                   ('NONDEFAULT',%s,%s,null,'member','PRIVATE-PLATFORM')""", (day,now,day,now))
        await conn.execute('set role gaia_earthscope_writer_preparer')
        collected = await collect_public_inputs(conn, day)
        assert len(collected['public_copy']) == 2
        serialized = json.dumps(collected, default=str)
        assert 'PRIVATE' not in serialized and 'DO-NOT-PROJECT' not in serialized
        actual, qualification = prepare_public_packet(day, now=now, synthetic=True, **collected)
        assert actual['facts']['schumann_value_hz'] == 7.9 and len(actual['recent_public_copy']) == 6
        for sql in ('select caption from content.daily_posts', 'select secret from raw.user_symptoms'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege): await conn.execute(sql)
        assert (await (await conn.execute("select has_table_privilege(current_user,'content.earthscope_writer_public_history','UPDATE')")).fetchone())[0] is False
        with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectNotInPrerequisiteState)):
            await conn.execute("update content.earthscope_writer_public_history set caption='bad'")
        await conn.execute('reset role')
        for role in ('anon', 'authenticated', 'service_role', 'gaia_earthscope_writer_backend'):
            await conn.execute('set role ' + role)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await conn.execute('select * from content.earthscope_writer_public_history')
            await conn.execute('reset role')
        assert (await (await conn.execute("select count(*) from content.daily_posts where caption='PRIVATE-ROW'")).fetchone())[0] == 1
        (tmp_path/'public-inputs.json').write_text(json.dumps({'facts':actual,'qualification':qualification,'cluster':str(cluster)},indent=2))


@pytest.mark.anyio
async def test_producer_receipt_includes_exact_packet_and_qualification(monkeypatch):
    day, now, data = inputs()
    async def collect(conn, selected_day): assert selected_day == day; return copy.deepcopy(data)
    async def clock(conn): return now
    async def enqueue(conn, p, version, worker, deadline, classification):
        assert classification == 'dated_production_facts'
        return {'job_id':p['job_id']}
    async def receipt(*args):
        return dict(status='expired',job_id='earthscope-20260921',facts_sha256='a'*64,claim_id=None,
                    failure_code='job_expired',outcome=None,outcome_sha256=None,acknowledgement_id=None)
    class Conn:
        async def commit(self): pass
    monkeypatch.setattr(shadow,'collect_public_inputs',collect)
    monkeypatch.setattr(shadow.queue,'now_at',clock)
    monkeypatch.setattr(shadow.queue,'enqueue',enqueue)
    monkeypatch.setattr(shadow.queue,'receipt',receipt)
    r = await shadow.run_shadow(Conn(),day,1,'fixture-worker',300)
    assert r['status'] == 'expired' and r['production_consumption'] is False
    assert r['source_qualification']['facts_sha256'] == sha256(r['facts_packet'])
