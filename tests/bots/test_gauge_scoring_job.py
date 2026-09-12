from __future__ import annotations

import sys
import json
import logging
import os
import subprocess
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from bots.gauges import gauge_scoring_job, gauge_scorer


PREFERENCES = {
    'chicago': 'America/Chicago', 'utc': 'UTC', 'london': 'Europe/London',
    'tokyo': 'Asia/Tokyo', 'los-angeles': 'America/Los_Angeles',
    'missing': None, 'invalid': 'Not/A_Zone',
}


def _dispatch(monkeypatch, instant, *, args=(), outcomes=None):
    class Clock(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            # A second clock read crosses midnight even for the first-boundary
            # case. The batch must nevertheless choose one date for all users.
            value = instant + timedelta(days=cls.calls)
            cls.calls += 1
            return cls.fromtimestamp(value.timestamp(), tz)

    monkeypatch.setattr(gauge_scoring_job, 'datetime', Clock)
    monkeypatch.setattr(gauge_scoring_job, 'DEFAULT_WORKERS', 2)
    monkeypatch.setattr(gauge_scoring_job, 'LOCAL_TZ', ZoneInfo('America/Chicago'))
    monkeypatch.setattr(gauge_scorer, 'LOCAL_TZ', gauge_scoring_job.LOCAL_TZ)
    monkeypatch.setattr(gauge_scoring_job.pg, 'connection_scope', nullcontext)
    monkeypatch.setattr(sys, 'argv', ['gauge_scoring_job.py', *args])
    queries, calls, verification = [], [], []

    def fetch(sql, *params):
        queries.append(sql)
        if 'app.user_locations' in sql:
            return [{'user_id': uid} for uid in PREFERENCES]
        if 'app.user_notification_preferences' in sql:
            return [{'user_id': uid, 'time_zone': zone} for uid, zone in PREFERENCES.items()]
        if 'marts.user_gauges_day' in sql:
            return [{'user_id': uid, 'day': params[1], 'updated_at': Clock.fromtimestamp(instant.timestamp(), timezone.utc)} for uid in params[0]]
        return []

    def score(uid, day, *, force=False):
        calls.append((uid, day, gauge_scorer._local_day_bounds(day), force))
        result = (outcomes or {}).get(uid, {'ok': True, 'skipped': False})
        if isinstance(result, Exception):
            raise result
        return result

    actual_verify = gauge_scoring_job._verify_outputs

    def verify(expected, refreshed, started_at):
        verification.append((set(expected), set(refreshed), started_at))
        return actual_verify(expected, refreshed, started_at)

    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', fetch)
    monkeypatch.setattr(gauge_scoring_job, 'score_user_day', score)
    monkeypatch.setattr(gauge_scoring_job, '_verify_outputs', verify)
    return Clock, queries, calls, verification


@pytest.mark.parametrize('instant, expected', [
    ('2026-09-11T04:03:44+00:00', '2026-09-10'),
    ('2026-09-11T04:59:59.999999+00:00', '2026-09-10'),
    ('2026-09-11T05:00:00+00:00', '2026-09-11'),
    ('2026-01-11T05:59:59.999999+00:00', '2026-01-10'),
    ('2026-01-11T06:00:00+00:00', '2026-01-11'),
])
def test_actual_batch_uses_one_scoring_day_for_all_preferences(monkeypatch, caplog, instant, expected):
    now = datetime.fromisoformat(instant)
    clock, queries, calls, verification = _dispatch(monkeypatch, now)
    with caplog.at_level(logging.INFO):
        gauge_scoring_job.main()
    assert clock.calls == 1
    assert {uid for uid, *_ in calls} == set(PREFERENCES)
    assert {day for _, day, *_ in calls} == {date.fromisoformat(expected)}
    assert all(start <= now < end for _, _, (start, end), _ in calls)
    assert not any('user_notification_preferences' in sql for sql in queries)
    assert verification == [(set((uid, date.fromisoformat(expected)) for uid in PREFERENCES),
                             set((uid, date.fromisoformat(expected)) for uid in PREFERENCES), now)]
    assert f'day={expected} scoring_timezone=' in caplog.text
    if expected == '2026-09-10':
        assert {bounds for _, _, bounds, _ in calls} == {
            (datetime(2026, 9, 10, 5, tzinfo=timezone.utc), datetime(2026, 9, 11, 5, tzinfo=timezone.utc))}


def test_explicit_historical_day_user_limit_and_force_are_preserved(monkeypatch):
    clock, _, calls, _ = _dispatch(monkeypatch, datetime(2026, 9, 11, 4, tzinfo=timezone.utc),
                                  args=['--day', '2026-03-08', '--limit', '2', '--force'])
    gauge_scoring_job.main()
    assert clock.calls == 1
    assert {uid for uid, *_ in calls} == set(sorted(PREFERENCES)[:2])
    assert all(day == date(2026, 3, 8) and force for _, day, _, force in calls)
    assert all((end-start) == timedelta(hours=23) for _, _, (start, end), _ in calls)


def test_batch_success_skip_failure_and_exception_accounting(monkeypatch, caplog):
    now = datetime(2026, 9, 11, 4, 3, 44, tzinfo=timezone.utc)
    outcomes = {'chicago': {'ok': True, 'skipped': True}, 'utc': {'ok': False},
                'tokyo': RuntimeError('synthetic score failure')}
    _, _, calls, verification = _dispatch(monkeypatch, now, outcomes=outcomes)
    with pytest.raises(SystemExit) as error, caplog.at_level(logging.ERROR):
        gauge_scoring_job.main()
    assert error.value.code == 1 and len(calls) == len(PREFERENCES)
    expected, refreshed, started_at = verification[0]
    assert expected == {(uid, date(2026, 9, 10)) for uid in PREFERENCES}
    assert refreshed == {(uid, date(2026, 9, 10)) for uid in PREFERENCES.keys() - outcomes.keys()}
    assert started_at == now
    assert 'exception:tokyo:2026-09-10' in caplog.text and 'not_ok:utc:2026-09-10' in caplog.text
    assert 'missing_updated_at' not in caplog.text and 'verification_failed' not in caplog.text


def test_single_user_override_bypasses_eligibility_queries(monkeypatch):
    _, queries, calls, _ = _dispatch(monkeypatch, datetime(2026,9,11,4,tzinfo=timezone.utc),
                                    args=['--user-id', 'tokyo'])
    gauge_scoring_job.main()
    assert len(calls) == 1 and calls[0][0:2] == ('tokyo', date(2026,9,10))
    assert not any('app.user_locations' in sql or 'user_notification_preferences' in sql for sql in queries)


def test_empty_batch_does_not_open_a_worker_connection(monkeypatch):
    clock, queries, calls, verification = _dispatch(monkeypatch, datetime(2026,9,11,4,tzinfo=timezone.utc))
    monkeypatch.setattr(gauge_scoring_job, '_fetch_user_ids', lambda: set())
    scope = Mock(side_effect=AssertionError('Empty batch must not connect'))
    monkeypatch.setattr(gauge_scoring_job.pg, 'connection_scope', scope)
    gauge_scoring_job.main()
    assert clock.calls == 1 and not calls and not queries
    assert verification[0][0:2] == (set(), set())
    scope.assert_not_called()


def test_output_verification_accepts_old_skips_but_rejects_stale_refresh_and_missing(monkeypatch):
    now = datetime(2026, 9, 11, 4, tzinfo=timezone.utc); day = date(2026, 9, 10)
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', lambda *a: [
        {'user_id': uid, 'day': day, 'updated_at': now-timedelta(hours=1)} for uid in ['skip', 'refresh']])
    assert gauge_scoring_job._verify_outputs({(uid, day) for uid in ['skip', 'refresh', 'missing']},
        {('refresh', day)}, now) == ['missing:missing:2026-09-10', 'stale_updated_at:refresh:2026-09-10']


@pytest.mark.parametrize('configured, resolved, expected_day, expected_start', [
    (None, 'America/Chicago', '2026-09-10', '2026-09-10T05:00:00+00:00'),
    ('Not/A_Zone', 'America/Chicago', '2026-09-10', '2026-09-10T05:00:00+00:00'),
    ('UTC', 'UTC', '2026-09-11', '2026-09-11T00:00:00+00:00'),
    ('Asia/Tokyo', 'Asia/Tokyo', '2026-09-11', '2026-09-10T15:00:00+00:00'),
])
def test_isolated_configuration_uses_scorer_resolved_zone(configured, resolved, expected_day, expected_start):
    script = '''
import json,sys
from datetime import datetime,timezone
from contextlib import nullcontext
from bots.gauges import gauge_scoring_job as job, gauge_scorer as scorer
class Clock(datetime):
    @classmethod
    def now(cls,tz=None): return datetime(2026,9,11,4,3,44,tzinfo=timezone.utc).astimezone(tz)
job.datetime=Clock
job._fetch_user_ids=lambda: {'synthetic-user'}
job.pg.connection_scope=nullcontext
job.pg.fetch=lambda *a,**k: (_ for _ in ()).throw(AssertionError('No database query allowed'))
job._verify_outputs=lambda *a: []
calls=[]
def score(uid,day,force=False):
    calls.append({'day':day.isoformat(),'bounds':[d.isoformat() for d in scorer._local_day_bounds(day)]})
    return {'ok':True,'skipped':True}
job.score_user_day=score
sys.argv=['gauge_scoring_job.py']
job.main()
print(json.dumps({'resolved':job.DEFAULT_TIMEZONE,'shared_object':job.LOCAL_TZ is scorer.LOCAL_TZ,'calls':calls}))
'''
    env = dict(os.environ, DATABASE_URL='postgresql://localhost/test', PYTHONDONTWRITEBYTECODE='1')
    env.pop('GAIA_TIMEZONE', None)
    if configured is not None: env['GAIA_TIMEZONE'] = configured
    result = subprocess.run([sys.executable, '-c', script], env=env, text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert data['resolved'] == resolved and data['shared_object']
    assert data['calls'][0]['day'] == expected_day and data['calls'][0]['bounds'][0] == expected_start


def test_fetch_user_ids_includes_recent_healthkit_and_app_users(monkeypatch) -> None:
    responses = iter(
        [
            [],
            [],
            [{"user_id": "healthkit-user"}],
            [{"user_id": "recent-app-user"}],
        ]
    )
    monkeypatch.setattr(gauge_scoring_job.pg, "fetch", lambda *args, **kwargs: next(responses))

    assert gauge_scoring_job._fetch_user_ids() == {"healthkit-user", "recent-app-user"}


def test_main_uses_one_connection_scope_per_bounded_worker(monkeypatch) -> None:
    entered: list[str] = []
    exited: list[str] = []
    scored: list[str] = []

    @contextmanager
    def connection_scope():
        entered.append("entered")
        try:
            yield
        finally:
            exited.append("exited")

    monkeypatch.setattr(sys, "argv", ["gauge_scoring_job.py"])
    monkeypatch.setattr(gauge_scoring_job.pg, "connection_scope", connection_scope)
    monkeypatch.setattr(gauge_scoring_job, "DEFAULT_WORKERS", 2)
    monkeypatch.setattr(gauge_scoring_job, "_fetch_user_ids", lambda: {f"user-{i}" for i in range(5)})
    monkeypatch.setattr(gauge_scoring_job, "_verify_outputs", lambda *args: [])
    monkeypatch.setattr(
        gauge_scoring_job,
        "score_user_day",
        lambda user_id, day, force=False: scored.append(user_id) or {"ok": True, "skipped": True},
    )

    gauge_scoring_job.main()

    assert entered == ["entered", "entered"]
    assert exited == ["exited", "exited"]
    assert sorted(scored) == [f"user-{i}" for i in range(5)]
