"""Bounded, read-only identity proof for the dedicated EarthScope preparer."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

LOGIN = "gaia_earthscope_preparer_runtime"
ROLE = "gaia_earthscope_writer_preparer"
HOST = "aws-1-us-east-2.pooler.supabase.com"
PROJECT = "qadwzkwubfbfuslfxkzl"
STAGES = frozenset({
    "connection_configuration", "connection_establishment", "read_only_setup",
    "identity", "membership", "set_role", "privileges",
    "source_permission_probes", "transaction_close",
})
VALIDATION_CATEGORIES = frozenset({
    "preparer_connection_invalid", "preparer_connection_unqualified",
    "read_only_not_confirmed", "preparer_identity_mismatch",
    "preparer_membership_mismatch", "preparer_privilege_mismatch",
})
SQLSTATE_CATEGORIES = {
    "08001": "connection_not_established", "08004": "connection_rejected",
    "08006": "connection_failure", "28000": "authorization_rejected",
    "28P01": "password_authentication_rejected", "42501": "insufficient_privilege",
    "42P01": "undefined_relation", "42703": "undefined_column",
    "3F000": "undefined_schema", "53300": "connection_limit",
    "57P03": "server_not_accepting_connections", "57014": "query_canceled",
    "55P03": "lock_unavailable", "25006": "read_only_violation",
    "25P02": "transaction_failed",
}


class ProbeValidationError(ValueError):
    def __init__(self, category):
        self.category = category
        super().__init__(category)


def failure_diagnostic(stage, exc):
    """Return literals only; never inspect exception text or server diagnostics."""
    stage = stage if type(stage) is str and stage in STAGES else "unknown"
    category = "unknown_connection_failure" if stage == "connection_establishment" else "unknown_failure"
    if isinstance(exc, ProbeValidationError):
        if type(exc.category) is str and exc.category in VALIDATION_CATEGORIES:
            category = exc.category
    elif isinstance(exc, psycopg.Error):
        try:
            code = exc.sqlstate
        except Exception:
            code = None
        if type(code) is str:
            category = SQLSTATE_CATEGORIES.get(code, category)
    return {"stage": stage, "category": category}


def exact_record(actual, expected):
    return (type(actual) is dict and actual.keys() == expected.keys()
            and all(type(actual[k]) is type(v) and actual[k] == v for k, v in expected.items()))


def github_reference(name, pattern):
    value = os.getenv(name, "")
    return value if re.fullmatch(pattern, value) else None


def connection_options(environ):
    dsn = environ.get("EARTHSCOPE_DRAFT_PREPARER_DSN", "")
    ca = environ.get("PGSSLROOTCERT", "")
    try:
        options = conninfo_to_dict(dsn) if dsn else {}
    except (psycopg.Error, ValueError):
        raise ProbeValidationError("preparer_connection_invalid") from None
    if (options.get("host") != HOST or options.get("port") != "5432"
            or options.get("dbname") != "postgres"
            or options.get("user") != LOGIN + "." + PROJECT
            or not options.get("password") or not ca or not Path(ca).is_file()
            or any(key in options for key in ("hostaddr", "service", "options"))):
        raise ProbeValidationError("preparer_connection_unqualified")
    # Explicit arguments override DSN/environment downgrades. Session mode is
    # required because the consumer retains SET ROLE between transactions.
    return {**options, "sslmode": "verify-full", "sslrootcert": ca,
            "connect_timeout": 5, "application_name": "gaia-earthscope-preparer"}


def verify_connection(conn, progress=None):
    progress = progress if progress is not None else {}
    progress["stage"] = "read_only_setup"
    with conn.transaction():
        conn.execute("set transaction read only")
        conn.execute("set local statement_timeout='8s'")
        conn.execute("set local lock_timeout='2s'")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select current_setting('transaction_read_only') as read_only")
            if not exact_record(cur.fetchone(), {"read_only": "on"}):
                raise ProbeValidationError("read_only_not_confirmed")
            progress["stage"] = "identity"
            cur.execute("""select session_user as login, current_user as effective_role,
                current_database() as database, current_setting('transaction_read_only') as read_only,
                rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,
                pg_has_role(session_user,'gaia_earthscope_writer_preparer','SET') as can_set,
                pg_has_role(session_user,'gaia_earthscope_writer_preparer','USAGE') as inherits
                from pg_roles where rolname=session_user""")
            identity = cur.fetchone()
            expected_identity = {"login": LOGIN, "effective_role": LOGIN,
                "database": "postgres", "read_only": "on", "rolsuper": False,
                "rolinherit": False, "rolcreaterole": False, "rolcreatedb": False,
                "rolreplication": False, "rolbypassrls": False, "can_set": True, "inherits": False}
            if not exact_record(identity, expected_identity):
                raise ProbeValidationError("preparer_identity_mismatch")
            progress["stage"] = "membership"
            cur.execute("""select r.rolname,m.admin_option,m.inherit_option,m.set_option
                from pg_auth_members m join pg_roles r on r.oid=m.roleid
                where m.member=(select oid from pg_roles where rolname=session_user)""")
            memberships = cur.fetchall()
            expected_membership = {"rolname": ROLE, "admin_option": False,
                                   "inherit_option": False, "set_option": True}
            if (type(memberships) is not list or len(memberships) != 1
                    or not exact_record(memberships[0], expected_membership)):
                raise ProbeValidationError("preparer_membership_mismatch")
            progress["stage"] = "set_role"
            cur.execute("set local role gaia_earthscope_writer_preparer")
            progress["stage"] = "privileges"
            cur.execute("""select current_user as effective_role,
                has_table_privilege(current_user,'content.earthscope_writer_public_history','SELECT') as history_read,
                has_table_privilege(current_user,'content.earthscope_writer_jobs','SELECT') as jobs_read,
                has_table_privilege(current_user,'content.earthscope_writer_jobs','INSERT') as jobs_insert,
                has_table_privilege(current_user,'content.earthscope_writer_claim_requests','SELECT') as claims_read,
                has_table_privilege(current_user,'content.daily_posts','SELECT,INSERT,UPDATE,DELETE') as public_posts_access,
                has_table_privilege(current_user,'content.earthscope_delivery_attempts','SELECT,INSERT,UPDATE,DELETE') as delivery_access""")
            effective = cur.fetchone()
            expected_effective = {"effective_role": ROLE, "history_read": True,
                "jobs_read": True, "jobs_insert": True, "claims_read": False,
                "public_posts_access": False, "delivery_access": False}
            if not exact_record(effective, expected_effective):
                raise ProbeValidationError("preparer_privilege_mismatch")
            progress["stage"] = "source_permission_probes"
            # Permission checks only; no source/member rows are read.
            for sql in (
                "select day,updated_at,kp_max,bz_min,sw_speed_avg,flares_count,cmes_count,sw_speed_now_kms,sw_speed_now,now_ts,kp_now from marts.space_weather_daily limit 0",
                "select kp_time,kp from marts.kp_obs limit 0",
                "select station_id,ts_utc,channel,value_num from ext.schumann limit 0",
                "select ts_utc,kp_index from ext.space_weather limit 0",
                "select ts,kp_latest from ext.magnetosphere_pulse limit 0",
            ):
                cur.execute(sql)
        progress["stage"] = "transaction_close"
    # Emit only the validated literals, never arbitrary returned server fields.
    return {"status": "verified", "identity": expected_identity, "effective": expected_effective,
            "memberships": [expected_membership], "source_rows_read": 0, "transaction_read_only": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = {"status": "preparer_identity_unavailable", "verified": False}
    progress = {"stage": "connection_configuration"}
    try:
        options = connection_options(os.environ)
        progress["stage"] = "connection_establishment"
        with psycopg.connect(**options) as conn:
            verified = verify_connection(conn, progress)
        # Success is committed only after transaction and connection close.
        result = {**verified, "verified": True, "host": HOST, "port": 5432,
                  "sslmode": "verify-full", "github_run_id": github_reference("GITHUB_RUN_ID", r"[0-9]{1,20}"),
                  "source_revision": github_reference("GITHUB_SHA", r"[0-9a-f]{40}")}
    except Exception as exc:
        result["diagnostic"] = failure_diagnostic(progress["stage"], exc)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    summary = {"status": result["status"], "verified": result["verified"]}
    if "diagnostic" in result:
        summary["diagnostic"] = result["diagnostic"]
    print(json.dumps(summary))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
