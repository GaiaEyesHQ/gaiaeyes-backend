"""Changed wait boundary and real event-loop timeout, without external I/O."""
import asyncio
from datetime import date
import json
import sys
from unittest.mock import AsyncMock, Mock
import pytest
from scripts import earthscope_local_primary as runner
from services.earthscope_writer_contract import DraftError

@pytest.mark.parametrize('seconds', [-1, 0, 601, 1000000, True, 1.5])
def test_invalid_wait_stops_before_connection(monkeypatch, seconds):
    connect = AsyncMock()
    monkeypatch.setattr(runner.psycopg.AsyncConnection, 'connect', connect)
    with pytest.raises(DraftError, match='invalid_wait_seconds'):
        asyncio.run(runner.configured_post(date(2026, 9, 29), 1, seconds, {}))
    connect.assert_not_awaited()

@pytest.mark.parametrize('seconds', [1, 600])
def test_valid_wait_reaches_configuration_validation(seconds):
    with pytest.raises(DraftError, match='local_primary_disabled'):
        asyncio.run(runner.configured_post(date(2026, 9, 29), 1, seconds, {}))

def test_real_async_timeout_leaves_failure_receipt_without_post(monkeypatch, tmp_path):
    receipt, post, daily = [tmp_path / name for name in ('receipt.json', 'post.json', 'daily.json')]
    monkeypatch.setattr(sys, 'argv', ['consumer', '--day', '2026-09-29',
        '--receipt', str(receipt), '--post-output', str(post), '--daily-output', str(daily)])
    monkeypatch.setattr(runner, 'review_rejection', lambda *a, **k: None)
    cancelled = []
    async def pending():
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    async def configured(*a, **k):
        return await asyncio.wait_for(pending(), timeout=0.01)
    publish = Mock(side_effect=AssertionError('Publication forbidden after timeout'))
    monkeypatch.setattr(runner, 'configured_post', configured)
    monkeypatch.setattr(runner, 'publish_once', publish)
    assert runner.main() == 1
    assert cancelled == [True]
    assert json.loads(receipt.read_text())['status'] == 'local_writer_wait_timeout'
    assert json.loads(receipt.read_text())['production_consumption'] is False
    assert not post.exists() and not daily.exists()
    publish.assert_not_called()
