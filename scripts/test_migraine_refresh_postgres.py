#!/usr/bin/env python3
"""Run correction regressions in a newly owned socket-only PostgreSQL cluster.

Requires existing PostgreSQL binaries and project/test Python dependencies.
Never reads a supplied database URL or reuses a database/server/cache directory.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "tests/api/test_migraine_times.py",
    "tests/services/test_migraine_time_correction.py",
    "tests/db/test_migraine_time_postgres.py",
    "tests/db/test_migraine_time_repairs.py",
    "tests/db/test_migraine_refresh_queue_postgres.py",
    "tests/db/test_migraine_refresh_publication_postgres.py",
    "tests/bots/test_gauge_scoring_job.py",
    "tests/bots/test_gauge_scoring_dates.py",
    "tests/bots/test_pattern_engine_job.py",
    "tests/scripts/test_ingest_queue_worker.py",
    "tests/scripts/test_render_cron.py",
    "tests/scripts/test_migraine_refresh_harness.py",
)
MIGRATIONS = (
    "tests/db/fixtures/migraine_postgres_prerequisites.sql",
    "supabase/migrations/20260908002922_add_migraine_episode_details.sql",
    "supabase/migrations/20260910033343_add_migraine_time_corrections.sql",
    "supabase/migrations/20261110032646_add_migraine_time_refresh_queue.sql",
)


def child_environment(home: Path, extra_pythonpath: list[str]) -> dict[str, str]:
    # Explicit allowlist: discard PG*, DSNs, auth tokens, dotenv paths and plugins.
    env = {
        "HOME": str(home), "PATH": "/usr/bin:/bin", "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "tests/db"), *extra_pythonpath]),
        "DATABASE_URL": "postgresql://synthetic:synthetic@127.0.0.1:1/unused",
    }
    if sys.platform.startswith("linux"):
        libdir = sysconfig.get_config_var("LIBDIR")
        if libdir and Path(libdir).is_absolute():
            env["LD_LIBRARY_PATH"] = str(Path(libdir).resolve())
    return env


def server_options(socket: Path) -> str:
    return (f"-c listen_addresses='' -c unix_socket_directories='{socket}' "
            "-c unix_socket_permissions=0700 -c port=55439")


def run(pg_bin: Path, extra_pythonpath: list[str]) -> int:
    if any((directory / ".env").exists() for directory in (ROOT, *ROOT.parents)):
        raise RuntimeError("Refusing checkout with .env in its ancestor chain; use a clean isolated checkout")
    required = ("initdb", "pg_ctl", "createdb", "psql")
    if not all((pg_bin / name).is_file() for name in required):
        raise RuntimeError("Required PostgreSQL binaries are missing")
    # Short path preserves the Unix socket path limit on macOS and Linux.
    home = Path(tempfile.mkdtemp(prefix="mqt-", dir="/tmp"))
    try:
        socket = home / ".codex/cache/gaia-migraine-postgres-17.11/socket"
        socket.mkdir(parents=True, mode=0o700)
        data = home / "data"
        env = child_environment(home, extra_pythonpath)
        def command(args: list[str | Path], *, check: bool = True) -> subprocess.CompletedProcess:
            return subprocess.run([str(a) for a in args], cwd=ROOT, env=env, check=check)
        try:
            command([sys.executable, "-I", "-c", "import sys; assert sys.version_info >= (3, 11)"])
            command([pg_bin / "initdb", "-D", data, "--auth-local=trust", "--auth-host=reject",
                     "--username=synthetic", "--no-locale", "--encoding=UTF8"])
            with (data / "postgresql.conf").open("a") as config:
                config.write("\nshared_memory_type=mmap\ndynamic_shared_memory_type=posix\n")
            command([pg_bin / "pg_ctl", "-D", data, "-l", home / "postgres.log",
                     "-o", server_options(socket), "-w", "start"])
            common = ["-h", socket, "-p", "55439", "-U", "synthetic"]
            command([pg_bin / "createdb", *common, "gaia_migraine_test"])
            psql = [pg_bin / "psql", "-X", "-v", "ON_ERROR_STOP=1", *common, "-d", "gaia_migraine_test"]
            command([*psql, "-c", "alter database gaia_migraine_test set gaia.migraine_disposable='true'; create role service_role bypassrls;"])
            for migration in MIGRATIONS:
                command([*psql, "-f", ROOT / migration])
            dsn = f"postgresql://synthetic@/gaia_migraine_test?host={socket}&port=55439"
            env.update(GAIA_MIGRAINE_TEST_DATABASE_URL=dsn, SUPABASE_DB_URL=dsn)
            return command([sys.executable, "-B", "-m", "pytest", "-q", "-s",
                            "-p", "anyio.pytest_plugin", "-p", "no:cacheprovider", *TARGETS], check=False).returncode
        finally:
            # Also clean up if startup partially succeeded. Never stop another cluster.
            if (data / "postmaster.pid").exists():
                command([pg_bin / "pg_ctl", "-D", data, "-m", "fast", "-w", "stop"])
    finally:
        # Retain evidence rather than deleting files under a server that failed to stop.
        if not (home / "data/postmaster.pid").exists():
            shutil.rmtree(home)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument("--extra-pythonpath", action="append", default=[])
    args = parser.parse_args()
    pg_bin = args.pg_bin
    if pg_bin is None:
        config = shutil.which("pg_config")
        if not config:
            parser.error("Install PostgreSQL in CI or provide --pg-bin; no automatic download is performed")
        pg_bin = Path(subprocess.check_output([config, "--bindir"], text=True).strip())
    return run(pg_bin.resolve(), args.extra_pythonpath)


if __name__ == "__main__":
    raise SystemExit(main())
