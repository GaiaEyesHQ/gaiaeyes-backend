#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, argparse, glob, math
from datetime import datetime, timezone

def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def is_ok(feed):
    return str(feed.get("status","")).lower() == "ok"

def parse_iso(ts):
    try:
        # Python 3.11+ supports fromisoformat with Z; fallback:
        return datetime.fromisoformat(ts.replace("Z","+00:00"))
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser(description="Gaia Eyes Feed Validator")
    ap.add_argument("--in", dest="inp", required=True, help="Input JSON feed")
    ap.add_argument("--history-dir", default=None, help="Folder with prior OK feeds")
    ap.add_argument("--history-window", type=int, default=12, help="How many recent OK feeds to use")
    ap.add_argument("--delta-threshold-f1", type=float, default=2.5)
    ap.add_argument("--delta-threshold-harm", type=float, default=4.0)
    ap.add_argument("--z-threshold", type=float, default=3.5)
    ap.add_argument("--max-age-hours", type=float, default=6.0)
    ap.add_argument("--require-overlay", action="store_true")
    ap.add_argument("--harmonic-check-mode", choices=["canonical","multiple"], default="canonical",
                    help="canonical (Tomsk targets) or multiple (n×F1). Default: canonical")
    args = ap.parse_args()

    info, warn, fail = [], [], []

    feed = load_json(args.inp)

    # ---------- Basic presence ----------
    overlay = feed.get("overlay_path") or feed.get("raw", {}).get("overlay_path")
    if args.require_overlay and not overlay:
        fail.append("overlay_path missing (required).")

    # Respect status
    status = feed.get("status","").lower()
    if status and status != "ok":
        info.append(f"Non-OK status: {status}. Skipping harmonic checks.")
        print_result(info, warn, fail)
        return 0 if not fail else 1

    # Pull top-level fields (preferred). If absent, try raw→(top-level)
    fundamental = feed.get("fundamental_hz")
    harmonics   = feed.get("harmonics_hz") or {}
    amp_idx     = feed.get("amplitude_idx")

    if fundamental is None:
        warn.append("fundamental_hz missing.")  # warn (Tomsk uses canonical F1 anyway)
    if not harmonics:
        fail.append("harmonics_hz missing or empty.")
    if not isinstance(amp_idx, dict):
        fail.append("amplitude_idx missing or not an object ({} if not available).")

    # ---------- Freshness ----------
    lm = feed.get("last_modified")
    if not lm:
        lm = feed.get("raw", {}).get("last_modified")
    if lm:
        t = parse_iso(lm)
        if t:
            age_h = (datetime.now(timezone.utc) - t).total_seconds()/3600.0
            if age_h > args.max_age_hours:
                warn.append(f"Feed older than {args.max_age_hours}h (age={age_h:.2f}h).")
        else:
            warn.append("last_modified present but unparsable.")

    # ---------- Harmonic checks ----------
    if harmonics:
        if args.harmonic_check_mode == "canonical":
            # Tomsk canonical guide bands (Hz) and tolerances (Hz)
            CANON = {"F1": 7.8, "F2": 14.3, "F3": 20.8, "F4": 27.3, "F5": 33.8}
            TOL   = {"F1": 1.0, "F2": 1.2,  "F3": 1.5,  "F4": 2.0,  "F5": 2.4}
            for k, target in CANON.items():
                if k in harmonics:
                    val = harmonics[k]
                    if not isinstance(val, (int, float)):
                        warn.append(f"{k} is not numeric.")
                        continue
                    if abs(val - target) > TOL[k]:
                        warn.append(f"{k} ({val:.2f}) deviates from canonical {target:.2f} by >{TOL[k]:.1f} Hz.")
        else:
            # Legacy: compare to multiples of F1
            if isinstance(fundamental, (int,float)):
                targets = {"F2": (2, 1.2), "F3": (3, 1.5), "F4": (4, 2.0), "F5": (5, 2.4)}
                for k, (n, tol) in targets.items():
                    if k in harmonics:
                        val = harmonics[k]
                        if not isinstance(val, (int,float)):
                            warn.append(f"{k} is not numeric.")
                            continue
                        target = n * fundamental
                        if abs(val - target) > tol:
                            warn.append(f"{k} ({val:.2f}) not ~{n}×F1 ({target:.2f}) within ±{tol:.1f} Hz.")
            else:
                warn.append("Multiple-of-F1 check requested but fundamental_hz not numeric; skipping.")

    # ---------- History delta checks (simple) ----------
    if args.history_dir and os.path.isdir(args.history_dir):
        files = sorted(glob.glob(os.path.join(args.history_dir, "*.json")))
        # load recent OK feeds (excluding current file if inside same folder)
        recent = []
        for p in reversed(files):
            try:
                d = load_json(p)
                if is_ok(d):
                    recent.append(d)
                    if len(recent) >= args.history_window:
                        break
            except Exception:
                continue
        if not recent:
            info.append(f"No prior OK feeds in history: {args.history_dir}")
        else:
            prev = recent[0]
            prev_f1 = prev.get("fundamental_hz")
            prev_h  = prev.get("harmonics_hz") or {}
            if isinstance(fundamental,(int,float)) and isinstance(prev_f1,(int,float)):
                if abs(fundamental - prev_f1) > args.delta_threshold_f1:
                    warn.append(f"ΔF1={fundamental - prev_f1:+.2f} exceeds {args.delta_threshold_f1} Hz vs previous.")
            for k, v in harmonics.items():
                pv = prev_h.get(k)
                if isinstance(v,(int,float)) and isinstance(pv,(int,float)):
                    if abs(v - pv) > args.delta_threshold_harm:
                        warn.append(f"Δ{k}={v - pv:+.2f} exceeds {args.delta_threshold_harm} Hz vs previous.")

    # ---------- Output ----------
    print("\n== Gaia Eyes Feed Validation ==\n")
    if info:
        print("INFO:")
        for m in info: print(f"  - {m}")
        print()
    if warn:
        print("WARN:")
        for m in warn: print(f"  - {m}")
        print()
    if fail:
        print("FAIL:")
        for m in fail: print(f"  - {m}")
        print()

    result = "FAIL" if fail else ("WARN" if warn else "PASS")
    print(f"Result: {result}")
    return 1 if fail else 0

def print_result(info, warn, fail):
    print("\n== Gaia Eyes Feed Validation ==\n")
    if info:
        print("INFO:")
        for m in info: print(f"  - {m}")
        print()
    if warn:
        print("WARN:")
        for m in warn: print(f"  - {m}")
        print()
    if fail:
        print("FAIL:")
        for m in fail: print(f"  - {m}")
        print()
    print(f"Result: {'FAIL' if fail else ('WARN' if warn else 'PASS')}")

if __name__ == "__main__":
    sys.exit(main())
