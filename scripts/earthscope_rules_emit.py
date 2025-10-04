#!/usr/bin/env python3
import os, sys, json, pathlib
from datetime import datetime, timezone

MEDIA_DIR = os.getenv("MEDIA_DIR", "../gaiaeyes-media")  # checked-out media repo path
OUT_PATH  = os.getenv("OUTPUT_JSON_PATH", f"{MEDIA_DIR}/data/earthscope.json")

def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _safe(v, t, d=None):
    try:
        return t(v)
    except Exception:
        return d

def combine_schumann(sch):
    # Prefer Cumiana, but show both; confidence-weighted blend (simple form)
    if not sch or "sources" not in sch: return None
    s = sch["sources"]; t = s.get("tomsk", {}) or {}; c = s.get("cumiana", {}) or {}
    t_f1, c_f1 = t.get("fundamental_hz"), c.get("fundamental_hz")
    weights = {"cumiana": 0.3, "tomsk": 0.7}
    if c_f1 is not None and t_f1 is not None:
        combined = (float(c_f1)*weights["cumiana"] + float(t_f1)*weights["tomsk"]) / (weights["cumiana"]+weights["tomsk"])
        primary = "tomsk"
        delta = abs(float(t_f1)-float(c_f1))
    elif c_f1 is not None:
        combined, primary, delta = float(c_f1), "cumiana", None
    elif t_f1 is not None:
        combined, primary, delta = float(t_f1), "tomsk", None
    else:
        return None
    return {
        "combined": {
            "f1_hz": round(combined,2), "primary": primary, "delta_hz": round(delta,2) if delta is not None else None
        },
        "sources": {
            "cumiana": {"f1_hz": c_f1, "image": "https://gennwu.github.io/gaiaeyes-media/images/cumiana_latest.png"},
            "tomsk":   {"f1_hz": t_f1, "image": "https://gennwu.github.io/gaiaeyes-media/images/tomsk_latest.png"}
        }
    }

def rules(space, flarecme, sch):
    now = space or {}
    kp   = _safe(now.get("now",{}).get("kp"), float, None)
    sw   = _safe(now.get("now",{}).get("solar_wind_kms"), float, None)
    bz   = _safe(now.get("now",{}).get("bz_nt"), float, None)
    g72  = (space or {}).get("next_72h", {}).get("headline") or ""
    flare= (flarecme or {}).get("flares", {}).get("max_24h")
    cmeh = (flarecme or {}).get("cmes", {}).get("headline") or ""

    # scientific lines
    sci = []
    if kp is not None: sci.append(f"Kp {kp:.1f}" + (" (active)" if kp>=4 else ""))
    if sw is not None: sci.append(f"Solar wind ~{int(round(sw))} km/s")
    if bz is not None: sci.append(f"Bz {bz:+.1f} nT")
    if flare: sci.append(f"Max flare 24h: {flare}")
    if cmeh: sci.append(cmeh)

    # mystical lines (gentle & honest)
    myst = []
    elevated = (kp and kp>=5) or (sw and sw>=650) or (bz is not None and bz<=-8) or (flare and flare.startswith(("M","X")))
    if elevated:
        myst.append("Field feels lively—some sensitives may feel wired or edgy.")
        myst.append("Grounding + breath breaks can help you stay centered.")
    else:
        myst.append("Field is fairly steady today.")
        myst.append("Light movement, water, and brief outdoor time support balance.")

    # self-care nudges (max 2)
    care = []
    if kp and kp>=5: care.append("Take a 5–10 min grounding break")
    if sw and sw>=650: care.append("Hydrate + short daylight break")
    if flare and flare.startswith(("M","X")) and len(care)<2: care.append("Plan short rest intervals")
    if not care: care.append("Easy movement + hydration")

    return sci[:4], myst[:3], care[:2]

def main():
    sp  = _load(f"{MEDIA_DIR}/data/space_weather.json")
    fc  = _load(f"{MEDIA_DIR}/data/flares_cmes.json")
    sch = _load(f"{MEDIA_DIR}/data/schumann_latest.json") or _load(f"{MEDIA_DIR}/data/cumiana_latest.json")
    sch_block = combine_schumann(sch) if sch else None

    sci, myst, care = rules(sp, fc, sch_block)
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "sci": sci, "mystical": myst, "care": care,
        "today": {
            "kp": (sp or {}).get("now",{}).get("kp"),
            "sw_kms": (sp or {}).get("now",{}).get("solar_wind_kms"),
            "bz_nt": (sp or {}).get("now",{}).get("bz_nt"),
            "flare_24h": (fc or {}).get("flares",{}).get("max_24h"),
            "cme_headline": (fc or {}).get("cmes",{}).get("headline")
        },
        "schumann": sch_block
    }

    p = pathlib.Path(OUT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",",":"), ensure_ascii=False))
    print(f"[earthscope] wrote -> {p}")

if __name__ == "__main__":
    main()