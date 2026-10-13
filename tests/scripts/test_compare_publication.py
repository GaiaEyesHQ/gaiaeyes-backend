"""Exercise media publication against local bare Git remotes; no network."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/publish_compare_series.sh"
FILES = [f"data/{name}.json" for name in ("quakes_history", "space_history", "compare_series")]
REAL_GIT = shutil.which("git")


def git(repo, *args):
    return subprocess.check_output([REAL_GIT, "-C", str(repo), *args], text=True).strip()


def configure(repo):
    git(repo, "config", "user.name", "Synthetic Test")
    git(repo, "config", "user.email", "synthetic@example.invalid")


@pytest.fixture
def media(tmp_path):
    remote, seed, checkout, other = [tmp_path / name for name in ("remote.git", "seed", "checkout", "other")]
    subprocess.run([REAL_GIT, "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
    subprocess.run([REAL_GIT, "clone", str(remote), str(seed)], check=True, capture_output=True)
    configure(seed)
    (seed / "data").mkdir()
    for file in FILES:
        (seed / file).write_text('{"version":"old"}\n')
    git(seed, "add", ".")
    git(seed, "commit", "-m", "initial media")
    git(seed, "push", "origin", "main")
    for repo in (checkout, other):
        subprocess.run([REAL_GIT, "clone", str(remote), str(repo)], check=True, capture_output=True)
        configure(repo)
    for file in FILES:
        (checkout / file).write_text('{"version":"intended"}\n')
    return remote, checkout, other


def publish(checkout, env=None):
    return subprocess.run(["bash", str(SCRIPT), str(checkout)], text=True, capture_output=True, env=env)


def competing_commit(other, conflict=False):
    file = FILES[0] if conflict else "unrelated.txt"
    (other / file).write_text('{"version":"competing"}\n')
    git(other, "add", file)
    git(other, "commit", "-m", "other media publisher")
    return git(other, "rev-parse", "HEAD")


def install_git_wrapper(tmp_path, script):
    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "git"
    wrapper.write_text('#!/usr/bin/env bash\nset -euo pipefail\n' + script + '\nexec "$REAL_GIT" "$@"\n')
    wrapper.chmod(0o755)
    return {**os.environ, "PATH": str(wrapper_dir) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": REAL_GIT, "PUSH_LOG": str(tmp_path / "pushes")}


def test_publishes_exact_files_and_preserves_other_media_commits(media):
    remote, checkout, other = media
    competing = competing_commit(other)
    git(other, "push", "origin", "main")
    result = publish(checkout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "verified_files=3" in result.stdout
    for file in FILES:
        assert git(remote, "show", f"main:{file}") == '{"version":"intended"}'
    assert git(remote, "show", "main:unrelated.txt") == '{"version":"competing"}'
    assert git(remote, "merge-base", competing, "main") == competing
    assert git(remote, "rev-parse", "main") == git(checkout, "rev-parse", "HEAD")


@pytest.mark.parametrize("conflict", [False, True])
def test_overlapping_push_retries_only_after_successful_rebase(tmp_path, media, conflict):
    remote, checkout, other = media
    competing = competing_commit(other, conflict=conflict)
    env = install_git_wrapper(tmp_path, '''
if [[ "$1" == "push" ]]; then
  if [[ ! -e "$PUSH_LOG" ]]; then
    "$REAL_GIT" -C "$OTHER_CHECKOUT" push origin main
  fi
  echo attempt >> "$PUSH_LOG"
fi
''')
    env["OTHER_CHECKOUT"] = str(other)
    result = publish(checkout, env)
    pushes = Path(env["PUSH_LOG"]).read_text().splitlines()
    if conflict:
        assert result.returncode != 0
        assert "Media rebase failed" in result.stderr
        assert len(pushes) == 1  # The conflicted HEAD must never get pushed.
        assert git(remote, "rev-parse", "main") == competing
        assert git(remote, "show", f"main:{FILES[0]}") == '{"version":"competing"}'
        assert "verified_files=3" not in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert len(pushes) == 2
        assert git(remote, "show", "main:unrelated.txt") == '{"version":"competing"}'
        for file in FILES:
            assert git(remote, "show", f"main:{file}") == '{"version":"intended"}'


def test_successful_push_exit_without_remote_commit_is_failure(tmp_path, media):
    remote, checkout, _ = media
    original = git(remote, "rev-parse", "main")
    env = install_git_wrapper(tmp_path, 'if [[ "$1" == "push" ]]; then exit 0; fi')
    result = publish(checkout, env)
    assert result.returncode != 0
    assert "Published commit is missing from remote main" in result.stderr
    assert git(remote, "rev-parse", "main") == original
    assert "verified_files=3" not in result.stdout


def test_remote_content_changed_after_push_is_failure(tmp_path, media):
    remote, checkout, _ = media
    env = install_git_wrapper(tmp_path, '''
if [[ "$1" == "push" ]]; then
  "$REAL_GIT" "$@"
  echo '{"version":"changed-after-push"}' > data/quakes_history.json
  "$REAL_GIT" add data/quakes_history.json
  "$REAL_GIT" commit -m "concurrent change after accepted push"
  "$REAL_GIT" push origin HEAD:main
  exit 0
fi
''')
    result = publish(checkout, env)
    assert result.returncode != 0
    assert "origin/main does not contain the generated data/quakes_history.json" in result.stderr
    assert git(remote, "show", f"main:{FILES[0]}") == '{"version":"changed-after-push"}'
    assert "verified_files=3" not in result.stdout


def test_push_retries_are_bounded(tmp_path, media):
    remote, checkout, _ = media
    original = git(remote, "rev-parse", "main")
    env = install_git_wrapper(tmp_path, '''
if [[ "$1" == "push" ]]; then
  echo attempt >> "$PUSH_LOG"
  exit 1
fi
''')
    result = publish(checkout, env)
    assert result.returncode != 0
    assert "Could not publish comparison after 3 attempts" in result.stderr
    assert len(Path(env["PUSH_LOG"]).read_text().splitlines()) == 3
    assert git(remote, "rev-parse", "main") == original


def test_missing_output_fails_before_commit_or_push(media):
    remote, checkout, _ = media
    original = git(remote, "rev-parse", "main")
    (checkout / FILES[0]).unlink()
    result = publish(checkout)
    assert result.returncode != 0
    assert git(remote, "rev-parse", "main") == original
    assert git(checkout, "rev-parse", "HEAD") == original
