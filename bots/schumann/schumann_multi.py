#!/usr/bin/env python3
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout, p.stderr

def load_json(path):
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except Exception:
        return None

def status_ok(j):
    return isinstance(j, dict) and j.get("status") == "ok"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefer", default="tomsk,cumiana",
                    help="Comma list of primary preference, e.g. 'tomsk,cumiana'")
    ap.add_argument("--out", required=True, help="Combined feed JSON path")
    ap.add_argument("--overlay", required=False, help="(optional) not used; each source writes its own overlay")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    # Paths for per-source artifacts
    tomsk_json   = os.path.join(HERE, "tomsk_now.json")
    tomsk_png    = os.path.join(HERE, "tomsk_overlay.png")
    cumiana_json = os.path.join(HERE, "cumiana_now.json")
    cumiana_png  = os.path.join(HERE, "cumiana_overlay.png")

    # 1) Run Tomsk
    rc_t, out_t, err_t = run([
        sys.executable, os.path.join(HERE, "tomsk_extractor.py"),
        "--out", tomsk_json, "--overlay", tomsk_png
    ] + (["--insecure"] if args.insecure else []) + (["--verbose"] if args.verbose else []))

    if args.verbose:
        print("[tomsk] rc=", rc_t); print(out_t); print(err_t, file=sys.stderr)

    # 2) Run Cumiana
    rc_c, out_c, err_c = run([
        sys.executable, os.path.join(HERE, "cumiana_extractor.py"),
        "--out", cumiana_json, "--overlay", cumiana_png
    ] + (["--insecure"] if args.insecure else []) + (["--verbose"] if args.verbose else []))

    if args.verbose:
        print("[cumiana] rc=", rc_c); print(out_c); print(err_c, file=sys.stderr)

    tj = load_json(tomsk_json)
    cj = load_json(cumiana_json)

    # Decide primary by preference
    prefer = [s.strip().lower() for s in args.prefer.split(",") if s.strip()]
    sources = {
        "tomsk": tj if isinstance(tj, dict) else None,
        "cumiana": cj if isinstance(cj, dict) else None,
    }
    primary = None
    for name in prefer:
        j = sources.get(name)
        if status_ok(j):
            primary = name
            break
    if primary is None:
        # if neither ok, still emit a combined status
        out = {
            "status": "no_fresh_source",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "message": "Neither Tomsk nor Cumiana produced OK status.",
            "sources": sources,
        }
        with open(args.out,"w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
        if args.verbose: print(json.dumps(out, indent=2))
        return 0

    pj = sources[primary]
    out = {
        "status": "ok",
        "primary": primary,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "overlay_path": f"{primary}_overlay.png",
        "fundamental_hz": pj.get("fundamental_hz"),
        "harmonics_hz": pj.get("harmonics_hz", {}),
        "confidence": pj.get("confidence"),
        "sources": {
            "tomsk": {
                "json": "tomsk_now.json",
                "overlay": "tomsk_overlay.png",
                "status": sources["tomsk"].get("status") if sources["tomsk"] else None,
            },
            "cumiana": {
                "json": "cumiana_now.json",
                "overlay": "cumiana_overlay.png",
                "status": sources["cumiana"].get("status") if sources["cumiana"] else None,
            }
        }
    }
    with open(args.out,"w",encoding="utf-8") as f:
        json.dump(out,f,ensure_ascii=False,indent=2)
    if args.verbose: print(json.dumps(out, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
