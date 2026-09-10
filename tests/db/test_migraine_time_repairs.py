"""G-R20/G-R21: actual readers/scorer plus disposable-PG save and retry."""
import json
import os
from datetime import date, datetime, timedelta, UTC
from pathlib import Path
from uuid import UUID, uuid4
from unittest.mock import Mock

import psycopg
import pytest
from psycopg.rows import dict_row
from bots.gauges import gauge_scorer as gauges
from bots.patterns import pattern_engine_job as patterns
from app.routers import symptoms as router
from services.migraine.time_correction import CorrectionTimestamp, TimeCorrectionIn
from test_migraine_time_postgres import seed, stamp, request_for, snapshot
from test_migraine_postgres_integration import _connect, _request, _insert_prompt, _database_url, USER_A

pytestmark = pytest.mark.anyio


def anyio_backend(): return 'asyncio'


def isolate_unrelated_gauge_inputs(monkeypatch):
    # Keep the actual correction orchestrator, scorer and symptom SQL reader.
    for name, value in {
        'load_definition_base': ({}, 'synthetic'), 'fetch_local_payload': {'synthetic': True},
        'resolve_signals': [], 'fetch_user_tags': [], 'fetch_exposure_summary': {},
        'fetch_recent_daily_checkins': {}, 'fetch_local_health_summary': {},
        'fetch_daily_features': {}, 'fetch_daily_features_baseline': [],
        'fetch_hrv_fallback': (None, None, None), 'compute_health_status': (None, {}),
        '_score_gauges': {}, 'apply_symptom_gauge_adjustments': ({}, {}),
        'apply_exposure_gauge_adjustments': ({}, {}),
        'apply_daily_check_in_energy_adjustment': ({}, {}), '_build_alerts': [],
        '_compute_trend': {}, 'table_columns': set(), '_upsert_gauge_delta': None,
    }.items():
        monkeypatch.setattr(gauges, name, Mock(return_value=value))
    monkeypatch.setattr(patterns, 'run_pattern_engine', Mock(return_value={}))


async def test_fractional_actual_route_audit_ack_and_exact_retry(monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED', '1')
    async def refreshed(*args): return {'status': 'complete', 'pending_components': []}
    monkeypatch.setattr(router, '_refresh_migraine_time_correction', refreshed)
    async with await _connect(autocommit=False) as conn:
        eid, event = await seed(conn, episode_id=UUID('33333333-3333-4333-8333-333333333333'))
        await conn.commit()
        context = await router.get_migraine_time_context(eid, _request(USER_A), conn)
        request = await request_for(conn, eid, start=stamp('2026-08-30T23:30:00.123456'),
                                    end=stamp('2026-09-01T02:30:00.000001'), state='resolved')
        response = await router.correct_migraine_episode_times(eid, request, _request(USER_A), conn)
        saved = await snapshot(conn, eid)
        assert datetime.fromisoformat(saved['canonical']['started_at']).microsecond == 123456
        assert datetime.fromisoformat(saved['canonical']['resolution_ts']).microsecond == 1
        encoded = router.MigraineTimeResponse.model_validate(response).model_dump(mode='json')
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute('select payload,time_correction from raw.user_migraine_episode_detail_revisions where correction_request_id=%s', (request.request_id,))
            row = await cur.fetchone()
            assert row['time_correction']['request'] == request.canonical_request()
            assert TimeCorrectionIn.model_validate(row['time_correction']['request']).canonical_request() == request.canonical_request()
            for field in ('start', 'end'):
                expected = getattr(request, field)
                assert CorrectionTimestamp.model_validate(encoded['data']['episode'][field]) == expected
                assert CorrectionTimestamp.model_validate(row['payload'][field]) == expected
                assert CorrectionTimestamp.model_validate(saved['detail'][field]) == expected
            await cur.execute('select ts_utc from raw.user_symptom_events where id=%s', (event,))
            assert (await cur.fetchone())['ts_utc'] == datetime(2026, 9, 1, 4, 30, tzinfo=UTC)
        retry = await router.correct_migraine_episode_times(eid, TimeCorrectionIn.model_validate(request.canonical_request()), _request(USER_A), conn)
        assert retry['data']['replayed'] and retry['data']['revision'] == 2
        assert await snapshot(conn, eid) == saved
        if directory := os.getenv('GAIA_TIME_REPAIR_EVIDENCE_DIR'):
            out = Path(directory); out.mkdir(parents=True, exist_ok=True)
            for name, value in [('context', context), ('ack', response)]:
                (out/f'backend-fractional-{name}.json').write_text(router.MigraineTimeResponse.model_validate(value).model_dump_json(indent=2)+'\n')
            (out/'backend-fractional-request.json').write_text(json.dumps(request.canonical_request(), indent=2)+'\n')


async def test_failed_actual_corrected_reader_preserves_gauge_and_committed_retry(monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_TIME_EDITING_ENABLED', '1')
    isolate_unrelated_gauge_inputs(monkeypatch)
    failed = True
    reads, writes = [], []
    # All SQL below uses the private guarded database; unrelated gauge inputs are synthetic.
    def fetch(query, *params):
        reads.append(query)
        if failed and 'from raw.user_symptom_events_effective' in query:
            raise RuntimeError('synthetic corrected-event read failure')
        with psycopg.connect(_database_url(), row_factory=dict_row) as sync:
            return sync.execute(query, params).fetchall()
    monkeypatch.setattr(gauges.pg, 'fetch', fetch)
    monkeypatch.setattr(gauges.pg, 'fetchrow', Mock(return_value=None))
    previous_gauges = {'sentinel': 'prior derived values'}
    def write(schema, table, payload, keys):
        writes.append((schema, table, payload))
        previous_gauges[str(payload['day'])] = payload
    monkeypatch.setattr(gauges, 'upsert_row', write)
    async with await _connect(autocommit=False) as conn:
        eid, _ = await seed(conn)
        await _insert_prompt(conn, prompt_id=uuid4(), user_id=USER_A, episode_id=UUID(eid), scheduled_for=datetime.now(UTC)+timedelta(days=2))
        await conn.commit()
        request = await request_for(conn, eid, start=stamp('2026-08-30T23:30:00'))
        response = await router.correct_migraine_episode_times(eid, request, _request(USER_A), conn)
        assert response['data']['refresh'] == {'status': 'pending', 'pending_components': ['daily_gauges']}
        assert any('from raw.user_symptom_events_effective' in query for query in reads)
        assert not writes and previous_gauges == {'sentinel': 'prior derived values'}
        committed = await snapshot(conn, eid)
        assert committed['detail']['lifecycle']['revision'] == 2
        failed = False
        retry = await router.correct_migraine_episode_times(eid, request, _request(USER_A), conn)
        assert retry['data']['refresh'] == {'status': 'complete', 'pending_components': []}
        assert retry['data']['replayed'] and retry['data']['request_id'] == str(request.request_id)
        assert await snapshot(conn, eid) == committed  # Includes canonical, medicines, audit and prompts.
        assert {str(row[2]['day']) for row in writes} == {'2026-08-30', '2026-08-31'}


@pytest.mark.parametrize('failed_source', ['raw.user_symptom_events_effective', 'raw.user_symptom_episodes'])
async def test_required_reader_failure_cannot_write_or_fall_back(monkeypatch, failed_source):
    isolate_unrelated_gauge_inputs(monkeypatch)
    reads = []
    def fetch(query, *params):
        reads.append(query)
        if f'from {failed_source}' in query: raise RuntimeError('required input unavailable')
        return []
    monkeypatch.setattr(gauges.pg, 'fetch', fetch)
    # An unavailable capability must not select the raw legacy event source.
    monkeypatch.setattr(gauges.pg, 'fetchrow', Mock(return_value={'available': False}))
    writer = Mock(); monkeypatch.setattr(gauges, 'upsert_row', writer)
    response = await router._refresh_migraine_time_correction(USER_A, {'refresh_days': ['2026-09-01'], 'pattern_since_day': '2026-06-13'})
    assert response == {'status': 'pending', 'pending_components': ['daily_gauges']}
    writer.assert_not_called()
    assert not any('from raw.user_symptom_events\n' in query for query in reads)


async def test_legacy_reader_keeps_existing_optional_empty_behavior(monkeypatch):
    monkeypatch.setattr(gauges, 'table_columns', Mock(return_value=set()))
    monkeypatch.setattr(gauges.pg, 'fetchrow', Mock(return_value={'available': False}))
    reader = Mock(side_effect=RuntimeError('legacy optional read'))
    monkeypatch.setattr(gauges.pg, 'fetch', reader)
    assert gauges.fetch_symptom_summary(USER_A, date(2026, 9, 1)) == gauges._build_symptom_signal_summary([])
    assert 'from raw.user_symptom_events\n' in reader.call_args.args[0]


async def test_required_pattern_source_never_falls_back_after_capability_loss(monkeypatch):
    metadata = Mock(return_value=False); monkeypatch.setattr(patterns, '_table_exists', metadata)
    reader = Mock(side_effect=RuntimeError('corrected daily source unavailable'))
    monkeypatch.setattr(patterns, '_fetch_rows', reader)
    with pytest.raises(RuntimeError, match='corrected daily'):
        patterns._fetch_symptom_rows(None, since_day=date(2026, 8, 1), as_of_day=date(2026, 9, 1), user_id=USER_A, require_corrected_symptoms=True)
    metadata.assert_not_called()
    assert 'from marts.symptom_daily_effective' in reader.call_args.args[1]
