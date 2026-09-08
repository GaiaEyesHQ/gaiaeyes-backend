#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PG_VERSION="17.11"
PG_SHA256="dd27f2b3c59e73ed14aa3324901242bf69a032a6347805f274e6260322d42979"
CACHE="$HOME/.codex/cache/gaia-migraine-postgres-$PG_VERSION"
PREFIX="$CACHE/prefix"
DATA="$CACHE/data"
SOCKET="$CACHE/socket"
SERVER_LOG="$CACHE/postgres.log"
PORT="55439"
DATABASE="gaia_migraine_test"
ADMIN="gaia_migraine_admin"
LOG_DIR="${GAIA_MIGRAINE_TEST_LOG_DIR:-$HOME/.codex/test-logs/gaia-migraine-postgres}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LOG="$LOG_DIR/$STAMP.log"
SERVER_STARTED=0

case "$CACHE" in
  "$HOME/.codex/cache/gaia-migraine-postgres-"*) ;;
  *) echo "Refusing unexpected runtime cache: $CACHE" >&2; exit 2 ;;
esac

mkdir -p "$CACHE/download" "$CACHE/src" "$PREFIX" "$LOG_DIR"
chmod 700 "$CACHE" "$LOG_DIR"
exec > >(tee "$RUN_LOG") 2>&1

finish() {
  status=$?
  if [[ -f "$SERVER_LOG" ]]; then
    {
      echo
      echo "===== PostgreSQL server log ====="
      cat "$SERVER_LOG"
    } >> "$RUN_LOG"
  fi
  if [[ "$SERVER_STARTED" == "1" ]]; then
    "$PREFIX/bin/pg_ctl" -D "$DATA" -m fast stop || true
  fi
  rm -rf "$DATA" "$SOCKET" "$SERVER_LOG"
  echo "Preserved verification log: $RUN_LOG"
  exit "$status"
}
trap finish EXIT

if [[ ! -x "$PREFIX/bin/postgres" ]] || ! "$PREFIX/bin/postgres" --version | grep -q "$PG_VERSION"; then
  ARCHIVE="$CACHE/download/postgresql-$PG_VERSION.tar.bz2"
  curl -fL --retry 2 --connect-timeout 20 --max-time 180 \
    -o "$ARCHIVE" "https://ftp.postgresql.org/pub/source/v$PG_VERSION/postgresql-$PG_VERSION.tar.bz2"
  actual_sha="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
  [[ "$actual_sha" == "$PG_SHA256" ]] || {
    echo "PostgreSQL archive checksum mismatch" >&2
    exit 3
  }
  rm -rf "$CACHE/src/postgresql-$PG_VERSION" "$PREFIX"
  mkdir -p "$PREFIX"
  tar -xjf "$ARCHIVE" -C "$CACHE/src"
  (
    cd "$CACHE/src/postgresql-$PG_VERSION"
    ./configure --prefix="$PREFIX" --without-readline --without-zlib --without-icu
    make -j4
    make install
  )
fi

rm -rf "$DATA" "$SOCKET" "$SERVER_LOG"
mkdir -p "$SOCKET"
chmod 700 "$SOCKET"

env -u DATABASE_URL -u DIRECT_URL -u SUPABASE_URL -u SUPABASE_DB_URL \
  -u PGHOST -u PGPORT -u PGDATABASE -u PGUSER -u PGPASSWORD \
  "$PREFIX/bin/initdb" -D "$DATA" --auth-local=trust --auth-host=reject \
  --username="$ADMIN" --no-locale --encoding=UTF8

env -u DATABASE_URL -u DIRECT_URL -u SUPABASE_URL -u SUPABASE_DB_URL \
  -u PGHOST -u PGPORT -u PGDATABASE -u PGUSER -u PGPASSWORD \
  "$PREFIX/bin/pg_ctl" -D "$DATA" -l "$SERVER_LOG" \
  -o "-c listen_addresses='' -c unix_socket_directories='$SOCKET' -c unix_socket_permissions=0700 -c port=$PORT -c fsync=on -c synchronous_commit=on" start
SERVER_STARTED=1

"$PREFIX/bin/createdb" -h "$SOCKET" -p "$PORT" -U "$ADMIN" "$DATABASE"
"$PREFIX/bin/psql" -X -v ON_ERROR_STOP=1 -h "$SOCKET" -p "$PORT" -U "$ADMIN" -d "$DATABASE" \
  -c "alter database $DATABASE set gaia.migraine_disposable = 'true';"
"$PREFIX/bin/psql" -X -v ON_ERROR_STOP=1 -h "$SOCKET" -p "$PORT" -U "$ADMIN" -d "$DATABASE" \
  -f tests/db/fixtures/migraine_postgres_prerequisites.sql
"$PREFIX/bin/psql" -X -v ON_ERROR_STOP=1 -h "$SOCKET" -p "$PORT" -U "$ADMIN" -d "$DATABASE" \
  -f supabase/migrations/20260908002922_add_migraine_episode_details.sql

if "$PREFIX/bin/pg_isready" -h 127.0.0.1 -p "$PORT" -d "$DATABASE"; then
  echo "Refusing test runtime because TCP unexpectedly accepted connections" >&2
  exit 4
fi

DSN="postgresql://$ADMIN@/$DATABASE?host=$SOCKET&port=$PORT"
env -u DIRECT_URL -u SUPABASE_URL -u SUPABASE_DB_URL \
  DATABASE_URL="postgresql://localhost/test" \
  GAIA_MIGRAINE_TEST_DATABASE_URL="$DSN" \
  venv/bin/python -m pytest -q \
    tests/db/test_migraine.py \
    tests/db/test_migraine_postgres_integration.py \
    tests/services/test_migraine_episode_contract.py \
    tests/services/test_migraine_follow_up.py \
    tests/api/test_symptoms.py \
    tests/api/test_feedback.py \
    tests/services/test_voice_symptoms.py
