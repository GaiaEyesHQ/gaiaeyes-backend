#!/usr/bin/env python3
"""Run synthetic persistence tests in an owned, temporary, socket-only database.
Pass an existing PostgreSQL bin directory; no download or shared cluster reset.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
binaries = Path(sys.argv[1]).resolve()
assert all((binaries / name).is_file() for name in ('initdb', 'pg_ctl', 'psql', 'createdb'))
env = {'PATH':'/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE':'1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
       'DATABASE_URL':'postgresql://synthetic:synthetic@127.0.0.1:1/synthetic', 'PYTHONPATH':str(root)}
with tempfile.TemporaryDirectory(prefix='gaia-migraine-active-', dir='/tmp') as directory:
    private = Path(directory); data = private/'data'; socket = private/'socket'; socket.mkdir(mode=0o700)
    def run(name, *args):
        subprocess.run([str(binaries/name), *map(str,args)], cwd=root, env=env, check=True)
    run('initdb','-D',data,'--auth-local=trust','--auth-host=reject','--username=synthetic','--no-locale','--encoding=UTF8')
    started = False
    try:
        run('pg_ctl','-D',data,'-l',private/'server.log','-o',f"-c listen_addresses='' -c unix_socket_directories='{socket}' -c unix_socket_permissions=0700 -c port=55447",'start')
        started = True
        args = ('-h',socket,'-p','55447','-U','synthetic')
        run('createdb',*args,'gaia_migraine_test')
        sqlargs = ('-X','-v','ON_ERROR_STOP=1',*args,'-d','gaia_migraine_test')
        run('psql',*sqlargs,'-c',"alter database gaia_migraine_test set gaia.migraine_disposable='true'")
        run('psql',*sqlargs,'-f','tests/db/fixtures/migraine_postgres_prerequisites.sql')
        run('psql',*sqlargs,'-c',"insert into dim.symptom_codes(symptom_code,label) values ('headache','Headache')")
        env['GAIA_MIGRAINE_ACTIVE_TEST_DATABASE_URL']=f'postgresql://synthetic@/gaia_migraine_test?host={socket}&port=55447'
        result = subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','anyio.pytest_plugin','-p','no:cacheprovider','tests/db/test_migraine_active.py'],cwd=root,env=env)
    finally:
        if started: run('pg_ctl','-D',data,'-m','fast','stop')
    sys.exit(result.returncode)
