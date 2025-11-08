#!/usr/bin/env python3
"""Quick database connectivity diagnostic helper.

Run this from the repository root (or any environment with settings configured)
 to confirm whether pgBouncer and the direct fallback are reachable. The script
 mirrors the backend's own connection logic so we test the same DSNs that the
 service will use.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict

from app.db import diagnose_connectivity, get_pool_configuration


async def _run(timeout: float) -> Dict[str, Any]:
    config = get_pool_configuration()
    results = await diagnose_connectivity(timeout=timeout)
    return {
        "configuration": config,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for each connection probe (default: 5.0)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    args = parser.parse_args(argv)

    payload = asyncio.run(_run(args.timeout))
    dumps = json.dumps(payload, indent=2 if args.pretty else None, sort_keys=args.pretty)
    print(dumps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
