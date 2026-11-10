from pathlib import Path
from scripts import test_migraine_refresh_postgres as harness


def test_child_environment_excludes_inherited_credentials(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://secret@example.invalid/prod")
    monkeypatch.setenv("PGHOST", "example.invalid")
    monkeypatch.setenv("DEV_BEARER", "synthetic-secret")
    env = harness.child_environment(Path("/tmp/owned"), [])
    assert not {"SUPABASE_DB_URL", "PGHOST", "DEV_BEARER"} & env.keys()
    assert "127.0.0.1:1/unused" in env["DATABASE_URL"]
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_server_is_socket_only_and_private():
    options = harness.server_options(Path("/tmp/owned/socket"))
    assert "listen_addresses=''" in options
    assert "unix_socket_directories='/tmp/owned/socket'" in options
    assert "unix_socket_permissions=0700" in options


def test_targets_include_real_queue_fence_and_http_cases():
    assert "tests/db/test_migraine_refresh_queue_postgres.py" in harness.TARGETS
    assert "tests/db/test_migraine_refresh_publication_postgres.py" in harness.TARGETS
    assert "tests/api/test_migraine_times.py" in harness.TARGETS


def test_nonzero_pytest_result_propagates_and_owned_cluster_is_removed(monkeypatch, tmp_path):
    import subprocess
    home = tmp_path / 'owned'
    home.mkdir()
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    for name in ('initdb', 'pg_ctl', 'createdb', 'psql'):
        (binaries / name).touch()
    monkeypatch.setattr(harness.tempfile, 'mkdtemp', lambda **kw: str(home))
    commands = []
    def fake(args, **kw):
        commands.append(args)
        if Path(args[0]).name == 'initdb':
            (home / 'data').mkdir()
            (home / 'data/postgresql.conf').touch()
        if args[-1] == 'start':
            (home / 'data/postmaster.pid').write_text('owned test fake')
        if args[-1] == 'stop':
            (home / 'data/postmaster.pid').unlink()
        return subprocess.CompletedProcess(args, 7 if 'pytest' in args else 0)
    monkeypatch.setattr(harness.subprocess, 'run', fake)
    assert harness.run(binaries, []) == 7
    assert commands[-1][-1] == 'stop'
    assert not home.exists()


def test_failed_stop_retains_owned_directory_and_fails(monkeypatch, tmp_path):
    import subprocess
    import pytest
    home = tmp_path / 'owned'
    home.mkdir()
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    for name in ('initdb', 'pg_ctl', 'createdb', 'psql'):
        (binaries / name).touch()
    monkeypatch.setattr(harness.tempfile, 'mkdtemp', lambda **kw: str(home))
    def fake(args, **kw):
        if Path(args[0]).name == 'initdb':
            (home / 'data').mkdir()
            (home / 'data/postgresql.conf').touch()
        if args[-1] == 'start':
            (home / 'data/postmaster.pid').write_text('owned test fake')
        if args[-1] == 'stop':
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(harness.subprocess, 'run', fake)
    with pytest.raises(subprocess.CalledProcessError):
        harness.run(binaries, [])
    assert (home / 'data/postmaster.pid').exists()



def test_linux_loader_path_is_derived_not_inherited(monkeypatch):
    monkeypatch.setenv('LD_LIBRARY_PATH', '/untrusted/inherited')
    monkeypatch.setattr(harness.sys, 'platform', 'linux')
    monkeypatch.setattr(harness.sysconfig, 'get_config_var', lambda key: '/trusted/python/lib')
    env = harness.child_environment(Path('/tmp/owned'), [])
    assert env['LD_LIBRARY_PATH'] == '/trusted/python/lib'
    assert '/untrusted' not in str(env)


def test_dotenv_checkout_rejected_before_database_creation(monkeypatch, tmp_path):
    import pytest
    (tmp_path / '.env').touch()
    monkeypatch.setattr(harness, 'ROOT', tmp_path)
    monkeypatch.setattr(harness.tempfile, 'mkdtemp', lambda **kw: pytest.fail('must reject before creating cluster'))
    with pytest.raises(RuntimeError, match='checkout with .env'):
        harness.run(tmp_path / 'bin', [])



def test_ancestor_dotenv_rejected_without_reading_contents(monkeypatch, tmp_path):
    import pytest
    checkout = tmp_path / 'parent/checkout'
    checkout.mkdir(parents=True)
    (tmp_path / '.env').touch()
    monkeypatch.setattr(harness, 'ROOT', checkout)
    monkeypatch.setattr(harness.tempfile, 'mkdtemp', lambda **kw: pytest.fail('must reject before creating cluster'))
    with pytest.raises(RuntimeError, match='ancestor chain'):
        harness.run(tmp_path / 'bin', [])
