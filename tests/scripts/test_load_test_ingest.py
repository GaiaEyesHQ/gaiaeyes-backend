from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "load_test_ingest.py"
    spec = importlib.util.spec_from_file_location("load_test_ingest", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_synthetic_samples_use_allowed_device_os():
    module = _load_module()

    sample = module._sample_for(
        "11111111-1111-1111-1111-111111111111",
        0,
        datetime(2026, 4, 26, tzinfo=timezone.utc),
    )

    assert sample["device_os"] == "ios"
    assert sample["source"] == "loadtest"
