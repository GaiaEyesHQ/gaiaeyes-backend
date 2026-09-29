"""No network or database: exercise the bounded review recovery decision."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import asyncio
import copy
from pathlib import Path
import subprocess
import yaml
import pytest
from scripts import earthscope_local_primary as runner
from services.earthscope_writer_contract import DraftError

DAY = datetime(2026,9,28,tzinfo=timezone.utc).date()
ROW = {'job_version':1,'intended_worker_id':'review-worker','input_classification':'dated_production_facts','status':'failed'}
class Connection:
    execute = AsyncMock()
    @asynccontextmanager
    async def transaction(self): yield

def setup(monkeypatch, row):
    monkeypatch.setattr(runner.queue,'one',AsyncMock(return_value=row))
    monkeypatch.setattr(runner.queue,'now_at',AsyncMock(return_value=datetime(2026,9,28,tzinfo=timezone.utc)))
    collect=AsyncMock(return_value=({'new_facts':True},None));monkeypatch.setattr(runner,'qualified_public_facts',collect)
    enqueue=AsyncMock(return_value={'job_version':2});monkeypatch.setattr(runner.queue,'enqueue',enqueue)
    return collect,enqueue

@pytest.mark.parametrize('status',['failed','expired'])
def test_explicit_next_failed_review_collects_new_facts(monkeypatch,status):
    row={**ROW,'status':status};collect,enqueue=setup(monkeypatch,row)
    result=asyncio.run(runner.prepare_or_reuse(Connection(),DAY,2,'review-worker',600,new_review_version=True))
    assert result=={'job_version':2};collect.assert_awaited_once();enqueue.assert_awaited_once()
    assert enqueue.call_args.args[1]=={'new_facts':True} and row=={**ROW,'status':status}

@pytest.mark.parametrize('status,version,selected',[(s,2,True) for s in ['queued','claimed','returned']]+[('failed',2,False),('failed',3,True),('failed',0,True)])
def test_no_implicit_retry_active_replacement_or_version_skip(monkeypatch,status,version,selected):
    collect,enqueue=setup(monkeypatch,{**ROW,'status':status})
    with pytest.raises(DraftError):asyncio.run(runner.prepare_or_reuse(Connection(),DAY,version,'review-worker',600,new_review_version=selected))
    collect.assert_not_awaited();enqueue.assert_not_awaited()

def test_same_version_is_idempotent(monkeypatch):
    collect,enqueue=setup(monkeypatch,copy.deepcopy(ROW))
    assert asyncio.run(runner.prepare_or_reuse(Connection(),DAY,1,'review-worker',600,new_review_version=True))==ROW
    collect.assert_not_awaited();enqueue.assert_not_awaited()

def test_production_cannot_select_new_review_version():
    with pytest.raises(DraftError,match='new_version_requires_review_only'):
        asyncio.run(runner.configured_post(DAY,2,600,{},new_review_version=True))

def test_workflow_version_uses_environment_and_script_parses():
    path=Path(__file__).resolve().parents[2]/'.github/workflows/earthscope_writer_review.yml'
    data=yaml.safe_load(path.read_text());step=next(s for s in data['jobs']['qualification']['steps'] if s.get('name')=='Current-day draft-only exchange')
    assert step['env']['REVIEW_VERSION']=='${{ inputs.review_version }}'
    assert '--new-review-version --version "$REVIEW_VERSION"' in step['run']
    assert '${{' not in step['run']
    subprocess.run(['bash','-n'],input=step['run'],text=True,check=True)


def test_version_is_available_in_same_workflow_step():
    import re
    path=Path(__file__).resolve().parents[2]/'.github/workflows/earthscope_writer_review.yml'
    data=yaml.safe_load(path.read_text());step=next(s for s in data['jobs']['qualification']['steps'] if s.get('name')=='Current-day draft-only exchange')
    variable=re.search(r'--version "\$(\w+)"',step['run']).group(1)
    assert variable in step['env'], 'GITHUB_ENV writes only apply to later steps'
    value=subprocess.check_output(['bash','-uc',f'printf %s "${variable}"'],env={variable:'2'},text=True)
    assert value=='2'


REJECTION = {"id": "editorial-review-9", "reason": "temporal_scope_broadening"}

def returned_row():
    outcome = {"status": "draft_review_ready", "draft": {"caption": "Original retained."}}
    return {**ROW, "status": "returned", "outcome": outcome,
            "outcome_sha256": runner.sha256(outcome), "acknowledgement_id": "prior-ack"}

def test_exact_editorial_rejection_appends_without_mutating_original(monkeypatch):
    row = returned_row(); before = copy.deepcopy(row)
    decision = {**REJECTION, "outcome_sha256": row["outcome_sha256"]}
    collect, enqueue = setup(monkeypatch, row)
    result = asyncio.run(runner.prepare_or_reuse(Connection(), DAY, 2, 'review-worker', 600,
        new_review_version=True, editorial_rejection=decision))
    assert result == {"job_version": 2}
    assert row == before
    collect.assert_awaited_once(); enqueue.assert_awaited_once()

@pytest.mark.parametrize("change", ["wrong_hash", "tampered_outcome", "no_ack", "active", "skip", "no_selection", "missing"])
def test_editorial_rejection_requires_exact_terminal_identity(monkeypatch, change):
    row = returned_row(); decision = {**REJECTION, "outcome_sha256": row["outcome_sha256"]}
    version = 2; selected = True
    if change == "wrong_hash": decision["outcome_sha256"] = "0" * 64
    if change == "tampered_outcome": row["outcome"]["draft"]["caption"] = "Changed"
    if change == "no_ack": row["acknowledgement_id"] = None
    if change == "active": row["status"] = "claimed"
    if change == "skip": version = 3
    if change == "no_selection": selected = False
    if change == "missing": row = None
    collect, enqueue = setup(monkeypatch, row)
    with pytest.raises(DraftError):
        asyncio.run(runner.prepare_or_reuse(Connection(), DAY, version, 'review-worker', 600,
            new_review_version=selected, editorial_rejection=decision))
    collect.assert_not_awaited(); enqueue.assert_not_awaited()

@pytest.mark.parametrize("case", ["production", "partial", "bad_id", "bad_hash", "bad_reason", "no_new_version"])
def test_rejection_input_fails_closed_before_connection(case):
    env = {"EARTHSCOPE_REVIEW_REJECTION_ID": "editorial-review-9",
           "EARTHSCOPE_REVIEW_REJECTION_SHA256": "a" * 64,
           "EARTHSCOPE_REVIEW_REJECTION_REASON": "temporal_scope_broadening"}
    if case == "partial": env.pop("EARTHSCOPE_REVIEW_REJECTION_REASON")
    if case == "bad_id": env["EARTHSCOPE_REVIEW_REJECTION_ID"] = "bad id"
    if case == "bad_hash": env["EARTHSCOPE_REVIEW_REJECTION_SHA256"] = "not-a-hash"
    if case == "bad_reason": env["EARTHSCOPE_REVIEW_REJECTION_REASON"] = "anything"
    with pytest.raises(DraftError):
        runner.review_rejection(env, review_only=case != "production", new_review_version=case != "no_new_version")

def test_rejection_valid_input_and_ordinary_absence():
    assert runner.review_rejection({}, review_only=False, new_review_version=False) is None
    env = {"EARTHSCOPE_REVIEW_REJECTION_ID": "editorial-review-9",
           "EARTHSCOPE_REVIEW_REJECTION_SHA256": "a" * 64,
           "EARTHSCOPE_REVIEW_REJECTION_REASON": "temporal_scope_broadening"}
    assert runner.review_rejection(env, review_only=True, new_review_version=True) == {**REJECTION, "outcome_sha256": "a" * 64}


@pytest.mark.parametrize("fails", [False, True])
def test_main_rejection_intent_and_terminal_receipt_are_distinct(monkeypatch, tmp_path, fails):
    import json
    import sys
    receipt = tmp_path / "review-receipt.json"
    monkeypatch.setattr(sys, "argv", ["review", "--day", DAY.isoformat(),
        "--receipt", str(receipt), "--post-output", str(tmp_path / "post.json"),
        "--daily-output", str(tmp_path / "daily.json"), "--review-only", "--new-review-version"])
    decision = {**REJECTION, "outcome_sha256": "a" * 64}
    monkeypatch.setattr(runner, "review_rejection", lambda *a, **kw: decision)
    intent = tmp_path / "review-receipt-intent.json"
    async def configured(*args, **kwargs):
        assert json.loads(intent.read_text())["editorial_rejection"] == decision
        assert not receipt.exists()
        if fails:
            raise DraftError("selected_failure")
        return {"metrics_json": {"writer_source": "local_primary"}}
    monkeypatch.setattr(runner, "configured_post", configured)
    monkeypatch.setattr(runner, "daily_json", lambda post: {"test_daily": True})
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert runner.main() == (1 if fails else 0)
    assert json.loads(receipt.read_text())["status"] == ("selected_failure" if fails else "review_ready")
    assert json.loads(intent.read_text())["status"] == "failed"
