"""Real isolated database failures through consumer CLI; never production DSNs."""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock
import psycopg
from scripts import earthscope_local_primary as runner

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('owned_queue_fixture', ROOT/'tests/api/test_earthscope_writer.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
postgres = base.postgres

def configure(monkeypatch, tmp_path, postgres):
    params, owner, _ = postgres
    with psycopg.connect(**params) as conn:
        assert conn.execute("select current_setting('gaia.g043_owner'),inet_server_addr()").fetchone() == (owner, None)
        conn.execute('truncate content.earthscope_writer_claim_requests,content.earthscope_writer_jobs')
    monkeypatch.setenv('EARTHSCOPE_DRAFT_PREPARER_DSN', 'synthetic-not-used')
    monkeypatch.setenv('EARTHSCOPE_DRAFT_WORKER_ID', base.WORKER)
    monkeypatch.setenv('GAIA_TIMEZONE', 'UTC')
    monkeypatch.setattr(runner, 'connection_options', lambda env: {**params, 'autocommit': False})
    monkeypatch.setattr(runner, 'activation', lambda env: {'acceptance_id': 'isolated-test', 'validator_id': 'isolated-test', 'caption_profile': 'isolated-test'})
    monkeypatch.setattr(runner, 'review_rejection', lambda *a, **k: None)
    monkeypatch.setattr(sys, 'argv', ['consumer', '--day', datetime.now(timezone.utc).date().isoformat(), '--wait-seconds', '1',
        '--receipt', str(tmp_path/'receipt.json'), '--post-output', str(tmp_path/'post.json'), '--daily-output', str(tmp_path/'daily.json')])
    publisher = Mock(side_effect=AssertionError('Publication must not occur'))
    monkeypatch.setattr(runner, 'publish_once', publisher)
    return params, publisher

def assert_failed(tmp_path, publisher, status, params):
    assert json.loads((tmp_path/'receipt.json').read_text())['status'] == status
    assert not (tmp_path/'post.json').exists() and not (tmp_path/'daily.json').exists()
    publisher.assert_not_called()
    with psycopg.connect(**params) as conn:
        assert conn.execute('select title from content.daily_posts').fetchall() == [('PUBLIC CANARY',)]

def test_missing_worker_times_out_without_publication(monkeypatch, tmp_path, postgres):
    params, publisher = configure(monkeypatch, tmp_path, postgres)
    async def seed():
        now = datetime.now(timezone.utc)
        async with await psycopg.AsyncConnection.connect(**params) as conn:
            await conn.execute('set role gaia_earthscope_writer_preparer')
            await runner.queue.enqueue(conn, base.facts(now, 'dated_production_facts'), 1, base.WORKER,
                                       now+timedelta(seconds=60), 'dated_production_facts')
    asyncio.run(seed())
    assert runner.main() == 1
    assert_failed(tmp_path, publisher, 'local_writer_wait_timeout', params)

def test_database_disconnect_fails_closed(monkeypatch, tmp_path, postgres):
    params, publisher = configure(monkeypatch, tmp_path, postgres)
    real_connect = psycopg.AsyncConnection.connect
    async def disconnected(**kwargs):
        conn = await real_connect(**kwargs)
        with psycopg.connect(**params) as admin:
            assert admin.execute('select pg_terminate_backend(%s)', (conn.info.backend_pid,)).fetchone() == (True,)
        return conn
    monkeypatch.setattr(runner.psycopg.AsyncConnection, 'connect', disconnected)
    assert runner.main() == 1
    assert_failed(tmp_path, publisher, 'local_primary_unavailable', params)
