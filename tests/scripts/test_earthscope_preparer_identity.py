from contextlib import contextmanager, nullcontext
from pathlib import Path
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
    def __init__(self, fail_stage=None, error=None, fail_close=False):
        self.statements = []
        self.read_only = {"read_only": "on"}
        self.fail_stage = fail_stage
        self.error = error or RuntimeError("synthetic failure")
        self.fail_close = fail_close
        self.fail_probe = None
        self.identity = {"login": identity.LOGIN, "effective_role": identity.LOGIN,
            "database": "postgres", "read_only": "on", "rolsuper": False,
            "rolinherit": False, "rolcreaterole": False, "rolcreatedb": False,
            "rolreplication": False, "rolbypassrls": False, "can_set": True, "inherits": False}
        self.memberships = [{"rolname": identity.ROLE, "admin_option": False,
                             "inherit_option": False, "set_option": True}]
        self.effective = {"effective_role": identity.ROLE, "history_read": True,
            "jobs_read": True, "jobs_insert": True, "claims_read": False,
            "public_posts_access": False, "delivery_access": False}
    def __enter__(self): return self
    def __exit__(self, *args):
        if self.fail_close: raise self.error
    @contextmanager
    def transaction(self):
        yield
        if self.fail_stage == "transaction_close": raise self.error
    def cursor(self, **kwargs): return nullcontext(self)
    def execute(self, sql):
        self.statements.append(sql)
        if sql.startswith("set transaction"):
            stage = "read_only_setup"
        elif "from pg_auth_members" in sql:
            stage = "membership"
        elif "from pg_roles" in sql:
            stage = "identity"
        elif sql.startswith("set local role"):
            stage = "set_role"
        elif "has_table_privilege" in sql:
            stage = "privileges"
        elif " from marts." in sql or " from ext." in sql:
            stage = "source_permission_probes"
        else:
            stage = None
        if stage is not None and stage == self.fail_stage: raise self.error
        if self.fail_probe and self.fail_probe in sql: raise self.error
    def fetchone(self):
        if self.statements[-1].startswith("select current_setting"):
            return self.read_only
        return self.identity if "from pg_roles" in self.statements[-1] else self.effective
    def fetchall(self): return self.memberships


def test_probe_is_read_only_and_uses_no_public_or_member_row_reads():
    conn = Connection()
    result = identity.verify_connection(conn)
    assert result["status"] == "verified"
    assert conn.statements[0] == "set transaction read only"
    assert conn.statements[1:4] == ["set local statement_timeout='8s'",
        "set local lock_timeout='2s'", "select current_setting('transaction_read_only') as read_only"]
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


SECRET = "G055-SENTINEL-DO-NOT-EMIT"


class OpaqueError(RuntimeError):
    def __str__(self):
        raise AssertionError("Exception text must not be inspected: " + SECRET)


class DatabaseError(identity.psycopg.Error):
    def __init__(self, code):
        self.code = code
        Exception.__init__(self, SECRET)
    @property
    def sqlstate(self): return self.code
    @property
    def diag(self): raise AssertionError("Server diagnostics must not be inspected: " + SECRET)
    def __str__(self): raise AssertionError("Exception text must not be inspected: " + SECRET)


def run_cli(monkeypatch, tmp_path, capsys, conn=None, stage=None, error=None):
    for key, value in environment(tmp_path).items(): monkeypatch.setenv(key, value)
    monkeypatch.setenv("GITHUB_RUN_ID", "36220163565")
    monkeypatch.setenv("GITHUB_SHA", "79cb3c05dd1bba70df630255a391db6480d9bb65")
    conn = conn or Connection(stage, error)
    def connect(**kwargs):
        if stage == "connection_establishment": raise error
        return conn
    monkeypatch.setattr(identity.psycopg, "connect", connect)
    if stage == "connection_configuration":
        def configure(env): raise error
        monkeypatch.setattr(identity, "connection_options", configure)
    path = tmp_path / "receipt.json"
    monkeypatch.setattr(sys, "argv", ["probe", "--receipt", str(path)])
    exit_code = identity.main()
    captured = capsys.readouterr()
    receipt_text = path.read_text()
    assert SECRET not in receipt_text + captured.out + captured.err
    assert captured.err == ""
    return exit_code, json.loads(receipt_text), json.loads(captured.out), conn


@pytest.mark.parametrize("stage", sorted(identity.STAGES))
def test_each_stage_reports_only_fixed_unknown_failure(monkeypatch, tmp_path, capsys, stage):
    error = OpaqueError(SECRET)
    code, receipt, stdout, _ = run_cli(monkeypatch, tmp_path, capsys, stage=stage, error=error)
    assert code == 1 and receipt["verified"] is False
    assert receipt["status"] == "preparer_identity_unavailable"
    assert receipt["diagnostic"] == {"stage": stage,
        "category": "unknown_connection_failure" if stage == "connection_establishment" else "unknown_failure"}
    assert stdout == receipt


@pytest.mark.parametrize("sqlstate,category", sorted(identity.SQLSTATE_CATEGORIES.items()))
def test_only_structured_allowlisted_sqlstate_classifies_error(monkeypatch, tmp_path, capsys, sqlstate, category):
    code, receipt, stdout, _ = run_cli(monkeypatch, tmp_path, capsys,
        stage="connection_establishment", error=identity.psycopg.errors.lookup(sqlstate)(SECRET))
    assert code == 1
    assert receipt["diagnostic"] == {"stage": "connection_establishment", "category": category}
    assert stdout == receipt and "sqlstate" not in receipt["diagnostic"]


@pytest.mark.parametrize("sqlstate", [None, "", "ZZ999", SECRET, "42501 " + SECRET,
                                      "28P01\n" + SECRET, {"secret": SECRET}, 42501])
def test_untrusted_sqlstate_is_never_parsed_or_emitted(monkeypatch, tmp_path, capsys, sqlstate):
    code, receipt, _, _ = run_cli(monkeypatch, tmp_path, capsys,
        stage="connection_establishment", error=DatabaseError(sqlstate))
    assert code == 1
    assert receipt["diagnostic"]["category"] == "unknown_connection_failure"


def test_broken_sqlstate_accessor_remains_unknown(monkeypatch, tmp_path, capsys):
    class BrokenError(DatabaseError):
        @property
        def sqlstate(self): raise OpaqueError(SECRET)
    code, receipt, _, _ = run_cli(monkeypatch, tmp_path, capsys,
        stage="connection_establishment", error=BrokenError(None))
    assert code == 1 and receipt["diagnostic"]["category"] == "unknown_connection_failure"


@pytest.mark.parametrize("value", ["off", SECRET, True, None])
def test_read_only_guard_stops_before_any_metadata_or_source_query(monkeypatch, tmp_path, capsys, value):
    conn = Connection(); conn.read_only = {"read_only": value}
    code, receipt, _, _ = run_cli(monkeypatch, tmp_path, capsys, conn=conn)
    assert code == 1
    assert receipt["diagnostic"] == {"stage": "read_only_setup", "category": "read_only_not_confirmed"}
    assert len(conn.statements) == 4
    assert not any(" from " in s for s in conn.statements)


@pytest.mark.parametrize("record,stage,category", [
    ("identity", "identity", "preparer_identity_mismatch"),
    ("memberships", "membership", "preparer_membership_mismatch"),
    ("effective", "privileges", "preparer_privilege_mismatch"),
])
def test_arbitrary_server_fields_are_rejected_without_echo(monkeypatch, tmp_path, capsys, record, stage, category):
    conn = Connection()
    row = getattr(conn, record)
    if type(row) is list: row = row[0]
    row["unexpected"] = SECRET
    code, receipt, _, _ = run_cli(monkeypatch, tmp_path, capsys, conn=conn)
    assert code == 1 and receipt["diagnostic"] == {"stage": stage, "category": category}


@pytest.mark.parametrize("probe", ["marts.space_weather_daily", "marts.kp_obs", "ext.schumann",
                                    "ext.space_weather", "ext.magnetosphere_pulse"])
def test_each_limit_zero_probe_failure_is_secret_safe(monkeypatch, tmp_path, capsys, probe):
    conn = Connection(error=DatabaseError("42501")); conn.fail_probe = probe
    code, receipt, _, _ = run_cli(monkeypatch, tmp_path, capsys, conn=conn)
    assert code == 1 and receipt["diagnostic"] == {
        "stage": "source_permission_probes", "category": "insufficient_privilege"}
    probes = [s for s in conn.statements if " from marts." in s or " from ext." in s]
    assert probes and all(s.endswith("limit 0") for s in probes)


def test_connection_close_failure_cannot_keep_success_result(monkeypatch, tmp_path, capsys):
    conn = Connection(error=OpaqueError(SECRET), fail_close=True)
    code, receipt, stdout, _ = run_cli(monkeypatch, tmp_path, capsys, conn=conn)
    assert code == 1 and not receipt["verified"]
    assert receipt["diagnostic"] == {"stage": "transaction_close", "category": "unknown_failure"}
    assert stdout == receipt and "identity" not in receipt


def test_success_keeps_receipt_and_exit_behavior(monkeypatch, tmp_path, capsys):
    code, receipt, stdout, conn = run_cli(monkeypatch, tmp_path, capsys)
    assert code == 0 and receipt["verified"] is True and receipt["status"] == "verified"
    assert stdout == {"status": "verified", "verified": True}
    assert "diagnostic" not in receipt
    assert receipt["identity"] == conn.identity and receipt["memberships"] == conn.memberships
    assert receipt["effective"] == conn.effective and receipt["source_rows_read"] == 0
    assert receipt["transaction_read_only"] and receipt["sslmode"] == "verify-full"
    assert receipt["github_run_id"] == "36220163565"
    assert receipt["source_revision"] == "79cb3c05dd1bba70df630255a391db6480d9bb65"
    assert len([s for s in conn.statements if s.endswith("limit 0")]) == 5


@pytest.mark.parametrize("configuration,category", [
    ("host='" + SECRET, "preparer_connection_invalid"),
    ("host=wrong.invalid password=" + SECRET, "preparer_connection_unqualified"),
])
def test_invalid_configuration_fails_before_connect_without_echo(monkeypatch, tmp_path, capsys, configuration, category):
    monkeypatch.setenv("EARTHSCOPE_DRAFT_PREPARER_DSN", configuration)
    monkeypatch.setenv("PGSSLROOTCERT", str(tmp_path / "missing-ca"))
    def forbidden(**kwargs): pytest.fail("connect must not be called")
    monkeypatch.setattr(identity.psycopg, "connect", forbidden)
    path = tmp_path / "receipt.json"
    monkeypatch.setattr(sys, "argv", ["probe", "--receipt", str(path)])
    assert identity.main() == 1
    output = capsys.readouterr()
    assert SECRET not in path.read_text() + output.out + output.err
    assert json.loads(path.read_text())["diagnostic"] == {
        "stage": "connection_configuration", "category": category}


def test_diagnostic_labels_and_github_references_reject_arbitrary_values(monkeypatch):
    assert identity.failure_diagnostic(SECRET, identity.ProbeValidationError(SECRET)) == {
        "stage": "unknown", "category": "unknown_failure"}
    for name, pattern in [("GITHUB_RUN_ID", r"[0-9]{1,20}"), ("GITHUB_SHA", r"[0-9a-f]{40}")]:
        monkeypatch.setenv(name, SECRET)
        assert identity.github_reference(name, pattern) is None
