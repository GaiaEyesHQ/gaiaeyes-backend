from datetime import datetime, timedelta, timezone
import sys

import pytest

from bots.notifications import evaluate_push_notifications as evaluate
from bots.notifications import send_push_notifications as sender
from bots.notifications.push_logic import NotificationCandidate, normalize_preferences

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def preferences(**changes):
    return normalize_preferences({'enabled': True, 'symptom_followups_enabled': True,
                                  'symptom_followup_push_enabled': True,
                                  'families': {'symptom_followups': True}, **changes})


def event(**changes):
    return {'id': 'event', 'user_id': 'user', 'family': 'pressure', 'severity': 'watch',
            'created_at': NOW - timedelta(minutes=10), 'payload': {}, **changes}


def prompt_candidate():
    return NotificationCandidate('symptom_followups', 'prompt_1', 'watch', 'Reminder',
                                 'Open the app', 'current_symptoms', 'prompt', payload={'prompt_id': 'prompt'})


def test_quiet_skip_does_not_insert_or_mark_delivered_and_can_queue_after_quiet(monkeypatch):
    candidate = prompt_candidate()
    rows = []
    monkeypatch.setattr(evaluate, '_build_candidates_for_user', lambda *args: [candidate])
    monkeypatch.setattr(evaluate, '_latest_events_by_family', lambda *args: {})
    monkeypatch.setattr(evaluate, '_queue_candidate', lambda **kw: rows.append(kw) or True)
    monkeypatch.setattr(evaluate, 'utc_now', lambda: NOW.replace(hour=23))
    prefs = preferences(quiet_hours_enabled=True)
    result = evaluate.evaluate_user_notifications('user', NOW.date(), prefs)
    assert result['skipped'] == 1 and not rows
    monkeypatch.setattr(evaluate, 'utc_now', lambda: NOW + timedelta(days=1))
    result = evaluate.evaluate_user_notifications('user', NOW.date(), prefs)
    assert result['queued'] == 1 and rows[0]['status'] == 'queued'


def test_queue_prompt_has_stable_dedupe_and_never_changes_delivered_at(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluate.pg, 'fetchrow', lambda sql, *params: calls.append((sql, params)) or {'id': 'event'})
    for now in [NOW, NOW + timedelta(days=1)]:
        evaluate._queue_candidate(user_id='user', candidate=prompt_candidate(), now_utc=now, status='queued')
    assert len(calls) == 2
    assert all('update raw.user_feedback_prompts' not in sql for sql, _ in calls)
    assert calls[0][1][7] == calls[1][1][7] == 'user:symptom_followups:prompt:prompt'


@pytest.mark.parametrize('changes,reason', [
    ({'enabled': False}, 'notifications_disabled'),
    ({'local_condition_alerts_enabled': False}, 'category_disabled'),
    ({'families': {'pressure': False}}, 'category_disabled'),
    ({'sensitivity': 'minimal'}, 'category_disabled'),
    ({'quiet_hours_enabled': True, 'quiet_start': '11:00', 'quiet_end': '13:00'}, 'quiet_hours'),
    ({'quiet_hours_enabled': True, 'quiet_start': '22:00', 'quiet_end': '08:00', 'time_zone': 'America/Chicago'}, 'quiet_hours'),
])
def test_sender_rechecks_preferences_and_quiet_hours(changes, reason):
    assert sender._event_policy(event(), preferences(**changes), NOW) == reason


def test_digest_is_dropped_when_any_contained_family_is_no_longer_allowed():
    digest = event(family='digest', severity='high', payload={'child_events': [
        {'family': 'pressure', 'severity': 'high'}, {'family': 'aqi', 'severity': 'watch'}]})
    assert sender._event_policy(digest, preferences(), NOW) is None
    assert sender._event_policy(digest, preferences(families={'aqi': False}), NOW) == 'category_disabled'
    assert sender._event_policy(digest, preferences(sensitivity='minimal'), NOW) == 'category_disabled'


@pytest.mark.parametrize('family,age,expected', [
    ('pressure', timedelta(hours=2), 'expired'),
    ('pressure', timedelta(minutes=59), None),
    ('symptom_followups', timedelta(hours=25), None),
    ('symptom_followups', timedelta(hours=23), None),
])
def test_backlog_expiry(family, age, expected):
    assert sender._event_policy(event(family=family, created_at=NOW-age), preferences(), NOW) == expected


@pytest.mark.parametrize('row', [
    None,
    {'status': 'answered'},
    {'status': 'pending', 'push_delivery_enabled': False, 'due_at': NOW},
    {'status': 'pending', 'push_delivery_enabled': True, 'due_at': NOW, 'delivered_at': NOW},
    {'status': 'snoozed', 'push_delivery_enabled': True, 'due_at': NOW + timedelta(hours=1)},
    {'status': 'pending', 'push_delivery_enabled': True, 'due_at': NOW - timedelta(days=2)},
])
def test_sender_drops_no_longer_current_prompt(monkeypatch, row):
    monkeypatch.setattr(sender.pg, 'fetchrow', lambda *args: row)
    assert sender._prompt_policy(event(family='symptom_followups', payload={'prompt_id': 'prompt'}), NOW)


def test_retry_delay_respects_provider_minimum_and_retry_after():
    assert sender._retry_delay({'status_code': 503}, NOW) == 900
    assert sender._retry_delay({'status_code': 429, 'retry_after': '3600'}, NOW) == 3600
    assert sender._retry_delay({'status_code': 503, 'retry_after': 'Fri, 16 Oct 2026 13:00:00 GMT'}, NOW) == 3600


@pytest.mark.parametrize('status', [0, 400, 403, 410])
def test_no_retry_for_ambiguous_or_permanent_failure(status):
    calls = []
    assert not sender._send_once(lambda: calls.append(1) or {'ok': False, 'status_code': status})['ok']
    assert len(calls) == 1


def test_no_retry_on_transport_exception():
    def send():
        raise TimeoutError('provider might have accepted')
    assert sender._send_once(send)['status_code'] == 0


def test_claim_must_succeed_before_preferences_or_provider(monkeypatch):
    monkeypatch.setattr(sender, '_fetch_queued_events', lambda **kwargs: [event()])
    monkeypatch.setattr(sender, '_claim_event', lambda *args: False)
    monkeypatch.setattr(sender, '_fetch_preferences', lambda *args: pytest.fail('must not send unclaimed event'))
    monkeypatch.setattr(sys, 'argv', ['sender'])
    sender.main()


def test_acceptance_is_not_prompt_delivery(monkeypatch, caplog):
    marks = []
    monkeypatch.setattr(sender, '_fetch_queued_events', lambda **kwargs: [event()])
    monkeypatch.setattr(sender, '_claim_event', lambda *args: event())
    monkeypatch.setattr(sender, '_fetch_preferences', lambda *args: preferences())
    monkeypatch.setattr(sender, 'utc_now', lambda: NOW)
    monkeypatch.setattr(sender, '_fetch_user_tokens', lambda *args: [{'id': 'token', 'device_token': 'synthetic', 'platform': 'ios', 'environment': 'dev'}])
    monkeypatch.setattr(sender, '_missing_apns_env', lambda: [])
    monkeypatch.setattr(sender, '_required_env', lambda *args: 'synthetic')
    monkeypatch.setattr(sender, 'create_provider_token', lambda **kwargs: 'synthetic')
    monkeypatch.setattr(sender, 'send_apns_notification', lambda **kwargs: {'ok': True, 'status_code': 200})
    monkeypatch.setattr(sender, '_mark_event_status', lambda *args: marks.append(args))
    monkeypatch.setattr(sender.pg, 'execute', lambda *args: pytest.fail('no prompt-delivery write'))
    monkeypatch.setattr(sys, 'argv', ['sender'])
    with caplog.at_level('INFO'):
        sender.main()
    assert marks[0][1] == 'sent'
    assert 'provider_accepted' in caplog.text and 'device_receipt=unconfirmed' in caplog.text


@pytest.fixture
def synthetic_sender(monkeypatch):
    state = {'event': event(), 'marks': [], 'deferrals': [], 'calls': [], 'responses': []}
    monkeypatch.setattr(sender, '_fetch_queued_events', lambda **kwargs: [state['event']])
    monkeypatch.setattr(sender, '_claim_event', lambda *args: state['event'])
    monkeypatch.setattr(sender, '_fetch_preferences', lambda *args: preferences())
    monkeypatch.setattr(sender, 'utc_now', lambda: NOW)
    monkeypatch.setattr(sender, '_fetch_user_tokens', lambda *args: [
        {'id': f'token-{i}', 'device_token': 'synthetic', 'platform': 'ios', 'environment': 'dev'}
        for i in range(len(state['responses']))])
    monkeypatch.setattr(sender, '_missing_apns_env', lambda: [])
    monkeypatch.setattr(sender, '_required_env', lambda *args: 'synthetic')
    monkeypatch.setattr(sender, 'create_provider_token', lambda **kwargs: 'synthetic')
    def send(**kwargs):
        state['calls'].append(kwargs)
        return state['responses'][len(state['calls'])-1]
    monkeypatch.setattr(sender, 'send_apns_notification', send)
    monkeypatch.setattr(sender, '_mark_event_status', lambda *args: state['marks'].append(args))
    monkeypatch.setattr(sender, '_defer_event', lambda *args, **kwargs: state['deferrals'].append((args, kwargs)))
    monkeypatch.setattr(sys, 'argv', ['sender'])
    return state


@pytest.mark.parametrize('previous,expected_delay', [(0,900), (1,1800), (2,None)])
def test_explicit_provider_rejection_has_bounded_deferred_retries(synthetic_sender, previous, expected_delay):
    state = synthetic_sender
    state['event']['payload'] = {'_push_delivery': {'attempts': previous}}
    state['responses'] = [{'ok':False, 'status_code':503}]
    with pytest.raises(SystemExit, match='1'):
        sender.main()
    assert len(state['calls']) == 1
    assert '_push_delivery' not in state['calls'][0]['body']
    if expected_delay:
        assert state['deferrals'][0][1] == {'delay':expected_delay, 'attempts':previous+1}
        assert not state['marks']
    else:
        assert not state['deferrals'] and state['marks'][0][1] == 'failed'


@pytest.mark.parametrize('other_status', [0,503])
def test_partial_acceptance_is_terminal_without_replaying_accepted_device(synthetic_sender, other_status):
    state = synthetic_sender
    state['responses'] = [{'ok':True,'status_code':200}, {'ok':False,'status_code':other_status}]
    sender.main()
    assert len(state['calls']) == 2
    assert state['marks'][0][1] == 'sent' and not state['deferrals']


def test_ambiguous_outcome_is_not_requeued(synthetic_sender):
    state = synthetic_sender
    state['responses'] = [{'ok':False,'status_code':0}]
    with pytest.raises(SystemExit, match='1'):
        sender.main()
    assert state['marks'][0][1:] == ('failed', NOW, 'delivery_unconfirmed')
    assert not state['deferrals']


def test_snoozed_prompt_waits_then_sends_once_due(synthetic_sender, monkeypatch):
    state = synthetic_sender
    state['event'] = event(family='symptom_followups', created_at=NOW-timedelta(days=2), payload={'prompt_id':'prompt'})
    due = NOW + timedelta(hours=1)
    monkeypatch.setattr(sender.pg, 'fetchrow', lambda *args: {
        'status':'snoozed', 'push_delivery_enabled':True, 'delivered_at':NOW-timedelta(hours=1), 'due_at':due})
    state['responses'] = [{'ok':True,'status_code':200}]
    sender.main()
    assert not state['calls'] and not state['marks']
    assert state['deferrals'][0][0][2] == 'prompt_not_due'
    monkeypatch.setattr(sender, 'utc_now', lambda: due)
    sender.main()
    assert len(state['calls']) == 1 and state['marks'][0][1] == 'sent'


def test_fcm_reason_never_logs_raw_provider_message():
    assert sender._fcm_reason({'status_code':400, 'body':{'error':{'message':'private payload'}}}) == 'http_400'


def test_explicit_snooze_remains_fresh_despite_previous_presentation():
    row = {'status':'snoozed', 'scheduled_for':NOW-timedelta(days=2),
           'delivered_at':NOW-timedelta(hours=2), 'snoozed_until':NOW-timedelta(minutes=1)}
    assert evaluate._symptom_followup_push_candidate_is_fresh(row, NOW)
    row['status'] = 'pending'
    assert not evaluate._symptom_followup_push_candidate_is_fresh(row, NOW)


def test_already_queued_follow_up_checks_owned_active_episode_at_send_time(monkeypatch):
    queries=[]
    def fetch(query,*params):
        queries.append((query,params)); return None
    monkeypatch.setattr(sender.pg,'fetchrow',fetch)
    assert sender._prompt_policy(event(family='symptom_followups',payload={'prompt_id':'synthetic'}),NOW)=='prompt_no_longer_current'
    sql,params=queries[0]
    assert params[0]=='synthetic'
    assert "ep.user_id = p.user_id" in sql and "activity.user_id = ep.user_id" in sql
    assert "activity_contract' = 'persistent_v1'" in sql and "ep.current_state <> 'resolved'" in sql
