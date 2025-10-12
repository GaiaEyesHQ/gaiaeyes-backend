#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tomsk Schumann extractor updated 9/10
- 0–72h continuous time anchor
- Tick-ruler from bottom hour ticks for robust px-per-hour (primary)
- Auto-bias computed from Last-Modified vs freshly painted frontier (guarded)
- Accepts up to ±90 min auto-bias (configurable) and always logs measured/applied
- Dynamic day boundaries for overlays only; timing is day3 (48–72 h)
- Overlay: horizontal band guides + labels; vertical red 'now' line
- Banded harmonic picker with ridge/heuristic fallbacks
"""

import os, sys, json, argparse
from datetime import datetime, timezone, timedelta
import requests
import numpy as np
import cv2

# --------------------------
# Constants / configuration
# --------------------------
TOMSK_IMG = "https://sos70.ru/provider.php?file=shm.jpg"
UTC_TO_TSST_HOURS = 7                 # Tomsk local on spectrogram
DEFAULT_ACCEPT_MINUTES = 90.0         # max |auto bias| to apply
FRONTIER_GUARD_PX = 30                # avoid sampling at very edge

# Tick detection (bottom hour marks)
TICK_STRIP_H = 14
TICK_MIN_SEP = 8
TICK_MIN_COUNT = 24

# ROI for the plot inside the image
ROI = (59, 31, 1539, 431)             # x0,y0,x1,y1

RIGHT_EXCLUDE_PX = 90  # ignore right margin (colorbar/legend)
MIN_GUARD_PX = 6       # min distance left of frontier

# Canonical harmonic windows (Hz) for picking
HARMONIC_WINDOWS = {
    "F1": (6.0, 9.5),
    "F2": (12.0, 18.5),
    "F3": (18.0, 27.5),
    "F4": (24.0, 36.5),
    "F5": (30.0, 45.5),
}

# Gridlines (Hz) for overlay and gridline suppression
GRID_HZ = [8.0, 12.0, 16.0, 20.0, 24.0, 28.0, 32.0, 36.0]

# --------------------------
# Helpers
# --------------------------
def fetch_image(url, insecure=False):
    kw = dict(stream=True, timeout=30)
    if insecure: kw.update(verify=False)
    r = requests.get(url, **kw)
    r.raise_for_status()
    last_mod = r.headers.get("Last-Modified", None)
    data = r.content
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img, last_mod

def parse_last_modified(h):
    if not h: return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S"):
        try:
            return datetime.strptime(h, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None

def tsst_now():
    return datetime.now(timezone.utc) + timedelta(hours=UTC_TO_TSST_HOURS)

def y_to_hz(y_pix, roi):
    x0,y0,x1,y1 = roi
    frac = (y_pix - y0) / max(1.0, (y1 - y0))
    return float(np.clip(frac * 40.0, 0.0, 40.0))

def hz_to_y(hz, roi):
    x0,y0,x1,y1 = roi
    frac = float(hz)/40.0
    return int(round(y0 + frac*(y1-y0)))

def hour_float(dt):
    return dt.hour + dt.minute/60.0 + dt.second/3600.0

def vertical_energy(gray):
    col = (gray.astype(np.float32)).mean(axis=0)
    col = (col - col.min()) / (np.ptp(col) + 1e-6)
    return col

def detect_tick_pph(img_bgr, roi, verbose=False):
    x0,y0,x1,y1 = roi
    y_top = max(y0, y1 - (TICK_STRIP_H + 2))
    strip = img_bgr[y_top:y1-2, x0:x1]
    if strip.size == 0:
        return None, 0, 0.0
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    sob = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    col_energy = np.abs(sob).mean(axis=0)
    k = max(3, (x1-x0)//600)
    col_energy = cv2.blur(col_energy.reshape(1,-1), (1, 2*k+1)).ravel()
    col_energy = (col_energy - col_energy.min()) / (np.ptp(col_energy) + 1e-6)
    peaks = []
    thr = max(0.25, float(np.median(col_energy)) + 0.35*float(np.std(col_energy)))
    for i in range(2, len(col_energy)-2):
        if col_energy[i] > thr and col_energy[i] == max(col_energy[i-2:i+3]):
            if peaks and (i - peaks[-1]) < TICK_MIN_SEP:
                if col_energy[i] > col_energy[peaks[-1]]:
                    peaks[-1] = i
            else:
                peaks.append(i)
    tick_count = len(peaks)
    if tick_count < 3: return None, tick_count, 0.0
    diffs = np.diff(peaks)
    if diffs.size == 0: return None, tick_count, 0.0
    pph_tick = float(np.median(diffs))
    quality = float(min(1.0, tick_count/72.0))
    if verbose:
        print(f"[ticks] count={tick_count} pph_tick={pph_tick:.3f} quality={quality:.2f}")
    return pph_tick, tick_count, quality

def estimate_day_boundaries(img_bgr, roi):
    x0,y0,x1,y1 = roi
    gray = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    ce = vertical_energy(gray)
    k = max(3, (x1-x0)//400)
    ce_s = cv2.blur(ce.reshape(1,-1), (1, 2*k+1)).ravel()
    W = (x1 - x0)
    approx1 = int(round(W/3)); approx2 = int(round(2*W/3))
    def snap(idx):
        lo = max(0, idx-40); hi = min(W-1, idx+40)
        seg = ce_s[lo:hi]
        local_min = lo + np.argmin(seg)
        return x0 + int(local_min)
    d1 = snap(approx1); d2 = snap(approx2)
    if not (x0+100 < d1 < d2 < x1-100):
        d1 = x0 + approx1; d2 = x0 + approx2
    day_w = (d2 - x0) / 2.0
    x_day0 = x0
    x_day1 = int(round(x0 + day_w))
    x_day2 = int(round(x_day1 + day_w))
    return x_day0, x_day1, x_day2, float(day_w)

def detect_frontier(img_bgr, roi):
    x0, y0, x1, y1 = roi
    x1_eff = max(x0 + 50, x1 - RIGHT_EXCLUDE_PX)
    crop = img_bgr[y0:y1, x0:x1_eff]
    if crop.size == 0: return x0
    gry = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    col_std = gry.std(axis=0)
    k = max(3, (x1_eff - x0) // 600)
    col_std = cv2.blur(col_std.reshape(1, -1), (1, 2 * k + 1)).ravel()
    col_std = (col_std - col_std.min()) / (np.ptp(col_std) + 1e-6)
    thr = float(np.percentile(col_std, 40)) * 0.9
    idx = None
    for i in range(len(col_std) - 1, -1, -1):
        if col_std[i] > thr:
            idx = i
            break
    if idx is None: idx = len(col_std) - 1
    return x0 + int(idx)

def px_per_hour(day_w): return day_w/24.0
def x_for_hour_in_day(x_day_start, pph, hour_in_day): return int(round(x_day_start + float(hour_in_day) * float(pph)))

def draw_overlay(img_bgr, roi, x_now, peaks=None, debug_lines=None, pph=None, pph_source=None):
    out = img_bgr.copy()
    x0,y0,x1,y1 = roi
    for hz in [8, 12, 16, 20, 24, 28, 32, 36]:
        y = hz_to_y(hz, roi)
        cv2.line(out, (x0, y), (x1, y), (255, 128, 0), 1)
    if debug_lines:
        if 'x_day1' in debug_lines:
            cv2.line(out, (debug_lines['x_day1'], y0), (debug_lines['x_day1'], y1), (180,180,180), 1)
        if 'x_day2' in debug_lines:
            cv2.line(out, (debug_lines['x_day2'], y0), (debug_lines['x_day2'], y1), (180,180,180), 1)
        if 'x_frontier' in debug_lines:
            cv2.line(out, (debug_lines['x_frontier'], y0), (debug_lines['x_frontier'], y1), (255,0,255), 1)
        if 'left_guard' in debug_lines:
            cv2.line(out, (debug_lines['left_guard'], y0), (debug_lines['left_guard'], y1), (0,255,255), 1)
        if 'right_guard' in debug_lines:
            cv2.line(out, (debug_lines['right_guard'], y0), (debug_lines['right_guard'], y1), (0,255,0), 1)
        if pph is not None and pph_source is not None:
            label = f"pph={pph:.3f} ({pph_source})"
            cv2.putText(out, label, (roi[0]+8, roi[1]+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
    cv2.line(out, (x_now, y0), (x_now, y1), (0, 0, 255), 2)
    if peaks:
        colors = [(255,255,255),(0,255,255),(0,255,0),(0,165,255),(255,0,255)]
        for i,(name,hz) in enumerate(peaks.items()):
            if hz is None: continue
            y = hz_to_y(hz, roi)
            cv2.circle(out, (x_now, y), 3, colors[i%len(colors)], -1)
    return out

# ----- banded picker with fallbacks -----
def estimate_peaks_banded(img_bgr, roi, x_now, verbose=False):
    """
    Banded harmonic picker (F1..F5) at x_now with robustness improvements:
    - Wider vertical slice (11 px) and HSV-V profile instead of raw gray
    - Gridline suppression (notches around 8,12,...,36 Hz)
    - Dynamic per-window threshold (median + fraction of (p95 - median))
    - F2-first strategy; F1 assisted by F2/2 when available
    """
    x0,y0,x1,y1 = roi
    x = int(np.clip(x_now, x0+1, x1-2))
    # Wider slice to stabilize ridge measurement
    slice_w = img_bgr[y0:y1, max(x-5,x0):min(x+6,x1), :]  # 11 px wide
    if slice_w.size == 0:
        return {k: None for k in HARMONIC_WINDOWS.keys()}

    # Use HSV Value channel (brightness correlates with signal power in colormap)
    hsv = cv2.cvtColor(slice_w, cv2.COLOR_BGR2HSV)
    V = hsv[:,:,2].astype(np.float32)
    prof = V.mean(axis=1)  # average across slice width
    # Gentle vertical smoothing
    prof = cv2.GaussianBlur(prof.reshape(-1,1), (1,9), 0).ravel()

    # Build a penalty mask for gridlines to avoid snapping to them
    penalty = np.zeros_like(prof, dtype=np.float32)
    Hpix = (y1 - y0)
    for ghz in GRID_HZ:
        yg = hz_to_y(ghz, roi)
        gi = int(np.clip(yg - y0, 0, Hpix-1))
        # 5-px wide Gaussian notch
        for d in range(-3, 4):
            idx = gi + d
            if 0 <= idx < Hpix:
                penalty[idx] += float(np.exp(-0.5*(d/2.0)**2)) * 12.0  # notch strength

    # Convert to "signal" where high means likely ridge, then suppress gridlines
    sig_raw = prof.copy()
    sig = sig_raw - penalty
    # Normalize to 0..1
    sig = (sig - sig.min()) / (np.ptp(sig) + 1e-6)

    def pick_in_window_named(band_name, enforce_floor=False, assist_center_hz=None):
        hz_lo, hz_hi = HARMONIC_WINDOWS[band_name]
        # optional stricter floor for F1 to reduce low bias
        if band_name == "F1" and enforce_floor:
            hz_lo = max(hz_lo, 6.8)
        y_lo = hz_to_y(hz_lo, roi); y_hi = hz_to_y(hz_hi, roi)
        lo = max(0, min(y_lo - y0, Hpix - 2))
        hi = max(1, min(y_hi - y0, Hpix - 1))
        if hi <= lo + 2:
            return None, 0.0
        seg = sig[lo:hi].copy()
        # Dynamic threshold using window statistics
        w_med = float(np.median(seg))
        w_p95 = float(np.percentile(seg, 95))
        dyn_thr = w_med + 0.25*(w_p95 - w_med)

        # If we have an assist center (e.g., F2/2 for F1), bias toward it
        if assist_center_hz is not None:
            yc = hz_to_y(assist_center_hz, roi) - y0
            # Create a tapered bump around the expected row to bias selection
            bump = np.zeros_like(seg, dtype=np.float32)
            for i in range(len(seg)):
                d = abs((lo + i) - yc)
                bump[i] = float(np.exp(-0.5*(d/3.0)**2)) * 0.15  # small, just nudge toward expected
            seg = seg + bump

        # Light smoothing and argmax
        seg = cv2.blur(seg.reshape(-1,1), (1, 7)).ravel()
        idx = int(np.argmax(seg))
        val = float(seg[idx])
        if val < dyn_thr:
            return None, val
        y_pick = y0 + lo + idx
        return y_to_hz(y_pick, roi), val

    picks = {k: None for k in HARMONIC_WINDOWS.keys()}
    strength = {k: 0.0 for k in HARMONIC_WINDOWS.keys()}

    # 1) Pick F2 first (usually more stable than F1)
    f2, v2 = pick_in_window_named("F2")
    picks["F2"], strength["F2"] = f2, v2

    # 2) Pick F1; if F2 exists, nudge around F2/2
    f1_assist = (f2 / 2.0) if f2 is not None else None
    f1, v1 = pick_in_window_named("F1", enforce_floor=True, assist_center_hz=f1_assist)
    picks["F1"], strength["F1"] = f1, v1

    # 3) Pick remaining bands normally
    for name in ["F3","F4","F5"]:
        fv, vv = pick_in_window_named(name)
        picks[name], strength[name] = fv, vv

    # Fallback repair using harmonic relations (existing helper)
    picks = repair_harmonics(picks)
    return picks

def clamp(v, lo, hi):
    return None if v is None else float(max(lo, min(hi, v)))

def repair_harmonics(peaks):
    """Back-fill missing bands using simple harmonic relations (guarded)."""
    p = dict(peaks)  # copy
    # back-derive F1 from F2 if needed
    if p.get("F1") is None and p.get("F2") is not None:
        p["F1"] = clamp(p["F2"]/2.0, *HARMONIC_WINDOWS["F1"])
    # fill any missing Fk as multiples of F1 (only if we have F1)
    if p.get("F1") is not None:
        f1 = p["F1"]
        for k in [2,3,4,5]:
            name = f"F{k}"
            if p.get(name) is None:
                candidate = f1 * k
                lo, hi = HARMONIC_WINDOWS[name]
                if lo <= candidate <= hi:
                    p[name] = candidate
    return p

# --------------------------
# Main
# --------------------------
def main():
    ap = argparse.ArgumentParser(description="Tomsk Schumann extractor")
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlay", required=False)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--time-bias-minutes", type=float, default=None,
                    help="Manual bias override (minutes, positive shifts right).")
    ap.add_argument("--reset-bias", action="store_true",
                    help="Force zero auto-bias for this run.")
    ap.add_argument("--accept-minutes", type=float, default=DEFAULT_ACCEPT_MINUTES,
                    help="Max |auto bias| minutes that will be applied.")
    ap.add_argument("--guard-minutes", type=float, default=15.0,
                    help="How many minutes (in pixels via px/hour) to stay left of the frontier; adaptive guard.")
    ap.add_argument("--tick-min-count", type=int, default=TICK_MIN_COUNT,
                    help="Minimum tick count to trust tick-ruler px/hour (default: 24).")
    ap.add_argument("--pph-source", choices=["auto","day","ticks"], default="auto",
                    help="Choose px-per-hour source: bottom ticks, day-width, or auto (prefer ticks when reliable).")
    ap.add_argument("--snap-threshold-minutes", type=float, default=20.0,
                    help="If time-anchor trails the frontier guard by more than this many minutes, snap to the frontier guard.")
    ap.add_argument("--draw-debug", action="store_true",
                    help="Draw extra guide lines: day splits, frontier and guard rails, plus pph source label.")
    ap.add_argument("--stale-hours", type=float, default=6.0,
                    help="Mark Tomsk as stale_source if Last-Modified age exceeds this many hours.")
    args = ap.parse_args()

    img, last_mod_h = fetch_image(TOMSK_IMG, insecure=args.insecure)
    if img is None:
        print("Failed to fetch image", file=sys.stderr)
        return 3

    last_mod = parse_last_modified(last_mod_h)
    if args.verbose and last_mod:
        print(f"[dates] Last-Modified={last_mod.isoformat()}")

    age_hours = None
    if last_mod is not None:
        age_hours = (datetime.now(timezone.utc) - last_mod).total_seconds() / 3600.0
        if args.verbose:
            print(f"[fresh] age={age_hours:.2f}h (stale > {args.stale_hours}h)")

    x0,y0,x1,y1 = ROI
    x_day0, x_day1, x_day2, day_w = estimate_day_boundaries(img, ROI)

    # px/hour from ticks (preferred when good), else from day width
    pph_day = day_w/24.0
    pph_tick, tick_count, tick_quality = detect_tick_pph(img, ROI, verbose=args.verbose)
    if args.pph_source == "ticks":
        if pph_tick is not None and tick_count >= int(args.tick_min_count):
            pph = pph_tick; pph_source = "ticks"
        else:
            pph = pph_day;   pph_source = "day_width (ticks-forced-fallback)"
    elif args.pph_source == "day":
        pph = pph_day;       pph_source = "day_width"
    else:
        if pph_tick is not None and tick_count >= int(args.tick_min_count):
            pph = pph_tick; pph_source = "ticks"
        else:
            pph = pph_day;  pph_source = "day_width"

    x_frontier = detect_frontier(img, ROI)
    guard_px = max(MIN_GUARD_PX, int(round(pph * (args.guard_minutes/60.0))))

    now_tsst = tsst_now()
    hour_now = hour_float(now_tsst)
    x_time = x_for_hour_in_day(x_day2, pph, hour_now)
    x_ideal = x_time

    measured_bias_minutes = None
    bias_minutes_applied = 0.0
    bias_accepted = False

    fresh_ok = False
    if last_mod is not None:
        age_min = (datetime.now(timezone.utc) - last_mod).total_seconds()/60.0
        fresh_ok = age_min < 45.0
    edge_ok = (x1 - x_frontier) > (guard_px + 2)

    if args.verbose:
        print(f"[frontier] {x_frontier}  [pph] {pph:.3f} (source={pph_source})  [x_time] {x_time}")

    if fresh_ok and edge_ok and not args.reset_bias:
        lm_tsst = last_mod.astimezone(timezone(timedelta(hours=UTC_TO_TSST_HOURS))) if last_mod else None
        if lm_tsst:
            lm_hour = hour_float(lm_tsst)
            x_lm = x_for_hour_in_day(x_day2, pph, lm_hour)
            dx_px = x_frontier - x_lm
            measured_bias_minutes = (dx_px / pph) * 60.0

    if args.time_bias_minutes is not None:
        bias_minutes_applied = float(args.time_bias_minutes); bias_accepted = True
    elif measured_bias_minutes is not None:
        if abs(measured_bias_minutes) <= float(args.accept_minutes):
            bias_minutes_applied = measured_bias_minutes; bias_accepted = True
        else:
            bias_minutes_applied = 0.0; bias_accepted = False
    else:
        bias_minutes_applied = 0.0; bias_accepted = False

    x_ideal = int(round(x_time + (bias_minutes_applied/60.0)*pph))

    left_guard  = x_day2 + 2
    right_guard = min(x1-2, x_frontier - guard_px)

    delta_px  = right_guard - x_ideal
    delta_min = (delta_px / max(pph, 1e-6)) * 60.0
    if delta_min > float(args.snap_threshold_minutes):
        x_now_pre = right_guard
    else:
        x_now_pre = x_ideal

    x_now = int(np.clip(x_now_pre, left_guard, right_guard))

    # ---- banded harmonic picking with fallbacks ----
    peaks_banded = estimate_peaks_banded(img, ROI, x_now, verbose=args.verbose)
    peaks = repair_harmonics(peaks_banded)

    # Overlay
    dbg = None
    if args.draw_debug:
        dbg = {
            'x_day1': x_day1,
            'x_day2': x_day2,
            'x_frontier': x_frontier,
            'left_guard': x_day2 + 2,
            'right_guard': min(x1-2, x_frontier - guard_px),
        }
    overlay_img = draw_overlay(
        img, ROI, x_now,
        peaks=peaks,
        debug_lines=dbg,
        pph=pph, pph_source=pph_source,
    )
    if args.overlay:
        cv2.imwrite(args.overlay, overlay_img)

    status_val = "ok"
    if age_hours is not None and age_hours > float(args.stale_hours):
        status_val = "stale_source"

    out = {
        "status": status_val,
        "source":"tomsk",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "last_modified": last_mod.isoformat() if last_mod else None,
        "fundamental_hz": peaks.get("F1", None),
        "harmonics_hz": {k:(None if v is None else float(v)) for k,v in peaks.items()},
        "amplitude_idx": {},
        "confidence": "high-panels",
        "overlay_path": args.overlay,
        "raw":{
            "tsst_time": now_tsst.isoformat(),
            "roi": {"x0":x0,"y0":y0,"x1":x1,"y1":y1},
            "group_boundaries_px": {
                "x_day0": x_day0, "x_day1": x_day1, "x_day2": x_day2, "day_w": day_w,
            },
            "debug": {
                "x_frontier": x_frontier,
                "x1_exclude_right_px": RIGHT_EXCLUDE_PX,
                "guard_px": guard_px,
                "x_time": x_time,
                "x_ideal": x_ideal,
                "right_guard": right_guard,
                "delta_min_to_guard": float(delta_min),
                "pph": pph,
                "pph_source": pph_source,
                "tick_count": tick_count if pph_source=="ticks" else 0,
                "tick_quality": tick_quality if pph_source=="ticks" else 0.0,
                "bias_minutes_applied": float(bias_minutes_applied),
                "measured_bias_minutes": (None if measured_bias_minutes is None else float(measured_bias_minutes)),
                "guard_applied": bool(x_now != x_ideal),
                "age_hours": (None if age_hours is None else float(age_hours)),
                "stale_hours": float(args.stale_hours),
            },
            "method": "tick-ruler px/h + adaptive frontier guard; day3(48–72h) time-anchor; banded picker + fallbacks",
        }
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    if args.verbose:
        print(json.dumps(out, indent=2))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
