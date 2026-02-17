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
    Return the first source in prefer_order whose payload has status "ok" and usable True.
    If none ok and usable, return first in prefer_order present in statuses.
    """
    for name in prefer_order:
        p = statuses.get(name)
        if not p or not isinstance(p, dict):
            continue
        if str(p.get("status", "")).lower() != "ok":
            continue
        # Require usable if present; default to True only when missing.
        if bool(p.get("usable", True)):
            return name
    for name in prefer_order:
        if name in statuses:
            return name
    # fallback to any
    return next(iter(statuses.keys())) if statuses else None


# --- Quality/Usable helpers ---

def _get_nested(d, path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def infer_quality_and_usable(name: str, payload: dict, peer_payload: dict | None = None) -> tuple[float, bool, list[str]]:
    """Infer a conservative quality_score (0..1) and usable flag.

    This is designed to protect downstream charts from occasional Tomsk time misalignment.
    - If extractors later emit `usable`/`quality_score`, those are respected.
    - Otherwise we infer from available debug fields and optional cross-station checks.
    """
    reasons: list[str] = []

    if not isinstance(payload, dict):
        return 0.0, False, ["payload_not_dict"]

    status = str(payload.get("status", "")).lower()
    if status != "ok":
        return 0.0, False, [f"status_{status or 'missing'}"]

    # Respect explicit flags if present
    if "quality_score" in payload or "usable" in payload:
        qs = float(payload.get("quality_score", 1.0))
        usable = bool(payload.get("usable", True))
        return max(0.0, min(1.0, qs)), usable, reasons

    # Start optimistic and apply conservative penalties
    qs = 1.0

    # Common fields
    confidence = str(payload.get("confidence", "")).lower()
    if confidence and confidence.startswith("low"):
        qs -= 0.25
        reasons.append("low_confidence")

    # Tomsk-specific: tick metrics + staleness (if present)
    if name == "tomsk":
        tick_count = _get_nested(payload, ["raw", "debug", "tick_count"], None)
        tick_quality = _get_nested(payload, ["raw", "debug", "tick_quality"], None)
        stale_hours = _get_nested(payload, ["raw", "debug", "stale_hours"], None)

        # If tick detection failed, reduce confidence (still may be usable)
        if tick_count is not None and int(tick_count) == 0:
            qs -= 0.20
            reasons.append("tick_count_0")
        if tick_quality is not None:
            try:
                tq = float(tick_quality)
                if tq <= 0:
                    qs -= 0.15
                    reasons.append("tick_quality_0")
                elif tq < 0.5:
                    qs -= 0.10
                    reasons.append("tick_quality_low")
            except Exception:
                qs -= 0.10
                reasons.append("tick_quality_parse")

        if stale_hours is not None:
            try:
                sh = float(stale_hours)
                if sh >= 6:
                    qs -= 0.20
                    reasons.append("stale_hours_ge_6")
                elif sh >= 3:
                    qs -= 0.10
                    reasons.append("stale_hours_ge_3")
            except Exception:
                qs -= 0.05
                reasons.append("stale_hours_parse")

        # Cross-station sanity: if Cumiana is OK, Tomsk fundamental should be reasonably close.
        if peer_payload and isinstance(peer_payload, dict) and str(peer_payload.get("status", "")).lower() == "ok":
            try:
                tf0 = float(payload.get("fundamental_hz"))
                cf0 = float(peer_payload.get("fundamental_hz"))
                diff = abs(tf0 - cf0)
                # If we're sampling the wrong time slice, this can jump noticeably.
                if diff > 0.6:
                    qs -= 0.60
                    reasons.append(f"f0_mismatch_vs_cumiana_{diff:.2f}")
                elif diff > 0.4:
                    qs -= 0.30
                    reasons.append(f"f0_mismatch_vs_cumiana_{diff:.2f}")
            except Exception:
                # If we can't compare, do nothing
                pass

    qs = max(0.0, min(1.0, qs))

    # Usable gate: require a minimum score. Tomsk is stricter because misalignment corrupts downstream.
    min_qs = 0.45 if name == "tomsk" else 0.30
    usable = qs >= min_qs
    if not usable:
        reasons.append("below_min_quality")

    return qs, usable, reasons

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

    # Infer and attach quality/usable flags before primary selection
    # Cumiana is treated as a stable anchor for cross-checking Tomsk when both are available.
    if isinstance(sources.get("cumiana"), dict):
        qs_c, use_c, reasons_c = infer_quality_and_usable("cumiana", sources["cumiana"], None)
        sources["cumiana"]["quality_score"] = qs_c
        sources["cumiana"]["usable"] = use_c
        sources["cumiana"]["quality_reasons"] = reasons_c

    if isinstance(sources.get("tomsk"), dict):
        peer = sources.get("cumiana") if isinstance(sources.get("cumiana"), dict) else None
        qs_t, use_t, reasons_t = infer_quality_and_usable("tomsk", sources["tomsk"], peer)
        sources["tomsk"]["quality_score"] = qs_t
        sources["tomsk"]["usable"] = use_t
        sources["tomsk"]["quality_reasons"] = reasons_t

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
        "primary_quality_score": (sources.get(primary, {}).get("quality_score") if primary else None),
        "primary_quality_reasons": (sources.get(primary, {}).get("quality_reasons") if primary else None),
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
