from contextlib import nullcontext
from pathlib import Path
import copy
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import earthscope_preparer_identity as identity


def environment(tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic-test-certificate-not-used-for-connection")
    return {"EARTHSCOPE_DRAFT_PREPARER_DSN":
            f"host={identity.HOST} port=5432 dbname=postgres user={identity.LOGIN}.{identity.PROJECT} password=synthetic-not-a-credential sslmode=disable",
            "PGSSLROOTCERT": str(ca)}


def test_connection_binds_project_login_session_pooler_and_verified_tls(tmp_path):
    result = identity.connection_options(environment(tmp_path))
    assert result["sslmode"] == "verify-full"
    assert result["connect_timeout"] == 5
    assert result["port"] == "5432"
    assert result["user"] == identity.LOGIN + "." + identity.PROJECT


@pytest.mark.parametrize("old,new", [
    ("port=5432", "port=6543"), (identity.HOST, "other.invalid"),
    (identity.LOGIN + "." + identity.PROJECT, "postgres." + identity.PROJECT),
    ("dbname=postgres", "dbname=other"),
    ("sslmode=disable", "hostaddr=127.0.0.1"),
    ("sslmode=disable", "options='-c role=postgres'"),
])
def test_unqualified_connection_is_rejected_before_connect(tmp_path, old, new):
    env = environment(tmp_path)
    env["EARTHSCOPE_DRAFT_PREPARER_DSN"] = env["EARTHSCOPE_DRAFT_PREPARER_DSN"].replace(old, new)
    with pytest.raises(ValueError):
        identity.connection_options(env)


class Connection:
    def __init__(self):
        self.statements = []
        self.identity = {"login": identity.LOGIN, "effective_role": identity.LOGIN,
            "database": "postgres", "read_only": "on", "rolsuper": False,
            "rolinherit": False, "rolcreaterole": False, "rolcreatedb": False,
            "rolreplication": False, "rolbypassrls": False, "can_set": True, "inherits": False}
        self.memberships = [{"rolname": identity.ROLE, "admin_option": False,
                             "inherit_option": False, "set_option": True}]
        self.effective = {"effective_role": identity.ROLE, "history_read": True,
            "jobs_read": True, "jobs_insert": True, "claims_read": False,
            "public_posts_access": False, "delivery_access": False}
        self.reads = 0
    def transaction(self): return nullcontext()
    def cursor(self, **kwargs): return nullcontext(self)
    def execute(self, sql): self.statements.append(sql)
    def fetchone(self):
        self.reads += 1
        return self.identity if self.reads == 1 else self.effective
    def fetchall(self): return self.memberships


def test_probe_is_read_only_and_uses_no_public_or_member_row_reads():
    conn = Connection()
    result = identity.verify_connection(conn)
    assert result["status"] == "verified"
    assert conn.statements[0] == "set transaction read only"
    assert all("limit 0" in s for s in conn.statements if " from marts." in s or " from ext." in s)
    assert result["source_rows_read"] == 0


@pytest.mark.parametrize("field", ["login", "rolsuper", "rolbypassrls", "inherits", "memberships", "public_posts_access"])
def test_probe_refuses_broad_identity_or_grants(field):
    conn = Connection()
    if field == "login": conn.identity[field] = "postgres"
    elif field == "memberships": conn.memberships[0]["admin_option"] = True
    elif field == "public_posts_access": conn.effective[field] = True
    else: conn.identity[field] = True
    with pytest.raises(ValueError): identity.verify_connection(conn)


def test_authentication_error_never_reaches_receipt_or_stdout(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(identity, "connection_options", lambda env: {})
    def fail(**kwargs): raise RuntimeError("SECRET-PASSWORD synthetic server diagnostic")
    monkeypatch.setattr(identity.psycopg, "connect", fail)
    path = tmp_path / "receipt.json"
    monkeypatch.setattr(sys, "argv", ["probe", "--receipt", str(path)])
    assert identity.main() == 1
    assert "SECRET" not in path.read_text() + capsys.readouterr().out
    assert json.loads(path.read_text())["verified"] is False
