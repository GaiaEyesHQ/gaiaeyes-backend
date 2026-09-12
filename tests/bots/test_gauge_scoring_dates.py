"""Synthetic actual-scorer/query contracts for the batch date compatibility fix."""
import asyncio
import copy
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from bots.gauges import gauge_scorer as scorer

USER = '90000000-0000-4000-8000-000000000001'


@pytest.fixture(autouse=True)
def no_database_and_chicago(monkeypatch):
    # Each test explicitly supplies its query responses. An unaccounted call
    # must fail locally rather than opening even the dummy configured DSN.
    def unexpected(*args, **kwargs):
        raise AssertionError('Unexpected database operation')
    for name in ['fetch', 'fetchrow', 'execute', 'connection_scope']:
        monkeypatch.setattr(scorer.pg, name, unexpected)
    monkeypatch.setattr(scorer, 'LOCAL_TZ', ZoneInfo('America/Chicago'))


def _isolate_other_inputs(monkeypatch):
    for name, result in {
        'load_definition_base': ({}, 'synthetic'), 'fetch_local_payload': {'synthetic': True},
        'resolve_signals': [], 'fetch_user_tags': [], 'fetch_recent_daily_checkins': {},
        'fetch_local_health_summary': {}, 'fetch_daily_features': {}, 'fetch_daily_features_baseline': [],
        'fetch_hrv_fallback': (None, None, None), 'compute_health_status': (None, {}),
        '_score_gauges': {}, 'apply_symptom_gauge_adjustments': ({}, {}),
        'apply_exposure_gauge_adjustments': ({}, {}), 'apply_daily_check_in_energy_adjustment': ({}, {}),
        '_build_alerts': [], '_compute_trend': {}, '_upsert_gauge_delta': None,
    }.items():
        monkeypatch.setattr(scorer, name, Mock(return_value=result))


@pytest.mark.parametrize('day,start_text,end_text,hours', [
    ('2026-03-08', '2026-03-08T06:00:00+00:00', '2026-03-09T05:00:00+00:00', 23),
    ('2026-11-01', '2026-11-01T05:00:00+00:00', '2026-11-02T06:00:00+00:00', 25),
    ('2026-09-10', '2026-09-10T05:00:00+00:00', '2026-09-11T05:00:00+00:00', 24),
])
def test_actual_explicit_scorer_uses_half_open_owner_bounds_and_exposure_lookback(
    monkeypatch, day, start_text, end_text, hours,
):
    _isolate_other_inputs(monkeypatch)
    expected_day = date.fromisoformat(day)
    start, end = datetime.fromisoformat(start_text), datetime.fromisoformat(end_text)
    assert scorer._local_day_bounds(expected_day) == (start, end)
    assert end - start == timedelta(hours=hours)
    queries, writes = [], []
    monkeypatch.setattr(scorer, 'table_columns', lambda *a: {'present'})
    monkeypatch.setattr(scorer.pg, 'fetchrow', lambda *a: {'available': True} if 'to_regclass' in a[0] else None)
    monkeypatch.setattr(scorer.pg, 'fetch', lambda sql, *params: queries.append((sql, params)) or [])
    monkeypatch.setattr(scorer, 'upsert_row', lambda *args: writes.append(args))
    result = scorer.score_user_day(USER, expected_day, require_corrected_symptoms=True)
    assert result['day'] == day and not result['skipped']
    assert len(queries) == 3
    for sql, params in queries:
        normalized = ' '.join(sql.split())
        assert 'where user_id = %s' in normalized and params[0] == USER
        if 'raw.user_exposure_events' in sql:
            assert params == (USER, start-timedelta(hours=72), end)
            assert 'event_ts_utc >= %s' in sql and 'event_ts_utc < %s' in sql
        else:
            assert params == (USER, start, end)
            column = 'last_interaction_at' if 'raw.user_symptom_episodes' in sql else 'ts_utc'
            assert f'{column} >= %s' in sql and f'{column} < %s' in sql
            assert 'raw.user_symptom_episodes' in sql or 'raw.user_symptom_events_effective' in sql
    assert len(writes) == 1
    assert writes[0][0:2] == ('marts', 'user_gauges_day')
    assert writes[0][2]['user_id'] == USER and writes[0][2]['day'] == expected_day
    assert writes[0][3] == ['user_id', 'day']


@pytest.mark.parametrize('now_text,expected_asof', [
    ('2026-09-11T04:03:44+00:00', '2026-09-11T04:03:44+00:00'),
    ('2026-09-12T04:03:44+00:00', '2026-09-11T05:00:00+00:00'),
])
def test_exposure_historical_asof_is_capped_at_scoring_day_end(monkeypatch, now_text, expected_asof):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.fromisoformat(now_text).astimezone(tz)
    monkeypatch.setattr(scorer, 'datetime', Clock)
    monkeypatch.setattr(scorer, 'table_columns', lambda *a: {'present'})
    reader = Mock(return_value=[]); monkeypatch.setattr(scorer.pg, 'fetch', reader)
    build = Mock(return_value={}); monkeypatch.setattr(scorer, '_build_exposure_signal_summary', build)
    scorer.fetch_exposure_summary(USER, date(2026, 9, 10))
    assert reader.call_args.args[1:] == (USER, datetime(2026, 9, 7, 5, tzinfo=timezone.utc),
                                        datetime(2026, 9, 11, 5, tzinfo=timezone.utc))
    assert build.call_args.kwargs['asof'] == datetime.fromisoformat(expected_asof)


def test_actual_unchanged_input_hash_skips_without_forcing_another_write(monkeypatch):
    _isolate_other_inputs(monkeypatch)
    monkeypatch.setattr(scorer, 'table_columns', lambda *a: {'present'})
    monkeypatch.setattr(scorer.pg, 'fetch', lambda *a: [])
    stored = {}; reads = []
    def fetchrow(sql, *params):
        if 'to_regclass' in sql: return {'available': True}
        reads.append((sql, params))
        return {'inputs_hash': stored['inputs_hash']} if stored else None
    monkeypatch.setattr(scorer.pg, 'fetchrow', fetchrow)
    writes = []
    def write(schema, table, payload, keys):
        writes.append(copy.deepcopy(payload)); stored.update(payload)
    monkeypatch.setattr(scorer, 'upsert_row', write)
    day = date(2026, 3, 8)
    assert not scorer.score_user_day(USER, day)['skipped']
    assert scorer.score_user_day(USER, day)['skipped']
    assert len(writes) == 1 and len(reads) == 2
    assert all(params == (USER, day) for _, params in reads)
    assert len(stored['inputs_hash']) == 64
    # Historical string and date callers retain the same key and fingerprint.
    assert scorer.score_user_day(USER, day.isoformat())['skipped']
    assert len(writes) == 1


@pytest.mark.parametrize('failed_source', ['raw.user_symptom_events_effective', 'raw.user_symptom_episodes'])
def test_persisted_chicago_refresh_days_and_strict_pending_retry_remain(monkeypatch, failed_source):
    from app.routers import symptoms as router
    from bots.patterns import pattern_engine_job
    _isolate_other_inputs(monkeypatch)
    monkeypatch.setattr(scorer, 'table_columns', lambda *a: set())
    monkeypatch.setattr(scorer.pg, 'fetchrow', lambda *a: None)
    receipt = {'refresh_days': ['2026-03-08', '2026-11-01'], 'pattern_since_day': '2026-03-08'}
    preserved = copy.deepcopy(receipt); queries = []; writes = []; fail = True
    # Preferences/environment changes must not reinterpret an existing receipt.
    monkeypatch.setenv('GAIA_TIMEZONE', 'Asia/Tokyo')
    def fetch(sql, *params):
        queries.append((sql, params))
        if fail and f'from {failed_source}' in sql: raise RuntimeError('synthetic required read failure')
        return []
    monkeypatch.setattr(scorer.pg, 'fetch', fetch)
    monkeypatch.setattr(scorer, 'upsert_row', lambda *args: writes.append(args))
    patterns = Mock(return_value={}); monkeypatch.setattr(pattern_engine_job, 'run_pattern_engine', patterns)
    pending = asyncio.run(router._refresh_migraine_time_correction(USER, receipt))
    assert pending == {'status': 'pending', 'pending_components': ['daily_gauges']}
    assert not writes and receipt == preserved
    assert not any('from raw.user_symptom_events\n' in sql for sql, _ in queries)
    fail = False; queries.clear()
    complete = asyncio.run(router._refresh_migraine_time_correction(USER, receipt))
    assert complete == {'status': 'complete', 'pending_components': []} and receipt == preserved
    assert {row[2]['day'].isoformat() for row in writes} == set(receipt['refresh_days'])
    assert len(writes) == 2
    assert all(call.kwargs['user_id'] == USER and call.kwargs['require_corrected_symptoms'] for call in patterns.call_args_list)
    bounds = {(p[1], p[2]) for sql, p in queries if 'raw.user_symptom_' in sql}
    assert bounds == {
        (datetime(2026,3,8,6,tzinfo=timezone.utc),datetime(2026,3,9,5,tzinfo=timezone.utc)),
        (datetime(2026,11,1,5,tzinfo=timezone.utc),datetime(2026,11,2,6,tzinfo=timezone.utc)),
    }


def test_direct_scorer_utc_default_is_unchanged_and_explicit_day_remains_authoritative(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime(2026,9,11,4,3,44,tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(scorer, 'datetime', Clock)
    assert scorer._coerce_day(None) == date(2026,9,11)
    assert scorer._coerce_day(date(2026,3,8)) == date(2026,3,8)
    assert scorer._coerce_day('2026-03-08') == date(2026,3,8)
