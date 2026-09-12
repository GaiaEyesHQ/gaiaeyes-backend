from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    ("failed_step", "publishes"),
    [
        (None, True),
        ("Run ingester", False),
        ("Refresh database daily/current rollup", False),
        ("Run ULF ingester", True),
    ],
)
def test_json_publication_survives_only_independent_provider_failure(
    failed_step, publishes
):
    """Exercise default success-only step scheduling against the real workflow."""
    workflow = Path(__file__).resolve().parents[2] / ".github/workflows/space-weather.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["run"]["steps"]
    relevant = {
        "Run ingester",
        "Refresh database daily/current rollup",
        "Commit & push updated JSON",
        "Run ULF ingester",
    }
    executed = []
    failed = False
    for step in steps:
        if step.get("name") not in relevant:
            continue
        assert "if" not in step
        assert not step.get("continue-on-error", False)
        if not failed:
            executed.append(step["name"])
            failed = step["name"] == failed_step

    assert ("Commit & push updated JSON" in executed) is publishes
    assert failed is (failed_step is not None)
    alert = next(step for step in steps if step.get("name") == "Create issue on failure")
    assert alert["if"] == "failure()"
