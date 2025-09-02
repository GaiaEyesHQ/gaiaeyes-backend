#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schumann_multi.py
- Runs BOTH Tomsk and Cumiana extractors every time
- Saves two overlays: tomsk_overlay.png and cumiana_overlay.png (in the overlay dir you pass)
- Writes a combined JSON with both sources under "sources", and selects a "primary"
- Honors preference order for primary selection: first OK source in --prefer list
"""

import os, sys, json, argparse, tempfile, subprocess, shutil
from datetime import datetime, timezone

HERE = os.path.abspath(os.path.dirname(__file__))

def run_extractor(
    name: str,
    script: str,
    out_json_path: str,
    overlay_path: str,
    insecure: bool,
    verbose: bool,
    extra_args=None,
) -> tuple[int, dict]:
    """
    Run a single extractor script, return (returncode, parsed_json_or_error_payload).
    The extractor writes directly to out_json_path and overlay_path.
    """
    cmd = [sys.executable, script, "--out", out_json_path, "--overlay", overlay_path]
    if insecure:
        cmd.append("--insecure")
    if verbose:
        cmd.append("--verbose")
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        rc = proc.returncode
        # Try to read JSON if it exists
        payload = {}
        if os.path.exists(out_json_path):
            try:
                with open(out_json_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception as e:
                payload = {
                    "status": "error",
                    "message": f"Failed to parse {name} JSON: {e}",
                    "stdout": proc.stdout[-2000:],
                    "stderr": proc.stderr[-2000:],
                }
        else:
            payload = {
                "status": "error",
                "message": f"{name} extractor did not produce JSON.",
                "stdout": proc.stdout[-2000:],
                "stderr": proc.stderr[-2000:],
            }

        # Attach basic runner logs when verbose for easier debugging
        if verbose:
            print(f"[exec] {' '.join(cmd)}", file=sys.stderr)
            if proc.stderr.strip():
                print(f"[{name}] stderr:\n{proc.stderr}", file=sys.stderr)
            if proc.stdout.strip():
                print(f"[{name}] stdout:\n{proc.stdout}", file=sys.stderr)

        return rc, payload
    except Exception as e:
        return 1, {"status": "error", "message": f"Failed to run {name}: {e}"}

def pick_primary(prefer_order, statuses):
    """
    prefer_order: list like ["tomsk", "cumiana"]
    statuses: dict name -> payload
    Return the first source in prefer_order whose payload has status "ok".
    If none ok, return first in prefer_order present in statuses.
    """
    for name in prefer_order:
        p = statuses.get(name)
        if p and str(p.get("status","")).lower() == "ok":
            return name
    for name in prefer_order:
        if name in statuses:
            return name
    # fallback to any
    return next(iter(statuses.keys())) if statuses else None

def main():
    ap = argparse.ArgumentParser(description="Run Tomsk + Cumiana and merge outputs")
    ap.add_argument("--out", required=True, help="Combined JSON output path (e.g. runs/schumann_now.json)")
    ap.add_argument("--overlay", required=True, help="Overlay *directory or file*. We'll write tomsk_overlay.png & cumiana_overlay.png in this dir.")
    ap.add_argument("--prefer", default="tomsk,cumiana", help="Primary preference order, comma-separated (default: tomsk,cumiana)")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-cache", action="store_true", help="(Reserved) No-op; kept for compatibility")
    # Optional pass-throughs to child extractors (add more if you need)
    ap.add_argument("--time-bias-minutes", type=float, default=None, help="Pass to Tomsk extractor if set")
    ap.add_argument("--guard-minutes", type=float, default=None, help="Pass to Tomsk extractor if set")
    ap.add_argument("--accept-minutes", type=float, default=None, help="Pass to Tomsk extractor if set")
    ap.add_argument("--pph-source", choices=["auto","day","ticks"], default=None, help="Pass to Tomsk extractor if set")
    ap.add_argument("--snap-threshold-minutes", type=float, default=None, help="Pass to Tomsk extractor if set")
    ap.add_argument("--draw-debug", action="store_true", help="Pass to Tomsk extractor")
    # Cumiana fixed offset (columns from right edge); if set, pass to Cumiana
    ap.add_argument("--cumiana-fixed-offset", type=int, default=None, help="Pass to Cumiana extractor as --fixed-offset")
    args = ap.parse_args()

    # Normalize overlay dir
    overlay_dir = args.overlay
    # If user provided a file path (e.g. runs/schumann_overlay.png), use its directory
    if overlay_dir.endswith(".png") or overlay_dir.endswith(".jpg") or overlay_dir.endswith(".jpeg"):
        overlay_dir = os.path.dirname(overlay_dir)
    if not overlay_dir:
        overlay_dir = "."

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(overlay_dir, exist_ok=True)

    # Build final overlay paths (written directly by child extractors)
    tomsk_overlay = os.path.join(overlay_dir, "tomsk_overlay.png")
    cumiana_overlay = os.path.join(overlay_dir, "cumiana_overlay.png")

    # Child extractor scripts
    tomsk_script   = os.path.join(HERE, "tomsk_extractor.py")
    cumiana_script = os.path.join(HERE, "cumiana_extractor.py")

    # Temp JSONs (we’ll let children write directly to final overlays, but JSONs go to temp first)
    with tempfile.TemporaryDirectory() as td:
        tomsk_json_tmp   = os.path.join(td, "tomsk.json")
        cumiana_json_tmp = os.path.join(td, "cumiana.json")

        # Build passthrough args for Tomsk
        tomsk_extra = []
        if args.time_bias_minutes is not None:
            tomsk_extra += ["--time-bias-minutes", str(args.time_bias_minutes)]
        if args.guard_minutes is not None:
            tomsk_extra += ["--guard-minutes", str(args.guard_minutes)]
        if args.accept_minutes is not None:
            tomsk_extra += ["--accept-minutes", str(args.accept_minutes)]
        if args.pph_source is not None:
            tomsk_extra += ["--pph-source", args.pph_source]
        if args.snap_threshold_minutes is not None:
            tomsk_extra += ["--snap-threshold-minutes", str(args.snap_threshold_minutes)]
        if args.draw_debug:
            tomsk_extra += ["--draw-debug"]

        # Build passthrough args for Cumiana
        cumiana_extra = []
        if args.cumiana_fixed_offset is not None:
            cumiana_extra += ["--fixed-offset", str(args.cumiana_fixed_offset)]

        # Run Tomsk
        rc_tomsk, payload_tomsk = run_extractor(
            "tomsk",
            tomsk_script,
            tomsk_json_tmp,
            tomsk_overlay,
            insecure=args.insecure,
            verbose=args.verbose,
            extra_args=tomsk_extra,
        )

        # Run Cumiana
        rc_cumiana, payload_cumiana = run_extractor(
            "cumiana",
            cumiana_script,
            cumiana_json_tmp,
            cumiana_overlay,
            insecure=args.insecure,
            verbose=args.verbose,
            extra_args=cumiana_extra,
        )

        # Collect
        sources = {}
        if payload_tomsk:
            # Ensure overlay_path points to our final overlay path
            if isinstance(payload_tomsk, dict):
                payload_tomsk["overlay_path"] = tomsk_overlay
            sources["tomsk"] = payload_tomsk

        if payload_cumiana:
            if isinstance(payload_cumiana, dict):
                payload_cumiana["overlay_path"] = cumiana_overlay
            sources["cumiana"] = payload_cumiana

    # Determine overall status
    any_ok = any(str(p.get("status","")).lower() == "ok" for p in sources.values())
    overall_status = "ok" if any_ok else "no_fresh_source"

    # Primary selection
    prefer_order = [s.strip().lower() for s in args.prefer.split(",") if s.strip()]
    primary = pick_primary(prefer_order, sources)

    # Top-level overlay_path for convenience = primary overlay (if present)
    overlay_path = None
    if primary and isinstance(sources.get(primary), dict):
        overlay_path = sources[primary].get("overlay_path")

    combined = {
        "status": overall_status,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "primary": primary,
        "overlay_path": overlay_path,
        "sources": sources,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    if args.verbose:
        print(json.dumps(combined, indent=2))

    # Exit code: 0 if at least one OK, else 1
    return 0 if any_ok else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
