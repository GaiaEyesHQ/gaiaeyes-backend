"""Real atomic claims and prompt dedupe, confined to a disposable loopback DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os

import pytest

from tests.integration.test_refresh_postgres import postgres_dsn, pg_client  # noqa: F401

pytestmark = pytest.mark.skipif(not os.getenv('GAIA_TEST_POSTGRES_DSN'), reason='disposable local Postgres required')


@pytest.fixture
def queue(pg_client):
    pg_client.execute('create schema content')
    pg_client.execute('''create table content.push_notification_events (
        id uuid primary key default gen_random_uuid(), user_id text, family text, event_key text,
        severity text, title text, body text, payload jsonb, dedupe_key text unique,
        status text check(status in ('queued','sent','skipped','failed')), created_at timestamptz,
        sent_at timestamptz, error_text text)''')
    yield pg_client
    pg_client.execute('drop schema content cascade')


def test_concurrent_claims_one_winner_and_crash_cannot_replay(queue, monkeypatch):
    from bots.notifications import send_push_notifications as sender
    monkeypatch.setattr(sender, 'pg', queue)
    row = queue.fetchrow("insert into content.push_notification_events (status) values ('queued') returning id")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: sender._claim_event(str(row['id'])), range(8)))
    assert sum(bool(row) for row in results) == 1
    assert not sender._claim_event(str(row['id']))
    stored = queue.fetchrow('select status,error_text,sent_at from content.push_notification_events where id=%s',row['id'])
    assert stored == {'status':'failed','error_text':'delivery_unconfirmed','sent_at':None}


def test_quiet_defer_then_claim_and_accept(queue, monkeypatch):
    from bots.notifications import send_push_notifications as sender
    monkeypatch.setattr(sender, 'pg', queue)
    row = queue.fetchrow("insert into content.push_notification_events (status) values ('queued') returning id")
    eid = str(row['id']); now = datetime.now(timezone.utc)
    assert sender._claim_event(eid)
    sender._defer_event({'id': eid}, now, 'quiet_hours')
    monkeypatch.setattr(sender, 'utc_now', lambda: now)
    assert not sender._fetch_queued_events(limit=100)
    monkeypatch.setattr(sender, 'utc_now', lambda: now + timedelta(minutes=5))
    assert str(sender._fetch_queued_events(limit=100)[0]['id']) == eid
    assert sender._claim_event(eid)
    sender._mark_event_status(eid, 'sent', now)
    assert not sender._claim_event(eid)
    assert queue.fetchrow('select status,sent_at from content.push_notification_events where id=%s',eid) == {'status':'sent','sent_at':now}


def test_prompt_dedupe_survives_day_boundary_and_does_not_write_delivery(queue, monkeypatch):
    from bots.notifications import evaluate_push_notifications as evaluator
    from bots.notifications.push_logic import NotificationCandidate
    monkeypatch.setattr(evaluator, 'pg', queue)
    c = NotificationCandidate('symptom_followups','followup','watch','Synthetic','Synthetic','current_symptoms','synthetic',payload={'prompt_id':'synthetic'})
    now = datetime.now(timezone.utc)
    assert evaluator._queue_candidate(user_id='synthetic',candidate=c,now_utc=now,status='queued')
    assert not evaluator._queue_candidate(user_id='synthetic',candidate=c,now_utc=now+timedelta(days=1),status='queued')
    # No raw.user_feedback_prompts table exists: any delivery write would fail.
    assert queue.fetchrow('select count(*) as n from content.push_notification_events')['n'] == 1


def test_deferred_batch_does_not_starve_eligible_row_101(queue, monkeypatch):
    from bots.notifications import send_push_notifications as sender
    monkeypatch.setattr(sender, 'pg', queue)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(sender, 'utc_now', lambda: now)
    for i in range(101):
        queue.execute("insert into content.push_notification_events (status,created_at,event_key) values ('queued',%s,%s)",
                      now + timedelta(seconds=i-101), str(i))
    first = sender._fetch_queued_events(limit=100)
    assert len(first) == 100 and all(row['event_key'] != '100' for row in first)
    for row in first:
        assert sender._claim_event(row['id'])
        sender._defer_event(row, now, 'quiet_hours')
    monkeypatch.setattr(sender, 'utc_now', lambda: now + timedelta(minutes=5))
    assert sender._fetch_queued_events(limit=100)[0]['event_key'] == '100'


def test_unknown_attempt_still_consumes_cooldown_across_bucket_boundary(queue, monkeypatch):
    from bots.notifications import evaluate_push_notifications as evaluator
    from bots.notifications.push_logic import NotificationCandidate
    monkeypatch.setattr(evaluator, 'pg', queue)
    now = datetime.now(timezone.utc).replace(hour=12, minute=1, second=0, microsecond=0)
    queue.execute("""insert into content.push_notification_events
        (user_id,family,event_key,severity,created_at,status,error_text)
        values ('synthetic','pressure','pressure_drop','watch',%s,'failed','delivery_unconfirmed')""",
        now - timedelta(minutes=2))
    monkeypatch.setattr(evaluator, 'utc_now', lambda: now)
    candidate = NotificationCandidate('pressure','pressure_drop','watch','Synthetic','Synthetic','local','synthetic')
    monkeypatch.setattr(evaluator, '_build_candidates_for_user', lambda *args: [candidate])
    result = evaluator.evaluate_user_notifications('synthetic', now.date(), evaluator.normalize_preferences({'enabled':True}))
    assert result['queued'] == 0
    assert queue.fetchrow('select count(*) as n from content.push_notification_events')['n'] == 1


def test_stale_queue_snapshot_cannot_bypass_retry_delay_or_reset_attempts(queue, monkeypatch):
    from bots.notifications import send_push_notifications as sender
    monkeypatch.setattr(sender, 'pg', queue)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(sender, 'utc_now', lambda: now)
    queue.execute("insert into content.push_notification_events (status,created_at) values ('queued',%s)", now)
    stale = sender._fetch_queued_events(limit=100)[0]
    assert sender._claim_event(stale['id'])
    sender._defer_event(stale, now, 'provider_retry', delay=900, attempts=1)
    # Another worker fetched before the first claim, but cannot send immediately.
    assert sender._claim_event(stale['id']) is None
    monkeypatch.setattr(sender, 'utc_now', lambda: now + timedelta(minutes=15))
    current = sender._claim_event(stale['id'])
    assert current['payload']['_push_delivery']['attempts'] == 1


def test_prompt_selection_allows_due_snooze_and_excludes_existing_attempt(queue, monkeypatch):
    from bots.notifications import evaluate_push_notifications as evaluator
    from bots.notifications.push_logic import NotificationCandidate
    monkeypatch.setattr(evaluator, 'pg', queue)
    queue.execute('create schema raw')
    queue.execute('''create table raw.user_feedback_prompts (
        id uuid primary key default gen_random_uuid(), user_id text, prompt_type text,
        episode_id uuid, symptom_code text, prompt_day date, question_text text,
        prompt_payload jsonb, status text, scheduled_for timestamptz,
        snoozed_until timestamptz, delivered_at timestamptz, push_delivery_enabled bool,
        created_at timestamptz default now())''')
    try:
        queue.execute('''create table raw.user_symptom_episodes (
            id uuid primary key default gen_random_uuid(), user_id text,
            symptom_code text, current_state text)''')
        queue.execute('''create table raw.user_symptom_episode_updates (
            episode_id uuid, user_id text, metadata jsonb)''')
        episode = queue.fetchrow("""insert into raw.user_symptom_episodes
            (user_id,symptom_code,current_state)
            values ('synthetic','MIGRAINE','ongoing') returning id""")
        row = queue.fetchrow("""insert into raw.user_feedback_prompts
            (user_id,episode_id,prompt_type,status,scheduled_for,snoozed_until,delivered_at,push_delivery_enabled)
            values ('synthetic',%s,'symptom_follow_up','snoozed',now()-interval '2 days',
                    now()-interval '1 minute',now()-interval '2 hours',true) returning id""", episode['id'])
        assert not evaluator._feedback_prompt_rows('synthetic','symptom_follow_up')
        queue.execute("""insert into raw.user_symptom_episode_updates
            (episode_id,user_id,metadata)
            values (%s,'different-owner','{"activity_contract":"persistent_v1"}')""", episode['id'])
        assert not evaluator._feedback_prompt_rows('synthetic','symptom_follow_up')
        queue.execute("""insert into raw.user_symptom_episode_updates
            (episode_id,user_id,metadata)
            values (%s,'synthetic','{"activity_contract":"persistent_v1"}')""", episode['id'])
        assert len(evaluator._feedback_prompt_rows('synthetic','symptom_follow_up')) == 1
        candidate = NotificationCandidate('symptom_followups','followup','watch','Synthetic','Synthetic',
                                          'current_symptoms','synthetic',payload={'prompt_id':str(row['id'])})
        assert evaluator._queue_candidate(user_id='synthetic',candidate=candidate,
                                         now_utc=datetime.now(timezone.utc),status='queued')
        assert not evaluator._feedback_prompt_rows('synthetic','symptom_follow_up')
    finally:
        queue.execute('drop schema raw cascade')
