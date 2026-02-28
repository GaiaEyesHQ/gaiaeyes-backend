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

F1_PLAUSIBLE_MIN_HZ = 7.2
F1_PLAUSIBLE_MAX_HZ = 8.6
F1_DIRECT_MIN_HZ = 7.0
F1_DIRECT_MAX_HZ = 9.0
F2_CANDIDATE_LIMIT = 5
FAMILY_GRID_STEP_HZ = 0.05
FAMILY_TOLERANCE_HZ = 0.5
FAMILY_REFINE_WINDOW_HZ = 0.6
FAMILY_SCORE_MIN_USABLE = 1.35
FAMILY_SCORE_WEIGHTS = {1: 1.0, 2: 1.0, 3: 0.8, 4: 0.6, 5: 0.4}

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
    _x0, y0, _x1, y1 = roi
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

def is_plausible_f1(f1_hz):
    if f1_hz is None:
        return False
    return bool(F1_PLAUSIBLE_MIN_HZ <= float(f1_hz) <= F1_PLAUSIBLE_MAX_HZ)

def default_picker_debug():
    return {
        "plausibility_reject_f2_count": 0,
        "plausibility_selected_f2_rank": None,
        "family_scoring_used": False,
        "family_best_f1": None,
        "family_best_score": None,
        "family_candidate_count": 0,
        "family_top3": [],
        "family_score_threshold": float(FAMILY_SCORE_MIN_USABLE),
        "family_fallback_used": False,
    }

def dedupe_sorted_floats(values, precision=3):
    out = []
    seen = set()
    for v in values:
        if v is None:
            continue
        fv = float(v)
        key = round(fv, precision)
        if key in seen:
            continue
        seen.add(key)
        out.append(fv)
    out.sort()
    return out

def select_family_by_scoring(sig, roi, candidates_f1, tolerance_hz):
    """
    Score candidate F1 values by summing ridge strengths at expected harmonics.
    Returns: (best_f1, best_score, top_scores[<=3]).
    """
    x0, y0, x1, y1 = roi
    h_pix = int(max(1, y1 - y0))
    tol_pix = max(1, int(round((float(tolerance_hz) / 40.0) * h_pix)))

    scored = []
    for f1 in dedupe_sorted_floats(candidates_f1):
        if not is_plausible_f1(f1):
            continue
        score = 0.0
        for k, weight in FAMILY_SCORE_WEIGHTS.items():
            target_hz = float(k) * float(f1)
            if target_hz <= 0.0 or target_hz > 40.0:
                continue
            y_idx = int(np.clip(hz_to_y(target_hz, roi) - y0, 0, h_pix - 1))
            lo = max(0, y_idx - tol_pix)
            hi = min(h_pix - 1, y_idx + tol_pix)
            if hi < lo:
                continue
            local_max = float(np.max(sig[lo:hi+1]))
            score += float(weight) * local_max
        scored.append({"f1": float(f1), "score": float(score)})

    if not scored:
        return None, None, []

    scored.sort(key=lambda x: x["score"], reverse=True)
    best = scored[0]
    top3 = [{"f1": float(item["f1"]), "score": float(item["score"])} for item in scored[:3]]
    return float(best["f1"]), float(best["score"]), top3

# ----- banded picker with fallbacks -----
def estimate_peaks_banded(img_bgr, roi, x_now, verbose=False, return_debug=False):
    """
    Banded harmonic picker (F1..F5) with:
    - Stage 1 plausibility-gated F2/F1 picks
    - Stage 2 harmonic family scoring with local harmonic refinement
    """
    picker_debug = default_picker_debug()
    x0, y0, x1, y1 = roi
    x = int(np.clip(x_now, x0 + 1, x1 - 2))

    # Wider slice to stabilize ridge measurement.
    slice_w = img_bgr[y0:y1, max(x - 5, x0):min(x + 6, x1), :]
    if slice_w.size == 0:
        empty = {k: None for k in HARMONIC_WINDOWS.keys()}
        return (empty, picker_debug) if return_debug else empty

    # Use HSV Value channel (brightness correlates with signal power in colormap).
    hsv = cv2.cvtColor(slice_w, cv2.COLOR_BGR2HSV)
    prof = hsv[:, :, 2].astype(np.float32).mean(axis=1)
    prof = cv2.GaussianBlur(prof.reshape(-1, 1), (1, 9), 0).ravel()

    # Build a penalty mask for gridlines to avoid snapping to them.
    penalty = np.zeros_like(prof, dtype=np.float32)
    h_pix = int(y1 - y0)
    for ghz in GRID_HZ:
        yg = hz_to_y(ghz, roi)
        gi = int(np.clip(yg - y0, 0, h_pix - 1))
        for d in range(-2, 3):
            idx = gi + d
            if 0 <= idx < h_pix:
                penalty[idx] += float(np.exp(-0.5 * (d / 1.6) ** 2)) * 6.0

    sig = prof - penalty
    sig = (sig - sig.min()) / (np.ptp(sig) + 1e-6)

    def subpixel_peak_idx(seg_s, idx):
        i0 = max(0, idx - 1)
        i2 = min(len(seg_s) - 1, idx + 1)
        if i2 - i0 == 2:
            y_m1, y_0, y_p1 = seg_s[i0], seg_s[idx], seg_s[i2]
            denom = (y_m1 - 2 * y_0 + y_p1)
            delta = 0.0 if abs(denom) < 1e-6 else 0.5 * (y_m1 - y_p1) / denom
            return idx + float(np.clip(delta, -0.5, 0.5))
        return float(idx)

    def segment_for_hz(hz_lo, hz_hi):
        y_lo = hz_to_y(hz_lo, roi)
        y_hi = hz_to_y(hz_hi, roi)
        lo = max(0, min(y_lo - y0, h_pix - 2))
        hi = max(1, min(y_hi - y0, h_pix - 1))
        if hi <= lo + 2:
            return None
        seg = sig[lo:hi].copy()
        if seg.size < 3:
            return None
        w_med = float(np.median(seg))
        w_p95 = float(np.percentile(seg, 95))
        dyn_thr = w_med + 0.22 * (w_p95 - w_med)
        seg_s = cv2.blur(seg.reshape(-1, 1), (1, 7)).ravel()
        return {"lo": int(lo), "seg_s": seg_s, "dyn_thr": float(dyn_thr)}

    def local_candidates_from_segment(seg_data, limit):
        if seg_data is None:
            return []
        seg_s = seg_data["seg_s"]
        dyn_thr = seg_data["dyn_thr"]
        candidates = []
        for i in range(1, len(seg_s) - 1):
            cur = float(seg_s[i])
            if cur < dyn_thr:
                continue
            if cur >= float(seg_s[i - 1]) and cur >= float(seg_s[i + 1]):
                candidates.append((i, cur))
        if not candidates:
            idx = int(np.argmax(seg_s))
            val = float(seg_s[idx])
            if val >= dyn_thr:
                candidates = [(idx, val)]
        candidates.sort(key=lambda x: x[1], reverse=True)
        out = []
        for idx, val in candidates[:limit]:
            idx_f = subpixel_peak_idx(seg_s, idx)
            y_pick = y0 + seg_data["lo"] + idx_f
            out.append({"hz": float(y_to_hz(y_pick, roi)), "value": float(val)})
        return out

    def pick_best_from_segment(seg_data):
        if seg_data is None:
            return None, 0.0
        seg_s = seg_data["seg_s"]
        dyn_thr = seg_data["dyn_thr"]
        idx = int(np.argmax(seg_s))
        val = float(seg_s[idx])
        if val < dyn_thr:
            return None, val
        idx_f = subpixel_peak_idx(seg_s, idx)
        y_pick = y0 + seg_data["lo"] + idx_f
        return float(y_to_hz(y_pick, roi)), float(val)

    def pick_in_window_named(band_name, enforce_floor=False, assist_center_hz=None):
        hz_lo, hz_hi = HARMONIC_WINDOWS[band_name]
        if band_name == "F1" and enforce_floor:
            hz_lo = max(hz_lo, F1_DIRECT_MIN_HZ)
        if assist_center_hz is not None:
            hz_lo = max(hz_lo, assist_center_hz - 0.6)
            hz_hi = min(hz_hi, assist_center_hz + 0.8)
        seg_data = segment_for_hz(hz_lo, hz_hi)
        return pick_best_from_segment(seg_data)

    def pick_candidates_in_window_named(band_name, enforce_floor=False, assist_center_hz=None, limit=F2_CANDIDATE_LIMIT):
        hz_lo, hz_hi = HARMONIC_WINDOWS[band_name]
        if band_name == "F1" and enforce_floor:
            hz_lo = max(hz_lo, F1_DIRECT_MIN_HZ)
        if assist_center_hz is not None:
            hz_lo = max(hz_lo, assist_center_hz - 0.6)
            hz_hi = min(hz_hi, assist_center_hz + 0.8)
        seg_data = segment_for_hz(hz_lo, hz_hi)
        return local_candidates_from_segment(seg_data, limit=limit)

    stage1_picks = {k: None for k in HARMONIC_WINDOWS.keys()}
    stage1_strength = {k: 0.0 for k in HARMONIC_WINDOWS.keys()}

    # Stage 1.1/1.2: F2 local maxima + F1 plausibility gate.
    f2_candidates = pick_candidates_in_window_named("F2", limit=F2_CANDIDATE_LIMIT)
    plausible_implied_f1 = []
    selected_rank = None
    for rank, cand in enumerate(f2_candidates):
        implied_f1 = float(cand["hz"]) / 2.0
        if is_plausible_f1(implied_f1):
            selected_rank = rank
            stage1_picks["F2"] = float(cand["hz"])
            stage1_strength["F2"] = float(cand["value"])
            break
        picker_debug["plausibility_reject_f2_count"] += 1
    for cand in f2_candidates:
        implied_f1 = float(cand["hz"]) / 2.0
        if is_plausible_f1(implied_f1):
            plausible_implied_f1.append(implied_f1)
    if selected_rank is not None:
        picker_debug["plausibility_selected_f2_rank"] = int(selected_rank)

    # Stage 1.3: direct F1 pick must be in a broader sane range, else drop.
    f1_assist = (stage1_picks["F2"] / 2.0) if stage1_picks["F2"] is not None else None
    f1_direct, v1 = pick_in_window_named("F1", enforce_floor=True, assist_center_hz=f1_assist)
    if f1_direct is not None and not (F1_DIRECT_MIN_HZ <= float(f1_direct) <= F1_DIRECT_MAX_HZ):
        f1_direct = None
        v1 = 0.0
    stage1_picks["F1"] = f1_direct
    stage1_strength["F1"] = float(v1)

    for name in ["F3", "F4", "F5"]:
        fv, vv = pick_in_window_named(name)
        stage1_picks[name], stage1_strength[name] = fv, float(vv)

    # Keep prior consistency nudge for fallback path.
    if stage1_picks.get("F1") is not None and stage1_picks.get("F2") is not None:
        f1_assist = stage1_picks["F2"] / 2.0
        if (f1_assist - stage1_picks["F1"]) > 0.4 and stage1_strength.get("F1", 0.0) < max(0.35, stage1_strength.get("F2", 0.0) * 0.6):
            f1_new = 0.7 * f1_assist + 0.3 * stage1_picks["F1"]
            lo, hi = HARMONIC_WINDOWS["F1"]
            stage1_picks["F1"] = float(min(hi, max(lo, f1_new)))

    # Stage 2 candidate generation.
    f1_local_candidates = pick_candidates_in_window_named("F1", enforce_floor=True, limit=20)
    candidates_f1 = [cand["hz"] for cand in f1_local_candidates if is_plausible_f1(cand["hz"])]
    candidates_f1.extend(plausible_implied_f1)
    candidates_f1 = dedupe_sorted_floats(candidates_f1)
    if len(candidates_f1) < 6:
        grid = np.arange(
            F1_PLAUSIBLE_MIN_HZ,
            F1_PLAUSIBLE_MAX_HZ + (FAMILY_GRID_STEP_HZ * 0.5),
            FAMILY_GRID_STEP_HZ,
        )
        candidates_f1 = dedupe_sorted_floats(candidates_f1 + [float(v) for v in grid])

    picker_debug["family_candidate_count"] = int(len(candidates_f1))

    best_f1, best_score, top3 = select_family_by_scoring(
        sig=sig,
        roi=roi,
        candidates_f1=candidates_f1,
        tolerance_hz=FAMILY_TOLERANCE_HZ,
    )
    picker_debug["family_best_f1"] = (None if best_f1 is None else float(best_f1))
    picker_debug["family_best_score"] = (None if best_score is None else float(best_score))
    picker_debug["family_top3"] = top3

    def refine_harmonic_near_prediction(band_name, predicted_hz):
        if predicted_hz is None or predicted_hz <= 0.0 or predicted_hz > 40.0:
            return None, 0.0
        band_lo, band_hi = HARMONIC_WINDOWS[band_name]
        hz_lo = max(band_lo, float(predicted_hz) - FAMILY_REFINE_WINDOW_HZ)
        hz_hi = min(band_hi, float(predicted_hz) + FAMILY_REFINE_WINDOW_HZ)
        seg_data = segment_for_hz(hz_lo, hz_hi)
        return pick_best_from_segment(seg_data)

    family_picks = {k: None for k in HARMONIC_WINDOWS.keys()}
    if best_f1 is not None:
        for k in [1, 2, 3, 4, 5]:
            band = f"F{k}"
            predicted = float(best_f1) * float(k)
            hz_refined, _strength = refine_harmonic_near_prediction(band, predicted)
            if hz_refined is not None:
                family_picks[band] = float(hz_refined)
        if family_picks["F1"] is None and is_plausible_f1(best_f1):
            family_picks["F1"] = float(best_f1)

    family_score_ok = best_score is not None and float(best_score) >= float(FAMILY_SCORE_MIN_USABLE)
    family_ready = bool(family_score_ok and is_plausible_f1(family_picks.get("F1")))

    if family_ready:
        picks = family_picks
        picker_debug["family_scoring_used"] = True
    else:
        picks = repair_harmonics(stage1_picks)
        picker_debug["family_fallback_used"] = True

    if picks.get("F1") is not None and not (F1_DIRECT_MIN_HZ <= float(picks["F1"]) <= F1_DIRECT_MAX_HZ):
        picks["F1"] = None

    if verbose:
        print(
            f"[family] candidates={picker_debug['family_candidate_count']} "
            f"best_f1={picker_debug['family_best_f1']} score={picker_debug['family_best_score']} "
            f"used={picker_debug['family_scoring_used']}"
        )

    if return_debug:
        return picks, picker_debug
    return picks

def clamp(v, lo, hi):
    return None if v is None else float(max(lo, min(hi, v)))

def repair_harmonics(peaks):
    """Back-fill missing bands using simple harmonic relations (guarded)."""
    p = dict(peaks)  # copy
    # back-derive F1 from F2 if needed
    if p.get("F1") is None and p.get("F2") is not None:
        f1_candidate = clamp(p["F2"]/2.0, *HARMONIC_WINDOWS["F1"])
        if f1_candidate is not None and f1_candidate >= F1_DIRECT_MIN_HZ:
            p["F1"] = f1_candidate
    if p.get("F1") is not None and float(p["F1"]) < F1_DIRECT_MIN_HZ:
        p["F1"] = None
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
    ap.add_argument("--out", required=False, help="Output JSON path (optional when --self-test is used).")
    ap.add_argument("--overlay", required=False)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="Fetch one image, run extraction, print family debug, and exit with health-check status.")
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
    if not args.out and not args.self_test:
        ap.error("--out is required unless --self-test is set")

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

    # Timing anchors should be geometry-based, not content-derived, because the right side of Tomsk
    # can be partially unpainted (blank) and content-based day splits can drift.
    x1_eff = max(x0 + 50, x1 - RIGHT_EXCLUDE_PX)
    W_time = float(x1_eff - x0)
    day_w_time = W_time / 3.0
    x_day0_time = x0
    x_day1_time = int(round(x0 + day_w_time))
    x_day2_time = int(round(x0 + 2.0 * day_w_time))
    pph_day_time = day_w_time / 24.0

    x_day0, x_day1, x_day2, day_w = estimate_day_boundaries(img, ROI)
    # Note: x_day* above are content-derived and used for overlay only. Timing uses x_day2_time.

    # px/hour from ticks (preferred when good), else from day width (geometry-based)
    pph_day = pph_day_time
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
    x_time = x_for_hour_in_day(x_day2_time, pph, hour_now)
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

    left_guard  = x_day2_time + 2
    right_guard = min(x1-2, x_frontier - guard_px)
    # If the latest painted frontier is too far left, we cannot safely sample "now".
    # In this case, emit a safe payload with no peaks rather than incorrect readings.
    guard_invalid = bool(right_guard <= left_guard + 10)

    delta_px  = right_guard - x_ideal
    delta_min = (delta_px / max(pph, 1e-6)) * 60.0
    if delta_min > float(args.snap_threshold_minutes):
        x_now_pre = right_guard
    else:
        x_now_pre = x_ideal

    x_now = int(np.clip(x_now_pre, left_guard, right_guard))
    if guard_invalid:
        # Force x_now to the safest available point left of the frontier.
        x_now = int(np.clip(right_guard, x0 + 2, x1 - 2))

    # ---- banded harmonic picking with fallbacks ----
    if not guard_invalid:
        peaks, picker_debug = estimate_peaks_banded(
            img,
            ROI,
            x_now,
            verbose=args.verbose,
            return_debug=True,
        )
    else:
        peaks = {k: None for k in HARMONIC_WINDOWS.keys()}
        picker_debug = default_picker_debug()
        picker_debug["family_fallback_used"] = True

    # Overlay
    dbg = None
    if args.draw_debug:
        dbg = {
            'x_day1': x_day1,
            'x_day2': x_day2,
            'x_frontier': x_frontier,
            'left_guard': x_day2_time + 2,
            'right_guard': right_guard,
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
    if guard_invalid and status_val == "ok":
        status_val = "no_recent_data"

    # Quality/usable gating for downstream source selection.
    family_best_score = picker_debug.get("family_best_score")
    family_score_ok = isinstance(family_best_score, (int, float)) and float(family_best_score) >= float(FAMILY_SCORE_MIN_USABLE)
    f1_val = peaks.get("F1")
    f1_plausible = is_plausible_f1(f1_val)
    if not f1_plausible:
        peaks["F1"] = None

    quality_reasons = []
    if not f1_plausible:
        quality_reasons.append("f1_not_plausible")
    if not family_score_ok:
        quality_reasons.append("low_family_score")
    if guard_invalid:
        quality_reasons.append("no_recent_data_guard")
    if status_val != "ok":
        quality_reasons.append(f"status_{status_val}")

    max_family_score = float(sum(FAMILY_SCORE_WEIGHTS.values()))
    quality_score = 0.0
    if isinstance(family_best_score, (int, float)):
        quality_score = float(np.clip(float(family_best_score) / max_family_score, 0.0, 1.0))
    if not f1_plausible:
        quality_score = min(quality_score, 0.20)
    if guard_invalid:
        quality_score = 0.0
    if status_val != "ok":
        quality_score = min(quality_score, 0.35)

    usable = bool(f1_plausible and family_score_ok and status_val == "ok")
    if not usable:
        quality_reasons.append("below_min_quality")

    out = {
        "status": status_val,
        "source":"tomsk",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "last_modified": last_mod.isoformat() if last_mod else None,
        "fundamental_hz": peaks.get("F1", None),
        "harmonics_hz": {k:(None if v is None else float(v)) for k,v in peaks.items()},
        "amplitude_idx": {},
        "quality_score": float(quality_score),
        "usable": usable,
        "quality_reasons": quality_reasons,
        "confidence": "high-panels",
        "overlay_path": args.overlay,
        "raw":{
            "tsst_time": now_tsst.isoformat(),
            "roi": {"x0":x0,"y0":y0,"x1":x1,"y1":y1},
            "group_boundaries_px": {
                "x_day0": x_day0, "x_day1": x_day1, "x_day2": x_day2, "day_w": day_w,
                "x_day1_time": x_day1_time, "x_day2_time": x_day2_time, "day_w_time": day_w_time,
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
                "tick_count": int(tick_count),
                "tick_quality": float(tick_quality),
                "tick_used": bool(pph_source == "ticks"),
                "bias_minutes_applied": float(bias_minutes_applied),
                "measured_bias_minutes": (None if measured_bias_minutes is None else float(measured_bias_minutes)),
                "guard_applied": bool(x_now != x_ideal),
                "age_hours": (None if age_hours is None else float(age_hours)),
                "stale_hours": float(args.stale_hours),
                **picker_debug,
            },
            "method": "tick-ruler px/h + adaptive frontier guard; day3(48–72h) time-anchor; stage1 plausibility gate + stage2 family scoring",
        }
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    if args.verbose:
        print(json.dumps(out, indent=2))

    if args.self_test:
        dbg = out.get("raw", {}).get("debug", {})
        print(
            f"self_test status={out.get('status')} usable={out.get('usable')} "
            f"F1={out.get('fundamental_hz')} F2={(out.get('harmonics_hz') or {}).get('F2')}"
        )
        print(json.dumps({
            "family_scoring_used": dbg.get("family_scoring_used"),
            "family_best_f1": dbg.get("family_best_f1"),
            "family_best_score": dbg.get("family_best_score"),
            "family_candidate_count": dbg.get("family_candidate_count"),
            "family_top3": dbg.get("family_top3"),
            "plausibility_reject_f2_count": dbg.get("plausibility_reject_f2_count"),
            "plausibility_selected_f2_rank": dbg.get("plausibility_selected_f2_rank"),
        }, ensure_ascii=False, indent=2))

        f1_ok = is_plausible_f1(out.get("fundamental_hz"))
        status_not_ok = str(out.get("status", "")).lower() != "ok"
        unusable = not bool(out.get("usable", True))
        return 0 if (f1_ok or (unusable and status_not_ok)) else 2
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
