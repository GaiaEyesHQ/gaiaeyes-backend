#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-source Schumann orchestrator.
- Tries sources in the given order (env PREFER or --prefer).
- Records ALL usable sources in the output JSON under "sources".
- Picks PRIMARY = first OK source in the preference order.
- Uses the PRIMARY's overlay as the top-level overlay_path.

Args:
  --out OUT.json
  --overlay OVERLAY.png
  --prefer "tomsk,cumiana"   (or set env PREFER=tomsk,cumiana)
  --insecure --verbose --no-cache
  --cumiana-img URL          (override cumiana image)

Env passthrough:
  TOMSK_TIME_BIAS_MINUTES   (e.g., -65)
"""

import os, sys, json, shlex, subprocess, argparse, tempfile, shutil
from datetime import datetime, timezone

def run(cmd, verbose=False):
    if verbose:
        print("[exec]", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def build_cmd(source, out_path, overlay_path, insecure, verbose, extras):
    base = [sys.executable, f"{source}_extractor.py", "--out", out_path, "--overlay", overlay_path]
    if insecure: base.append("--insecure")
    if verbose:  base.append("--verbose")
    if extras:   base += extras
    return base

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlay", default=None)
    ap.add_argument("--prefer", default=os.getenv("PREFER", "tomsk,cumiana"))
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    # Note: argparse transforms "--cumiana-img" -> attribute "cumiana_img"
    ap.add_argument("--cumiana-img", dest="cumiana_img", default=None)
    args = ap.parse_args()

    prefer = [s.strip() for s in args.prefer.split(",") if s.strip()]
    if not prefer:
        prefer = ["tomsk","cumiana"]

    tmpdir = tempfile.mkdtemp(prefix="schumann_multi_")
    collected = {}
    primary_key = None
    primary_overlay = None

    try:
        for src in prefer:
            ojson = os.path.join(tmpdir, f"{src}.json")
            oimg  = os.path.join(tmpdir, f"{src}.png")
            extras = []
            if src == "cumiana" and args.cumiana_img:
                extras += ["--img-url", args.cumiana_img]

            cmd = build_cmd(src, ojson, oimg, args.insecure, args.verbose, extras)
            rc, out, err = run(cmd, verbose=args.verbose)

            if args.verbose and err:
                print(f"[{src}] stderr:\n{err}", flush=True)

            # Load the extractor's JSON from disk; fall back to stdout if needed
            payload = None
            try:
                with open(ojson, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                try:
                    payload = json.loads(out)
                except Exception:
                    payload = {
                        "status":"down",
                        "source":src,
                        "message": f"{src} extractor failed (rc={rc})"
                    }

            collected[src] = payload

            # Choose primary = first OK in preference order
            if primary_key is None and payload.get("status") == "ok":
                primary_key = src
                if args.overlay:
                    try:
                        shutil.copyfile(oimg, args.overlay)
                        primary_overlay = args.overlay
                    except Exception:
                        primary_overlay = None

        # Compose final
        if primary_key is None:
            final = {
                "status": "no_fresh_source",
                "message": f"No fresh Schumann spectrogram available. Tried: {', '.join(prefer)}.",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "overlay_path": primary_overlay,
                "sources": collected
            }
        else:
            primary = collected[primary_key]
            final = {
                "status": "ok",
                "primary": primary_key,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "overlay_path": primary_overlay or primary.get("overlay_path"),
                "fundamental_hz": primary.get("fundamental_hz"),
                "harmonics_hz": primary.get("harmonics_hz", {}),
                "amplitude_idx": primary.get("amplitude_idx", {}),
                "confidence": primary.get("confidence"),
                "sources": collected
            }

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(final, f, ensure_ascii=False, indent=2)
        print(json.dumps(final, ensure_ascii=False, indent=2))

        return 0 if final["status"] == "ok" else 3

    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

if __name__ == "__main__":
    sys.exit(main())
