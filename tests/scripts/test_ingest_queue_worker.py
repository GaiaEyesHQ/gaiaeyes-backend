from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers import ingest_queue_worker as worker


def test_worker_retry_delay_env_parsing_falls_back_for_invalid_value(monkeypatch):
    monkeypatch.setenv("GAIA_INGEST_WORKER_RETRY_DELAY", "not-a-float")
    monkeypatch.setattr(sys, "argv", ["ingest_queue_worker.py"])

    args = worker._parse_args()

    assert args.retry_delay == 5.0
