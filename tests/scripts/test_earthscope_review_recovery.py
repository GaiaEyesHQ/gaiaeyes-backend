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
