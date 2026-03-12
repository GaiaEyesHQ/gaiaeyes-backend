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
RIGHT_PICK_SAFETY_PX = 24
RIGHT_PICK_SAFETY_PX_F = 12
UTC_TO_TSST_HOURS = 7
TICK_MIN_SEP = 8
TICK_MIN_COUNT = 24
MIN_GUARD_PX = 6
DEFAULT_ACCEPT_MINUTES = 90.0
DEFAULT_SNAP_THRESHOLD_MINUTES = 45.0
TICK_PPH_REL_TOL = 0.20

FRONTIER_COLOR_S_MIN = 35
FRONTIER_COLOR_V_MIN = 28
FRONTIER_MIN_ACTIVITY = 0.16
FRONTIER_MIN_RUN_PX = 8

# Early-day rollover heuristic: sometimes SOS70 rightmost panel is still "yesterday".
ROLLOVER_EARLY_HOUR_MIN = 3.0
ROLLOVER_EARLY_HOUR_MAX = 8.5
ROLLOVER_MIN_GAP_HOURS = 8.0
ROLLOVER_MIN_FRONTIER_DAY_FILL = 0.88
ROLLOVER_MIN_RIGHT_TAIL_ACTIVITY = 0.10

# Series colors (RGB for reading; drawing uses BGR). Order is consistent across charts.
SERIES = {
    "s1": ("white",  (240,240,240), (255,255,255), "F1", "A1", "Q1"),
    "s2": ("yellow", (230,210,30),  (0,255,255),   "F2", "A2", "Q2"),
    "s3": ("red",    (200,40,40),   (0,0,255),     "F3", "A3", "Q3"),
    "s4": ("green",  (40,160,60),   (0,200,100),   "F4", "A4", "Q4"),
}

# Per-series lane windows (normalized in plotting ROI, top=0 -> bottom=1).
SERIES_LANE_WINDOWS = {
    "F": {"F1": (0.02, 0.22), "F2": (0.24, 0.42), "F3": (0.43, 0.59), "F4": (0.60, 0.76)},
    "A": {"A1": (0.03, 0.32), "A2": (0.20, 0.54), "A3": (0.42, 0.76), "A4": (0.68, 0.995)},
    "Q": {"Q1": (0.05, 0.36), "Q2": (0.24, 0.58), "Q3": (0.42, 0.78), "Q4": (0.70, 0.995)},
}

# Pick windows can be narrower than scale windows to avoid high-side mis-locks.
PICK_LANE_WINDOWS = {
    "F": {"F1": (0.02, 0.22), "F2": (0.26, 0.45), "F3": (0.43, 0.59), "F4": (0.62, 0.80)},
    "A": {"A1": (0.03, 0.32), "A2": (0.25, 0.60), "A3": (0.42, 0.76), "A4": (0.68, 0.995)},
    "Q": {"Q1": (0.05, 0.36), "Q2": (0.24, 0.58), "Q3": (0.42, 0.78), "Q4": (0.70, 0.96)},
}

# Per-series value ranges read from SOS70 chart axes (top=max, bottom=min).
SERIES_VALUE_RANGES = {
    "F": {"F1": (7.20, 8.40), "F2": (13.10, 14.50), "F3": (18.60, 20.20), "F4": (24.10, 26.50)},
    "A": {"A1": (1.00, 45.00), "A2": (1.00, 61.50), "A3": (2.20, 12.20), "A4": (1.10, 10.20)},
    "Q": {"Q1": (4.00, 38.00), "Q2": (5.00, 17.50), "Q3": (7.00, 23.00), "Q4": (5.00, 30.00)},
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

def resolve_plot_right_edge(x0, x1, x1_dyn):
    """
    Resolve the right plotting edge without double-cutting.
    - static cut: fixed margin to avoid legend/logo area
    - dynamic cut: logo detector
    Dynamic cut is ignored if it clips too far beyond the static cut.
    """
    x1_static = int(max(x0 + 50, x1 - RIGHT_EXCLUDE_PX))
    x1_dyn_clamped = int(np.clip(int(x1_dyn), x0 + 50, x1))
    # Guard against aggressive dynamic trims into valid data.
    if x1_dyn_clamped < (x1_static - 25):
        return x1_static, x1_static, x1_dyn_clamped, False
    x1_eff = int(min(x1_static, x1_dyn_clamped))
    dyn_used = bool(x1_dyn_clamped <= x1_static)
    return x1_eff, x1_static, x1_dyn_clamped, dyn_used

def safe_pick_x(x_now, roi, dbg, back_px, safety_px=RIGHT_PICK_SAFETY_PX):
    """
    Keep x-picking away from the far-right logo/legend zone while staying near x_now.
    """
    x0, _y0, x1, _y1 = roi
    default_plot_end = max(x0 + 50, x1 - RIGHT_EXCLUDE_PX)
    x_plot_end = int(dbg.get("x_plot_end", default_plot_end) or default_plot_end)
    safe_right = int(np.clip(x_plot_end - int(safety_px), x0 + 2, x1 - 2))
    x_pick = int(np.clip(min(int(x_now) - int(back_px), safe_right), x0 + 1, x1 - 2))
    return x_pick, safe_right

def lane_window_to_rows(roi, norm_lo, norm_hi, pad_top=4, pad_bot=18):
    x0, y0, x1, y1 = roi
    y0i = min(y1 - 1, y0 + pad_top)
    y1i = max(y0i + 1, y1 - pad_bot)
    h = max(1.0, float(y1i - y0i))
    y_lo = int(round(y0i + float(norm_lo) * h))
    y_hi = int(round(y0i + float(norm_hi) * h))
    y_lo = max(y0i, min(y1i - 1, y_lo))
    y_hi = max(y0i, min(y1i - 1, y_hi))
    return y0i, y1i, min(y_lo, y_hi), max(y_lo, y_hi)

def find_series_style(chart_type, series_name):
    for _key, (label, rgb, bgr_draw, f_lbl, a_lbl, q_lbl) in SERIES.items():
        n = {"F": f_lbl, "A": a_lbl, "Q": q_lbl}[chart_type]
        if n == series_name:
            return {"label": label, "rgb": rgb, "draw": bgr_draw}
    return None

def attach_lane_norms(picks, roi, chart_type):
    lanes = SERIES_LANE_WINDOWS.get(chart_type, {})
    out = dict(picks)
    for series_name, data in picks.items():
        d = dict(data)
        if series_name in lanes:
            n_lo, n_hi = lanes[series_name]
            _y0i, _y1i, y_lo, y_hi = lane_window_to_rows(roi, n_lo, n_hi)
            y = int(d.get("y_px", y_lo))
            span = max(1.0, float(y_hi - y_lo))
            lane_norm = (float(y) - float(y_lo)) / span
            d["lane_norm"] = float(np.clip(lane_norm, 0.0, 1.0))
        out[series_name] = d
    return out

def convert_picks_to_values(picks, chart_type):
    """
    Convert picked y-positions into chart values using per-series lane ranges.
    """
    ranges = SERIES_VALUE_RANGES.get(chart_type, {})
    values = {}
    for series_name, data in picks.items():
        if series_name not in ranges:
            continue
        vmin, vmax = ranges[series_name]
        ln = float(data.get("lane_norm", data.get("y_norm", 0.5)))
        ln = float(np.clip(ln, 0.0, 1.0))
        values[series_name] = float(vmax - ln * (vmax - vmin))
    return values

def refine_series_local_snap(
    img_bgr,
    roi,
    x_center,
    picks,
    chart_type,
    series_name,
    search_px=6,
    band_px=2,
    edge_margin_px=0,
    search_up_px=None,
    search_down_px=None,
    prefer_lower_weight=0.0,
    min_y_px=None,
    max_y_px=None,
):
    """
    Small local y-snap around an existing pick to reduce residual 1-3 px offsets.
    Keeps the search constrained to both the lane and a local neighborhood.
    """
    if series_name not in picks:
        return picks, {}
    style = find_series_style(chart_type, series_name)
    if style is None:
        return picks, {}
    lanes = PICK_LANE_WINDOWS.get(chart_type, {})
    if series_name not in lanes:
        return picks, {}

    x0, y0, x1, y1 = roi
    x = int(np.clip(x_center, x0 + 1, x1 - 2))
    lo = max(x0, x - int(band_px))
    hi = min(x1, x + int(band_px) + 1)

    y0i, y1i, lane_y0, lane_y1 = lane_window_to_rows(roi, lanes[series_name][0], lanes[series_name][1])
    crop = img_bgr[y0i:y1i, lo:hi, :]
    if crop.size == 0:
        return picks, {}

    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    tgt_hsv = bgr_to_hsv_color((style["rgb"][2], style["rgb"][1], style["rgb"][0]))
    row_cost = hsv_row_distance(crop_hsv, tgt_hsv, style["label"]).astype(np.float32).ravel()
    row_cost = cv2.blur(row_cost.reshape(-1, 1), (1, 5)).ravel()

    # Hard lane gate
    lane0 = max(0, lane_y0 - y0i + int(edge_margin_px))
    lane1 = min(crop.shape[0] - 1, lane_y1 - y0i - int(edge_margin_px))
    if lane1 <= lane0:
        lane0 = max(0, lane_y0 - y0i)
        lane1 = min(crop.shape[0] - 1, lane_y1 - y0i)
    if min_y_px is not None:
        lane0 = max(lane0, int(min_y_px) - y0i)
    if max_y_px is not None:
        lane1 = min(lane1, int(max_y_px) - y0i)
    if lane1 <= lane0:
        return picks, {}
    lane_mask = np.ones_like(row_cost) * 8.0
    lane_mask[lane0:lane1 + 1] = 0.0
    row_cost = row_cost + lane_mask

    # Anchor the local search inside the currently allowed lane/constraints.
    # This prevents ordered passes from becoming no-ops when the seed pick is outside bounds.
    y_ref = int(np.clip(int(picks[series_name]["y_px"]) - y0i, lane0, lane1))
    up_px = int(search_px if search_up_px is None else search_up_px)
    dn_px = int(search_px if search_down_px is None else search_down_px)
    s0 = max(lane0, y_ref - up_px)
    s1 = min(lane1, y_ref + dn_px)
    if s1 <= s0:
        s0, s1 = lane0, lane1
        if s1 <= s0:
            return picks, {}

    local_cost = row_cost[s0:s1 + 1].copy()
    if float(prefer_lower_weight) > 0.0 and lane1 > lane0:
        ys = np.arange(s0, s1 + 1, dtype=np.float32)
        frac_up = (float(lane1) - ys) / max(1.0, float(lane1 - lane0))
        local_cost = local_cost + float(prefer_lower_weight) * (frac_up ** 2)

    y_rel = int(s0 + int(np.argmin(local_cost)))
    y_pix = int(y0i + y_rel)
    y_norm = (y_pix - y0i) / max(1.0, float(y1i - y0i))
    lane_norm = (float(y_pix) - float(lane_y0)) / max(1.0, float(lane_y1 - lane_y0))

    picks[series_name]["y_px"] = int(y_pix)
    picks[series_name]["y_norm"] = float(y_norm)
    picks[series_name]["lane_norm"] = float(np.clip(lane_norm, 0.0, 1.0))
    dbg = {
        f"{series_name.lower()}_local_snap_x": int(x),
        f"{series_name.lower()}_local_snap_y_px": int(y_pix),
        f"{series_name.lower()}_local_snap_search_px": int(search_px),
        f"{series_name.lower()}_local_snap_search_up_px": int(up_px),
        f"{series_name.lower()}_local_snap_search_down_px": int(dn_px),
        f"{series_name.lower()}_local_snap_prefer_lower_weight": float(prefer_lower_weight),
    }
    return picks, dbg

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

def smooth_1d(arr, radius):
    arr = np.asarray(arr, dtype=np.float32).ravel()
    r = int(max(0, radius))
    if arr.size <= 2 or r <= 0:
        return arr.copy()
    k = 2 * r + 1
    kernel = np.ones(k, dtype=np.float32) / float(k)
    return np.convolve(arr, kernel, mode="same")

def normalize_robust(arr):
    arr = np.asarray(arr, dtype=np.float32).ravel()
    if arr.size == 0:
        return arr
    p10 = float(np.percentile(arr, 10))
    p90 = float(np.percentile(arr, 90))
    if (p90 - p10) < 1e-6:
        return np.zeros_like(arr)
    return np.clip((arr - p10) / (p90 - p10), 0.0, 1.0)

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

def detect_frontier(img_bgr, roi, return_debug=False):
    x0, y0, x1, y1 = roi
    x1_dyn = detect_right_logo_margin(img_bgr, roi)
    x1_eff, x1_static, x1_dyn_clamped, dyn_used = resolve_plot_right_edge(x0, x1, x1_dyn)
    crop = img_bgr[y0:y1, x0:x1_eff]
    if crop.size == 0:
        frontier = x0
        dbg = {"method": "empty", "activity_thr": None, "activity_right_tail": None}
        return (frontier, dbg) if return_debug else frontier

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)

    color_mask = ((sat >= FRONTIER_COLOR_S_MIN) & (val >= FRONTIER_COLOR_V_MIN)).astype(np.float32)
    col_color = color_mask.mean(axis=0)

    col_diff = np.zeros(gray.shape[1], dtype=np.float32)
    if gray.shape[1] > 1:
        col_diff[1:] = np.abs(np.diff(gray, axis=1)).mean(axis=0)

    smooth_r = max(2, int((x1_eff - x0) / 700.0))
    color_s = smooth_1d(col_color, smooth_r)
    diff_s = smooth_1d(col_diff, smooth_r)

    color_n = normalize_robust(color_s)
    diff_n = normalize_robust(diff_s)
    activity = 0.45 * color_n + 0.55 * diff_n

    thr = max(FRONTIER_MIN_ACTIVITY, float(np.percentile(activity, 65)) * 0.85)
    run = max(FRONTIER_MIN_RUN_PX, int(round((x1_eff - x0) / 220.0)))

    idx = None
    for i in range(len(activity) - 1, run - 2, -1):
        window = activity[i - run + 1:i + 1]
        if float(np.mean(window)) >= thr:
            idx = i
            break

    method = "activity_scan"
    if idx is None:
        col_std = gray.std(axis=0)
        col_std = smooth_1d(col_std, max(2, int((x1_eff - x0) / 600.0)))
        col_std = (col_std - col_std.min()) / (np.ptp(col_std) + 1e-6)
        thr_std = max(0.10, float(np.percentile(col_std, 55)) * 0.9)
        for i in range(len(col_std) - 1, -1, -1):
            if float(col_std[i]) > thr_std:
                idx = i
                break
        method = "std_fallback"

    if idx is None:
        idx = len(activity) - 1
        method = "right_edge_fallback"

    frontier = x0 + int(idx)
    tail_len = int(min(len(activity), max(20, run * 2)))
    right_tail = float(np.mean(activity[-tail_len:])) if tail_len > 0 else 0.0
    dbg = {
        "method": method,
        "activity_thr": float(thr),
        "activity_right_tail": right_tail,
        "activity_run_px": int(run),
        "x1_eff": int(x1_eff),
        "x1_static": int(x1_static),
        "x1_dyn": int(x1_dyn_clamped),
        "x1_dyn_used": bool(dyn_used),
    }
    return (frontier, dbg) if return_debug else frontier

def x_for_hour_in_day(x_day_start, pph, hour_in_day):
    return int(round(x_day_start + float(hour_in_day) * float(pph)))

def compute_x_now(img_bgr, roi, tick_min_count=24, guard_minutes=15.0,
                  pp_hour_source="auto", verbose=False, accept_minutes=DEFAULT_ACCEPT_MINUTES,
                  last_modified=None, stale_hours=6.0, min_guard_px=MIN_GUARD_PX):
    x0, y0, x1, y1 = sanitize_roi(img_bgr, roi)

    # Timing uses geometry-derived day boundaries from the plotting area width.
    x1_dyn = detect_right_logo_margin(img_bgr, (x0, y0, x1, y1))
    x1_eff, x1_static, x1_dyn_clamped, dyn_used = resolve_plot_right_edge(x0, x1, x1_dyn)
    x_plot_end = x1_eff
    w_time = float(x1_eff - x0)
    day_w_time = w_time / 3.0
    x_day0_time = x0
    x_day1_time = int(round(x0 + day_w_time))
    x_day2_time = int(round(x0 + 2.0 * day_w_time))
    pph_day = day_w_time / 24.0

    # Content-derived splits are kept for diagnostics only.
    x_day0, x_day1, x_day2, day_w = estimate_day_boundaries(img_bgr, (x0, y0, x1, y1))

    pph_tick, tick_count, tick_quality = detect_tick_pph(img_bgr, (x0, y0, x1, y1), verbose=verbose)
    pph = pph_day
    pph_src = "day_width"
    use_ticks = (pph_tick is not None and tick_count >= int(tick_min_count))
    tick_pph_rel_err = None
    tick_pph_valid = False
    if use_ticks:
        tick_pph_rel_err = abs(float(pph_tick) - float(pph_day)) / max(float(pph_day), 1e-6)
        tick_pph_valid = bool(tick_pph_rel_err <= float(TICK_PPH_REL_TOL))
    if pp_hour_source == "ticks":
        if use_ticks and tick_pph_valid:
            pph = pph_tick
            pph_src = "ticks"
        else:
            pph_src = "day_width (ticks-forced-fallback)"
    elif pp_hour_source == "auto" and use_ticks and tick_pph_valid:
        pph = pph_tick
        pph_src = "ticks"
    elif pp_hour_source == "auto" and use_ticks and not tick_pph_valid:
        pph_src = "day_width (tick-mismatch-fallback)"

    x_frontier, frontier_dbg = detect_frontier(img_bgr, (x0, y0, x1, y1), return_debug=True)
    guard_px = max(int(min_guard_px), int(round(pph * (guard_minutes / 60.0))))

    now_tsst = tsst_now()
    hour_now = hour_float(now_tsst)
    x_time = x_for_hour_in_day(x_day2_time, pph, hour_now)
    x_ideal = x_time

    measured_bias_minutes = None
    bias_minutes_applied = 0.0
    fresh_ok = False
    if last_modified is not None:
        age_min = (datetime.now(timezone.utc) - last_modified).total_seconds() / 60.0
        fresh_ok = age_min < 45.0
    edge_ok = (x1 - x_frontier) > (guard_px + 2)

    if fresh_ok and edge_ok:
        lm_tsst = last_modified.astimezone(timezone(timedelta(hours=UTC_TO_TSST_HOURS)))
        lm_hour = hour_float(lm_tsst)
        x_lm = x_for_hour_in_day(x_day2_time, pph, lm_hour)
        dx_px = x_frontier - x_lm
        measured_bias_minutes = (dx_px / max(pph, 1e-6)) * 60.0
        if abs(measured_bias_minutes) <= float(accept_minutes):
            bias_minutes_applied = float(measured_bias_minutes)

    x_ideal = int(round(x_time + (bias_minutes_applied / 60.0) * pph))
    left_guard = x_day2_time + 2
    right_guard = min(x1 - 2, x_frontier - guard_px)
    guard_invalid = bool(right_guard <= left_guard + 10)

    delta_guard_px = right_guard - x_ideal
    delta_guard_min = (delta_guard_px / max(pph, 1e-6)) * 60.0
    delta_frontier_px = x_frontier - x_ideal
    delta_frontier_min = (delta_frontier_px / max(pph, 1e-6)) * 60.0
    frontier_day_fill = float((x_frontier - x_day2_time) / max(day_w_time, 1e-6))
    rollover_candidate = bool(
        (hour_now >= float(ROLLOVER_EARLY_HOUR_MIN))
        and (hour_now <= float(ROLLOVER_EARLY_HOUR_MAX))
        and (delta_guard_min >= float(ROLLOVER_MIN_GAP_HOURS * 60.0))
        and (frontier_day_fill >= float(ROLLOVER_MIN_FRONTIER_DAY_FILL))
        and (float(frontier_dbg.get("activity_right_tail") or 0.0) >= float(ROLLOVER_MIN_RIGHT_TAIL_ACTIVITY))
    )
    # Snap only when ideal time is beyond available right edge (future vs data).
    if rollover_candidate:
        x_now_pre = right_guard
        x_now_method = "rollover_snap_to_guard"
    elif delta_frontier_min < -float(DEFAULT_SNAP_THRESHOLD_MINUTES):
        x_now_pre = right_guard
        x_now_method = "snap_to_guard"
    else:
        x_now_pre = x_ideal
        x_now_method = "ideal"

    if x_now_method in {"snap_to_guard", "rollover_snap_to_guard"}:
        x_now = int(np.clip(x_now_pre, left_guard, right_guard))
    else:
        x_now = int(np.clip(x_now_pre, x0 + 2, x1 - 2))
    if guard_invalid:
        x_now = int(np.clip(right_guard, x0 + 2, x1 - 2))
        x_now_method = "guard_invalid"

    age_hours = None
    if last_modified is not None:
        age_hours = (datetime.now(timezone.utc) - last_modified).total_seconds() / 3600.0
    status = "ok"
    if age_hours is not None and age_hours > float(stale_hours):
        status = "stale_source"
    if guard_invalid and status == "ok":
        status = "no_recent_data"

    dbg = {
        "x_day0": x_day0,
        "x_day1": x_day1,
        "x_day2": x_day2,
        "day_w": day_w,
        "x_day0_time": x_day0_time,
        "x_day1_time": x_day1_time,
        "x_day2_time": x_day2_time,
        "day_w_time": day_w_time,
        "x_plot_end": x_plot_end,
        "x1_static": x1_static,
        "x1_dyn": x1_dyn_clamped,
        "x1_dyn_used": bool(dyn_used),
        "pph": pph,
        "pph_source": pph_src,
        "pph_tick": pph_tick,
        "tick_pph_rel_err": tick_pph_rel_err,
        "tick_pph_valid": bool(tick_pph_valid),
        "tick_count": int(tick_count),
        "tick_quality": float(tick_quality),
        "tick_used": bool(pph_src == "ticks"),
        "x_frontier": x_frontier,
        "frontier_method": frontier_dbg.get("method"),
        "frontier_activity_thr": frontier_dbg.get("activity_thr"),
        "frontier_activity_right_tail": frontier_dbg.get("activity_right_tail"),
        "frontier_activity_run_px": frontier_dbg.get("activity_run_px"),
        "guard_px": guard_px,
        "left_guard": left_guard,
        "right_guard": right_guard,
        "x_time": x_time,
        "x_ideal": x_ideal,
        "x_now": x_now,
        "x_now_method": x_now_method,
        "hour_now_tsst": float(hour_now),
        "rollover_hour_min": float(ROLLOVER_EARLY_HOUR_MIN),
        "rollover_hour_max": float(ROLLOVER_EARLY_HOUR_MAX),
        "delta_min_to_guard": float(delta_guard_min),
        "delta_min_to_frontier": float(delta_frontier_min),
        "frontier_day_fill": float(frontier_day_fill),
        "rollover_candidate": bool(rollover_candidate),
        "bias_minutes_applied": float(bias_minutes_applied),
        "measured_bias_minutes": measured_bias_minutes,
        "age_hours": age_hours,
        "status": status,
    }
    return x_now, dbg

def harmonize_x_now_across_charts(x_vals, dbg_vals, rois):
    """
    Keep F/A/Q aligned in time when one chart drifts.
    If spread is large, avoid blindly trusting right-edge rollover snaps.
    Prefer non-rollover candidates when available; otherwise fall back to median.
    """
    keys = ("F", "A", "Q")
    xs = [int(x_vals[k]) for k in keys]
    spread_px = int(max(xs) - min(xs))
    pphs = [float(dbg_vals[k].get("pph", 0.0) or 0.0) for k in keys]
    pph_ref = float(np.median([p for p in pphs if p > 0.0])) if any(p > 0.0 for p in pphs) else 18.0
    spread_hours = float(spread_px / max(pph_ref, 1e-6))
    threshold_hours = 1.25
    harmonized = spread_hours > threshold_hours
    x_anchor = int(round(float(np.median(xs))))
    reason = "median"

    if harmonized:
        pairs = [("F", "A"), ("F", "Q"), ("A", "Q")]
        pair_diffs = []
        for a, b in pairs:
            d_px = abs(int(x_vals[a]) - int(x_vals[b]))
            d_hr = float(d_px / max(pph_ref, 1e-6))
            pair_diffs.append((d_hr, d_px, a, b))
        pair_diffs.sort(key=lambda t: t[0])
        best_hr, _best_px, k1, k2 = pair_diffs[0]
        if best_hr <= 1.25:
            x_anchor = int(round((int(x_vals[k1]) + int(x_vals[k2])) / 2.0))
            reason = "pair_cluster"
        else:
            non_roll_keys = [k for k in keys if not bool(dbg_vals[k].get("rollover_candidate", False))]
            if len(non_roll_keys) > 0:
                x_anchor = int(round(float(np.median([int(x_vals[k]) for k in non_roll_keys]))))
                reason = "prefer_non_rollover"
            else:
                fills = {k: float(dbg_vals[k].get("frontier_day_fill", 1.0) or 1.0) for k in keys}
                fill_span = float(max(fills.values()) - min(fills.values()))
                # Strong frontier disagreement: choose conservative (left-most) anchor.
                if fill_span >= 0.25:
                    x_anchor = int(min(int(x_vals[k]) for k in keys))
                    reason = "frontier_disagreement_conservative"

    out = dict(x_vals)
    if harmonized:
        for key in keys:
            x0, _y0, x1, _y1 = rois[key]
            out[key] = int(np.clip(x_anchor, x0 + 2, x1 - 2))
            dbg_vals[key]["x_now_before_harmonize"] = int(x_vals[key])
            dbg_vals[key]["x_now"] = int(out[key])
            dbg_vals[key]["x_now_method"] = f"harmonized_{reason}"
        dbg_vals["shared_x_now"] = int(x_anchor)
        dbg_vals["x_now_harmonize_reason"] = reason
    dbg_vals["x_now_harmonized"] = bool(harmonized)
    dbg_vals["x_now_spread_px"] = int(spread_px)
    dbg_vals["x_now_spread_hours"] = float(spread_hours)
    return out, dbg_vals

def pick_colored_lines_at_x(img_bgr, roi, x_now, chart_type="F", band_px=5, freq_max_hz=40.0, x_right_limit=None):
    """
    For each series color, find y where HSV distance is minimal around x_now.
    Uses small per-series vertical windows for F (based on nominal Hz ranges) to avoid grid/legend.
    Returns y positions and normalized [0..1] values from top->bottom plus draw color and proper label per chart.
    """
    x0,y0,x1,y1 = roi
    x = int(np.clip(x_now, x0+1, x1-2))
    xr = None
    if x_right_limit is not None:
        xr = int(np.clip(x_right_limit, x0 + 1, x1 - 2))
        x = min(x, xr)
    lo = max(x0, x - band_px); hi = min(x1, x + band_px + 1)
    if xr is not None:
        hi = min(hi, xr + 1)
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

    # Chart-specific normalized row windows to avoid grid/legend false positives.
    # These bands follow stable visual lanes on SOS70 parameter plots.
    lane_windows = PICK_LANE_WINDOWS

    def norm_window_to_rows(norm_lo, norm_hi):
        h = max(1.0, float(y1i - y0i))
        y_lo = int(round(y0i + float(norm_lo) * h))
        y_hi = int(round(y0i + float(norm_hi) * h))
        y_lo = max(y0i, min(y1i - 1, y_lo))
        y_hi = max(y0i, min(y1i - 1, y_hi))
        return (min(y_lo, y_hi), max(y_lo, y_hi))

    results = {}
    for key, (label, rgb, bgr_draw, f_lbl, a_lbl, q_lbl) in SERIES.items():
        series_name = {"F": f_lbl, "A": a_lbl, "Q": q_lbl}[chart_type]
        # Build row cost from HSV distance
        tgt_hsv = bgr_to_hsv_color((rgb[2], rgb[1], rgb[0]))  # convert from RGB->BGR then to HSV
        row_cost = hsv_row_distance(crop_hsv, tgt_hsv, label)

        # Apply lane windowing to avoid wrong traces.
        n_lo, n_hi = lane_windows[chart_type][series_name]
        wy0, wy1 = norm_window_to_rows(n_lo, n_hi)

        wy0c = max(0, wy0 - y0i)
        wy1c = min(crop.shape[0] - 1, wy1 - y0i)
        if wy1c > wy0c:
            mask = np.ones_like(row_cost) * 10.0
            mask[wy0c:wy1c+1] = 0.0
            row_cost = row_cost + mask
            # Mild center bias inside the valid window; disabled for F where it caused drift.
            bias_weight = 0.0 if (chart_type == "F" or series_name in {"A2", "A4", "Q4"}) else 0.10
            if bias_weight > 0.0:
                c = 0.5 * (wy0c + wy1c)
                span = max(3.0, 0.5 * (wy1c - wy0c))
                ridx = np.arange(row_cost.size, dtype=np.float32)
                row_cost = row_cost + bias_weight * ((ridx - c) / span) ** 2

        # Light median filter to stabilize row cost.
        row_cost = cv2.blur(row_cost.reshape(-1,1), (1,5)).ravel()
        y_rel = int(np.argmin(row_cost))
        y_pix = y0i + y_rel
        y_norm = (y_pix - y0i) / max(1.0, (y1i - y0i))
        lane_span = max(1.0, float(wy1 - wy0))
        lane_norm = (float(y_pix) - float(wy0)) / lane_span
        results[series_name] = {
            "y_px": int(y_pix),
            "y_norm": float(y_norm),
            "lane_norm": float(np.clip(lane_norm, 0.0, 1.0)),
            "draw": bgr_draw,
        }
    return results

def refine_f1_f4_with_path_tracking(img_bgr, roi, x_now, picks):
    """
    Refine F1/F4 by tracking a smooth path across the last few x-columns into x_now.
    This reduces right-edge mis-picks when local color minima jump between nearby lanes.
    """
    x0, y0, x1, y1 = roi
    pad_top, pad_bot = 4, 18
    y0i = min(y1 - 1, y0 + pad_top)
    y1i = max(y0i + 1, y1 - pad_bot)
    x_lo = int(np.clip(x_now - 14, x0 + 1, x1 - 2))
    x_hi = int(np.clip(x_now, x0 + 1, x1 - 2))
    if x_hi <= x_lo:
        return picks, {}

    crop = img_bgr[y0i:y1i, x_lo:x_hi+1, :]
    if crop.size == 0:
        return picks, {}

    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    H = int(crop.shape[0])
    W = int(crop.shape[1])
    target_col = int(np.clip((x_now - 1) - x_lo, 0, W - 1))
    lane_norm = {"F1": PICK_LANE_WINDOWS["F"]["F1"], "F4": PICK_LANE_WINDOWS["F"]["F4"]}
    series_meta = {
        "F1": {"label": "white", "rgb": (240, 240, 240), "smooth": 0.55},
        "F4": {"label": "green", "rgb": (40, 160, 60), "smooth": 0.35},
    }
    dbg = {}

    for name in ("F1", "F4"):
        if name not in picks:
            continue
        meta = series_meta[name]
        n_lo, n_hi = lane_norm[name]
        h = float(y1i - y0i)
        wy0c = int(np.clip(round(n_lo * h), 0, H - 1))
        wy1c = int(np.clip(round(n_hi * h), 0, H - 1))
        if wy1c <= wy0c + 1:
            continue

        tgt_hsv = bgr_to_hsv_color((meta["rgb"][2], meta["rgb"][1], meta["rgb"][0]))
        cost = np.zeros((H, W), dtype=np.float32)
        for c in range(W):
            col_cost = hsv_row_distance(crop_hsv[:, c:c+1, :], tgt_hsv, meta["label"]).astype(np.float32).ravel()
            cost[:, c] = col_cost

        # Keep tracker inside the expected lane.
        outside = np.ones(H, dtype=np.float32) * 8.0
        outside[wy0c:wy1c+1] = 0.0
        cost += outside[:, None]
        cost = cv2.GaussianBlur(cost, (1, 5), 0)

        max_step = 3
        smooth = float(meta["smooth"])
        dp = np.full((W, H), 1e9, dtype=np.float32)
        dp[0, :] = cost[:, 0]
        for c in range(1, W):
            prev = dp[c - 1, :]
            for y in range(H):
                lo = max(0, y - max_step)
                hi = min(H - 1, y + max_step)
                ys = np.arange(lo, hi + 1, dtype=np.int16)
                vals = prev[lo:hi+1] + smooth * np.abs(ys.astype(np.float32) - float(y))
                j = int(np.argmin(vals))
                dp[c, y] = cost[y, c] + vals[j]

        y_best = int(np.argmin(dp[target_col, :]))
        y_pix = int(y0i + y_best)
        y_norm = (y_pix - y0i) / max(1.0, float(y1i - y0i))
        picks[name]["y_px"] = int(y_pix)
        picks[name]["y_norm"] = float(y_norm)
        lane_span = max(1.0, float(wy1c - wy0c))
        lane_norm_val = (float(y_best) - float(wy0c)) / lane_span
        picks[name]["lane_norm"] = float(np.clip(lane_norm_val, 0.0, 1.0))

        dbg[f"{name.lower()}_path_x_range"] = [int(x_lo), int(x_hi)]
        dbg[f"{name.lower()}_path_target_col"] = int(target_col)
        dbg[f"{name.lower()}_path_y_px"] = int(y_pix)

    return picks, dbg

def refine_series_path_tracking(
    img_bgr,
    roi,
    x_now,
    picks,
    chart_type,
    series_name,
    span_px=12,
    smooth=0.45,
    max_step=3,
    edge_margin_px=1,
    min_y_px=None,
    max_y_px=None,
    target_back_px=1,
    left_weight=0.45,
    right_weight=1.0,
    direct_switch_px=4,
    direct_cost_ratio=0.95,
    allow_direct=True,
):
    """
    Track a series across recent x-columns and snap at the target column.
    This is less brittle than single-column local minima when traces jump/spike.
    """
    if series_name not in picks:
        return picks, {}
    style = find_series_style(chart_type, series_name)
    if style is None:
        return picks, {}
    lanes = PICK_LANE_WINDOWS.get(chart_type, {})
    if series_name not in lanes:
        return picks, {}

    x0, y0, x1, y1 = roi
    pad_top, pad_bot = 4, 18
    y0i = min(y1 - 1, y0 + pad_top)
    y1i = max(y0i + 1, y1 - pad_bot)
    x_lo = int(np.clip(x_now - int(span_px), x0 + 1, x1 - 2))
    x_hi = int(np.clip(x_now, x0 + 1, x1 - 2))
    if x_hi <= x_lo:
        return picks, {}

    crop = img_bgr[y0i:y1i, x_lo:x_hi + 1, :]
    if crop.size == 0:
        return picks, {}
    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    H = int(crop.shape[0])
    W = int(crop.shape[1])
    target_col = int(np.clip((x_hi - int(target_back_px)) - x_lo, 0, W - 1))

    n_lo, n_hi = lanes[series_name]
    _y0i2, _y1i2, lane_y0, lane_y1 = lane_window_to_rows(roi, n_lo, n_hi)
    lane0 = max(0, int(lane_y0 - y0i + int(edge_margin_px)))
    lane1 = min(H - 1, int(lane_y1 - y0i - int(edge_margin_px)))
    if min_y_px is not None:
        lane0 = max(lane0, int(min_y_px) - y0i)
    if max_y_px is not None:
        lane1 = min(lane1, int(max_y_px) - y0i)
    if lane1 <= lane0:
        return picks, {}

    tgt_hsv = bgr_to_hsv_color((style["rgb"][2], style["rgb"][1], style["rgb"][0]))
    cost = np.zeros((H, W), dtype=np.float32)
    for c in range(W):
        col_cost = hsv_row_distance(crop_hsv[:, c:c + 1, :], tgt_hsv, style["label"]).astype(np.float32).ravel()
        cost[:, c] = col_cost

    outside = np.ones(H, dtype=np.float32) * 8.0
    outside[lane0:lane1 + 1] = 0.0
    cost += outside[:, None]
    cost = cv2.GaussianBlur(cost, (1, 5), 0)
    if W > 1:
        col_w = np.linspace(float(left_weight), float(right_weight), W, dtype=np.float32)
        cost *= col_w.reshape(1, W)

    dp = np.full((W, H), 1e9, dtype=np.float32)
    dp[0, :] = cost[:, 0]
    for c in range(1, W):
        prev = dp[c - 1, :]
        for yy in range(lane0, lane1 + 1):
            lo = max(lane0, yy - int(max_step))
            hi = min(lane1, yy + int(max_step))
            ys = np.arange(lo, hi + 1, dtype=np.int16)
            vals = prev[lo:hi + 1] + float(smooth) * np.abs(ys.astype(np.float32) - float(yy))
            dp[c, yy] = cost[yy, c] + float(np.min(vals))

    y_rel = int(np.argmin(dp[target_col, lane0:lane1 + 1])) + lane0
    y_direct = int(np.argmin(cost[lane0:lane1 + 1, target_col])) + lane0
    path_col_cost = float(cost[y_rel, target_col])
    direct_col_cost = float(cost[y_direct, target_col])
    use_direct = bool(allow_direct) and (
        abs(y_direct - y_rel) >= int(direct_switch_px)
        and direct_col_cost <= path_col_cost * float(direct_cost_ratio)
    )
    if use_direct:
        y_rel = y_direct
    y_pix = int(y0i + y_rel)
    y_norm = (y_pix - y0i) / max(1.0, float(y1i - y0i))
    lane_norm = (float(y_pix) - float(lane_y0)) / max(1.0, float(lane_y1 - lane_y0))

    picks[series_name]["y_px"] = int(y_pix)
    picks[series_name]["y_norm"] = float(y_norm)
    picks[series_name]["lane_norm"] = float(np.clip(lane_norm, 0.0, 1.0))
    dbg = {
        f"{series_name.lower()}_path2_x_range": [int(x_lo), int(x_hi)],
        f"{series_name.lower()}_path2_target_col": int(target_col),
        f"{series_name.lower()}_path2_y_px": int(y_pix),
        f"{series_name.lower()}_path2_y_direct_px": int(y0i + y_direct),
        f"{series_name.lower()}_path2_direct_used": bool(use_direct),
        f"{series_name.lower()}_path2_direct_allowed": bool(allow_direct),
        f"{series_name.lower()}_path2_left_weight": float(left_weight),
        f"{series_name.lower()}_path2_right_weight": float(right_weight),
    }
    return picks, dbg

def draw_overlay_with_picks(img_bgr, roi, x_now, picks, title, chart_type="F", x_marker=None):
    out = img_bgr.copy()
    x0,y0,x1,y1 = roi
    x_draw = int(x_now if x_marker is None else x_marker)
    x_draw = int(np.clip(x_draw, x0 + 1, x1 - 2))
    # markers + labels
    for series_name, val in picks.items():
        y = int(val["y_px"]); color = val["draw"]
        cv2.circle(out, (x_draw, y), 5, color, -1)
        txt = f"{series_name}"
        cv2.putText(out, txt, (min(x_draw+8, x1-140), max(y-6, y0+14)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
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

    xF, dbgF = compute_x_now(F_img, roiF, last_modified=F_lm_dt, verbose=args.verbose, min_guard_px=4)
    xA, dbgA = compute_x_now(A_img, roiA, last_modified=A_lm_dt, verbose=args.verbose)
    xQ, dbgQ = compute_x_now(Q_img, roiQ, last_modified=Q_lm_dt, verbose=args.verbose)

    x_map, dbg_map = harmonize_x_now_across_charts(
        x_vals={"F": xF, "A": xA, "Q": xQ},
        dbg_vals={"F": dbgF, "A": dbgA, "Q": dbgQ},
        rois={"F": roiF, "A": roiA, "Q": roiQ},
    )
    xF, xA, xQ = x_map["F"], x_map["A"], x_map["Q"]
    dbgF, dbgA, dbgQ = dbg_map["F"], dbg_map["A"], dbg_map["Q"]

    # Read traces slightly left of x_now to avoid right-edge repaint artifacts.
    xF_pick, xF_safe_right = safe_pick_x(xF, roiF, dbgF, back_px=1, safety_px=RIGHT_PICK_SAFETY_PX_F)
    xF_pick_edge = int(np.clip(min(xF, xF_safe_right), roiF[0] + 1, roiF[2] - 2))
    xA_pick, xA_safe_right = safe_pick_x(xA, roiA, dbgA, back_px=4)
    xQ_pick, xQ_safe_right = safe_pick_x(xQ, roiQ, dbgQ, back_px=1)
    dbgF["x_pick"] = xF_pick
    dbgF["x_pick_edge"] = xF_pick_edge
    dbgF["x_pick_safe_right"] = xF_safe_right
    dbgF["x_overlay"] = xF_pick_edge
    dbgA["x_pick"] = xA_pick
    dbgA["x_pick_safe_right"] = xA_safe_right
    dbgA["x_overlay"] = xA_pick
    dbgQ["x_pick"] = xQ_pick
    dbgQ["x_pick_safe_right"] = xQ_safe_right
    dbgQ["x_overlay"] = xQ_pick

    picksF = pick_colored_lines_at_x(F_img, roiF, xF_pick, chart_type="F", band_px=3, freq_max_hz=float(args.freq_max_hz), x_right_limit=xF_safe_right)
    picksF, dbgF_path = refine_f1_f4_with_path_tracking(F_img, roiF, xF_pick_edge, picksF)
    if dbgF_path:
        dbgF.update(dbgF_path)
    picksF, dbgF_f1_path2 = refine_series_path_tracking(
        F_img,
        roiF,
        xF_pick_edge,
        picksF,
        "F",
        "F1",
        span_px=10,
        smooth=0.35,
        max_step=6,
        target_back_px=1,
        left_weight=0.35,
        right_weight=1.0,
        direct_switch_px=4,
        direct_cost_ratio=0.95,
        allow_direct=False,
    )
    if dbgF_f1_path2:
        dbgF.update(dbgF_f1_path2)
    picksF, dbgF_f2_path2 = refine_series_path_tracking(
        F_img,
        roiF,
        xF_pick_edge,
        picksF,
        "F",
        "F2",
        span_px=10,
        smooth=0.28,
        max_step=6,
        target_back_px=1,
        left_weight=0.40,
        right_weight=1.0,
        direct_switch_px=4,
        direct_cost_ratio=0.95,
        allow_direct=False,
    )
    if dbgF_f2_path2:
        dbgF.update(dbgF_f2_path2)
    picksF, dbgF_f4_path2 = refine_series_path_tracking(
        F_img,
        roiF,
        xF_pick_edge,
        picksF,
        "F",
        "F4",
        span_px=10,
        smooth=0.25,
        max_step=7,
        target_back_px=1,
        left_weight=0.40,
        right_weight=1.0,
        direct_switch_px=4,
        direct_cost_ratio=0.95,
        allow_direct=False,
    )
    if dbgF_f4_path2:
        dbgF.update(dbgF_f4_path2)
    picksF, dbgF_f1 = refine_series_local_snap(
        F_img,
        roiF,
        xF_pick_edge,
        picksF,
        "F",
        "F1",
        search_px=8,
        band_px=2,
        edge_margin_px=1,
        search_up_px=4,
        search_down_px=12,
        prefer_lower_weight=0.02,
    )
    if dbgF_f1:
        dbgF.update(dbgF_f1)
    picksA = pick_colored_lines_at_x(A_img, roiA, xA_pick, chart_type="A", band_px=5, freq_max_hz=float(args.freq_max_hz), x_right_limit=xA_safe_right)
    picksQ = pick_colored_lines_at_x(Q_img, roiQ, xQ_pick, chart_type="Q", band_px=5, freq_max_hz=float(args.freq_max_hz), x_right_limit=xQ_safe_right)
    picksA, dbgA_a2_path2 = refine_series_path_tracking(
        A_img,
        roiA,
        xA_pick,
        picksA,
        "A",
        "A2",
        span_px=10,
        smooth=0.45,
        max_step=3,
        target_back_px=1,
        left_weight=0.45,
        right_weight=1.0,
        direct_switch_px=4,
        direct_cost_ratio=0.95,
    )
    if dbgA_a2_path2:
        dbgA.update(dbgA_a2_path2)
    picksQ, dbgQ_q4_path2 = refine_series_path_tracking(
        Q_img,
        roiQ,
        xQ_pick,
        picksQ,
        "Q",
        "Q4",
        span_px=10,
        smooth=0.40,
        max_step=3,
        target_back_px=1,
        left_weight=0.45,
        right_weight=1.0,
        direct_switch_px=4,
        direct_cost_ratio=0.95,
    )
    if dbgQ_q4_path2:
        dbgQ.update(dbgQ_q4_path2)

    picksF, dbgF_f3 = refine_series_local_snap(F_img, roiF, xF_pick_edge, picksF, "F", "F3", search_px=6, band_px=2)
    if dbgF_f3:
        dbgF.update(dbgF_f3)
    picksF, dbgF_f4 = refine_series_local_snap(
        F_img,
        roiF,
        xF_pick_edge,
        picksF,
        "F",
        "F4",
        search_px=8,
        band_px=2,
        edge_margin_px=1,
        search_up_px=6,
        search_down_px=14,
        prefer_lower_weight=0.05,
    )
    if dbgF_f4:
        dbgF.update(dbgF_f4)
    picksA, dbgA_a1 = refine_series_local_snap(A_img, roiA, xA_pick, picksA, "A", "A1", search_px=6, band_px=2)
    if dbgA_a1:
        dbgA.update(dbgA_a1)
    picksA, dbgA_a2 = refine_series_local_snap(
        A_img,
        roiA,
        xA_pick,
        picksA,
        "A",
        "A2",
        search_px=6,
        band_px=2,
        edge_margin_px=1,
        search_up_px=4,
        search_down_px=10,
    )
    if dbgA_a2:
        dbgA.update(dbgA_a2)
    picksA, dbgA_a3 = refine_series_local_snap(
        A_img,
        roiA,
        xA_pick,
        picksA,
        "A",
        "A3",
        search_px=8,
        band_px=2,
        edge_margin_px=1,
        search_up_px=6,
        search_down_px=30,
        prefer_lower_weight=0.04,
    )
    if dbgA_a3:
        dbgA.update(dbgA_a3)
    picksA, dbgA_a4 = refine_series_local_snap(
        A_img,
        roiA,
        xA_pick,
        picksA,
        "A",
        "A4",
        search_px=8,
        band_px=2,
        edge_margin_px=1,
        search_up_px=4,
        search_down_px=36,
        prefer_lower_weight=0.05,
    )
    if dbgA_a4:
        dbgA.update(dbgA_a4)

    # Enforce vertical ordering where neighboring series must remain separated.
    if "F1" in picksF and "F2" in picksF:
        f2_max_y = None
        if "F3" in picksF:
            f2_max_y = int(picksF["F3"]["y_px"]) - 10
        picksF, dbgF_f2_ord = refine_series_local_snap(
            F_img,
            roiF,
            xF_pick_edge,
            picksF,
            "F",
            "F2",
            search_px=8,
            band_px=2,
            search_up_px=14,
            search_down_px=2,
            prefer_lower_weight=0.0,
            min_y_px=int(picksF["F1"]["y_px"]) + 10,
            max_y_px=f2_max_y,
        )
        if dbgF_f2_ord:
            dbgF.update(dbgF_f2_ord)
    if "A1" in picksA and "A2" in picksA:
        a2_min_y = int(picksA["A1"]["y_px"]) + 14
        a2_max_y = None
        if "A3" in picksA:
            a2_max_y = int(picksA["A3"]["y_px"]) - 12
        if a2_max_y is not None and a2_max_y <= (a2_min_y + 4):
            a2_max_y = None
        picksA, dbgA_a2_ord = refine_series_local_snap(
            A_img,
            roiA,
            xA_pick,
            picksA,
            "A",
            "A2",
            search_px=8,
            band_px=2,
            search_up_px=4,
            search_down_px=10,
            min_y_px=a2_min_y,
            max_y_px=a2_max_y,
        )
        if dbgA_a2_ord:
            dbgA.update(dbgA_a2_ord)
    if "A2" in picksA and "A3" in picksA:
        a3_min_y = int(picksA["A2"]["y_px"]) + 12
        a3_max_y = None
        if "A4" in picksA:
            a3_max_y = int(picksA["A4"]["y_px"]) - 12
        if a3_max_y is not None and a3_max_y <= (a3_min_y + 4):
            a3_max_y = None
        picksA, dbgA_a3_ord = refine_series_local_snap(
            A_img,
            roiA,
            xA_pick,
            picksA,
            "A",
            "A3",
            search_px=12,
            band_px=2,
            edge_margin_px=1,
            search_up_px=6,
            search_down_px=32,
            min_y_px=a3_min_y,
            max_y_px=a3_max_y,
        )
        if dbgA_a3_ord:
            dbgA.update(dbgA_a3_ord)
    if "A3" in picksA and "A4" in picksA:
        picksA, dbgA_a4_ord = refine_series_local_snap(
            A_img,
            roiA,
            xA_pick,
            picksA,
            "A",
            "A4",
            search_px=10,
            band_px=2,
            edge_margin_px=1,
            search_up_px=4,
            search_down_px=42,
            prefer_lower_weight=0.06,
            min_y_px=int(picksA["A3"]["y_px"]) + 12,
        )
        if dbgA_a4_ord:
            dbgA.update(dbgA_a4_ord)
    picksQ, dbgQ_q4 = refine_series_local_snap(
        Q_img,
        roiQ,
        xQ_pick,
        picksQ,
        "Q",
        "Q4",
        search_px=9,
        band_px=2,
        edge_margin_px=2,
        search_up_px=4,
        search_down_px=20,
        prefer_lower_weight=0.01,
    )
    if dbgQ_q4:
        dbgQ.update(dbgQ_q4)
    if "Q3" in picksQ and "Q4" in picksQ:
        picksQ, dbgQ_q4_ord = refine_series_local_snap(
            Q_img,
            roiQ,
            xQ_pick,
            picksQ,
            "Q",
            "Q4",
            search_px=10,
            band_px=2,
            edge_margin_px=2,
            search_up_px=4,
            search_down_px=20,
            prefer_lower_weight=0.01,
            min_y_px=int(picksQ["Q3"]["y_px"]) + 8,
        )
        if dbgQ_q4_ord:
            dbgQ.update(dbgQ_q4_ord)

    picksF = attach_lane_norms(picksF, roiF, "F")
    picksA = attach_lane_norms(picksA, roiA, "A")
    picksQ = attach_lane_norms(picksQ, roiQ, "Q")

    valsF = convert_picks_to_values(picksF, "F")
    valsA = convert_picks_to_values(picksA, "A")
    valsQ = convert_picks_to_values(picksQ, "Q")

    dbgF["scale_ranges"] = SERIES_VALUE_RANGES["F"]
    dbgA["scale_ranges"] = SERIES_VALUE_RANGES["A"]
    dbgQ["scale_ranges"] = SERIES_VALUE_RANGES["Q"]

    # overlays
    F_overlay = A_overlay = Q_overlay = None
    if save_overlays:
        F_overlay = os.path.join(args.dir, "tomsk_params_f_overlay.png")
        A_overlay = os.path.join(args.dir, "tomsk_params_a_overlay.png")
        Q_overlay = os.path.join(args.dir, "tomsk_params_q_overlay.png")
        def stamp(img, roi, x_now, title):
            chart = ("F" if "F " in title else ("A" if "A " in title else "Q"))
            use_picks = picksF if chart == "F" else (picksA if chart == "A" else picksQ)
            x_draw = xF_pick_edge if chart == "F" else (xA_pick if chart == "A" else xQ_pick)
            out = draw_overlay_with_picks(img, roi, x_now, use_picks, title, chart_type=chart, x_marker=x_draw)
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
            "scale_ranges": SERIES_VALUE_RANGES,
            "scale_units": {"F_hz": "Hz", "A_value": "idx", "Q_value": "idx"},
            "F_norm": {k: float(v["y_norm"]) for k,v in picksF.items()},
            "F_y_px": {k: int(v["y_px"]) for k,v in picksF.items()},
            "F_lane_norm": {k: float(v.get("lane_norm", v["y_norm"])) for k,v in picksF.items()},
            "F_hz": {k: float(v) for k,v in valsF.items()},
            "A_norm": {k: float(v["y_norm"]) for k,v in picksA.items()},
            "A_y_px": {k: int(v["y_px"]) for k,v in picksA.items()},
            "A_lane_norm": {k: float(v.get("lane_norm", v["y_norm"])) for k,v in picksA.items()},
            "A_value": {k: float(v) for k,v in valsA.items()},
            "Q_norm": {k: float(v["y_norm"]) for k,v in picksQ.items()},
            "Q_y_px": {k: int(v["y_px"]) for k,v in picksQ.items()},
            "Q_lane_norm": {k: float(v.get("lane_norm", v["y_norm"])) for k,v in picksQ.items()},
            "Q_value": {k: float(v) for k,v in valsQ.items()},
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
