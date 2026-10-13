#!/usr/bin/env python3
"""Publish verified quake history to Storage, or fetch it for the media mirror."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.history_json import validate_quakes_history

OBJECT_KEY = "data/quakes_history.json"


def public_url():
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        raise ValueError("SUPABASE_URL is required")
    bucket = os.environ.get("BUCKET", "space-visuals")
    return f"{base}/storage/v1/object/public/{bucket}/{OBJECT_KEY}"


def read_public(url):
    # Anonymous read-back checks the same public path the consumer needs.
    request = urllib.request.Request(
        f"{url}?v={time.time_ns()}", headers={"Cache-Control": "no-cache"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ValueError(f"public history retrieval failed (HTTP {exc.code})") from exc
    except OSError as exc:
        raise ValueError("public history retrieval failed (network error)") from exc
    data = json.loads(raw)
    validate_quakes_history(data)
    return raw, data


def sync(mode, path):
    url = public_url()
    if mode == "publish":
        # Validate before any write. Never fall back to the image uploader.
        raw = path.read_bytes()
        data = json.loads(raw)
        validate_quakes_history(data)
        from scripts.supabase_storage import upload_bytes

        try:
            upload_bytes(OBJECT_KEY, raw, "application/json")
        except Exception as exc:
            # Storage errors can contain server response bodies. Do not log them.
            raise ValueError(f"history upload failed ({type(exc).__name__})") from exc
        _, published = read_public(url)
        if published != data:
            raise ValueError("public history does not match the generated JSON")
    else:
        raw, data = read_public(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    newest = max(day for day, count in data["series"]["all_daily"] if count > 0)
    print(f"[quakes_history] {mode} verified: timestamp_utc={data['timestamp_utc']} "
          f"newest_quake_day={newest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("publish", "fetch"))
    args = parser.parse_args()
    path = Path(os.environ.get("OUTPUT_JSON_PATH", "quakes_history.json"))
    try:
        sync(args.mode, path)
    except (OSError, ValueError) as exc:
        print(f"[quakes_history] {args.mode} failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
