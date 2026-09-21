import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
import yaml

from scripts import upload_earthscope_images as uploader


ROOT = Path(__file__).resolve().parents[2]
ENV = {
    "SUPABASE_URL": "https://storage.example.invalid/ \r\n",
    "SUPABASE_SERVICE_ROLE_KEY": "synthetic-secret-never-log",
}


@pytest.fixture
def images(tmp_path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    for name in uploader.REQUIRED_ASSETS:
        (image_dir / name).write_bytes(b"synthetic-image")
    return image_dir


def fake_curl(monkeypatch, results):
    calls = []
    remaining = iter(results)

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        value = next(remaining, (0, "200"))
        if isinstance(value, Exception):
            raise value
        code, status = value
        return subprocess.CompletedProcess(argv, code, status)

    monkeypatch.setattr(uploader.subprocess, "run", run)
    return calls


def invoke(images):
    logs, sleeps = [], []
    result = uploader.upload_images(images, ENV, log=logs.append, sleep=sleeps.append)
    return result, logs, sleeps


def test_complete_manifest_ignores_station_and_other_images(images, monkeypatch):
    for name in ["tomsk_full_latest.png", "cumiana_latest.png", "gaia_eyes_logo_cat.png", "dailypost.png"]:
        (images / name).write_bytes(b"unrelated")
    calls = fake_curl(monkeypatch, [(0, "201")])
    result, logs, sleeps = invoke(images)
    assert result == 0
    assert len(calls) == 8
    assert {Path(argv[-1][1:]).name for argv, _ in calls} == set(uploader.REQUIRED_ASSETS)
    assert "required_ok=8 required_failed=0" in logs[-1]
    assert sleeps == []


@pytest.mark.parametrize("name", uploader.REQUIRED_ASSETS)
@pytest.mark.parametrize("invalid", ["missing", "empty", "directory", "symlink"])
def test_invalid_required_asset_fails_before_any_upload(images, monkeypatch, name, invalid):
    path = images / name
    path.unlink()
    if invalid == "empty":
        path.touch()
    elif invalid == "directory":
        path.mkdir()
    elif invalid == "symlink":
        target = images / "outside.jpg"
        target.write_bytes(b"do-not-upload")
        path.symlink_to(target)
    calls = fake_curl(monkeypatch, [])
    result, logs, _ = invoke(images)
    assert result == 1
    assert calls == []
    assert any(f"/{name} result=missing-or-invalid" in line for line in logs)


def test_missing_directory_fails_closed(tmp_path, monkeypatch):
    calls = fake_curl(monkeypatch, [])
    assert invoke(tmp_path / "missing")[0] == 1
    assert calls == []


@pytest.mark.parametrize("code", [5, 6, 7, 18, 28, 35, 52, 55, 56, 92])
def test_transient_transport_then_success_has_exact_attempts(images, monkeypatch, code):
    calls = fake_curl(monkeypatch, [(code, "000"), (0, "200")])
    result, logs, sleeps = invoke(images)
    assert result == 0
    assert len(calls) == 9
    assert calls[0] == calls[1]  # Same object, bytes and upsert headers.
    assert sleeps == [2]
    assert f"curl={code} http=000 result=retry" in logs[0]
    assert "attempt=2/3 curl=0 http=200 result=ok" in logs[1]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_http_then_success(images, monkeypatch, status):
    calls = fake_curl(monkeypatch, [(0, str(status)), (0, "201")])
    result, _, sleeps = invoke(images)
    assert result == 0
    assert len(calls) == 9
    assert sleeps == [2]


@pytest.mark.parametrize("failure", [(35, "000"), (56, "000"), (0, "429"), (0, "503")])
def test_exhaustion_fails_even_after_other_required_successes(images, monkeypatch, failure):
    calls = fake_curl(monkeypatch, [(0, "200")] + [failure] * 3)
    result, logs, sleeps = invoke(images)
    assert result == 1
    assert len(calls) == 10
    assert sleeps == [2, 4]
    assert "attempt=3/3" in logs[3] and "result=failed" in logs[3]
    assert "required_ok=7 required_failed=1" in logs[-1]


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 409])
def test_permanent_http_failure_is_not_retried_or_masked(images, monkeypatch, status):
    calls = fake_curl(monkeypatch, [(0, "200"), (0, str(status))])
    result, logs, sleeps = invoke(images)
    assert result == 1
    assert len(calls) == 8
    assert sleeps == []
    assert f"http={status} result=failed" in logs[1]
    assert "required_ok=7 required_failed=1" in logs[-1]


@pytest.mark.parametrize("code", [3, 26, 60, 77])
def test_permanent_curl_failure_not_retried(images, monkeypatch, code):
    calls = fake_curl(monkeypatch, [(code, "000")])
    result, _, sleeps = invoke(images)
    assert result == 1 and len(calls) == 8 and sleeps == []


@pytest.mark.parametrize("status", ["200", "403"])
def test_optional_legacy_output_is_attempted_but_does_not_gate(images, monkeypatch, status):
    (images / "dailypost.jpg").write_bytes(b"legacy")
    calls = fake_curl(monkeypatch, [(0, "200")] * 8 + [(0, status)])
    result, logs, _ = invoke(images)
    assert result == 0 and len(calls) == 9
    assert "optional object=" in logs[-2]
    assert f"optional_failed={int(status != '200')}" in logs[-1]


def test_request_contract_bounds_and_safe_diagnostics(images, monkeypatch):
    calls = fake_curl(monkeypatch, [])
    result, logs, _ = invoke(images)
    assert result == 0
    argv, kwargs = calls[0]
    assert argv[:2] == ["curl", "--disable"]  # Ignore per-user curlrc overrides.
    assert argv[argv.index("--request") + 1] == "PUT"
    assert argv[argv.index("--connect-timeout") + 1] == "10"
    assert argv[argv.index("--max-time") + 1] == "30"
    assert kwargs["timeout"] == 35
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert "--insecure" not in argv and "-k" not in argv and "--location" not in argv
    assert 'header = "x-upsert: true"' in kwargs["input"]
    assert 'header = "Content-Type: image/jpeg"' in kwargs["input"]
    assert f'header = "Authorization: Bearer {ENV["SUPABASE_SERVICE_ROLE_KEY"]}"' in kwargs["input"]
    assert f'header = "apikey: {ENV["SUPABASE_SERVICE_ROLE_KEY"]}"' in kwargs["input"]
    assert 'url = "https://storage.example.invalid/storage/v1/object/space-visuals/social/earthscope/latest/daily_caption.jpg"' in kwargs["input"]
    output = "\n".join(logs)
    for secret in [ENV["SUPABASE_SERVICE_ROLE_KEY"], "storage.example.invalid", "Authorization", "apikey"]:
        assert secret not in output
        assert secret not in " ".join(argv)


@pytest.mark.parametrize("error", [
    subprocess.TimeoutExpired(["curl", "synthetic-secret-never-log"], 35, output="private URL"),
    OSError("private URL synthetic-secret-never-log"),
])
def test_subprocess_errors_are_sanitized(images, monkeypatch, error):
    calls = fake_curl(monkeypatch, [error])
    result, logs, sleeps = invoke(images)
    if isinstance(error, subprocess.TimeoutExpired):
        assert result == 0 and len(calls) == 9 and sleeps == [2]
    else:
        assert result == 1 and len(calls) == 8 and sleeps == []
    assert "private URL" not in "\n".join(logs)
    assert ENV["SUPABASE_SERVICE_ROLE_KEY"] not in "\n".join(logs)


@pytest.mark.parametrize("url", [
    "https://user:secret@host.invalid", "https://host.invalid?token=secret",
    "https://host.invalid/#secret", "https://host.invalid/path",
    "https://host.invalid\nheader=secret", "not-a-url", "https://host.invalid:invalid",
])
def test_invalid_url_is_never_echoed_or_used(images, monkeypatch, url):
    calls = fake_curl(monkeypatch, [])
    logs = []
    assert uploader.upload_images(images, {**ENV, "SUPABASE_URL": url}, log=logs.append) == 1
    assert calls == []
    assert url not in "\n".join(logs) and "secret" not in "\n".join(logs)


@pytest.mark.parametrize("key", ["", "secret\nheader=injected"])
def test_invalid_credentials_fail_without_upload(images, monkeypatch, key):
    calls = fake_curl(monkeypatch, [])
    logs = []
    assert uploader.upload_images(images, {**ENV, "SUPABASE_SERVICE_ROLE_KEY": key}, log=logs.append) == 1
    assert calls == [] and "injected" not in "\n".join(logs)


def test_unexpected_curl_output_is_not_echoed_or_success(images, monkeypatch):
    calls = fake_curl(monkeypatch, [(0, "synthetic-secret-never-log")])
    result, logs, _ = invoke(images)
    assert result == 1 and len(calls) == 8
    assert ENV["SUPABASE_SERVICE_ROLE_KEY"] not in "\n".join(logs)


def test_manifest_matches_current_renderer_and_consumers():
    # Read/parse source only: importing the renderer can load live configuration.
    renderer = (ROOT / "bots/earthscope_post/gaia_eyes_viral_bot.py").read_text()
    poster = (ROOT / "bots/earthscope_post/meta_poster.py").read_text()
    tree = ast.parse((ROOT / "bots/earthscope_post/reel_builder.py").read_text())
    backgrounds = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "STORY_BACKGROUND_NAMES" for t in node.targets))
    for name in uploader.REQUIRED_ASSETS[:4]:
        assert f'"{name}"' in renderer
        assert f'/{name}"' in poster
    assert set(backgrounds) == set(uploader.REQUIRED_ASSETS[4:])
    assert 'repo_paths.extend(save_reel_backgrounds(energy))' in renderer


def test_real_curl_put_contract_against_loopback_only(images, monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            requests.append((self.path, dict(self.headers), self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(503 if len(requests) == 1 else 200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_):
            pass

    for name in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logs, sleeps = [], []
    try:
        assert uploader.upload_asset(
            images / "daily_caption.jpg", f"http://127.0.0.1:{server.server_port}",
            ENV["SUPABASE_SERVICE_ROLE_KEY"], required=True, log=logs.append, sleep=sleeps.append,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert len(requests) == 2 and sleeps == [2]
    assert requests[0] == requests[1]
    path, headers, body = requests[0]
    assert path == uploader.OBJECT_PATH_BASE + "/daily_caption.jpg"
    assert headers["Authorization"] == f'Bearer {ENV["SUPABASE_SERVICE_ROLE_KEY"]}'
    assert headers["apikey"] == ENV["SUPABASE_SERVICE_ROLE_KEY"]
    assert headers["x-upsert"] == "true" and headers["Content-Type"] == "image/jpeg"
    assert body == b"synthetic-image"
    assert "http=503 result=retry" in logs[0] and "http=200 result=ok" in logs[1]
    assert ENV["SUPABASE_SERVICE_ROLE_KEY"] not in "\n".join(logs)


@pytest.mark.parametrize("failed_asset", ["", "daily_stats.jpg"])
def test_actual_workflow_step_exit_with_fake_curl(images, tmp_path, failed_asset):
    """Execute the actual step and CLI; the only transport is a temporary stub."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/gaia_eyes_daily.yml").read_text())
    steps = workflow["jobs"]["render"]["steps"]
    step_index = next(i for i, s in enumerate(steps) if s.get("name", "").startswith("Upload rendered images"))
    assert steps[step_index + 1]["name"] == "Publish EarthScope daily JSON to media repo"
    assert not steps[step_index].get("continue-on-error", False)
    assert workflow["jobs"]["post"]["needs"] == "render"
    assert workflow["jobs"]["reel"]["needs"] == "render"
    bins = tmp_path / "bin"
    bins.mkdir()
    (bins / "python").symlink_to(sys.executable)
    stub = bins / "curl"
    stub.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
from pathlib import Path
config = sys.stdin.read()
name = Path(sys.argv[-1][1:]).name
with open(os.environ["CURL_CALLS"], "a") as f:
    f.write(json.dumps({"name": name, "put": "PUT" in sys.argv, "upsert": "x-upsert: true" in config}) + "\\n")
sys.stdout.write("403" if name == os.environ["FAIL_ASSET"] else "200")
''')
    stub.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    # Isolated environment: no real credentials or proxy configuration inherited.
    result = subprocess.run(
        ["/bin/bash", "-c", steps[step_index]["run"]], cwd=ROOT,
        env={**ENV, "PATH": str(bins), "MEDIA_REPO_PATH": str(images.parent),
             "FAIL_ASSET": failed_asset, "CURL_CALLS": str(log)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == (1 if failed_asset else 0), result.stdout + result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 8 and all(c["put"] and c["upsert"] for c in calls)
    assert ENV["SUPABASE_SERVICE_ROLE_KEY"] not in result.stdout + result.stderr
