#!/usr/bin/env python3
"""HEAD-check the external assets listed in docs/web/ASSET_INVENTORY.json."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Iterable, Tuple
from urllib.parse import urlparse

import requests

UA = "GaiaEyes-Codex/1.0 (+https://gaiaeyes.com)"
TIMEOUT = 20


def iter_urls(inventory: dict) -> Iterable[str]:
    seen = set()
    for section, payload in inventory.items():
        for asset in payload.get("assets", []):
            url = asset.get("url")
            if not url:
                continue
            host = urlparse(url).hostname or ""
            if host.endswith("gaiaeyes.com"):
                # Internal assets are not checked by this job.
                continue
            if url in seen:
                continue
            seen.add(url)
            yield url


def head_request(url: str) -> Tuple[int, float]:
    """Return (status_code, elapsed_ms) using HEAD with GET fallback."""
    for method in ("HEAD", "GET"):
        try:
            start = time.perf_counter()
            resp = requests.request(
                method,
                url,
                headers={"User-Agent": UA, "Accept": "*/*"},
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            elapsed = (time.perf_counter() - start) * 1000
        except requests.RequestException as exc:  # pragma: no cover - network dependent
            last_exc = exc
            continue
        else:
            return resp.status_code, elapsed
    raise RuntimeError(f"{url}: request failed ({last_exc})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inventory",
        default="docs/web/ASSET_INVENTORY.json",
        help="Path to the asset inventory JSON (default: %(default)s)",
    )
    args = parser.parse_args()

    try:
        with open(args.inventory, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        print(f"error: unable to read {args.inventory}: {exc}", file=sys.stderr)
        return 1

    failures = []
    total = 0
    for url in iter_urls(data):
        total += 1
        try:
            status, elapsed = head_request(url)
        except Exception as exc:  # pragma: no cover - network dependent
            failures.append((url, str(exc)))
            continue
        if status >= 400:
            failures.append((url, f"HTTP {status}"))
        else:
            print(f"OK {status:3d} {elapsed:7.1f} ms {url}")

    if failures:
        print("\nAsset check FAILED:", file=sys.stderr)
        for url, reason in failures:
            print(f" - {url}: {reason}", file=sys.stderr)
        print(f"Checked {total} URLs; {len(failures)} failed.", file=sys.stderr)
        return 2

    print(f"\nAll {total} external assets responded <400.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
