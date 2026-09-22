"""G046 relevant hosted-catalog reproduction, solely synthetic owned PostgreSQL."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from datetime import date, datetime, timezone

import psycopg
import pytest

from services.earthscope_public_facts import collect_public_inputs, prepare_public_packet
from services.earthscope_writer_contract import validate_facts, sha256

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT/'supabase/migrations/20260921201551_create_earthscope_writer_jobs.sql'
MIGRATION = ROOT/'supabase/migrations/20260921225050_qualify_earthscope_public_facts.sql'
FIXTURE = ROOT/'tests/fixtures/earthscope_hosted_catalog.sql'
FROZEN = ROOT/'tests/fixtures/earthscope_g044_before.sql'
DAY = date(2026, 9, 21)
NOW = datetime(2026, 9, 21, 1, tzinfo=timezone.utc)
PREPARER = 'gaia_earthscope_writer_preparer'
PACKET = Path(os.environ.get('G046_EVIDENCE_DIR', '/tmp/gaia-g046-evidence'))

def record(name, value):
    PACKET.mkdir(parents=True, exist_ok=True)
    (PACKET/(name+'.json')).write_text(json.dumps(value,indent=2,default=str)+'\n')

@pytest.fixture
def anyio_backend(): return 'asyncio'

@pytest.fixture(scope='module')
def cluster():
    binary=Path('/Users/gennwu/.codex/cache/gaia-migraine-postgres-17.11/prefix/bin')
    if not (binary/'pg_ctl').is_file(): pytest.skip('Owned PostgreSQL unavailable; no external fallback')
    root=Path(tempfile.mkdtemp(prefix='gaia-g046-',dir='/tmp')).resolve()
    data,sock=root/'data',root/'socket';sock.mkdir(mode=0o700)
    token=secrets.token_hex(20);port=40000+secrets.randbelow(20000)
    marker={'uid':os.getuid(),'data':str(data),'owner':token}
    (root/'owner.json').write_text(json.dumps(marker))
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','SUPABASE','DATABASE','DIRECT_'))}
    env.update(PGPASSFILE='/dev/null',PGSERVICEFILE='/dev/null',PGCONNECT_TIMEOUT='3')
    def run(name,*args):
        r=subprocess.run([str(binary/name),*map(str,args)],env=env,capture_output=True,text=True,timeout=25)
        assert r.returncode==0,r.stderr
        return r.stdout
    run('initdb','-D',data,'-U','gaia_g046_admin','--auth=trust','--no-locale','--encoding=UTF8')
    with (data/'postgresql.conf').open('a') as f:
        f.write(f"\nlisten_addresses=''\nunix_socket_directories='{sock}'\nunix_socket_permissions=0700\nport={port}\nfsync=on\nsynchronous_commit=on\n")
    run('pg_ctl','-D',data,'-l',root/'postgres.log','-w','-t','15','start')
    params=dict(host=str(sock),port=port,user='gaia_g046_admin',dbname='postgres',autocommit=True,
                connect_timeout=3,options='-c statement_timeout=8000 -c lock_timeout=3000')
    try:
        with psycopg.connect(**params) as c:
            c.execute('create role postgres login nosuperuser bypassrls createrole createdb')
            c.execute('create role anon;create role authenticated;create role service_role bypassrls')
            c.execute('grant anon,authenticated,service_role to postgres with inherit false,set true')
        record('cluster',{'path':str(root),'postgres_version':run('postgres','--version'),'tcp_listener':False})
        yield params,root
    finally:
        assert root.stat().st_uid==os.getuid() and not root.is_symlink()
        assert json.loads((root/'owner.json').read_text())==marker
        run('pg_ctl','-D',data,'-m','fast','-w','-t','15','stop')
        closed={'owned_cluster_stopped':True,'tcp_listener':False,'path':str(root)}
        (root/'closed.json').write_text(json.dumps(closed));record('cluster-closed',closed)

@pytest.fixture
def database(cluster):
    params,root=cluster;name='fixture_'+secrets.token_hex(6)
    with psycopg.connect(**params) as admin:
        admin.execute('create database '+name+' owner postgres')
    params={**params,'user':'postgres','dbname':name}
    with psycopg.connect(**params) as c:
        assert c.execute('select rolsuper,rolbypassrls,rolcreaterole,rolcreatedb from pg_roles where rolname=current_user').fetchone()==(False,True,True,True)
        c.execute(FIXTURE.read_text())
        # Roles persist at cluster scope; role memberships never authorize reads.
        c.execute(QUEUE.read_text())
        # Synthetic reviewed-login provisioning is separate from migrations.
        # CREATEROLE admin membership alone does not grant SET ROLE in PG17.
        c.execute('grant gaia_earthscope_writer_preparer,gaia_earthscope_writer_backend to postgres with inherit false,set true')
        c.execute('grant usage on schema marts to '+PREPARER)
        c.execute('grant select(day,updated_at,kp_max,bz_min,sw_speed_avg,flares_count,cmes_count) on marts.space_weather_daily to '+PREPARER)
    return params

def snapshot(c):
    return {
        'view':c.execute("select pg_get_viewdef('marts.schumann_daily'::regclass,true)").fetchone()[0],
        'columns':c.execute("select attname,atttypid from pg_attribute where attrelid='marts.schumann_daily'::regclass and attnum>0 order by attnum").fetchall(),
        'policies':c.execute("select schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check from pg_policies where tablename in ('kp_obs','magnetosphere_pulse','daily_posts') and policyname not like 'earthscope_writer_preparer_%' order by schemaname,tablename,policyname").fetchall(),
        'defaults':c.execute('select defaclnamespace::regnamespace::text,defaclobjtype,defaclacl::text from pg_default_acl order by 1,2').fetchall(),
        'rls':c.execute("select oid::regclass::text,relrowsecurity,relforcerowsecurity from pg_class where oid in ('marts.kp_obs'::regclass,'ext.magnetosphere_pulse'::regclass,'content.daily_posts'::regclass) order by 1").fetchall(),
        'view_rows':c.execute('select * from marts.schumann_daily order by station_id,day').fetchall(),
    }

def grants(c):
    return c.execute("""select c.oid::regclass::text,c.relacl::text,
        array(select a.attname||':'||a.attacl::text from pg_attribute a where a.attrelid=c.oid and a.attacl is not null order by a.attname)
        from pg_class c where c.oid in ('marts.kp_obs'::regclass,'ext.schumann'::regclass,
        'ext.magnetosphere_pulse'::regclass,'marts.space_weather_daily'::regclass,
        'ext.space_weather'::regclass,'content.earthscope_writer_public_history'::regclass) order by 1""").fetchall()

def test_reproduce_both_g044_failures(database):
    with psycopg.connect(**database) as c:
        with pytest.raises(psycopg.errors.UndefinedColumn) as exc: c.execute(FROZEN.read_text())
        c.execute('rollback')
        assert c.execute("select to_regclass('content.earthscope_writer_public_history')").fetchone()[0] is None
        # Isolate B2 using only the exact column grants; G044's failed transaction
        # correctly leaves neither these grants nor its view installed.
        c.execute('grant usage on schema ext to '+PREPARER)
        c.execute('grant select(kp_time,kp) on marts.kp_obs to '+PREPARER)
        c.execute('grant select(ts,kp_latest) on ext.magnetosphere_pulse to '+PREPARER)
        c.execute('set role '+PREPARER)
        assert c.execute("select has_column_privilege(current_user,'marts.kp_obs','kp','SELECT')").fetchone()[0]
        assert c.execute('select kp_time,kp from marts.kp_obs').fetchall()==[]
        assert c.execute('select ts,kp_latest from ext.magnetosphere_pulse').fetchall()==[]
        c.execute('reset role')
        record('baseline-failures',{'G044_sqlstate':exc.value.sqlstate,'error':str(exc.value),'migration_rolled_back':True,'column_granted_but_kp_and_pulse_empty':True,'migration_owner':'postgres NOSUPERUSER BYPASSRLS CREATEROLE CREATEDB'})

@pytest.mark.anyio
async def test_corrected_sequence_visible_inputs_and_existing_consumers(database):
    with psycopg.connect(**database) as c:
        c.execute("set time zone 'Pacific/Honolulu'")
        before=snapshot(c);c.execute(MIGRATION.read_text());assert snapshot(c)==before
        policies=c.execute("select schemaname,tablename,policyname,roles,cmd,qual from pg_policies where policyname in ('earthscope_writer_preparer_kp','earthscope_writer_preparer_pulse') order by tablename").fetchall()
        assert len(policies)==2 and all(x[3]==[PREPARER] and x[4]=='SELECT' and x[5]=='true' for x in policies)
        assert c.execute('select rolsuper,rolbypassrls,rolcanlogin from pg_roles where rolname=%s',(PREPARER,)).fetchone()==(False,False,False)
    packets=[]
    for zone in ('UTC','Pacific/Honolulu','Asia/Tokyo'):
        async with await psycopg.AsyncConnection.connect(**database) as c:
            await c.execute("select set_config('TimeZone',%s,false)",(zone,));await c.execute('set role '+PREPARER)
            values=await collect_public_inputs(c,DAY)
            assert values['kp']['kp']==4 and values['pulse']['kp_latest']==3
            p,q=prepare_public_packet(DAY,now=NOW,synthetic=True,**values)
            assert p['facts']['schumann_value_hz']==8.0
            assert q['sources']['schumann']['source_path']=='ext.schumann'
            assert q['sources']['schumann']['projection'][1]['last_fundamental_ts']=='2026-09-21T00:25:00+00:00'
            assert 'PRIVATE' not in json.dumps([p,q])
            validate_facts(p,'synthetic_review_fixture',NOW)
            # Same actual projection must also satisfy unchanged dated wire shape.
            dated=dict(p,sample_kind=p['sample_kind'],example_status='production_observed_input')
            validate_facts(dated,'dated_production_facts',NOW)
            packets.append((p,q))
    assert packets[0]==packets[1]==packets[2]
    record('corrected-sequence',{'zones':['UTC','Pacific/Honolulu','Asia/Tokyo'],'unchanged_view_policy_defaults_and_rows':True,'policies':policies,'facts_packet':packets[0][0],'source_qualification':packets[0][1],'packet_sha256':sha256(packets[0][0])})

@pytest.mark.anyio
@pytest.mark.parametrize('sample_time,value,expected',[('2026-09-21T00:25Z',8,8.0),('2026-09-20T23:59Z',8,None),('2026-09-21T01:01Z',8,None),(None,8,None),('2026-09-21T00:25Z','NaN',None),('2026-09-21T00:25Z','Infinity',None),('2026-09-21T00:25Z',-1,None),('2026-09-21T00:25Z',0,0.0)])
async def test_schumann_unavailable_never_request_dated(database,sample_time,value,expected):
    with psycopg.connect(**database) as c:
        c.execute(MIGRATION.read_text());c.execute('truncate ext.schumann')
        c.execute("insert into ext.schumann values ('tomsk',%s,'fundamental_hz',%s)",(sample_time,value))
    async with await psycopg.AsyncConnection.connect(**database) as c:
        await c.execute("set time zone 'Pacific/Honolulu'");await c.execute('set role '+PREPARER)
        data=await collect_public_inputs(c,DAY)
        p,q=prepare_public_packet(DAY,now=NOW,synthetic=True,**data)
        assert p['facts']['schumann_value_hz']==expected
        if sample_time=='2026-09-21T01:01Z': assert q['sources']['schumann']['rejected'][0]['status']=='future_observation'

@pytest.mark.anyio
async def test_pulse_fallback_is_actually_visible(database):
    with psycopg.connect(**database) as c:
        c.execute(MIGRATION.read_text());c.execute('truncate marts.kp_obs')
    async with await psycopg.AsyncConnection.connect(**database) as c:
        await c.execute('set role '+PREPARER);data=await collect_public_inputs(c,DAY)
        p,q=prepare_public_packet(DAY,now=NOW,synthetic=True,**data)
        assert p['facts']['kp_now']==3 and q['fields']['kp_now']['source']=='pulse.kp_latest'

@pytest.mark.anyio
async def test_read_write_member_isolation_and_permission_restore(database):
    with psycopg.connect(**database) as c:
        before=snapshot(c);c.execute(MIGRATION.read_text());applied_grants=grants(c)
        c.execute('set role '+PREPARER)
        for sql in ['select caption from content.daily_posts','select secret from raw.user_symptoms',
                    "insert into ext.schumann values('x',now(),'fundamental_hz',8)",
                    'update marts.kp_obs set kp=9','delete from ext.magnetosphere_pulse',
                    "update content.earthscope_writer_public_history set caption='bad'",'select * from marts.schumann_daily']:
            with pytest.raises((psycopg.errors.InsufficientPrivilege,psycopg.errors.ObjectNotInPrerequisiteState)):c.execute(sql)
        c.execute('reset role')
        for role in ('anon','authenticated','service_role','gaia_earthscope_writer_backend'):
            c.execute('set role '+role)
            for obj in ('earthscope_writer_public_history','earthscope_writer_jobs','earthscope_writer_claim_requests'):
                if role=='gaia_earthscope_writer_backend' and obj!='earthscope_writer_public_history':continue
                with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('select * from content.'+obj)
            c.execute('reset role')
        # Existing actual public policies are deliberately unchanged. This task
        # does not claim to repair the earlier broad anon daily_posts policy.
        c.execute('set role anon');assert c.execute('select kp from marts.kp_obs').fetchall()==[];c.execute('reset role')
        assert snapshot(c)==before
        c.execute((ROOT/'tests/fixtures/earthscope_public_inputs_deactivate.sql').read_text())
        c.execute('set role '+PREPARER)
        for sql in ['select kp from marts.kp_obs','select kp_latest from ext.magnetosphere_pulse','select value_num from ext.schumann','select caption from content.earthscope_writer_public_history']:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute(sql)
        c.execute('reset role');assert snapshot(c)==before
        assert c.execute("select count(*) from pg_policies where policyname in ('earthscope_writer_preparer_kp','earthscope_writer_preparer_pulse')").fetchone()[0]==0
        c.execute((ROOT/'tests/fixtures/earthscope_public_inputs_restore.sql').read_text());assert grants(c)==applied_grants;assert snapshot(c)==before
        assert c.execute("select count(*) from content.daily_posts where caption like 'PRIVATE%'").fetchone()[0]==2
    async with await psycopg.AsyncConnection.connect(**database) as c:
        await c.execute('set role '+PREPARER);values=await collect_public_inputs(c,DAY)
        assert values['kp']['kp']==4 and values['pulse']['kp_latest']==3
    record('permission-recovery',{'preparer_writes_private_member_reads_denied':True,'client_queue_and_view_default_grants_revoked':True,'deactivate_denies_collection':True,'restore_exact_acl_match':True,'existing_view_policies_defaults_and_rows_preserved':True,'private_canaries_preserved':True})

def test_unverified_raw_timestamp_type_fails_closed(database):
    with psycopg.connect(**database) as c:
        # Controlled fixture mutation only: preserve the view while changing its
        # timestamp interpretation to simulate an incompatible deployment target.
        c.execute('drop view marts.schumann_daily')
        c.execute("alter table ext.schumann alter column ts_utc type timestamp using ts_utc at time zone 'UTC'")
        with pytest.raises(psycopg.errors.RaiseException,match='timestamp with time zone'):c.execute(MIGRATION.read_text())
        c.execute('rollback')
        assert c.execute("select to_regclass('content.earthscope_writer_public_history')").fetchone()[0] is None

@pytest.mark.anyio
async def test_prepared_login_membership_recipe_uses_restricted_identity(database):
    with psycopg.connect(**database) as c:
        c.execute(MIGRATION.read_text())
        c.execute('create role g046_api_login login noinherit;create role g046_preparer_login login noinherit')
    binary=Path('/Users/gennwu/.codex/cache/gaia-migraine-postgres-17.11/prefix/bin/psql')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','SUPABASE','DATABASE','DIRECT_'))}
    env.update(PGPASSFILE='/dev/null',PGSERVICEFILE='/dev/null',PGCONNECT_TIMEOUT='3')
    result=subprocess.run([str(binary),'-X','-h',database['host'],'-p',str(database['port']),'-U','postgres',
        '-d',database['dbname'],'-v','ON_ERROR_STOP=1','-v','api_login_role=g046_api_login',
        '-v','preparer_login_role=g046_preparer_login','-f',str(ROOT/'tests/fixtures/earthscope_service_grants.sql')],
        env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    async with await psycopg.AsyncConnection.connect(**{**database,'user':'g046_preparer_login'}) as c:
        assert (await (await c.execute('select rolsuper,rolbypassrls from pg_roles where rolname=current_user')).fetchone())==(False,False)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):await c.execute('select kp from marts.kp_obs')
        await c.execute('set role '+PREPARER)
        identity=await (await c.execute('select session_user,current_user')).fetchone()
        assert identity==('g046_preparer_login',PREPARER)
        values=await collect_public_inputs(c,DAY)
        assert values['kp']['kp']==4 and values['pulse']['kp_latest']==3
        with pytest.raises(psycopg.errors.InsufficientPrivilege):await c.execute('select caption from content.daily_posts')
    with psycopg.connect(**database) as c:
        membership=c.execute("select inherit_option,set_option from pg_auth_members where member='g046_preparer_login'::regrole and roleid=%s::regrole",(PREPARER,)).fetchone()
        assert membership==(False,True)
    record('restricted-login',{'session_user':identity[0],'current_user':identity[1],'login_superuser':False,'login_bypassrls':False,'inherit_option':False,'set_option':True,'collection_passed':True,'mixed_table_denied':True,'provisioning':'synthetic login only; real runtime names remain unknown'})
