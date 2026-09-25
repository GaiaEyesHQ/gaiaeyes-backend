"""Bounded, read-only identity proof for the dedicated EarthScope preparer."""
import argparse
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

LOGIN = "gaia_earthscope_preparer_runtime"
ROLE = "gaia_earthscope_writer_preparer"
HOST = "aws-1-us-east-2.pooler.supabase.com"
PROJECT = "qadwzkwubfbfuslfxkzl"


def connection_options(environ):
    dsn = environ.get("EARTHSCOPE_DRAFT_PREPARER_DSN", "")
    ca = environ.get("PGSSLROOTCERT", "")
    options = conninfo_to_dict(dsn) if dsn else {}
    if (options.get("host") != HOST or options.get("port") != "5432"
            or options.get("dbname") != "postgres"
            or options.get("user") != LOGIN + "." + PROJECT
            or not options.get("password") or not ca or not Path(ca).is_file()
            or any(key in options for key in ("hostaddr", "service", "options"))):
        raise ValueError("preparer_connection_unqualified")
    # Explicit arguments override DSN/environment downgrades. Session mode is
    # required because the consumer retains SET ROLE between transactions.
    return {**options, "sslmode": "verify-full", "sslrootcert": ca,
            "connect_timeout": 5, "application_name": "gaia-earthscope-preparer"}


def verify_connection(conn):
    with conn.transaction():
        conn.execute("set transaction read only")
        conn.execute("set local statement_timeout='8s'")
        conn.execute("set local lock_timeout='2s'")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""select session_user as login, current_user as effective_role,
                current_database() as database, current_setting('transaction_read_only') as read_only,
                rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,
                pg_has_role(session_user,'gaia_earthscope_writer_preparer','SET') as can_set,
                pg_has_role(session_user,'gaia_earthscope_writer_preparer','USAGE') as inherits
                from pg_roles where rolname=session_user""")
            identity = cur.fetchone()
            if (identity["login"] != LOGIN or identity["effective_role"] != LOGIN
                    or identity["database"] != "postgres" or identity["read_only"] != "on"
                    or not identity["can_set"] or identity["inherits"]
                    or any(identity[k] for k in ("rolsuper", "rolinherit", "rolcreaterole",
                                                "rolcreatedb", "rolreplication", "rolbypassrls"))):
                raise ValueError("preparer_identity_mismatch")
            cur.execute("""select r.rolname,m.admin_option,m.inherit_option,m.set_option
                from pg_auth_members m join pg_roles r on r.oid=m.roleid
                where m.member=(select oid from pg_roles where rolname=session_user)""")
            memberships = cur.fetchall()
            if memberships != [{"rolname": ROLE, "admin_option": False,
                                "inherit_option": False, "set_option": True}]:
                raise ValueError("preparer_membership_mismatch")
            cur.execute("set local role gaia_earthscope_writer_preparer")
            cur.execute("""select current_user as effective_role,
                has_table_privilege(current_user,'content.earthscope_writer_public_history','SELECT') as history_read,
                has_table_privilege(current_user,'content.earthscope_writer_jobs','SELECT') as jobs_read,
                has_table_privilege(current_user,'content.earthscope_writer_jobs','INSERT') as jobs_insert,
                has_table_privilege(current_user,'content.earthscope_writer_claim_requests','SELECT') as claims_read,
                has_table_privilege(current_user,'content.daily_posts','SELECT,INSERT,UPDATE,DELETE') as public_posts_access,
                has_table_privilege(current_user,'content.earthscope_delivery_attempts','SELECT,INSERT,UPDATE,DELETE') as delivery_access""")
            effective = cur.fetchone()
            if (effective["effective_role"] != ROLE
                    or not all(effective[k] for k in ("history_read", "jobs_read", "jobs_insert"))
                    or any(effective[k] for k in ("claims_read", "public_posts_access", "delivery_access"))):
                raise ValueError("preparer_privilege_mismatch")
            # Permission checks only; no source/member rows are read.
            for sql in (
                "select day,updated_at,kp_max,bz_min,sw_speed_avg,flares_count,cmes_count,sw_speed_now_kms,sw_speed_now,now_ts,kp_now from marts.space_weather_daily limit 0",
                "select kp_time,kp from marts.kp_obs limit 0",
                "select station_id,ts_utc,channel,value_num from ext.schumann limit 0",
                "select ts_utc,kp_index from ext.space_weather limit 0",
                "select ts,kp_latest from ext.magnetosphere_pulse limit 0",
            ):
                cur.execute(sql)
    return {"status": "verified", "identity": identity, "effective": effective,
            "memberships": memberships, "source_rows_read": 0, "transaction_read_only": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = {"status": "preparer_identity_unavailable", "verified": False}
    try:
        options = connection_options(os.environ)
        with psycopg.connect(**options) as conn:
            result = {**verify_connection(conn), "verified": True, "host": HOST, "port": 5432,
                      "sslmode": "verify-full", "github_run_id": os.getenv("GITHUB_RUN_ID"),
                      "source_revision": os.getenv("GITHUB_SHA")}
    except Exception:
        # Never log DSNs, authentication errors, passwords or raw server errors.
        pass
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "verified": result["verified"]}))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
