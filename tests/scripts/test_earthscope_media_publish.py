import os
from pathlib import Path
import subprocess

import pytest
import yaml


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize("competing_file", ["space_weather.json", "earthscope_daily.json"])
def test_daily_json_push_handles_concurrent_media_writer(tmp_path, competing_file):
    """Run the actual workflow shell against a remote advanced by another writer."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    publisher = tmp_path / "publisher"
    competitor = tmp_path / "competitor"
    git(tmp_path, "clone", str(remote), str(publisher))
    git(publisher, "config", "user.name", "Test")
    git(publisher, "config", "user.email", "test@example.invalid")
    (publisher / "data").mkdir()
    (publisher / "data/earthscope_daily.json").write_text('"initial"\n')
    git(publisher, "add", ".")
    git(publisher, "commit", "-m", "Initial")
    git(publisher, "push", "origin", "main")
    git(tmp_path, "clone", str(remote), str(competitor))
    git(competitor, "config", "user.name", "Test")
    git(competitor, "config", "user.email", "test@example.invalid")
    (competitor / "data" / competing_file).write_text('"competing"\n')
    git(competitor, "add", ".")
    git(competitor, "commit", "-m", "Concurrent update")
    git(competitor, "push", "origin", "main")
    (publisher / "data/earthscope_daily.json").write_text('"daily"\n')
    workflow = Path(__file__).resolve().parents[2] / ".github/workflows/gaia_eyes_daily.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["render"]["steps"]
    script = next(s["run"] for s in steps if s.get("name") == "Publish EarthScope daily JSON to media repo")
    result = subprocess.run(
        ["bash", "-c", script], cwd=publisher,
        env={**os.environ, "MEDIA_REPO_PATH": str(publisher)},
        capture_output=True, text=True, timeout=20,
    )
    assert "[rejected]" in result.stderr
    assert git(remote, "show", f"main:data/{competing_file}") == '"competing"'
    if competing_file == "space_weather.json":
        assert result.returncode == 0, result.stderr
        assert git(remote, "show", "main:data/earthscope_daily.json") == '"daily"'
    else:
        assert result.returncode != 0
