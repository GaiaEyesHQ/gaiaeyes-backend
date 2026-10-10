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
            return [{'user_id': uid, 'day': params[1], 'updated_at': Clock.fromtimestamp(instant.timestamp(), timezone.utc), 'inputs_hash': 'synthetic-hash'} for uid in params[0]]
        return []

    def score(uid, day, *, force=False, diagnostics=None):
        diagnostics.update(inputs_hash="synthetic-hash", previous_inputs_hash="synthetic-hash", output_existed=True, evaluated_at=instant)
        calls.append((uid, day, gauge_scorer._local_day_bounds(day), force))
        result = (outcomes or {}).get(uid, {'ok': True, 'skipped': False})
        if isinstance(result, Exception):
            raise result
        return result

    actual_verify = gauge_scoring_job._verify_outputs

    def verify(expected, refreshed, started_at, evaluations, summary):
        verification.append((set(expected), set(refreshed), started_at))
        return actual_verify(expected, refreshed, started_at, evaluations, summary)

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
    assert clock.calls == 2
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
    assert clock.calls == 2
    assert {uid for uid, *_ in calls} == set(sorted(PREFERENCES)[:2])
    assert all(day == date(2026, 3, 8) and force for _, day, _, force in calls)
    assert all((end-start) == timedelta(hours=23) for _, _, (start, end), _ in calls)


def test_batch_success_skip_failure_and_exception_accounting(monkeypatch, caplog):
    now = datetime(2026, 9, 11, 4, 3, 44, tzinfo=timezone.utc)
    outcomes = {'chicago': {'ok': True, 'skipped': True, 'skip_reason': 'unchanged_inputs'}, 'utc': {'ok': False},
                'tokyo': RuntimeError('synthetic score failure')}
    _, _, calls, verification = _dispatch(monkeypatch, now, outcomes=outcomes)
    with pytest.raises(SystemExit) as error, caplog.at_level(logging.ERROR):
        gauge_scoring_job.main()
    assert error.value.code == 1 and len(calls) == len(PREFERENCES)
    expected, refreshed, started_at = verification[0]
    assert expected == {(uid, date(2026, 9, 10)) for uid in PREFERENCES}
    assert refreshed == {(uid, date(2026, 9, 10)) for uid in PREFERENCES.keys() - outcomes.keys()}
    assert started_at == now
    assert 'score_exception' in caplog.text and 'score_not_ok' in caplog.text
    assert 'tokyo' not in caplog.text and 'utc' not in caplog.text
    assert 'missing_updated_at' not in caplog.text and 'verification_failed' not in caplog.text


def test_single_user_override_bypasses_eligibility_queries(monkeypatch):
    _, queries, calls, _ = _dispatch(monkeypatch, datetime(2026,9,11,4,tzinfo=timezone.utc),
                                    args=['--user-id', 'tokyo'])
    gauge_scoring_job.main()
    assert len(calls) == 1 and calls[0][0:2] == ('tokyo', date(2026,9,10))
    assert not any('app.user_locations' in sql or 'user_notification_preferences' in sql for sql in queries)


def test_empty_batch_does_not_open_a_worker_connection(monkeypatch):
    clock, queries, calls, verification = _dispatch(monkeypatch, datetime(2026,9,11,4,tzinfo=timezone.utc))
    monkeypatch.setattr(gauge_scoring_job, '_fetch_user_ids', lambda failures: set())
    scope = Mock(side_effect=AssertionError('Empty batch must not connect'))
    monkeypatch.setattr(gauge_scoring_job.pg, 'connection_scope', scope)
    gauge_scoring_job.main()
    assert clock.calls == 2 and not calls and not queries
    assert verification[0][0:2] == (set(), set())
    scope.assert_not_called()


def test_output_verification_accepts_old_skips_but_rejects_stale_refresh_and_missing(monkeypatch):
    now = datetime(2026, 9, 11, 4, tzinfo=timezone.utc); day = date(2026, 9, 10)
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', lambda *a: [
        {'user_id': uid, 'day': day, 'updated_at': now-timedelta(hours=1), 'inputs_hash': 'same'}
        for uid in ['skip', 'refresh']])
    expected = {(uid, day) for uid in ['skip', 'refresh', 'missing']}
    evaluations = {key: {'inputs_hash': 'same', 'evaluated_at': now} for key in expected}
    summary = {}
    assert gauge_scoring_job._verify_outputs(expected, {('refresh', day)}, now,
        evaluations, summary) == ['missing_output', 'stale_updated_at']
    assert summary['outputs_found'] == 2
    assert summary['oldest_output_changed_at'] == (now-timedelta(hours=1)).isoformat()


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
job._fetch_user_ids=lambda failures: {'synthetic-user'}
job.pg.connection_scope=nullcontext
job.pg.fetch=lambda *a,**k: (_ for _ in ()).throw(AssertionError('No database query allowed'))
job._verify_outputs=lambda *a: []
calls=[]
def score(uid,day,force=False,diagnostics=None):
    calls.append({'day':day.isoformat(),'bounds':[d.isoformat() for d in scorer._local_day_bounds(day)]})
    return {'ok':True,'skipped':True,'skip_reason':'unchanged_inputs'}
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

    assert gauge_scoring_job._fetch_user_ids([]) == {"healthkit-user", "recent-app-user"}


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
    monkeypatch.setattr(gauge_scoring_job, "_fetch_user_ids", lambda failures: {f"user-{i}" for i in range(5)})
    monkeypatch.setattr(gauge_scoring_job, "_verify_outputs", lambda *args: [])
    monkeypatch.setattr(
        gauge_scoring_job,
        "score_user_day",
        lambda user_id, day, force=False, diagnostics=None: scored.append(user_id) or {"ok": True, "skipped": True, "skip_reason": "unchanged_inputs"},
    )

    gauge_scoring_job.main()

    assert entered == ["entered", "entered"]
    assert exited == ["exited", "exited"]
    assert sorted(scored) == [f"user-{i}" for i in range(5)]


def _summary(caplog):
    return json.loads(next(record.message.split('evaluation_summary=', 1)[1]
                          for record in caplog.records if 'evaluation_summary=' in record.message))


def test_summary_distinguishes_evaluation_from_old_unchanged_output(monkeypatch, caplog):
    now = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    outcomes = {uid: {'ok': True, 'skipped': True, 'skip_reason': 'unchanged_inputs'} for uid in PREFERENCES}
    _dispatch(monkeypatch, now, outcomes=outcomes)
    original = gauge_scoring_job.pg.fetch

    def fetch(sql, *params):
        rows = original(sql, *params)
        if 'marts.user_gauges_day' in sql:
            for row in rows:
                row['updated_at'] -= timedelta(hours=9)
        return rows

    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', fetch)
    with caplog.at_level(logging.INFO):
        gauge_scoring_job.main()
    summary = _summary(caplog)
    assert summary['status'] == 'pass' and summary['verification_completed']
    assert summary['evaluated'] == summary['unchanged_inputs'] == summary['outputs_found'] == len(PREFERENCES)
    assert summary['refreshed'] == 0 and summary['failures'] == {}
    assert summary['last_evaluated_at'] == now.isoformat()
    assert summary['latest_output_changed_at'] == (now - timedelta(hours=9)).isoformat()
    assert 'synthetic-hash' not in caplog.text and 'user=' not in caplog.text
    assert 'chicago' not in caplog.text


@pytest.mark.parametrize('source', ['app.user_locations', 'public.app_user_entitlements_active',
                                  'gaia.samples', 'raw.app_analytics_events'])
def test_incomplete_eligibility_is_a_failure_even_when_other_users_succeed(monkeypatch, caplog, source):
    _dispatch(monkeypatch, datetime(2026, 10, 7, 15, tzinfo=timezone.utc))
    original = gauge_scoring_job.pg.fetch

    def fetch(sql, *params):
        if source in sql:
            raise RuntimeError('PRIVATE_IDENTIFIER_AND_HEALTH_PAYLOAD')
        return original(sql, *params)

    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', fetch)
    with caplog.at_level(logging.INFO), pytest.raises(SystemExit) as error:
        gauge_scoring_job.main()
    summary = _summary(caplog)
    assert error.value.code == 1 and summary['status'] == 'fail'
    assert summary['eligibility_source_failures'] == [source]
    assert summary['verification_completed']
    assert 'PRIVATE_IDENTIFIER_AND_HEALTH_PAYLOAD' not in caplog.text


@pytest.mark.parametrize('stored_hash, reason', [('previous', 'changed_inputs_pending'),
                                               ('concurrent', 'input_hash_mismatch')])
def test_hash_verification_detects_unprocessed_change_even_with_recent_timestamp(monkeypatch, stored_hash, reason):
    now = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    day = date(2026, 10, 7); key = ('synthetic-user', day)
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', lambda *args: [
        {'user_id': key[0], 'day': day, 'updated_at': now, 'inputs_hash': stored_hash}])
    evaluations = {key: {'inputs_hash': 'changed', 'previous_inputs_hash': 'previous',
                         'output_existed': True, 'evaluated_at': now}}
    assert gauge_scoring_job._verify_outputs({key}, {key}, now, evaluations, {}) == [reason]


def test_missing_output_is_a_failure_even_when_scorer_reports_unchanged(monkeypatch, caplog):
    _dispatch(monkeypatch, datetime(2026, 10, 7, 15, tzinfo=timezone.utc),
              args=['--user-id', 'chicago'],
              outcomes={'chicago': {'ok': True, 'skipped': True, 'skip_reason': 'unchanged_inputs'}})
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', lambda *args: [])
    with caplog.at_level(logging.INFO), pytest.raises(SystemExit):
        gauge_scoring_job.main()
    summary = _summary(caplog)
    assert summary['failures'] == {'missing_output': 1}
    assert summary['scope'] == 'selected_users' and summary['eligible_users'] is None
    assert summary['outputs_found'] == 0


def test_all_eligibility_sources_failed_cannot_pass_as_empty_batch(monkeypatch, caplog):
    _dispatch(monkeypatch, datetime(2026, 10, 7, 15, tzinfo=timezone.utc))
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', Mock(side_effect=RuntimeError('private payload')))
    with caplog.at_level(logging.INFO), pytest.raises(SystemExit):
        gauge_scoring_job.main()
    summary = _summary(caplog)
    assert summary['expected_outputs'] == summary['evaluated'] == 0
    assert len(summary['eligibility_source_failures']) == 4 and summary['status'] == 'fail'


@pytest.mark.parametrize('failure', ['verification', 'worker'])
def test_infrastructure_failure_emits_incomplete_private_summary(monkeypatch, caplog, failure):
    _dispatch(monkeypatch, datetime(2026, 10, 7, 15, tzinfo=timezone.utc), args=['--user-id', 'chicago'])
    if failure == 'verification':
        monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', Mock(side_effect=RuntimeError('private payload')))
    else:
        monkeypatch.setattr(gauge_scoring_job.pg, 'connection_scope', Mock(side_effect=RuntimeError('private payload')))
    with caplog.at_level(logging.INFO), pytest.raises(SystemExit):
        gauge_scoring_job.main()
    summary = _summary(caplog)
    assert summary['status'] == 'fail'
    assert summary['failures'][f'{failure}_failed'] == 1
    assert summary['verification_completed'] is (failure != 'verification')
    assert 'private payload' not in caplog.text and 'user=' not in caplog.text


def test_unexplained_skip_is_not_reported_as_unchanged(monkeypatch, caplog):
    _dispatch(monkeypatch, datetime(2026, 10, 7, 15, tzinfo=timezone.utc), args=['--user-id', 'chicago'],
              outcomes={'chicago': {'ok': True, 'skipped': True}})
    with caplog.at_level(logging.INFO), pytest.raises(SystemExit):
        gauge_scoring_job.main()
    assert _summary(caplog)['failures'] == {'unexplained_skip': 1}
    assert _summary(caplog)['unchanged_inputs'] == 0


def test_failed_changed_input_write_reports_pending_without_printing_inputs(monkeypatch, caplog):
    now = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    _dispatch(monkeypatch, now, args=['--user-id', 'chicago'])

    def score(uid, day, *, force=False, diagnostics=None):
        diagnostics.update(inputs_hash='private-new-hash', previous_inputs_hash='private-old-hash',
                           output_existed=True, evaluated_at=now)
        raise RuntimeError('PRIVATE HEALTH DATA IN DATABASE ERROR')

    monkeypatch.setattr(gauge_scoring_job, 'score_user_day', score)
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', lambda *args: [
        {'user_id': 'chicago', 'day': date(2026, 10, 7),
         'updated_at': gauge_scoring_job.datetime.fromtimestamp(now.timestamp() - 3600, timezone.utc),
         'inputs_hash': 'private-old-hash'}])
    with caplog.at_level(logging.INFO), pytest.raises(SystemExit):
        gauge_scoring_job.main()
    summary = _summary(caplog)
    assert summary['evaluated'] == 1 and summary['refreshed'] == 0
    assert summary['failures'] == {'score_exception': 1, 'changed_inputs_pending': 1}
    assert 'PRIVATE HEALTH' not in caplog.text
    assert 'private-new-hash' not in caplog.text and 'private-old-hash' not in caplog.text
    assert 'chicago' not in caplog.text


def test_existing_output_without_evaluation_evidence_cannot_pass(monkeypatch):
    now = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    key = ('synthetic', date(2026, 10, 7))
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', lambda *args: [
        {'user_id': key[0], 'day': key[1], 'updated_at': now, 'inputs_hash': 'same'}])
    assert gauge_scoring_job._verify_outputs({key}, set(), now, {}, {}) == ['not_evaluated']


def _verify_overwritten_output(monkeypatch, *, stored_hash='newer', offset=1,
                               proof_hash='evaluated', proof_timestamp=True, refreshed=True,
                               proof_offset=0):
    now = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    key = ('synthetic-user', date(2026, 10, 7))
    row = {'user_id': key[0], 'day': key[1], 'inputs_hash': stored_hash,
           'updated_at': now + timedelta(seconds=offset)}
    fetch = Mock(return_value=[row])
    monkeypatch.setattr(gauge_scoring_job.pg, 'fetch', fetch)
    monkeypatch.setattr(gauge_scoring_job, 'score_user_day',
                        Mock(side_effect=AssertionError('Verification must not rescore or write')))
    evaluation = {'inputs_hash': 'evaluated', 'previous_inputs_hash': 'previous',
                  'output_existed': True, 'evaluated_at': now,
                  'verified_output_inputs_hash': proof_hash,
                  'verified_output_updated_at': now + timedelta(seconds=proof_offset) if proof_timestamp else None}
    summary = {}
    errors = gauge_scoring_job._verify_outputs(
        {key}, {key} if refreshed else set(), now, {key: evaluation}, summary)
    fetch.assert_called_once()
    gauge_scoring_job.score_user_day.assert_not_called()
    return errors, summary


def test_later_writer_is_distinguished_from_exact_evaluation_without_rescoring(monkeypatch):
    errors, summary = _verify_overwritten_output(monkeypatch)
    assert errors == []
    assert summary['outputs_found'] == summary['outputs_superseded'] == 1
    assert summary['outputs_matching_evaluation'] == 0


def test_exact_evaluation_remains_separate_from_superseded_outputs(monkeypatch):
    errors, summary = _verify_overwritten_output(monkeypatch, stored_hash='evaluated', offset=0)
    assert errors == []
    assert summary['outputs_found'] == summary['outputs_matching_evaluation'] == 1
    assert summary['outputs_superseded'] == 0


@pytest.mark.parametrize('offset', [0, -1, -3600])
def test_equal_or_older_different_hash_never_counts_as_superseded(monkeypatch, offset):
    errors, summary = _verify_overwritten_output(monkeypatch, offset=offset)
    assert 'input_hash_mismatch' in errors
    if offset == -3600:
        assert 'stale_updated_at' in errors
    assert summary['outputs_superseded'] == 0


@pytest.mark.parametrize('proof_hash, proof_timestamp', [(None, True), ('wrong', True), ('evaluated', False)])
def test_new_timestamp_without_matching_output_proof_cannot_mask_mismatch(monkeypatch, proof_hash, proof_timestamp):
    errors, summary = _verify_overwritten_output(
        monkeypatch, proof_hash=proof_hash, proof_timestamp=proof_timestamp)
    assert errors == ['input_hash_mismatch']
    assert summary['outputs_superseded'] == 0


def test_previous_hash_reversion_remains_pending_even_after_verified_write(monkeypatch):
    errors, summary = _verify_overwritten_output(monkeypatch, stored_hash='previous')
    assert errors == ['changed_inputs_pending']
    assert summary['outputs_superseded'] == 0


def test_missing_hash_never_counts_as_superseded(monkeypatch):
    errors, summary = _verify_overwritten_output(monkeypatch, stored_hash=None)
    assert errors == ['input_hash_mismatch']
    assert summary['outputs_superseded'] == 0


def test_output_observed_on_unchanged_skip_can_be_superseded(monkeypatch):
    errors, summary = _verify_overwritten_output(monkeypatch, refreshed=False, proof_offset=-7200)
    assert errors == []
    assert summary['outputs_superseded'] == 1


def test_later_but_still_stale_writer_cannot_supersede_old_unchanged_skip(monkeypatch):
    errors, summary = _verify_overwritten_output(
        monkeypatch, refreshed=False, proof_offset=-7200, offset=-3600)
    assert errors == ['input_hash_mismatch']
    assert summary['outputs_superseded'] == 0
