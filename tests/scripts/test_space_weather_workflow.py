from pathlib import Path

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/space-weather.yml"


@pytest.mark.parametrize(
    ("failed_steps", "publishes", "failed_jobs"),
    [
        (set(), True, set()),
        ({("run", "Run ingester")}, False, {"run"}),
        ({("run", "Refresh database daily/current rollup")}, False, {"run"}),
        ({("run", "Commit & push updated JSON")}, False, {"run"}),
        ({("run", "Checkout media repo (gaiaeyes-media)")}, False, {"run"}),
        ({("ulf", "Run ULF ingester")}, True, {"ulf"}),
        ({("ulf", "Install deps")}, True, {"ulf"}),
        (
            {("run", "Run ingester"), ("ulf", "Run ULF ingester")},
            False,
            {"run", "ulf"},
        ),
    ],
)
def test_provider_failures_are_isolated(failed_steps, publishes, failed_jobs):
    """Exercise independent jobs and success-only steps in the real workflow."""
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    assert set(jobs) == {"run", "ulf"}
    outcomes = {}
    alerts = set()
    for job_id, job in jobs.items():
        assert not job.get("needs")
        assert "if" not in job
        assert not job.get("continue-on-error", False)
        failed = False
        for step in job["steps"]:
            key = (job_id, step["name"])
            assert not step.get("continue-on-error", False)
            if step.get("uses", "").startswith("dacbd/create-issue-action@"):
                assert step["if"] == "failure()"
                if failed:
                    alerts.add(job_id)
                continue
            assert "if" not in step
            if failed:
                outcomes[key] = "skipped"
            elif key in failed_steps:
                outcomes[key] = "failure"
                failed = True
            else:
                outcomes[key] = "success"

    assert (outcomes[("run", "Commit & push updated JSON")] == "success") is publishes
    assert outcomes[("ulf", "Run ULF ingester")] == (
        "skipped" if ("ulf", "Install deps") in failed_steps
        else "failure" if ("ulf", "Run ULF ingester") in failed_steps
        else "success"
    )
    assert alerts == failed_jobs


@pytest.mark.parametrize(
    ("job_id", "title", "step_ids"),
    [
        ("run", "Space-weather ingestion failed", {"ingest", "rollup", "publish"}),
        ("ulf", "ULF geomagnetic ingestion failed", {"ingest"}),
    ],
)
def test_failure_alert_identifies_provider_and_exact_run(job_id, title, step_ids):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"][job_id]["steps"]
    alert = next(s for s in steps if s.get("uses", "").startswith("dacbd/create-issue-action@"))
    assert alert["with"]["title"] == title
    body = alert["with"]["body"]
    assert "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" in body
    assert "${{ github.run_attempt }}" in body
    assert "${{ github.job }}" in body
    assert "${{ github.sha }}" in body
    assert step_ids <= {s.get("id") for s in steps}
    for step_id in step_ids:
        assert "${{ steps." + step_id + ".outcome || 'not run' }}" in body


def test_ulf_job_has_its_own_runtime_without_media_credentials():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    ulf = jobs["ulf"]
    steps = ulf["steps"]
    assert any(s.get("uses", "").startswith("actions/checkout@") for s in steps)
    setup = next(s for s in steps if s.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["python-version"] == "3.11"
    install = next(s for s in steps if s["name"] == "Install deps")
    assert "pip install httpx asyncpg" in install["run"]
    ingest = next(s for s in steps if s["name"] == "Run ULF ingester")
    assert ingest["run"] == "python bots/geomag_ulf/ingest_ulf.py"
    assert not any("ingest_ulf.py" in s.get("run", "") for s in jobs["run"]["steps"])
    assert ulf["env"] == {
        "SUPABASE_DB_URL": jobs["run"]["env"]["SUPABASE_DB_URL"],
        "HTTP_USER_AGENT": jobs["run"]["env"]["HTTP_USER_AGENT"],
    }
