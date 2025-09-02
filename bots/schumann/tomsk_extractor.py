#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tomsk Schumann extractor
- 0–72h continuous time anchor
- Tick‑ruler from bottom hour ticks for robust px‑per‑hour (primary)
- Auto-bias computed from Last-Modified vs freshly painted frontier (guarded)
- Accepts up to ±90 min auto-bias (configurable) and always logs measured/applied
- Dynamic day boundaries for overlays only; timing is day3 (48–72 h)
- Overlay: horizontal band guides + labels; vertical red 'now' line
"""

import os, io, sys, json, math, time, argparse
from datetime import datetime, timezone, timedelta
import requests
import numpy as np
import cv2

# --------------------------
# Constants / configuration
# --------------------------
TOMSK_IMG = "https://sosrff.tsu.ru/new/shm.jpg"
UTC_TO_TSST_HOURS = 7                 # Tomsk local on spectrogram
DEFAULT_ACCEPT_MINUTES = 90.0         # max |auto bias| to apply
FRONTIER_GUARD_PX = 30                # avoid sampling at very edge

# Tick detection (bottom hour marks)
TICK_STRIP_H = 14          # height of bottom strip to scan for ticks
TICK_MIN_SEP = 8           # minimum px between tick peaks (avoid double-picks)
TICK_MIN_COUNT = 24        # minimal number of ticks to trust tick-ruler (default; can be overridden by CLI)

# ROI for the plot inside the image (stable across Tomsk layouts)
ROI = (59, 31, 1539, 431)             # x0,y0,x1,y1

BAND_HZ = [8.0, 12.5, 16.0, 20.0, 24.0, 28.0, 32.0, 36.0]  # guide lines to draw
F_LABELS = {"F1":"{:.1f}Hz","F2":"{:.1f}","F3":"{:.1f}","F4":"{:.1f}","F5":"{:.1f}"}

RIGHT_EXCLUDE_PX = 90  # ignore right margin (colorbar/legend) when finding frontier
MIN_GUARD_PX = 6       # minimum distance we keep away from the frontier (adaptive guard floor)

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
    # Return UTC datetime or None
    if not h: return None
    try:
        # Example: 'Sun, 31 Aug 2025 20:05:03 GMT'
        return datetime.strptime(h, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def tsst_now():
    # Spectrogram timeline is Tomsk time (UTC+7)
    return datetime.now(timezone.utc) + timedelta(hours=UTC_TO_TSST_HOURS)

def y_to_hz(y_pix, roi):
    # Linear mapping 0..40 Hz (Tomsk axis)
    x0,y0,x1,y1 = roi
    frac = (y_pix - y0) / max(1.0, (y1 - y0))
    return max(0.0, min(40.0, frac * 40.0))

def hz_to_y(hz, roi):
    x0,y0,x1,y1 = roi
    frac = float(hz)/40.0
    return int(round(y0 + frac*(y1-y0)))

def hour_float(dt):
    return dt.hour + dt.minute/60.0 + dt.second/3600.0

def vertical_energy(gray):
    # Column energy for detecting day boundaries
    col = (gray.astype(np.float32)).mean(axis=0)
    col = (col - col.min()) / (np.ptp(col) + 1e-6)
    return col

def detect_tick_pph(img_bgr, roi, verbose=False):
    """
    Detect bottom hour ticks across the full 0–72h axis and return a robust
    px-per-hour estimate derived from median tick spacing.

    Returns (pph_tick, tick_count, quality)
      - pph_tick: float or None
      - tick_count: number of ticks detected
      - quality: 0..1 score (roughly tick_count/72 clipped)
    """
    x0,y0,x1,y1 = roi
    # Bottom strip right above bottom border (avoid the very last row)
    y_top = max(y0, y1 - (TICK_STRIP_H + 2))
    strip = img_bgr[y_top:y1-2, x0:x1]
    if strip.size == 0:
        return None, 0, 0.0

    # Use horizontal Sobel to enhance vertical edges (tick marks)
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    sob = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    col_energy = np.abs(sob).mean(axis=0)
    # Smooth
    k = max(3, (x1-x0)//600)
    col_energy = cv2.blur(col_energy.reshape(1,-1), (1, 2*k+1)).ravel()
    # Normalize
    col_energy = (col_energy - col_energy.min()) / (np.ptp(col_energy) + 1e-6)

    # Peak picking with simple non-maximum suppression
    peaks = []
    thr = max(0.25, float(np.median(col_energy)) + 0.35*float(np.std(col_energy)))
    for i in range(2, len(col_energy)-2):
        if col_energy[i] > thr and col_energy[i] == max(col_energy[i-2:i+3]):
            if peaks and (i - peaks[-1]) < TICK_MIN_SEP:
                # keep the stronger of two close peaks
                if col_energy[i] > col_energy[peaks[-1]]:
                    peaks[-1] = i
            else:
                peaks.append(i)

    tick_count = len(peaks)
    if tick_count < 3:
        return None, tick_count, 0.0

    # Robust spacing = median diff
    diffs = np.diff(peaks)
    if diffs.size == 0:
        return None, tick_count, 0.0
    pph_tick = float(np.median(diffs))
    quality = float(min(1.0, tick_count/72.0))

    if verbose:
        print(f"[ticks] count={tick_count} pph_tick={pph_tick:.3f} quality={quality:.2f}")
    return pph_tick, tick_count, quality

def estimate_day_boundaries(img_bgr, roi):
    """
    Return x_day0, x_day1, x_day2, day_w (float)
    Uses vertical energy troughs/peaks to estimate daily partitions.
    Falls back to equal thirds if uncertain.
    """
    x0,y0,x1,y1 = roi
    gray = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    ce = vertical_energy(gray)

    # Smooth & look for structure near 1/3 and 2/3
    k = max(3, (x1-x0)//400)
    ce_s = cv2.blur(ce.reshape(1,-1), (1, 2*k+1)).ravel()

    W = (x1 - x0)
    approx1 = int(round(W/3))
    approx2 = int(round(2*W/3))

    def snap(idx):
        lo = max(0, idx-40); hi = min(W-1, idx+40)
        seg = ce_s[lo:hi]
        local_min = lo + np.argmin(seg)
        return x0 + int(local_min)

    d1 = snap(approx1)
    d2 = snap(approx2)

    # Guard: ensure ordering and minimum spacing
    if not (x0+100 < d1 < d2 < x1-100):
        # fallback equal thirds
        d1 = x0 + approx1
        d2 = x0 + approx2

    # The image shows 3 days: [day0, day1), [day1, day2), [day2, day3=x1)
    day_w = (d2 - x0) / 2.0  # average of first 2 spans (more stable)
    # convert to canonical boundaries consistent with charts
    x_day0 = x0
    x_day1 = int(round(x0 + day_w))
    x_day2 = int(round(x_day1 + day_w))
    return x_day0, x_day1, x_day2, float(day_w)

def detect_frontier(img_bgr, roi):
    """Find the freshest painted column (right-most meaningful paint).
    Excludes the right margin/colorbar and uses per-column variance so we
    don't latch onto the flat legend/panel area.
    """
    x0, y0, x1, y1 = roi
    x1_eff = max(x0 + 50, x1 - RIGHT_EXCLUDE_PX)  # safety: leave ≥50px content
    crop = img_bgr[y0:y1, x0:x1_eff]
    if crop.size == 0:
        return x0  # fallback

    # Column statistics
    # Use grayscale standard deviation (texture) as an activity signal
    gry = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    col_std = gry.std(axis=0)
    # smooth a little to remove tiny spikes
    k = max(3, (x1_eff - x0) // 600)
    col_std = cv2.blur(col_std.reshape(1, -1), (1, 2 * k + 1)).ravel()
    # normalize
    col_std = (col_std - col_std.min()) / (np.ptp(col_std) + 1e-6)

    # adaptive threshold: anything with enough structure counts as "painted"
    # percentiles handle day-to-day palette shifts
    thr = float(np.percentile(col_std, 40)) * 0.9  # a bit more permissive

    # scan from right to left, pick last column above threshold
    idx = None
    for i in range(len(col_std) - 1, -1, -1):
        if col_std[i] > thr:
            idx = i
            break

    if idx is None:
        # fallback: use last column of effective crop
        idx = len(col_std) - 1

    return x0 + int(idx)

def px_per_hour(day_w):
    # 24 hours per day bucket
    return day_w/24.0

def x_for_hour_in_day(x_day_start, pph, hour_in_day):
    """Return x for a given hour within a specific day band (0..24)."""
    return int(round(x_day_start + float(hour_in_day) * float(pph)))

def draw_overlay(img_bgr, roi, x_now, peaks=None, debug_lines=None, pph=None, pph_source=None):
    """ Blue band lines, labels, and red now line. """
    out = img_bgr.copy()
    x0,y0,x1,y1 = roi

    # Horizontal blue guides
    for hz in [8, 12, 16, 20, 24, 28, 32, 36]:
        y = hz_to_y(hz, roi)
        cv2.line(out, (x0, y), (x1, y), (255, 128, 0), 1)  # bluish

    # Optional debug verticals
    if debug_lines:
        # expect dict with keys possibly: x_frontier, left_guard, right_guard, x_day1, x_day2
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
        # annotate pph source
        if pph is not None and pph_source is not None:
            label = f"pph={pph:.3f} ({pph_source})"
            cv2.putText(out, label, (roi[0]+8, roi[1]+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)

    # Vertical red 'now'
    cv2.line(out, (x_now, y0), (x_now, y1), (0, 0, 255), 2)

    # Optional dots for peaks
    if peaks:
        colors = [(255,255,255),(0,255,255),(0,255,0),(0,165,255),(255,0,255)]
        for i,(name,(hz,val)) in enumerate(peaks.items()):
            y = hz_to_y(hz, roi)
            cv2.circle(out, (x_now, y), 3, colors[i%len(colors)], -1)
    return out

def estimate_peaks(img_bgr, roi, x_now):
    """
    Very light touch: sample intensity along small vertical window around x_now,
    detect bands by vertical profile peaks. Map top five bands into F1..F5 by y.
    """
    x0,y0,x1,y1 = roi
    x = np.clip(x_now, x0+1, x1-2)
    w = img_bgr[y0:y1, x-2:x+3]  # 5px wide slice
    gry = cv2.cvtColor(w, cv2.COLOR_BGR2GRAY).mean(axis=1)
    # invert so brighter (yellow/red) -> larger value
    sig = gry.max() - gry
    sig = (sig - sig.min()) / (np.ptp(sig)+1e-6)

    # find local maxima with minimal spacing
    peaks = []
    for y in range(3, len(sig)-3):
        if sig[y] > 0.60 and sig[y] == max(sig[y-3:y+4]):
            peaks.append((y0+y, float(sig[y])))
    # keep strongest 7 by intensity, then map by y (low->high freq)
    peaks = sorted(peaks, key=lambda t: -t[1])[:7]
    peaks = sorted(peaks, key=lambda t: t[0])  # ascending y (low Hz -> high y)
    # convert to Hz, pick bands nearest canonical F1..F5 ladders
    hz_list = [y_to_hz(y, roi) for (y,_) in peaks]
    # Simple pick: choose five evenly from low->high
    if len(hz_list) >= 5:
        chosen = [hz_list[i] for i in [0,1,2,3,4]]
    else:
        # pad with None
        chosen = hz_list + [None]*(5-len(hz_list))
    out = {}
    for i,hz in enumerate(chosen, start=1):
        if hz is not None: out[f"F{i}"]=hz
    return out

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
    args = ap.parse_args()

    img, last_mod_h = fetch_image(TOMSK_IMG, insecure=args.insecure)
    if img is None:
        print("Failed to fetch image", file=sys.stderr)
        return 3

    last_mod = parse_last_modified(last_mod_h)
    if args.verbose and last_mod:
        print(f"[dates] Last-Modified={last_mod.isoformat()}")

    x0,y0,x1,y1 = ROI
    x_day0, x_day1, x_day2, day_w = estimate_day_boundaries(img, ROI)

    # Candidate px-per-hour from day width and from tick ruler
    pph_day = px_per_hour(day_w)
    pph_tick, tick_count, tick_quality = detect_tick_pph(img, ROI, verbose=args.verbose)

    # Decide pph source
    if args.pph_source == "ticks":
        if pph_tick is not None and tick_count >= int(args.tick_min_count):
            pph = pph_tick; pph_source = "ticks"
        else:
            pph = pph_day;   pph_source = "day_width (ticks-forced-fallback)"
    elif args.pph_source == "day":
        pph = pph_day;       pph_source = "day_width"
    else:
        # auto: prefer ticks when reliable
        if pph_tick is not None and tick_count >= int(args.tick_min_count):
            pph = pph_tick; pph_source = "ticks"
        else:
            pph = pph_day;  pph_source = "day_width"

    x_frontier = detect_frontier(img, ROI)
    # Adaptive guard: keep ~guard-minutes left of the freshest painted column
    guard_px = max(MIN_GUARD_PX, int(round(pph * (args.guard_minutes/60.0))))

    # Desired time position: always inside day3 (48–72 h) band
    now_tsst = tsst_now()
    hour_now = hour_float(now_tsst)  # [0,24)
    x_time = x_for_hour_in_day(x_day2, pph, hour_now)
    x_ideal = x_time  # will add bias later if any

    # Compute measured bias from Last-Modified vs frontier when fresh and not at edge
    measured_bias_minutes = None
    bias_minutes_applied = 0.0
    bias_accepted = False

    fresh_ok = False
    if last_mod is not None:
        age_min = (datetime.now(timezone.utc) - last_mod).total_seconds()/60.0
        # treat fresh if < 45 minutes
        fresh_ok = age_min < 45.0

    edge_ok = (x1 - x_frontier) > (guard_px + 2)

    if args.verbose:
        print(f"[frontier] {x_frontier}  [pph] {pph:.3f} (source={pph_source})  [x_time] {x_time}")

    if fresh_ok and edge_ok and not args.reset_bias:
        # Estimate what x should be using Last-Modified (in TSST) vs frontier
        lm_tsst = last_mod.astimezone(timezone(timedelta(hours=UTC_TO_TSST_HOURS))) if last_mod else None
        if lm_tsst:
            lm_hour = hour_float(lm_tsst)   # [0,24)
            x_lm = x_for_hour_in_day(x_day2, pph, lm_hour)
            dx_px = x_frontier - x_lm
            measured_bias_minutes = (dx_px / pph) * 60.0

    # Decide what bias to apply
    if args.time_bias_minutes is not None:
        bias_minutes_applied = float(args.time_bias_minutes)
        bias_accepted = True
    elif measured_bias_minutes is not None:
        if abs(measured_bias_minutes) <= float(args.accept_minutes):
            bias_minutes_applied = measured_bias_minutes
            bias_accepted = True
        else:
            bias_minutes_applied = 0.0
            bias_accepted = False
    else:
        bias_minutes_applied = 0.0
        bias_accepted = False

    # Apply bias to ideal time position
    x_ideal = int(round(x_time + (bias_minutes_applied/60.0)*pph))

    # Guards for day3 and frontier
    left_guard  = x_day2 + 2
    right_guard = min(x1-2, x_frontier - guard_px)

    # Snap-to-frontier fallback: if anchor trails guard by more than threshold minutes, snap
    delta_px  = right_guard - x_ideal
    delta_min = (delta_px / max(pph, 1e-6)) * 60.0
    if delta_min > float(args.snap_threshold_minutes):
        x_now_pre = right_guard
    else:
        x_now_pre = x_ideal

    # Final clamp (keeps us in day3 as well)
    x_now = int(np.clip(x_now_pre, left_guard, right_guard))
    guard_applied = (x_now != x_ideal)

    # Peaks (optional, light)
    peaks = estimate_peaks(img, ROI, x_now)

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
        peaks={k:(v,1.0) for k,v in peaks.items()},
        debug_lines=dbg,
        pph=pph,
        pph_source=pph_source,
    )
    if args.overlay:
        cv2.imwrite(args.overlay, overlay_img)

    # Output JSON
    out = {
        "status":"ok",
        "source":"tomsk",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "last_modified": last_mod.isoformat() if last_mod else None,
        "fundamental_hz": peaks.get("F1", None),
        "harmonics_hz": {k:float(v) for k,v in peaks.items()},
        "amplitude_idx": {},  # sampling disabled (not stable on Tomsk palette)
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
                "x_now_pre_guard": x_now_pre,
                "x_ideal": x_ideal,
                "right_guard": right_guard,
                "delta_min_to_guard": float(delta_min),
                "snap_threshold_minutes": float(args.snap_threshold_minutes),
                "pph": pph,
                "pph_source": pph_source,
                "tick_count": tick_count if pph_source=="ticks" else 0,
                "tick_quality": tick_quality if pph_source=="ticks" else 0.0,
                "bias_minutes_applied": bias_minutes_applied,
                "measured_bias_minutes": measured_bias_minutes,
                "bias_accepted": bias_accepted,
                "guard_applied": guard_applied,
            },
            "method": "tick‑ruler px/h + adaptive frontier guard; day3(48–72h) time‑anchor; optional auto‑bias",
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