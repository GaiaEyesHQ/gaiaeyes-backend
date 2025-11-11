#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tomsk SOS70 parameter charts extractor (72h rolling; same time math as your tomsk_extractor.py)
Outputs numeric readouts AND clear overlays marking x_now + picked colored lines.

Usage:
  python tomsk_sos70_params_extractor.py \
    --out runs/tomsk_params_values.json \
    --dir runs \
    --save-overlays true \
    --freq-max-hz 40 \
    --verbose
"""
import os, json, argparse
from datetime import datetime, timezone, timedelta
from io import BytesIO
import requests, numpy as np, cv2
from PIL import Image

URL_F = "https://sos70.ru/provider.php?file=srf.jpg"
URL_A = "https://sos70.ru/provider.php?file=sra.jpg"
URL_Q = "https://sos70.ru/provider.php?file=srq.jpg"

# ROI tuned to Tomsk-style charts
ROI = (59, 31, 1539, 431)
TICK_STRIP_H = 14
RIGHT_EXCLUDE_PX = 70
RIGHT_LOGO_SCAN_PX = 180
UTC_TO_TSST_HOURS = 7
TICK_MIN_SEP = 8
TICK_MIN_COUNT = 24
MIN_GUARD_PX = 6

# Series colors (RGB for reading; drawing uses BGR). Order is consistent across charts.
SERIES = {
    "s1": ("white",  (240,240,240), (255,255,255), "F1", "A1", "Q1"),
    "s2": ("yellow", (230,210,30),  (0,255,255),   "F2", "A2", "Q2"),
    "s3": ("red",    (200,40,40),   (0,0,255),     "F3", "A3", "Q3"),
    "s4": ("green",  (40,160,60),   (0,200,100),   "F4", "A4", "Q4"),
}

def bgr_to_hsv_color(bgr_tuple):
    color = np.uint8([[list(bgr_tuple)]])
    hsv = cv2.cvtColor(color, cv2.COLOR_BGR2HSV)[0,0]
    return hsv.astype(np.float32)

def hsv_row_distance(row_hsv, target_hsv, label):
    """
    Weighted HSV distance per row. For 'white' we emphasize low-S, high-V.
    For chromatic colors we emphasize hue circular distance and moderate S/V.
    row_hsv: HxWx3 in HSV; we reduce across columns later.
    """
    H = row_hsv[:,:,0].astype(np.float32)
    S = row_hsv[:,:,1].astype(np.float32)
    V = row_hsv[:,:,2].astype(np.float32)
    th, ts, tv = target_hsv
    if label == "white":
        # prefer low saturation, high value
        d = ( (S/255.0)**2 * 2.0 ) + ((1.0 - V/255.0)**2 * 1.5)
        return d.mean(axis=1)
    # hue circular distance in [0..180]
    dh = np.minimum(np.abs(H - th), 180.0 - np.abs(H - th)) / 90.0  # ~0..1
    ds = (S - ts)/255.0
    dv = (V - tv)/255.0
    d = (dh**2)*3.0 + (ds**2)*1.0 + (dv**2)*0.5
    return d.mean(axis=1)

def sanitize_roi(img_bgr, roi, min_width=120):
    h, w = img_bgr.shape[:2]
    x0, y0, x1, y1 = roi
    x0 = max(0, min(x0, w-1))
    x1 = max(0, min(x1, w))
    y0 = max(0, min(y0, h-1))
    y1 = max(0, min(y1, h))
    if x1 - x0 < min_width:
        # fallback to centered band if ROI is too narrow or invalid
        cx = w // 2
        half = max(min_width//2, min(w//2 - 1, 400))
        x0 = max(0, cx - half)
        x1 = min(w, cx + half)
    if y1 <= y0 + 10:
        y0 = max(0, (h//2) - 100)
        y1 = min(h, (h//2) + 100)
    return int(x0), int(y0), int(x1), int(y1)


# Helper to detect right logo/panel and shrink ROI x1 accordingly
def detect_right_logo_margin(img_bgr, roi, scan_px=RIGHT_LOGO_SCAN_PX):
    """
    Detect the cyan/white SOS70 logo strip on the right and return a tighter x1.
    We scan the rightmost `scan_px` columns for high-S (cyan) or very high V (white)
    blocks that are mostly outside the plotting area.
    """
    x0,y0,x1,y1 = roi
    h, w = img_bgr.shape[:2]
    xR0 = max(x0, x1 - min(scan_px, max(60, int(0.12*(x1-x0)))))
    band = img_bgr[y0:y1, xR0:x1, :]
    if band.size == 0:
        return x1
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    H = hsv[:,:,0].astype(np.float32)
    S = hsv[:,:,1].astype(np.float32)
    V = hsv[:,:,2].astype(np.float32)
    # cyan-ish: H in [75,105], S high; or bright white V very high, S low
    cyan = ((H >= 75) & (H <= 105) & (S > 90)).astype(np.uint8)
    white = ((S < 40) & (V > 220)).astype(np.uint8)
    mask = np.maximum(cyan, white)
    col_score = mask.mean(axis=0)  # fraction per column
    # find first column from the right where the logo coverage exceeds 0.25
    for i in range(col_score.size - 1, -1, -1):
        if col_score[i] > 0.25:
            # cut the ROI a few pixels left of this to be safe
            x1_new = xR0 + i - 4
            return max(x0 + 50, min(x1 - 2, int(x1_new)))
    return x1

def fetch_image(url, timeout=30):
    r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    last_mod = r.headers.get("Last-Modified")
    im = Image.open(BytesIO(r.content)).convert("RGB")
    return np.array(im)[:, :, ::-1], last_mod  # BGR for cv2

def parse_last_modified(h):
    if not h: return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S"):
        try:
            return datetime.strptime(h, fmt).replace(tzinfo=timezone.utc)
        except Exception: pass
    return None

def tsst_now(): return datetime.now(timezone.utc) + timedelta(hours=UTC_TO_TSST_HOURS)
def hour_float(dt): return dt.hour + dt.minute/60.0 + dt.second/3600.0

def y_to_unit(y_pix, roi, unit_min, unit_max):
    x0,y0,x1,y1 = roi
    frac = (y_pix - y0) / max(1.0, (y1 - y0))
    return float(unit_min + frac*(unit_max - unit_min))

def vertical_energy(gray):
    col = (gray.astype(np.float32)).mean(axis=0)
    return (col - col.min()) / (np.ptp(col) + 1e-6)

def detect_tick_pph(img_bgr, roi, verbose=False):
    x0,y0,x1,y1 = roi
    if x1 - x0 < 10:
        return None, 0, 0.0
    y_top = max(y0, y1 - (TICK_STRIP_H + 2))
    strip = img_bgr[y_top:y1-2, x0:x1]
    if strip.size == 0: return None, 0, 0.0
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    sob = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    col_energy = np.abs(sob).mean(axis=0)
    k = max(3, (x1-x0)//600)
    col_energy = cv2.blur(col_energy.reshape(1,-1), (1, 2*k+1)).ravel()
    col_energy = (col_energy - col_energy.min()) / (np.ptp(col_energy) + 1e-6)
    peaks, thr = [], max(0.25, float(np.median(col_energy)) + 0.35*float(np.std(col_energy)))
    for i in range(2, len(col_energy)-2):
        if col_energy[i] > thr and col_energy[i] == max(col_energy[i-2:i+3]):
            if peaks and (i - peaks[-1]) <  TICK_MIN_SEP:
                if col_energy[i] > col_energy[peaks[-1]]: peaks[-1] = i
            else:
                peaks.append(i)
    tick_count = len(peaks)
    if tick_count < 3: return None, tick_count, 0.0
    diffs = np.diff(peaks)
    if diffs.size == 0: return None, tick_count, 0.0
    pph_tick = float(np.median(diffs))
    quality = float(min(1.0, tick_count/72.0))
    if verbose: print(f"[ticks] count={tick_count} pph_tick={pph_tick:.3f} quality={quality:.2f}")
    return pph_tick, tick_count, quality

# Helper: find explicit tick columns (hour lines) in ROI
def find_tick_columns(img_bgr, roi):
    """
    Return sorted pixel x-positions of hour tick lines within roi.
    Uses the same strip/sobel logic as detect_tick_pph but retains peaks.
    """
    x0,y0,x1,y1 = roi
    if x1 - x0 < 10:
        return []
    y_top = max(y0, y1 - (TICK_STRIP_H + 2))
    strip = img_bgr[y_top:y1-2, x0:x1]
    if strip.size == 0:
        return []
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    sob = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    col_energy = np.abs(sob).mean(axis=0)
    k = max(3, (x1-x0)//600)
    col_energy = cv2.blur(col_energy.reshape(1,-1), (1, 2*k+1)).ravel()
    col_energy = (col_energy - col_energy.min()) / (np.ptp(col_energy) + 1e-6)
    thr = max(0.25, float(np.median(col_energy)) + 0.35*float(np.std(col_energy)))
    peaks = []
    for i in range(2, len(col_energy)-2):
        if col_energy[i] > thr and col_energy[i] == max(col_energy[i-2:i+3]):
            if peaks and (i - peaks[-1]) < TICK_MIN_SEP:
                if col_energy[i] > col_energy[peaks[-1]]:
                    peaks[-1] = i
            else:
                peaks.append(i)
    return [x0 + int(p) for p in peaks]

def estimate_day_boundaries(img_bgr, roi):
    x0,y0,x1,y1 = sanitize_roi(img_bgr, roi)
    gray = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    ce = vertical_energy(gray)
    k = max(3, (x1-x0)//400)
    ce_s = cv2.blur(ce.reshape(1,-1), (1, 2*k+1)).ravel()
    W = (x1 - x0); approx1 = int(round(W/3)); approx2 = int(round(2*W/3))
    def snap(idx):
        lo = max(0, idx-40); hi = min(W-1, idx+40)
        if hi <= lo or ce_s.size == 0:
            # fallback to unsnapped position within ROI
            return x0 + int(max(1, min(W-2, idx)))
        seg = ce_s[lo:hi]
        if seg.size == 0:
            return x0 + int(max(1, min(W-2, idx)))
        return x0 + int(lo + int(np.argmin(seg)))
    d1 = snap(approx1); d2 = snap(approx2)
    if not (x0+100 < d1 < d2 < x1-100): d1 = x0 + approx1; d2 = x0 + approx2
    day_w = (d2 - x0) / 2.0
    x_day0 = x0; x_day1 = int(round(x0 + day_w)); x_day2 = int(round(x_day1 + day_w))
    return x_day0, x_day1, x_day2, float(day_w)

def detect_frontier(img_bgr, roi):
    x0, y0, x1, y1 = roi
    x1_dyn = detect_right_logo_margin(img_bgr, roi)
    x1_eff = max(x0 + 50, min(x1_dyn, x1) - RIGHT_EXCLUDE_PX//2)
    crop = img_bgr[y0:y1, x0:x1_eff]
    if crop.size == 0: return x0
    gry = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    col_std = gry.std(axis=0)
    k = max(3, (x1_eff - x0) // 600)
    col_std = cv2.blur(col_std.reshape(1, -1), (1, 2 * k + 1)).ravel()
    col_std = (col_std - col_std.min()) / (np.ptp(col_std) + 1e-6)
    thr = float(np.percentile(col_std, 40)) * 0.9
    idx = next((i for i in range(len(col_std)-1, -1, -1) if col_std[i] > thr), len(col_std)-1)
    return x0 + int(idx)

def x_for_hour_in_day(x_day_start, pph, hour_in_day):
    return int(round(x_day_start + float(hour_in_day) * float(pph)))

def compute_x_now(img_bgr, roi, tick_min_count=24, guard_minutes=15.0,
                  pp_hour_source="auto", verbose=False, accept_minutes=90.0,
                  last_modified=None, stale_hours=6.0):
    # 1) Use full sanitized ROI for day boundaries & px/hour
    x0f, y0f, x1f, y1f = sanitize_roi(img_bgr, roi)
    # 2) Build a trimmed ROI only for frontier guarding
    x1_trim = detect_right_logo_margin(img_bgr, (x0f, y0f, x1f, y1f))
    roi_full = (x0f, y0f, x1f, y1f)
    roi_trim = (x0f, y0f, x1_trim, y1f)

    # Day boundaries & pph from full width
    x_day0, x_day1, x_day2, day_w = estimate_day_boundaries(img_bgr, roi_full)
    pph_day = day_w / 24.0
    pph_tick, tick_count, _ = detect_tick_pph(img_bgr, roi_full, verbose=verbose)

    # If tick-based px/hour strongly disagrees with day-width, prefer ticks for geometry too
    # Heuristic: high-confidence ticks (>=48) and >20% discrepancy -> rebuild day geometry
    rebuild_from_ticks = False
    if pph_tick is not None and tick_count >= 48:
        discrep = abs(pph_tick - pph_day) / max(pph_day, 1e-6)
        rebuild_from_ticks = discrep > 0.20

    # choose px-per-hour; prefer day width; only trust ticks if very close to day estimate
    use_ticks = (pph_tick is not None and tick_count >= int(tick_min_count))
    pph = pph_day; pph_src = "day_width"
    if pp_hour_source == "ticks" and use_ticks:
        pph = pph_tick; pph_src = "ticks (forced)"
    elif pp_hour_source == "auto" and use_ticks:
        if rebuild_from_ticks or (abs(pph_tick - pph_day) / max(pph_day, 1e-6) <= 0.08):
            pph = pph_tick; pph_src = "ticks"

    # Optionally rebuild day1/day2 positions from tick px/hour to fix bad day-width snaps
    if rebuild_from_ticks and pph is not None:
        day_w_from_ticks = 24.0 * float(pph)
        x_day1 = int(round(x_day0 + day_w_from_ticks))
        x_day2 = int(round(x_day0 + 2.0 * day_w_from_ticks))
        day_w = day_w_from_ticks

    # Frontier based on trimmed ROI only (ignores right logo/panel)
    x_frontier = detect_frontier(img_bgr, roi_trim)
    guard_px = max(MIN_GUARD_PX, int(round(pph * (guard_minutes/60.0))))

    # Phase-align using explicit tick columns near the frontier (refines @now)
    x_now = None
    tick_cols = find_tick_columns(img_bgr, roi_trim)
    if tick_cols:
        # Keep ticks inside day 3 and left of the frontier guard
        left_day3 = x_day2 + 4
        right_guard = min(x1f - 2, x_frontier - guard_px)
        G = [x for x in tick_cols if left_day3 <= x <= right_guard]
        if len(G) >= 6:
            G = np.array(G, dtype=np.float32)
            # Consecutive hour indices, last tick nearest the frontier is floor(current hour)
            now_hour = hour_float(now_tsst)
            # pick the tick closest to frontier as anchor
            anchor_idx = int(np.argmax(G))  # rightmost in G
            # Assign integer hours decreasing to the left
            hours = np.arange(len(G), dtype=np.float32)
            hours = (now_hour - (hours.max() - hours))[::-1]
            # Fit hour = a*x + b (robust linear model via least squares)
            A = np.vstack([G, np.ones_like(G)]).T
            sol, _, _, _ = np.linalg.lstsq(A, hours, rcond=None)
            a, b = float(sol[0]), float(sol[1])
            # Invert to get x at current hour
            x_now_lin = a and int(round((now_hour - b) / a)) or right_guard
            # Clamp into guards
            x_now = int(np.clip(x_now_lin, left_day3, right_guard))

    # Compute time in Tomsk local and map to x within day3 (full ROI geometry)
    now_tsst = tsst_now()
    hour_now = hour_float(now_tsst)
    x_time = x_for_hour_in_day(x_day2, pph, hour_now)

    measured_bias_minutes = None; bias_minutes_applied = 0.0
    fresh_ok = False
    if last_modified is not None:
        age_min = (datetime.now(timezone.utc) - last_modified).total_seconds()/60.0
        fresh_ok = age_min < 45.0

    left_guard  = x_day2 + 2
    right_guard = min(x1f - 2, x_frontier - guard_px)

    if fresh_ok:
        lm_tsst = last_modified.astimezone(timezone(timedelta(hours=UTC_TO_TSST_HOURS)))
        lm_hour = hour_float(lm_tsst)
        x_lm = x_for_hour_in_day(x_day2, pph, lm_hour)
        dx_px = x_frontier - x_lm
        measured_bias_minutes = (dx_px / max(pph, 1e-6)) * 60.0
        if abs(measured_bias_minutes) <= float(accept_minutes):
            bias_minutes_applied = float(measured_bias_minutes)

    x_ideal = int(round(x_time + (bias_minutes_applied/60.0)*pph))
    if x_now is None:
        right_guard = min(x1f - 2, x_frontier - guard_px)
        x_now = int(np.clip(x_ideal, left_guard, right_guard))

    age_hours = None
    if last_modified is not None:
        age_hours = (datetime.now(timezone.utc) - last_modified).total_seconds()/3600.0
    status = "ok" if (age_hours is None or age_hours <= float(stale_hours)) else "stale_source"

    dbg = {
        "x_day0": x_day0, "x_day1": x_day1, "x_day2": x_day2,
        "day_w": day_w, "pph": pph, "pph_source": pph_src,
        "x_frontier": x_frontier, "guard_px": guard_px,
        "x_time": x_time, "x_ideal": x_ideal, "x_now": x_now,
        "bias_minutes_applied": bias_minutes_applied,
        "measured_bias_minutes": measured_bias_minutes,
        "status": status,
        "rebuild_from_ticks": rebuild_from_ticks,
        "pph_tick": pph_tick,
        "tick_pph": pph_tick, "tick_count": tick_count,
        "x_now_method": ("ticks_phase" if tick_cols and x_now is not None else "pph_guard"),
    }
    return x_now, dbg

def pick_colored_lines_at_x(img_bgr, roi, x_now, chart_type="F", band_px=5, freq_max_hz=40.0):
    """
    For each series color, find y where HSV distance is minimal around x_now.
    Uses small per-series vertical windows for F (based on nominal Hz ranges) to avoid grid/legend.
    Returns y positions and normalized [0..1] values from top->bottom plus draw color and proper label per chart.
    """
    x0,y0,x1,y1 = roi
    x = int(np.clip(x_now, x0+1, x1-2))
    lo = max(x0, x - band_px); hi = min(x1, x + band_px + 1)
    # avoid chart borders: shrink vertical span slightly
    pad_top, pad_bot = 4, 18
    y0i = min(y1-1, y0 + pad_top)
    y1i = max(y0i+1, y1 - pad_bot)
    crop = img_bgr[y0i:y1i, lo:hi, :]
    if crop.size == 0 or (hi - lo) <= 0:
        mid_y = (y0 + y1) // 2
        results = {}
        for key, (label, rgb, bgr_draw, f_lbl, a_lbl, q_lbl) in SERIES.items():
            series_name = {"F": f_lbl, "A": a_lbl, "Q": q_lbl}[chart_type]
            results[series_name] = {"y_px": int(mid_y), "y_norm": 0.5, "draw": bgr_draw}
        return results

    # Convert band to HSV once
    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    # Helper to convert Hz ranges to row indices (for F windows)
    def hz_to_row_bounds(hz_lo, hz_hi):
        y_lo = int(round(y0i + (hz_lo/freq_max_hz) * (y1i - y0i)))
        y_hi = int(round(y0i + (hz_hi/freq_max_hz) * (y1i - y0i)))
        y_lo, y_hi = sorted((max(y0i, y_lo), min(y1i-1, y_hi)))
        return y_lo, y_hi

    # nominal vertical windows for F1..F4 (SOS70 chart label-aligned)
    f_windows = {
        "F1": hz_to_row_bounds(6.8, 8.9),
        "F2": hz_to_row_bounds(12.5, 16.5),
        "F3": hz_to_row_bounds(18.5, 22.8),
        "F4": hz_to_row_bounds(24.5, 27.8),
    }

    results = {}
    for key, (label, rgb, bgr_draw, f_lbl, a_lbl, q_lbl) in SERIES.items():
        series_name = {"F": f_lbl, "A": a_lbl, "Q": q_lbl}[chart_type]
        # Build row cost from HSV distance
        tgt_hsv = bgr_to_hsv_color((rgb[2], rgb[1], rgb[0]))  # convert from RGB->BGR then to HSV
        row_cost = hsv_row_distance(crop_hsv, tgt_hsv, label)

        # Apply windowing for F to avoid wrong trace
        if chart_type == "F":
            wy0, wy1 = f_windows[series_name]  # absolute image coords
            # convert to crop row indices
            wy0c = max(0, wy0 - y0); wy1c = min(crop.shape[0]-1, wy1 - y0)
            if wy1c > wy0c:
                # penalize outside window
                mask = np.ones_like(row_cost) * 10.0
                mask[wy0c:wy1c+1] = 0.0
                row_cost = row_cost + mask

        # Light median filter to stabilize row cost
        row_cost = cv2.blur(row_cost.reshape(-1,1), (1,5)).ravel()
        y_rel = int(np.argmin(row_cost))
        y_pix = y0i + y_rel
        y_norm = (y_pix - y0i) / max(1.0, (y1i - y0i))
        results[series_name] = {"y_px": int(y_pix), "y_norm": float(y_norm), "draw": bgr_draw}
    return results

def draw_overlay_with_picks(img_bgr, roi, x_now, picks, title, chart_type="F"):
    out = img_bgr.copy()
    x0,y0,x1,y1 = roi
    # vertical x_now
    cv2.line(out, (x_now, y0), (x_now, y1), (0,0,255), 2)
    # markers + labels
    for series_name, val in picks.items():
        y = int(val["y_px"]); color = val["draw"]
        cv2.circle(out, (x_now, y), 5, color, -1)
        txt = f"{series_name}"
        cv2.putText(out, txt, (min(x_now+8, x1-140), max(y-6, y0+14)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
    cv2.putText(out, title, (x0+8, y0+18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1, cv2.LINE_AA)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dir", default="runs")
    ap.add_argument("--save-overlays", default="true")
    ap.add_argument("--freq-max-hz", type=float, default=40.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    save_overlays = str(args.save_overlays).lower() == "true"
    os.makedirs(args.dir, exist_ok=True)

    # fetch images
    F_img, F_lm = fetch_image(URL_F)
    A_img, A_lm = fetch_image(URL_A)
    Q_img, Q_lm = fetch_image(URL_Q)
    F_lm_dt = parse_last_modified(F_lm)
    A_lm_dt = parse_last_modified(A_lm)
    Q_lm_dt = parse_last_modified(Q_lm)

    roiF = sanitize_roi(F_img, ROI)
    roiA = sanitize_roi(A_img, ROI)
    roiQ = sanitize_roi(Q_img, ROI)

    xF, dbgF = compute_x_now(F_img, roiF, last_modified=F_lm_dt, verbose=args.verbose)
    xA, dbgA = compute_x_now(A_img, roiA, last_modified=A_lm_dt, verbose=args.verbose)
    xQ, dbgQ = compute_x_now(Q_img, roiQ, last_modified=Q_lm_dt, verbose=args.verbose)

    picksF = pick_colored_lines_at_x(F_img, roiF, xF, chart_type="F", band_px=5, freq_max_hz=float(args.freq_max_hz))
    picksA = pick_colored_lines_at_x(A_img, roiA, xA, chart_type="A", band_px=5, freq_max_hz=float(args.freq_max_hz))
    picksQ = pick_colored_lines_at_x(Q_img, roiQ, xQ, chart_type="Q", band_px=5, freq_max_hz=float(args.freq_max_hz))

    # overlays
    F_overlay = A_overlay = Q_overlay = None
    if save_overlays:
        F_overlay = os.path.join(args.dir, "tomsk_params_f_overlay.png")
        A_overlay = os.path.join(args.dir, "tomsk_params_a_overlay.png")
        Q_overlay = os.path.join(args.dir, "tomsk_params_q_overlay.png")
        def stamp(img, roi, x_now, title):
            out = draw_overlay_with_picks(img, roi, x_now, picksF if "F " in title else (picksA if "A " in title else picksQ), title, chart_type=("F" if "F " in title else ("A" if "A " in title else "Q")))
            x0,y0,x1,y1 = roi
            now_local = tsst_now().strftime("%Y-%m-%d %H:%M TSST")
            cv2.putText(out, now_local, (x0+8, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255,255,255), 1, cv2.LINE_AA)
            return out
        cv2.imwrite(F_overlay, stamp(F_img, roiF, xF, "F params @ x_now"))
        cv2.imwrite(A_overlay, stamp(A_img, roiA, xA, "A params @ x_now"))
        cv2.imwrite(Q_overlay, stamp(Q_img, roiQ, xQ, "Q params @ x_now"))

    freq_max = float(args.freq_max_hz)

    out = {
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "tomsk_sos70_param_charts",
        "freq_max_hz": freq_max,
        "values": {
            "F_norm": {k: float(v["y_norm"]) for k,v in picksF.items()},
            "F_y_px": {k: int(v["y_px"]) for k,v in picksF.items()},
            "A_norm": {k: float(v["y_norm"]) for k,v in picksA.items()},
            "A_y_px": {k: int(v["y_px"]) for k,v in picksA.items()},
            "Q_norm": {k: float(v["y_norm"]) for k,v in picksQ.items()},
            "Q_y_px": {k: int(v["y_px"]) for k,v in picksQ.items()},
        },
        "debug": { "F": dbgF, "A": dbgA, "Q": dbgQ,
                   "urls": {"F": URL_F, "A": URL_A, "Q": URL_Q},
                   "overlays": {"F": F_overlay, "A": A_overlay, "Q": Q_overlay} }
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    if args.verbose:
        print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
