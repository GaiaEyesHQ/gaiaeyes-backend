"""Actual isolated PostgreSQL + API tests. Never accepts an application DSN."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.db import earthscope_writer as queue
from app.routers import earthscope_writer as router
from app.security import earthscope_writer as security
from scripts import earthscope_draft_shadow as shadow
from services.earthscope_writer_contract import (
    DraftError, ELIGIBILITY, FACT_KEYS, WORKER_CONTRACT, job_envelope, sha256,
)

pytestmark = pytest.mark.anyio
MIGRATION = ROOT / "supabase/migrations/20260921201551_create_earthscope_writer_jobs.sql"
TOKEN = "synthetic-worker-only-token-for-offline-tests-000043"
WORKER = "gaia-test-mac"
HEADERS = {"Authorization": "Bearer " + TOKEN, "X-Gaia-Worker-Id": WORKER}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def postgres():
    binary = Path('/Users/gennwu/.codex/cache/gaia-migraine-postgres-17.11/prefix/bin')
    if not (binary / 'pg_ctl').is_file():
        pytest.skip('Owned cached PostgreSQL runtime unavailable; no external DSN fallback')
    root = Path(tempfile.mkdtemp(prefix='gaia-g043-', dir='/tmp')).resolve()
    data, sock = root / 'data', root / 'socket'
    sock.mkdir(mode=0o700)
    owner = secrets.token_hex(20)
    port = 40000 + secrets.randbelow(20000)
    marker = {'uid': os.getuid(), 'data': str(data), 'owner': owner}
    (root / 'owner.json').write_text(json.dumps(marker))
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'SUPABASE', 'DATABASE', 'DIRECT_'))}
    env.update(PGPASSFILE='/dev/null', PGSERVICEFILE='/dev/null', PGCONNECT_TIMEOUT='3')
    def run(name, *args):
        result = subprocess.run([str(binary/name), *map(str, args)], env=env,
                                capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result.stderr
        return result.stdout
    run('initdb', '-D', data, '-U', 'gaia_g043_test', '--auth=trust', '--no-locale', '--encoding=UTF8')
    with (data / 'postgresql.conf').open('a') as file:
        file.write(f"\nlisten_addresses=''\nunix_socket_directories='{sock}'\nunix_socket_permissions=0700\nport={port}\nfsync=on\nsynchronous_commit=on\n")
    run('pg_ctl', '-D', data, '-l', root/'postgres.log', '-w', '-t', '15', 'start')
    params = dict(host=str(sock), port=port, user='gaia_g043_test', dbname='gaia_g043_test',
                  connect_timeout=3, autocommit=True, options='-c statement_timeout=8000 -c lock_timeout=3000')
    try:
        run('createdb', '-h', sock, '-p', port, '-U', 'gaia_g043_test', 'gaia_g043_test')
        with psycopg.connect(**params) as conn:
            conn.execute(f"alter database gaia_g043_test set gaia.g043_owner='{owner}'")
            conn.execute("""create role anon; create role authenticated; create role service_role bypassrls;
                create schema content; create schema marts; create schema raw;
                grant usage on schema content to anon, authenticated, service_role;
                create table marts.space_weather_daily(day date primary key,updated_at timestamptz,
                    kp_max numeric,bz_min numeric,sw_speed_avg numeric,flares_count integer,cmes_count integer);
                create table content.daily_posts(title text,day date,updated_at timestamptz,
                    user_id uuid,platform text,caption text,metrics_json jsonb);
                insert into content.daily_posts(title) values ('PUBLIC CANARY');
                create table raw.user_symptoms(secret text); insert into raw.user_symptoms values ('PRIVATE CANARY');""")
            conn.execute(MIGRATION.read_text())
            conn.execute("""grant usage on schema marts to gaia_earthscope_writer_preparer;
                grant select (day,updated_at,kp_max,bz_min,sw_speed_avg,flares_count,cmes_count)
                on marts.space_weather_daily to gaia_earthscope_writer_preparer""")
            conn.execute("""alter table marts.space_weather_daily add column sw_speed_now_kms numeric,
                add column sw_speed_now numeric,add column now_ts timestamptz,add column kp_now numeric;
                create table marts.kp_obs(kp_time timestamptz,kp numeric);
                create schema ext;
                create table ext.schumann(station_id text,ts_utc timestamptz,channel text,value_num numeric);
                create table ext.space_weather(ts_utc timestamptz,kp_index numeric);
                create table ext.magnetosphere_pulse(ts timestamptz,kp_latest numeric);""")
            conn.execute((ROOT / 'supabase/migrations/20260921225050_qualify_earthscope_public_facts.sql').read_text())
        yield params, owner, root
    finally:
        assert root.stat().st_uid == os.getuid() and not root.is_symlink()
        assert json.loads((root / 'owner.json').read_text()) == marker
        run('pg_ctl', '-D', data, '-m', 'fast', '-w', '-t', '15', 'stop')
        (root / 'closed.json').write_text(json.dumps({'owned_cluster_stopped': True, 'tcp_listener': False}))


@pytest.fixture
async def database(postgres):
    params, owner, root = postgres
    @asynccontextmanager
    async def connect(role=None, autocommit=True):
        async with await psycopg.AsyncConnection.connect(**{**params, 'autocommit': autocommit}) as conn:
            row = await queue.one(conn, "select current_database() as db,inet_server_addr() as ip,current_setting('gaia.g043_owner') as owner")
            assert row == {'db': 'gaia_g043_test', 'ip': None, 'owner': owner}
            if role:
                assert role in ('gaia_earthscope_writer_backend', 'gaia_earthscope_writer_preparer', 'anon', 'authenticated', 'service_role')
                await conn.execute('set role ' + role)
            yield conn
    async with connect() as conn:
        await conn.execute('truncate content.earthscope_writer_claim_requests,content.earthscope_writer_jobs,marts.space_weather_daily')
    yield connect
    async with connect() as conn:
        assert (await queue.one(conn, 'select title from content.daily_posts'))['title'] == 'PUBLIC CANARY'
        assert (await queue.one(conn, 'select secret from raw.user_symptoms'))['secret'] == 'PRIVATE CANARY'


def facts(now, classification='synthetic_review_fixture'):
    values = dict.fromkeys(FACT_KEYS)
    values.update(kp_max_24h=2.0, bz_min=-1.25, solar_wind_kms=350.5, recent_signal_history=[])
    return {'schema_version': '1.0', 'job_id': 'earthscope-' + now.strftime('%Y%m%d'), 'sample_kind': 'quiet',
            'example_status': 'synthetic_g043' if classification.startswith('synthetic') else 'production_observed_input',
            'day': now.date().isoformat(), 'facts_as_of': (now-timedelta(seconds=1)).isoformat(),
            'geographic_scope': 'public synthetic context; café / 日本語', 'facts': values,
            'source_manifest': [{'source_id': 'synthetic-public-mart', 'source_type': 'canonical_public_mart',
                                 'source_path': 'marts.space_weather_daily', 'source_sha256': 'a'*64}],
            'recent_public_copy': []}


async def prepared(database, *, classification='synthetic_review_fixture', seconds=600, now=None):
    clock = now or datetime.now(timezone.utc)
    async with database('gaia_earthscope_writer_preparer') as conn:
        return await queue.enqueue(conn, facts(clock, classification), 1, WORKER, clock+timedelta(seconds=seconds), classification, now=clock)


async def claimed(database, **kwargs):
    row = await prepared(database, **kwargs)
    async with database('gaia_earthscope_writer_backend') as conn:
        result = await queue.claim_next(conn, WORKER, str(uuid4()), now=kwargs.get('now'))
    return result['job'], row


def outcome(job, *, status='draft_review_ready', now=None):
    candidate, bundle = {'title': 'Synthetic draft'}, {'caption': 'Synthetic café draft, not for publication.'}
    draft = {'schema_version': '1.0', 'candidate': candidate, 'bundle': bundle,
             'validation': {'status': 'passed', 'issues': [], 'validator_id': 'synthetic-validator',
                            'provenance': {'job_id': job['job_id'], 'job_version': job['job_version'],
                                           'facts_sha256': job['facts_sha256'], 'candidate_sha256': sha256(candidate),
                                           'bundle_sha256': sha256(bundle)}}}
    return {'schema_version': '1.0', 'artifact_kind': 'durable_draft_only_worker_outcome',
            'worker_contract': WORKER_CONTRACT, 'status': status, 'terminal': True,
            'recorded_at': (now or datetime.now(timezone.utc)).isoformat(),
            'job_id': job['job_id'], 'job_version': job['job_version'], 'facts_sha256': job['facts_sha256'],
            'claim_id': job['claim']['claim_id'], 'job_envelope_sha256': sha256(job),
            'input_classification': job['input_classification'],
            'current_conditions_eligible': job['input_classification'] == 'dated_production_facts',
            'writer_invoked': True, 'issues': [] if status == 'draft_review_ready' else ['synthetic failure'],
            'draft': draft if status == 'draft_review_ready' else None, 'partial_output_sha256': None,
            'failed_result_diagnostic': None, 'outcome_role': 'draft_review_only_not_editorially_accepted',
            'eligibility': dict(ELIGIBILITY)}


@pytest.fixture
def api(database, monkeypatch):
    app = FastAPI()
    app.include_router(router.router)
    class Pool:
        def connection(self, **kwargs):
            return database('gaia_earthscope_writer_backend', autocommit=False)
    async def pool():
        return Pool()
    monkeypatch.setattr(router, 'get_pool', pool)
    monkeypatch.setenv('EARTHSCOPE_DRAFT_QUEUE_ENABLED', '1')
    monkeypatch.setenv('EARTHSCOPE_DRAFT_WORKER_ID', WORKER)
    monkeypatch.setenv('EARTHSCOPE_DRAFT_WORKER_TOKEN_SHA256', hashlib.sha256(TOKEN.encode()).hexdigest())
    return app


async def post(api, path, value, headers=HEADERS):
    async with AsyncClient(transport=ASGITransport(app=api), base_url='http://synthetic.test') as client:
        return await client.post('/v1/earthscope/writer/' + path, json=value, headers=headers)


async def test_claim_request_replay_and_competing_claims_are_atomic(database, api):
    await prepared(database)
    request = {'schema_version': '1.0', 'worker_contract': WORKER_CONTRACT, 'claim_request_id': str(uuid4())}
    responses = await asyncio.gather(*(post(api, 'claim-next', request) for _ in range(8)))
    assert all(r.status_code == 200 and r.json() == responses[0].json() for r in responses)
    job = responses[0].json()['job']
    assert job['facts_sha256'] == sha256(job['facts_packet'])
    competitors = await asyncio.gather(*(post(api, 'claim-next', {**request, 'claim_request_id': str(uuid4())}) for _ in range(4)))
    assert all(r.status_code == 409 and r.json()['detail']['code'] == 'worker_busy' for r in competitors)
    async with database() as conn:
        assert (await queue.one(conn, 'select count(*) as n from content.earthscope_writer_claim_requests'))['n'] == 1


async def test_two_new_competing_requests_claim_once(database, api):
    await prepared(database)
    results = await asyncio.gather(*(post(api, 'claim-next', {'schema_version': '1.0', 'worker_contract': WORKER_CONTRACT,
                                                            'claim_request_id': str(uuid4())}) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]


async def test_idle_retry_does_not_silently_claim_a_later_job(database, api):
    request = {'schema_version': '1.0', 'worker_contract': WORKER_CONTRACT, 'claim_request_id': str(uuid4())}
    first = await post(api, 'claim-next', request)
    await prepared(database)
    repeated = await post(api, 'claim-next', request)
    assert first.json() == repeated.json() == {'status': 'idle', 'job': None}
    fresh = await post(api, 'claim-next', {**request, 'claim_request_id': str(uuid4())})
    assert fresh.json()['status'] == 'claimed'


async def test_ack_commit_lost_response_recovered_after_expiry_and_day_rollover(database, api, tmp_path):
    job, row = await claimed(database, classification='dated_production_facts')
    value = outcome(job)
    request = {'outcome': value, 'outcome_sha256': sha256(value)}
    lost = await post(api, 'return-outcome', request)  # Simulate losing this response after its transaction commits.
    assert lost.status_code == 200
    later = datetime.now(timezone.utc) + timedelta(days=1)
    async with database('gaia_earthscope_writer_backend') as conn:
        ack = await queue.return_outcome(conn, WORKER, value, sha256(value), now=later)
        with pytest.raises(DraftError, match='claim_mismatch'):
            await queue.return_outcome(conn, 'another-worker', value, sha256(value), now=later)
        conflict = {**value, 'issues': ['different']}
        with pytest.raises(DraftError, match='outcome_conflict'):
            await queue.return_outcome(conn, WORKER, conflict, sha256(conflict), now=later)
    assert ack == lost.json()
    (tmp_path/'ack-loss.json').write_text(json.dumps({'job': job, 'outcome': value, 'same_ack_after_expiry': ack}, indent=2))


async def test_never_committed_expired_return_is_durably_rejected(database):
    job, row = await claimed(database)
    value = outcome(job)
    async with database('gaia_earthscope_writer_backend') as conn:
        with pytest.raises(DraftError, match='claim_expired'):
            await queue.return_outcome(conn, WORKER, value, sha256(value), now=row['deadline_at'] + timedelta(seconds=1))
    async with database() as conn:
        stored = await queue.one(conn, 'select status,failure_code,acknowledgement_id from content.earthscope_writer_jobs')
        assert stored == {'status': 'expired', 'failure_code': 'claim_expired', 'acknowledgement_id': None}


@pytest.mark.parametrize('status', ['writer_busy', 'validation_failed', 'interrupted_local_partial'])
async def test_nonready_terminal_outcomes_are_durable_drafts(database, api, status):
    job, _ = await claimed(database)
    value = outcome(job, status=status)
    response = await post(api, 'return-outcome', {'outcome': value, 'outcome_sha256': sha256(value)})
    assert response.status_code == 200
    async with database() as conn:
        row = await queue.one(conn, 'select status,failure_code,outcome from content.earthscope_writer_jobs')
        assert row['status'] == 'failed' and row['failure_code'] == status and row['outcome'] == value


@pytest.mark.parametrize('change,code', [
    ({'facts_sha256': '0'*64}, 'facts_binding_mismatch'), ({'job_version': 2}, 'claim_mismatch'),
    ({'claim_id': str(uuid4())}, 'claim_mismatch'), ({'job_envelope_sha256': '0'*64}, 'facts_binding_mismatch'),
    ({'eligibility': {**ELIGIBILITY, 'publisher': True}}, 'invalid_outcome'),
    ({'input_classification': 'dated_production_facts'}, 'facts_binding_mismatch'),
    ({'current_conditions_eligible': True}, 'invalid_outcome'),
])
async def test_return_identity_and_eligibility_refuse_without_ack(database, api, change, code):
    job, _ = await claimed(database)
    value = {**outcome(job), **change}
    response = await post(api, 'return-outcome', {'outcome': value, 'outcome_sha256': sha256(value)})
    assert response.status_code in (400, 409) and response.json()['detail']['code'] == code
    async with database() as conn:
        assert (await queue.one(conn, 'select acknowledgement_id from content.earthscope_writer_jobs'))['acknowledgement_id'] is None


async def test_conflicting_concurrent_returns_commit_one_ack(database, api):
    job, _ = await claimed(database)
    good = outcome(job)
    other = outcome(job, status='writer_busy')
    responses = await asyncio.gather(*(post(api, 'return-outcome', {'outcome': v, 'outcome_sha256': sha256(v)}) for v in (good, other)))
    assert sorted(r.status_code for r in responses) == [200, 409]


@pytest.mark.parametrize('case', ['missing', 'invalid', 'wrong-worker', 'unconfigured', 'disabled', 'broad-token'])
async def test_worker_auth_is_narrow_and_fail_closed(database, api, monkeypatch, case):
    headers = dict(HEADERS)
    if case == 'missing': headers = {}
    if case == 'invalid': headers['Authorization'] = 'Bearer ' + 'x'*40
    if case == 'wrong-worker': headers['X-Gaia-Worker-Id'] = 'wrong-worker'
    if case == 'unconfigured': monkeypatch.delenv('EARTHSCOPE_DRAFT_WORKER_TOKEN_SHA256')
    if case == 'disabled': monkeypatch.delenv('EARTHSCOPE_DRAFT_QUEUE_ENABLED')
    if case == 'broad-token': monkeypatch.setattr(security, 'READ_TOKENS', {TOKEN})
    async def no_pool():
        raise AssertionError('Unauthenticated request must never acquire DB')
    monkeypatch.setattr(router, 'get_pool', no_pool)
    response = await post(api, 'claim-next', {}, headers)
    assert response.status_code == (503 if case in ('unconfigured', 'disabled') else 401)


async def test_hash_mismatch_and_storage_outage_are_explicit(database, api, monkeypatch):
    job, _ = await claimed(database)
    response = await post(api, 'return-outcome', {'outcome': outcome(job), 'outcome_sha256': '0'*64})
    assert response.status_code == 400 and response.json()['detail']['code'] == 'hash_mismatch'
    async def unavailable():
        raise ConnectionError('Never expose a database URI or credential')
    monkeypatch.setattr(router, 'get_pool', unavailable)
    response = await post(api, 'return-outcome', {'outcome': outcome(job), 'outcome_sha256': '0'*64})
    assert response.status_code == 503 and response.json() == {'detail': {'code': 'storage_unavailable'}}


@pytest.mark.parametrize('mutation', ['yesterday', 'future', 'wrong-day', 'synthetic-as-production'])
async def test_preparation_freshness_and_classification_fail_closed(database, mutation):
    now = datetime.now(timezone.utc)
    packet = facts(now, 'dated_production_facts')
    if mutation == 'yesterday': packet = facts(now - timedelta(days=1), 'dated_production_facts')
    if mutation == 'future': packet['facts_as_of'] = (now + timedelta(seconds=1)).isoformat()
    if mutation == 'wrong-day': packet['day'] = (now - timedelta(days=1)).date().isoformat()
    if mutation == 'synthetic-as-production': packet['example_status'] = 'synthetic_fixture'
    async with database('gaia_earthscope_writer_preparer') as conn:
        with pytest.raises(DraftError):
            await queue.enqueue(conn, packet, 1, WORKER, now + timedelta(seconds=60), 'dated_production_facts', now=now)
    async with database() as conn:
        assert (await queue.one(conn, 'select count(*) as n from content.earthscope_writer_jobs'))['n'] == 0


async def test_preparation_idempotency_version_gate_and_lease_no_reassignment(database):
    now = datetime.now(timezone.utc)
    row = await prepared(database, now=now)
    async with database('gaia_earthscope_writer_preparer') as conn:
        repeated = await queue.enqueue(conn, facts(now), 1, WORKER, now + timedelta(seconds=100), 'synthetic_review_fixture', now=now)
        assert repeated == row
        with pytest.raises(DraftError, match='job_version_conflict'):
            await queue.enqueue(conn, facts(now), 2, WORKER, now + timedelta(seconds=100), 'synthetic_review_fixture', now=now)
    async with database('gaia_earthscope_writer_backend') as conn:
        request_id = str(uuid4())
        claimed_result = await queue.claim_next(conn, WORKER, request_id, now=now)
        with pytest.raises(DraftError, match='claim_expired'):
            await queue.claim_next(conn, WORKER, request_id, now=row['deadline_at'])
        assert await queue.claim_next(conn, WORKER, str(uuid4()), now=row['deadline_at']) == {'status': 'idle', 'job': None}


async def test_production_midnight_rollover_rejects_new_return(database):
    now = datetime.now(timezone.utc).replace(hour=23, minute=59, second=50, microsecond=0)
    job, _ = await claimed(database, classification='dated_production_facts', now=now)
    value = outcome(job, now=now + timedelta(seconds=1))
    async with database('gaia_earthscope_writer_backend') as conn:
        with pytest.raises(DraftError, match='facts_stale'):
            await queue.return_outcome(conn, WORKER, value, sha256(value), now=now + timedelta(seconds=20))


@pytest.mark.parametrize('role', ['anon', 'authenticated', 'service_role'])
async def test_client_roles_have_no_queue_access(database, role):
    async with database(role) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute('select * from content.earthscope_writer_jobs')


async def test_backend_role_cannot_enqueue_or_read_private_tables(database):
    async with database('gaia_earthscope_writer_backend') as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await queue.enqueue(conn, facts(datetime.now(timezone.utc)), 1, WORKER,
                                datetime.now(timezone.utc)+timedelta(seconds=60), 'synthetic_review_fixture')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute('select * from raw.user_symptoms')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("update content.earthscope_writer_jobs set facts_sha256=repeat('a',64)")


async def test_shadow_public_facts_and_unavailable_worker_expire_durably(database, tmp_path):
    now = datetime.now(timezone.utc)
    async with database() as conn:
        await conn.execute('insert into marts.space_weather_daily values (%s,%s,2,-1,350,0,0)', (now.date(), now-timedelta(seconds=2)))
    async with database('gaia_earthscope_writer_preparer') as conn:
        receipt = await shadow.run_shadow(conn, now.date(), 1, WORKER, 1)
        assert receipt['status'] == 'expired' and receipt['failure_code'] == 'job_expired'
        assert receipt['claim_id'] is None and receipt['outcome'] is None
        assert receipt['production_consumption'] is False
        packet = (await queue.one(conn, 'select facts_packet from content.earthscope_writer_jobs'))['facts_packet']
        assert packet['facts']['kp_now'] is None and packet['facts']['schumann_value_hz'] is None
        assert packet['facts_as_of'] == (now-timedelta(seconds=2)).isoformat()
        assert 'PRIVATE CANARY' not in json.dumps(packet)
        shadow.write_receipt(tmp_path/'receipt.json', receipt)
        with pytest.raises(FileExistsError): shadow.write_receipt(tmp_path/'receipt.json', {'different': True})


async def test_shadow_is_default_off_and_does_not_connect(monkeypatch):
    monkeypatch.delenv('EARTHSCOPE_DRAFT_SHADOW_ENABLED', raising=False)
    async def forbidden(*args, **kwargs):
        raise AssertionError('Default-off producer must not connect')
    monkeypatch.setattr(shadow.psycopg.AsyncConnection, 'connect', forbidden)
    assert await shadow.configured_shadow(datetime.now(timezone.utc).date(), 1, 1) == {'status': 'disabled', 'production_consumption': False}


async def test_workflow_is_separate_manual_opt_in_only():
    import yaml
    doc = yaml.load((ROOT/'.github/workflows/earthscope_draft_shadow.yml').read_text(), Loader=yaml.BaseLoader)
    assert set(doc['on']) == {'workflow_dispatch'}
    assert doc['on']['workflow_dispatch']['inputs']['enabled']['default'] == 'false'
    job = doc['jobs']['draft_shadow']
    assert 'inputs.enabled == true' in job['if'] and job['timeout-minutes'] == '10'
    commands = ' '.join(step.get('run', '') for step in job['steps'])
    assert 'earthscope_draft_shadow.py' in commands
    assert all(name not in commands for name in ['earthscope_generate.py', 'meta_poster', 'reel_builder', 'render'])


async def test_claim_envelope_hash_is_stable_across_database_timezones(database):
    await prepared(database, classification='dated_production_facts')
    request_id = str(uuid4())
    async with database('gaia_earthscope_writer_backend') as conn:
        await conn.execute("set timezone='Pacific/Honolulu'")
        first = await queue.claim_next(conn, WORKER, request_id)
        await conn.execute("set timezone='Asia/Tokyo'")
        second = await queue.claim_next(conn, WORKER, request_id)
    assert first == second
    assert first['job']['deadline_at'].endswith('+00:00')
    assert first['job']['claim']['lease_expires_at'].endswith('+00:00')


async def test_shadow_receipt_records_acknowledged_draft_without_production_consumption(database, tmp_path):
    now = datetime.now(timezone.utc)
    async with database() as conn:
        await conn.execute('insert into marts.space_weather_daily values (%s,%s,2,-1,350,0,0)', (now.date(), now-timedelta(seconds=2)))
    async def worker():
        for _ in range(50):
            async with database('gaia_earthscope_writer_backend') as conn:
                result = await queue.claim_next(conn, WORKER, str(uuid4()))
                if result['job']:
                    value = outcome(result['job'])
                    return await queue.return_outcome(conn, WORKER, value, sha256(value))
            await asyncio.sleep(.02)
        raise AssertionError('Synthetic producer did not enqueue')
    async with database('gaia_earthscope_writer_preparer') as conn:
        receipt, ack = await asyncio.gather(shadow.run_shadow(conn, now.date(), 1, WORKER, 5), worker())
    assert receipt['status'] == 'returned' and receipt['acknowledgement_id'] == ack['acknowledgement_id']
    assert receipt['production_consumption'] is False
    shadow.write_receipt(tmp_path/'receipt.json', receipt)


async def test_corrupted_persisted_facts_hash_refuses_claim(database, api):
    await prepared(database)
    async with database() as conn:
        await conn.execute("update content.earthscope_writer_jobs set facts_sha256=repeat('0',64)")
    response = await post(api, 'claim-next', {'schema_version': '1.0', 'worker_contract': WORKER_CONTRACT,
                                           'claim_request_id': str(uuid4())})
    assert response.status_code == 409 and response.json()['detail']['code'] == 'facts_binding_mismatch'


@pytest.mark.parametrize('payload', ['{"x":NaN}', '{"schema_version":"1.0","schema_version":"2.0"}',
                                   '['*1100 + '0' + ']'*1100, 'x'*(1024*1024+1)])
async def test_invalid_or_over_bound_json_fails_before_database(api, monkeypatch, payload):
    async def no_pool():
        raise AssertionError('Invalid input reached DB')
    monkeypatch.setattr(router, 'get_pool', no_pool)
    async with AsyncClient(transport=ASGITransport(app=api), base_url='http://synthetic.test') as client:
        response = await client.post('/v1/earthscope/writer/claim-next', content=payload, headers=HEADERS)
    assert response.status_code == 400 and response.json()['detail']['code'] == 'invalid_request'
