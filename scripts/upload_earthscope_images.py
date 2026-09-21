#!/usr/bin/env python3
"""Upload only EarthScope consumer assets, with bounded, idempotent retries.

The daily renderer's all mode writes four cards and four clean backgrounds.
The post/reel jobs need those assets before publication may continue. The older
dailypost.jpg is still fetched as a fallback, but is not written by all mode.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit


OBJECT_PATH_BASE = "/storage/v1/object/space-visuals/social/earthscope/latest"
REQUIRED_ASSETS = (
    "daily_caption.jpg",
    "daily_stats.jpg",
    "daily_affects.jpg",
    "daily_playbook.jpg",
    "reel_bg_1.jpg",
    "reel_bg_2.jpg",
    "reel_bg_3.jpg",
    "reel_bg_4.jpg",
)
OPTIONAL_ASSETS = ("dailypost.jpg",)
MAX_ATTEMPTS = 3
CONNECT_TIMEOUT_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 30
PROCESS_TIMEOUT_SECONDS = 35
# DNS/connect, incomplete transfer, timeout, handshake reset, empty response,
# send/receive and HTTP/2 stream failures. Certificate errors (60) are permanent.
RETRYABLE_CURL_CODES = frozenset({5, 6, 7, 18, 28, 35, 52, 55, 56, 92})


def storage_config(environ):
    """Validate without echoing credential or URL values on failure."""
    base = environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    try:
        parsed = urlsplit(base)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.port != 0
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and not any(char.isspace() or ord(char) < 32 for char in base)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("SUPABASE_URL must be an HTTP(S) origin without credentials, path or query")
    if not key or any(ord(char) < 32 or ord(char) == 127 for char in key):
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY is missing or invalid")
    return base, key


def usable_asset(path):
    try:
        return not path.is_symlink() and path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def put_once(path, base, key):
    # Keep credentials out of process arguments. Never print this config, raw
    # stderr, response bodies, or subprocess exceptions (which can contain it).
    config = "\n".join(
        f"{name} = {json.dumps(value)}"
        for name, value in (
            ("url", f"{base}{OBJECT_PATH_BASE}/{path.name}"),
            ("header", f"Authorization: Bearer {key}"),
            ("header", f"apikey: {key}"),
            ("header", "x-upsert: true"),
            ("header", "Content-Type: image/jpeg"),
        )
    ) + "\n"
    try:
        result = subprocess.run(
            [
                "curl", "--disable", "--silent", "--output", os.devnull,
                "--write-out", "%{http_code}", "--request", "PUT",
                "--connect-timeout", str(CONNECT_TIMEOUT_SECONDS),
                "--max-time", str(REQUEST_TIMEOUT_SECONDS),
                "--config", "-", "--data-binary", f"@{path}",
            ],
            input=config,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 28, 0
    except OSError:
        # Local executable/config failure is not a transport retry.
        return -1, 0
    status = result.stdout.strip()
    return result.returncode, int(status) if re.fullmatch(r"[0-9]{3}", status) else 0


def upload_asset(path, base, key, *, required, sleep, log):
    kind = "required" if required else "optional"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        curl_code, status = put_once(path, base, key)
        ok = curl_code == 0 and status in {200, 201}
        retryable = curl_code in RETRYABLE_CURL_CODES or (
            curl_code == 0 and (status == 429 or 500 <= status <= 599)
        )
        retry = not ok and retryable and attempt < MAX_ATTEMPTS
        outcome = "ok" if ok else "retry" if retry else "failed"
        log(
            f"[upload] {kind} object={OBJECT_PATH_BASE}/{path.name} "
            f"attempt={attempt}/{MAX_ATTEMPTS} curl={curl_code} "
            f"http={status:03d} result={outcome}"
        )
        if ok:
            return True
        if not retry:
            return False
        sleep(2 ** attempt)
    return False


def upload_images(image_dir, environ, *, sleep=time.sleep, log=print):
    try:
        base, key = storage_config(environ)
    except ValueError as exc:
        log(f"[upload] error: {exc}")
        return 1

    # Preflight the whole required set before changing any remote objects.
    missing = [name for name in REQUIRED_ASSETS if not usable_asset(image_dir / name)]
    if missing:
        for name in missing:
            log(f"[upload] required object={OBJECT_PATH_BASE}/{name} result=missing-or-invalid")
        log(f"[upload] failed preflight: required_missing={len(missing)} uploaded=0")
        return 1

    required_ok = 0
    optional_ok = 0
    optional_failed = 0
    for name in REQUIRED_ASSETS:
        required_ok += upload_asset(image_dir / name, base, key, required=True, sleep=sleep, log=log)
    for name in OPTIONAL_ASSETS:
        path = image_dir / name
        if not usable_asset(path):
            log(f"[upload] optional object={OBJECT_PATH_BASE}/{name} result=absent-or-invalid-skipped")
            continue
        if upload_asset(path, base, key, required=False, sleep=sleep, log=log):
            optional_ok += 1
        else:
            optional_failed += 1
    failed = len(REQUIRED_ASSETS) - required_ok
    log(
        f"[upload] done required_ok={required_ok} required_failed={failed} "
        f"optional_ok={optional_ok} optional_failed={optional_failed}"
    )
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-dir", type=Path, required=True)
    args = parser.parse_args()
    return upload_images(args.image_dir, os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
