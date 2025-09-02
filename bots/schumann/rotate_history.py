#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copy the unified feed (and its overlay) into a history folder with a timestamped name.

- Uses the feed's `timestamp_utc` when available; falls back to "now".
- Copies the JSON and overlay PNG (if present).
- Optional retention: keep only the most recent N snapshots.

Usage:
  python rotate_history.py \
    --in runs/schumann_now.json \
    --overlay runs/schumann_overlay.png \
    --history-dir runs/history \
    --keep 200
"""

import argparse, json, os, shutil, datetime as dt, glob, sys

def iso_to_dt(s: str):
    if not s: return None
    try:
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="Unified JSON from schumann_multi.py")
    ap.add_argument("--overlay", default=None, help="Overlay path that pairs with the feed")
    ap.add_argument("--history-dir", required=True, help="Where to write timestamped snapshots")
    ap.add_argument("--keep", type=int, default=200, help="Keep only most recent N snapshots (0 = unlimited)")
    args = ap.parse_args()

    os.makedirs(args.history_dir, exist_ok=True)

    # read current feed
    with open(args.in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # derive timestamp
    ts = iso_to_dt(data.get("timestamp_utc"))
    if ts is None:
        ts = dt.datetime.now(dt.timezone.utc)
    # format: YYYYmmdd_HHMMSSZ
    ts_tag = ts.astimezone(dt.timezone.utc).strftime("%Y%m%d_%H%M%SZ")

    # build target paths
    base = f"feed_{ts_tag}"
    out_json = os.path.join(args.history_dir, base + ".json")
    out_png  = os.path.join(args.history_dir, base + ".png")

    # copy JSON
    shutil.copy2(args.in_path, out_json)

    # copy overlay (prefer explicit arg; else read from JSON if present)
    overlay_src = args.overlay or data.get("overlay_path")
    if overlay_src and os.path.exists(overlay_src):
        shutil.copy2(overlay_src, out_png)

    # optional retention pruning
    if args.keep > 0:
        snaps = sorted(glob.glob(os.path.join(args.history_dir, "feed_*.json")))
        extra = max(0, len(snaps) - args.keep)
        for p in snaps[:extra]:
            png = p[:-5] + ".png"
            try:
                os.remove(p)
                if os.path.exists(png): os.remove(png)
            except Exception:
                pass

    print(json.dumps({
        "status": "ok",
        "written": {"json": out_json, "overlay": out_png if os.path.exists(out_png) else None},
        "keep": args.keep
    }, indent=2))

if __name__ == "__main__":
    sys.exit(main())
