#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cumiana Schumann extractor (http://www.vlf.it/cumiana/last-plotted.jpg)
- Robust "now" anchoring (fixed/redrail/frontier; fixed works well at 22 px)
- Yellow trace (2nd SR freq) detector with ridge fallback (F1 band 6–9 Hz)
- (Temporarily) outputs Schumann only; Geophone/ULF/ELF sampling disabled
- Overlay: red 'now' line + blue horizontal guides + small colored dots on traces
"""

import os, sys, json, argparse
from datetime import datetime, timezone
from typing import Optional, Tuple

import numpy as np
import cv2
import requests

CUMIANA_IMG = "http://www.vlf.it/cumiana/last-plotted.jpg"

# Default ROI covering the plotted area (x0,y0,x1,y1)
ROI = (47, 24, 909, 332)

# Cumiana right Y-axis is TOP=20 Hz, BOTTOM=0 Hz (linear)
AXIS_HZ_MIN, AXIS_HZ_MAX = 0.0, 20.0

# "Now" anchoring
DEFAULT_REDRAIL_OFFSET_PX = 8
DEFAULT_FIXED_OFFSET_PX   = 22  # empirically best for Cumiana

# Frontier detection / guards
DEFAULT_GUARD_PX = 16
DEFAULT_EXCLUDE_RIGHT_PX = 0

# Trace row “hints” we then refine locally at x_now
TRACE_HINTS = {
    "yellow":   37,   # yellow (F2) – not used for sampling, only for search bands
    "geophone": 160,  # green
    "ulf10":    190,  # magenta
    "elf100":   140,  # light blue
}

# Horizontal guides to draw (Hz)
BAND_GUIDES = [2,4,6,8,10,12,14,16,18,20]

# dB axis defaults
DB_TOP_DEFAULT = -20.0
DB_BOTTOM_DEFAULT = -120.0


# -------------------------- fetch & headers --------------------------

def fetch_image(url, insecure=False, headers=None):
    kw = dict(stream=True, timeout=30)
    if insecure:
        kw["verify"] = False
    if headers is not None:
        kw["headers"] = headers
    r = requests.get(url, **kw)
    r.raise_for_status()
    lm = r.headers.get("Last-Modified", None)
    arr = np.frombuffer(r.content, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img, lm


def parse_last_modified(h):
    if not h:
        return None
    try:
        # e.g., "Mon, 01 Sep 2025 19:00:10 GMT"
        return datetime.strptime(h, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return None


# -------------------------- geometry helpers --------------------------

def y_to_hz(y_pix, roi):
    """Map image row to Hz. Cumiana axis is 20 Hz at top, 0 Hz at bottom."""
    x0, y0, x1, y1 = roi
    frac = (y_pix - y0) / max(1.0, (y1 - y0))
    hz = AXIS_HZ_MAX - frac * (AXIS_HZ_MAX - AXIS_HZ_MIN)  # inverted
    return float(max(AXIS_HZ_MIN, min(AXIS_HZ_MAX, hz)))


def hz_to_y(hz, roi):
    """Inverse mapping: Hz to image row."""
    x0, y0, x1, y1 = roi
    frac = (AXIS_HZ_MAX - hz) / (AXIS_HZ_MAX - AXIS_HZ_MIN)  # inverted
    return int(round(y0 + frac * (y1 - y0)))


def y_to_db(y_pix, roi, top_db=-20.0, bottom_db=-120.0):
    """
    Map image row to the left Y-axis dB scale.
    Cumiana chart labels show -20 dB at the very top and -120 dB at the bottom.
    We treat the scale as linear between ROI.y0..ROI.y1.
    """
    x0, y0, x1, y1 = roi
    frac = (float(y_pix) - float(y0)) / max(1.0, float(y1 - y0))  # 0 at top, 1 at bottom
    return float(top_db + frac * (bottom_db - top_db))


# -------------------------- "now" line anchoring --------------------------

def detect_right_red_border(img_bgr, roi):
    """Detect Cumiana’s tall red border at far right of ROI; return absolute x or None."""
    x0, y0, x1, y1 = roi
    scan_w = min(40, max(1, x1 - x0))
    band = img_bgr[y0:y1, x1 - scan_w:x1]
    if band.size == 0:
        return None

    b, g, r = cv2.split(band.astype(np.int16))
    red_excess = (r - np.maximum(b, g)).clip(min=0).mean(axis=0).astype(np.float32)
    if red_excess.size == 0:
        return None

    j = int(np.argmax(red_excess))
    peak = float(red_excess[j])
    if peak < 25.0:
        return None

    col = band[:, j, :]
    red_dominant = (col[:, 2] > (np.maximum(col[:, 0], col[:, 1]) + 15)).mean()
    if red_dominant < 0.70:
        return None

    return int((x1 - scan_w) + j)


def detect_frontier(img, roi, guard_px=DEFAULT_GUARD_PX, exclude_right_px=DEFAULT_EXCLUDE_RIGHT_PX):
    """Find last 'painted' column inside ROI by scanning from right with a small run-length guard."""
    x0, y0, x1, y1 = roi
    crop = img[y0:y1, x0:x1]
    if exclude_right_px > 0:
        crop = crop[:, :max(1, crop.shape[1] - exclude_right_px)]

    colsum = crop.mean(axis=(0, 2))
    if colsum.size == 0:
        return x1 - guard_px - 1

    tail = colsum[-min(180, colsum.size):]
    thr = float(np.quantile(tail, 0.10) + 0.08 * (tail.max() - tail.min()))

    run_needed = 3
    idx = crop.shape[1] - 1
    run = 0
    for i in range(colsum.size - 1, -1, -1):
        if colsum[i] > thr:
            run += 1
            if run >= run_needed:
                idx = i
                break
        else:
            run = 0

    x = x0 + idx
    if (x1 - x) <= guard_px:
        x = x1 - guard_px - 1
    return int(x)


# -------------------------- amplitude / pseudo-spectrogram --------------------------

def _stripe_v_mean(img_bgr, x_center, y0, y1, half_w=3):
    """Mean HSV-V over a thin vertical stripe centered at x_center and rows [y0,y1)."""
    h, w = img_bgr.shape[:2]
    xc = int(np.clip(x_center, 0, w - 1))
    xL = int(max(0, xc - int(half_w)))
    xR = int(min(w - 1, xc + int(half_w)))

    y0i = int(np.clip(y0, 0, h - 1))
    y1i = int(np.clip(y1, y0i + 1, h))

    patch = img_bgr[y0i:y1i, xL:xR + 1]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2].astype(np.float32) / 255.0
    return float(np.clip(v.mean(), 0.0, 1.0))


def compute_amplitude_idx(img_bgr, roi, x_sample, *, band_defs=None, stripe_half_w=3):
    """Compute band intensity proxies (0..1) from the Cumiana spectrogram image."""
    x0, y0, x1, y1 = roi
    if band_defs is None:
        # Cumiana shows 0..20 Hz
        band_defs = {
            "sr_total_0_20": (0.0, 20.0),
            "band_7_9": (7.0, 9.0),
            "band_13_15": (13.0, 15.0),
            # Cumiana axis tops at 20 Hz; use a practical high-band proxy
            "band_18_20": (18.0, 20.0),
        }

    out = {}

    # Total band uses full ROI rows
    out["sr_total_0_20"] = _stripe_v_mean(img_bgr, x_sample, y0, y1, half_w=stripe_half_w)

    for name, (hz_lo, hz_hi) in band_defs.items():
        if name == "sr_total_0_20":
            continue
        y_top = hz_to_y(hz_hi, roi)
        y_bot = hz_to_y(hz_lo, roi)
        ya, yb = min(y_top, y_bot), max(y_top, y_bot)
        # Expand slightly to be resilient to rounding
        ya = max(y0, ya - 1)
        yb = min(y1, yb + 1)
        if yb <= ya:
            out[name] = 0.0
        else:
            out[name] = _stripe_v_mean(img_bgr, x_sample, ya, yb, half_w=stripe_half_w)

    return out


def compute_spectrogram_bins(img_bgr, roi, x_sample, *, n_bins=160, stripe_half_w=2):
    """Compute a 1D pseudo-spectrogram column: intensity by frequency bin (0..1).

    We sample HSV-V down the ROI at x_sample and downsample to n_bins bins.
    """
    x0, y0, x1, y1 = roi
    h = max(1, int(y1 - y0))
    n = int(max(16, n_bins))

    # Map bins linearly across the ROI rows
    edges = np.linspace(0, h, n + 1)
    bins = []
    for i in range(n):
        ya = int(y0 + np.floor(edges[i]))
        yb = int(y0 + np.ceil(edges[i + 1]))
        yb = max(ya + 1, yb)
        bins.append(_stripe_v_mean(img_bgr, x_sample, ya, yb, half_w=stripe_half_w))

    return bins


# -------------------------- detection & sampling --------------------------

def local_row_avg(img_bgr, y, x_now, half=3):
    """Average HSV-V (brightness) across a short horizontal slice centered at (x_now, y)."""
    x_center = x_now
    x0 = max(0, x_center - half)
    x1 = min(img_bgr.shape[1] - 1, x_center + half)
    patch = img_bgr[max(0, y - 1):min(img_bgr.shape[0], y + 2), x0:x1 + 1]
    if patch.ndim == 2:
        v = patch.astype(np.float32).mean()
    else:
        v = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.float32).mean()
    return float(v)


def find_trace_row_near(img_bgr, x_now, hint_y, window=10):
    best_y, best_v = hint_y, -1e9
    for dy in range(-window, window + 1):
        y = int(np.clip(hint_y + dy, 0, img_bgr.shape[0] - 2))
        v = local_row_avg(img_bgr, y, x_now, half=3)
        if v > best_v:
            best_v, best_y = v, y
    return best_y


def find_trace_row_near_color(img_bgr, x_now, hint_y, name, window=30, span_px=21):
    """
    Color-guided row finder for Cumiana traces.
    name ∈ {"geophone","ulf10","elf100"}.
    Uses a wider vertical stripe (span_px) to integrate color mask horizontally,
    then selects the best row using a smoothed score. Falls back to brightness-based
    finder if the color evidence is weak.
    """
    h, w = img_bgr.shape[:2]
    x_sample = int(np.clip(x_now, 4, w - 5))

    # Clamp span to odd width and sensible bounds
    span_px = int(max(7, min(61, span_px)))
    if span_px % 2 == 0:
        span_px += 1

    y_top = int(np.clip(hint_y - window, 0, h - 2))
    y_bot = int(np.clip(hint_y + window, 0, h - 2))
    if y_bot <= y_top:
        return find_trace_row_near(img_bgr, x_now, hint_y, window=10)

    half = span_px // 2
    xL = max(0, x_sample - half)
    xR = min(w - 1, x_sample + half)
    stripe = img_bgr[y_top:y_bot, xL:xR+1]
    if stripe.size == 0:
        return find_trace_row_near(img_bgr, x_now, hint_y, window=10)

    hsv = cv2.cvtColor(stripe, cv2.COLOR_BGR2HSV)

    # HSV gates (slightly relaxed from before)
    if name == "geophone":       # green
        lower = (48, 80, 55);   upper = (88, 255, 255)
    elif name == "ulf10":        # magenta/purple
        lower = (140, 110, 70); upper = (180, 255, 255)
    elif name == "elf100":       # cyan/light-blue
        lower = (85, 50, 95);   upper = (110, 255, 255)
    else:
        return find_trace_row_near(img_bgr, x_now, hint_y, window=10)

    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    V = hsv[:, :, 2].astype(np.float32) / 255.0
    S = hsv[:, :, 1].astype(np.float32) / 255.0

    # Integrate horizontally to get a per-row score; reward saturation & brightness
    row_mask_mean = mask.mean(axis=1).astype(np.float32) / 255.0
    row_sv = (S * V).mean(axis=1)
    row_score = 0.85 * row_mask_mean + 0.15 * row_sv
    row_score = cv2.GaussianBlur(row_score.reshape(-1, 1), (1, 9), 0).reshape(-1)

    if row_score.size == 0:
        return find_trace_row_near(img_bgr, x_now, hint_y, window=10)

    idx = int(np.argmax(row_score))

    # Require some evidence: mask coverage and standout versus median
    if (float(row_score[idx]) < (float(np.median(row_score)) + 0.10)) or (mask.sum() < 120):
        return find_trace_row_near(img_bgr, x_now, hint_y, window=10)

    return int(y_top + idx)


def detect_yellow_f2_hz(img_bgr, roi, x_now, *,
                        hue_min=10, hue_max=55,
                        sat_min=60, val_min=80,
                        band_min_hz=11.5, band_max_hz=19.0,
                        return_band=False):
    """
    Detect yellow (2nd SR) around x_now within a tunable band (default ~11.5–19 Hz).
    We sample a bundle of columns slightly left of the red now-line to avoid bleed.
    Returns Hz (or None). If return_band=True, returns tuple (Hz|None, (y0,y1,cx)).
    """
    cx = int(np.clip(x_now - 2, roi[0] + 3, roi[2] - 4))
    xs = [int(np.clip(cx + dx, roi[0] + 2, roi[2] - 3)) for dx in (-3, -2, -1, 0, 1)]

    y_top = hz_to_y(band_max_hz, roi)
    y_bot = hz_to_y(band_min_hz, roi)
    y0, y1 = min(y_top, y_bot), max(y_top, y_bot)
    if y1 - y0 <= 3:
        return (None, (y0, y1, cx)) if return_band else None

    stripes = [img_bgr[y0:y1, x-1:x+2] for x in xs]
    stripes = [s for s in stripes if s.size > 0]
    if not stripes:
        return (None, (y0, y1, cx)) if return_band else None
    stripe = np.concatenate(stripes, axis=1)
    hsv = cv2.cvtColor(stripe, cv2.COLOR_BGR2HSV)
    H, S, V = cv2.split(hsv)

    mask = cv2.inRange(hsv, (int(hue_min), int(sat_min), int(val_min)),
                             (int(hue_max), 255, 255))
    sat01 = (S.astype(np.float32) / 255.0)
    row_score = (mask.astype(np.float32) / 255.0) * sat01
    row_score = cv2.GaussianBlur(row_score.mean(axis=1), (1, 5), 0).reshape(-1)

    if row_score.size == 0:
        return (None, (y0, y1, cx)) if return_band else None

    idx = int(np.argmax(row_score))
    if row_score[idx] < (float(np.median(row_score)) + 0.05):
        return (None, (y0, y1, cx)) if return_band else None

    y = y0 + idx
    hz = y_to_hz(y, roi)
    if not (band_min_hz <= hz <= band_max_hz):
        return (None, (y0, y1, cx)) if return_band else None
    f1 = hz / 2.0
    if not (6.0 <= f1 <= 9.5):
        return (None, (y0, y1, cx)) if return_band else None

    return (float(hz), (y0, y1, cx)) if return_band else float(hz)


def ridge_f1_hz(img_bgr, roi, x_now):
    """Fallback: brightest ridge in 6–9 Hz."""
    y_lo = hz_to_y(9.0, roi)
    y_hi = hz_to_y(6.0, roi)
    y0, y1 = min(y_lo, y_hi), max(y_lo, y_hi)
    x = int(np.clip(x_now, roi[0] + 2, roi[2] - 3))
    w = img_bgr[y0:y1, x - 2:x + 2]
    if w.size == 0:
        return None
    gry = cv2.cvtColor(w, cv2.COLOR_BGR2GRAY)
    col = gry.mean(axis=1)
    if col.size == 0:
        return None
    idx = int(np.argmax(col))
    f1 = y_to_hz(y0 + idx, roi)
    return float(f1) if (6.0 <= f1 <= 9.5) else None


def sample_traces(img_bgr, roi, x_now, x_offset=10, win=28, span=21, db_top=DB_TOP_DEFAULT, db_bottom=DB_BOTTOM_DEFAULT):
    """Return (traces, pos_rows) with dB values mapped from vertical position."""
    x0, y0, x1, y1 = roi

    ge_y = y0 + TRACE_HINTS["geophone"]
    ul_y = y0 + TRACE_HINTS["ulf10"]
    el_y = y0 + TRACE_HINTS["elf100"]

    # sample LEFT of the now-line to avoid red bleed
    x_sample = int(np.clip(x_now - int(x_offset), x0 + 6, x1 - 6))

    ge_y_c = find_trace_row_near_color(img_bgr, x_sample, ge_y, "geophone", window=int(win), span_px=int(span))
    ul_y_c = find_trace_row_near_color(img_bgr, x_sample, ul_y, "ulf10",    window=int(win), span_px=int(span))
    el_y_c = find_trace_row_near_color(img_bgr, x_sample, el_y, "elf100",   window=int(win), span_px=int(span))

    ge_y = ge_y_c if ge_y_c is not None else find_trace_row_near(img_bgr, x_sample, ge_y, window=int(max(10, win//2)))
    ul_y = ul_y_c if ul_y_c is not None else find_trace_row_near(img_bgr, x_sample, ul_y, window=int(max(10, win//2)))
    el_y = el_y_c if el_y_c is not None else find_trace_row_near(img_bgr, x_sample, el_y, window=int(max(10, win//2)))

    ge_y = int(np.clip(ge_y, y0, y1 - 1))
    ul_y = int(np.clip(ul_y, y0, y1 - 1))
    el_y = int(np.clip(el_y, y0, y1 - 1))

    ge_db = y_to_db(ge_y, roi, top_db=db_top, bottom_db=db_bottom)
    ul_db = y_to_db(ul_y, roi, top_db=db_top, bottom_db=db_bottom)
    el_db = y_to_db(el_y, roi, top_db=db_top, bottom_db=db_bottom)

    traces = {
        "yellow_hz": None,
        "geophone_db": ge_db,
        "ulf10_db":    ul_db,
        "elf100_db":   el_db,
        "db_axis": {"top": db_top, "bottom": db_bottom},
        "rows": {"ge": int(ge_y), "ul": int(ul_y), "el": int(el_y)}
    }
    return traces, {"ge": ge_y, "ul": ul_y, "el": el_y}


# -------------------------- overlay --------------------------

def draw_overlay(img_bgr, roi, x_now, traces_pos=None, fvals=None, draw_debug=False, f2_band=None):
    out = img_bgr.copy()
    x0, y0, x1, y1 = roi

    for hz in BAND_GUIDES:
        y = hz_to_y(hz, roi)
        cv2.line(out, (x0, y), (x1, y), (255, 128, 0), 1)

    cv2.line(out, (x_now, y0), (x_now, y1), (0, 0, 255), 2)

    # optional: visualize the F2 probe band (thin cyan bracket)
    if f2_band is not None:
        y0b, y1b, cx = f2_band
        y0b = int(np.clip(y0b, roi[1], roi[3]-1))
        y1b = int(np.clip(y1b, roi[1], roi[3]-1))
        cv2.line(out, (x_now - 10, y0b), (x_now - 3, y0b), (255, 255, 0), 1)
        cv2.line(out, (x_now - 10, y1b), (x_now - 3, y1b), (255, 255, 0), 1)

    if traces_pos:
        # draw the dots exactly where we sampled the traces (left of now-line)
        x_dot = max(x0 + 6, x_now - int(max(0, fvals.get("trace_x_offset", 10))) ) if fvals else max(x0 + 6, x_now - 10)
        if "ge" in traces_pos: cv2.circle(out, (x_dot, traces_pos["ge"]), 3, (0, 255, 0), -1)
        if "ul" in traces_pos: cv2.circle(out, (x_dot, traces_pos["ul"]), 3, (255, 0, 255), -1)
        if "el" in traces_pos: cv2.circle(out, (x_dot, traces_pos["el"]), 3, (255, 255, 0), -1)

    if fvals and fvals.get("F2_det") is not None:
        yy = hz_to_y(fvals["F2_det"], roi)
        x_dot = max(roi[0] + 6, x_now - 6)
        cv2.circle(out, (x_dot, yy), 4, (0, 255, 255), -1)
        cv2.line(out, (x_dot - 6, yy), (x_dot - 1, yy), (0, 255, 255), 2)
        cv2.putText(out, "F2", (x_dot + 6, yy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

    if draw_debug and fvals:
        f1 = fvals.get("F1"); f2det = fvals.get("F2_det")
        if f1 is not None:
            cv2.putText(out, f"F1={f1:.2f} Hz", (roi[0]+6, roi[1]+34), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,200,0), 1, cv2.LINE_AA)
        if f2det is not None:
            cv2.putText(out, f"F2_det={f2det:.2f} Hz", (roi[0]+6, roi[1]+52), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,200,255), 1, cv2.LINE_AA)

    return out


# -------------------------- main --------------------------

def main():
    ap = argparse.ArgumentParser(description="Cumiana Schumann extractor")
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlay")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--verbose", action="store_true")

    ap.add_argument("--guard-px", type=int, default=DEFAULT_GUARD_PX,
                    help="Right-edge guard (px) applied to the now-line")
    ap.add_argument("--exclude-right", type=int, default=DEFAULT_EXCLUDE_RIGHT_PX,
                    help="Ignore this many rightmost columns inside ROI when finding frontier")

    # NEW: tunables for where/how we sample the traces (to avoid red bleed, etc.)
    ap.add_argument("--trace-x-offset", type=int, default=10,
                    help="Pixels to the LEFT of the now-line to sample traces (avoid red bleed)")
    ap.add_argument("--trace-window", type=int, default=28,
                    help="Half-window (px) for vertical color search around each trace hint")

    ap.add_argument("--prefer", choices=["auto","yellow","ridge"], default="auto",
                    help="Preference for F2 yellow vs F1 ridge when both available")
    ap.add_argument("--draw-debug", action="store_true", help="Annotate overlay with debug text")

    ap.add_argument("--anchor", choices=["auto", "frontier", "redrail", "fixed"], default="fixed",
                    help="How to anchor 'now'. 'fixed' works best for Cumiana.")
    ap.add_argument("--redrail-offset-px", type=int, default=DEFAULT_REDRAIL_OFFSET_PX,
                    help="Pixels to step left from the detected red border for the now-line.")
    ap.add_argument("--fixed-offset-px", type=int, default=DEFAULT_FIXED_OFFSET_PX,
                    help="If --anchor fixed, place now at ROI.x1 - this many pixels.")

    # Yellow (F2) detector + visualize scan band
    ap.add_argument("--f2-hue-min", type=int, default=10, help="Yellow hue min (HSV)")
    ap.add_argument("--f2-hue-max", type=int, default=55, help="Yellow hue max (HSV)")
    ap.add_argument("--f2-sat-min", type=int, default=60, help="Yellow saturation min (HSV)")
    ap.add_argument("--f2-val-min", type=int, default=80, help="Yellow value (brightness) min (HSV)")
    ap.add_argument("--f2-band-min", type=float, default=11.5, help="F2 search band min Hz")
    ap.add_argument("--f2-band-max", type=float, default=19.0, help="F2 search band max Hz")
    ap.add_argument("--show-f2-band", action="store_true", help="Draw a small bracket indicating the F2 probe band")

    ap.add_argument("--trace-span-px", type=int, default=21,
                    help="Total horizontal pixels integrated for color traces")
    ap.add_argument("--db-top", type=float, default=DB_TOP_DEFAULT,
                    help="Top of left dB axis (default -20)")
    ap.add_argument("--db-bottom", type=float, default=DB_BOTTOM_DEFAULT,
                    help="Bottom of left dB axis (default -120)")

    args = ap.parse_args()

    # Until we refine Cumiana's non-SR channels, skip Geophone/ULF/ELF sampling
    SKIP_TRACES = True

    img, last_mod = fetch_image(CUMIANA_IMG, insecure=args.insecure)
    if img is None:
        print("Failed to fetch Cumiana image", file=sys.stderr)
        return 3

    # ---- "now" anchoring
    x_now_source = "frontier"
    if args.anchor == "fixed":
        x_now = ROI[2] - int(args.fixed_offset_px)
        x_now_source = "fixed"
    elif args.anchor == "redrail":
        xr = detect_right_red_border(img, ROI)
        if xr is not None:
            x_now = max(ROI[0], min(ROI[2] - 1, xr - int(args.redrail_offset_px)))
            x_now_source = "redrail"
        else:
            x_now = detect_frontier(img, ROI, guard_px=args.guard_px, exclude_right_px=args.exclude_right)
            x_now_source = "frontier(fallback)"
    elif args.anchor == "auto":
        xr = detect_right_red_border(img, ROI)
        if xr is not None:
            x_now = max(ROI[0], min(ROI[2] - 1, xr - int(args.redrail_offset_px)))
            x_now_source = "redrail(auto)"
        else:
            x_now = detect_frontier(img, ROI, guard_px=args.guard_px, exclude_right_px=args.exclude_right)
            x_now_source = "frontier(auto)"
    else:  # frontier
        x_now = detect_frontier(img, ROI, guard_px=args.guard_px, exclude_right_px=args.exclude_right)
        x_now_source = "frontier"

    # ---- traces (temporarily disabled geophone/ULF/ELF)
    if True:  # SKIP_TRACES
        traces, pos = ({"yellow_hz": None}, None)

    # Sample LEFT of the now-line to avoid red bleed
    x_sample = int(np.clip(x_now - int(args.trace_x_offset), ROI[0] + 6, ROI[2] - 6))

    # Compute amplitude proxies and a 160-bin pseudo-spectrogram column
    amplitude_idx = compute_amplitude_idx(img, ROI, x_sample, stripe_half_w=3)
    spectrogram_bins = compute_spectrogram_bins(img, ROI, x_sample, n_bins=160, stripe_half_w=2)

    # Basic quality gating (conservative)
    quality_reasons = []
    quality_score = 1.0
    mean_intensity = float(np.mean(spectrogram_bins)) if spectrogram_bins else 0.0

    if mean_intensity < 0.01:
        quality_score -= 0.60
        quality_reasons.append("low_mean_intensity")

    # If we had to fallback to frontier due to missing redrail in auto/redrail mode, slightly reduce.
    if "fallback" in str(x_now_source):
        quality_score -= 0.10
        quality_reasons.append("anchor_fallback")

    quality_score = float(np.clip(quality_score, 0.0, 1.0))
    usable = bool(quality_score >= 0.35)
    if not usable:
        quality_reasons.append("below_min_quality")

    # Frequency axis metadata for bins (Cumiana is 0..20 Hz, top is max)
    freq_start_hz = float(AXIS_HZ_MIN)
    freq_step_hz = float((AXIS_HZ_MAX - AXIS_HZ_MIN) / max(1, (160 - 1)))

    # ---- frequency detectors
    f2_hz, f2_band = detect_yellow_f2_hz(
        img, ROI, x_now,
        hue_min=args.f2_hue_min, hue_max=args.f2_hue_max,
        sat_min=args.f2_sat_min, val_min=args.f2_val_min,
        band_min_hz=args.f2_band_min, band_max_hz=args.f2_band_max,
        return_band=True
    )
    if f2_hz is not None:
        traces["yellow_hz"] = float(f2_hz)

    f1_hz = ridge_f1_hz(img, ROI, x_now)

    # Decide which source we used (this also controls JSON "strategy"/"note")
    pick_f1 = None
    pick_source = None  # "yellow" or "ridge"

    if args.prefer == "yellow":
        if f2_hz is not None:
            pick_f1, pick_source = (f2_hz / 2.0), "yellow"
        elif f1_hz is not None:
            pick_f1, pick_source = f1_hz, "ridge"
    elif args.prefer == "ridge":
        if f1_hz is not None:
            pick_f1, pick_source = f1_hz, "ridge"
        elif f2_hz is not None:
            pick_f1, pick_source = (f2_hz / 2.0), "yellow"
    else:  # auto
        if f2_hz is not None and (6.0 <= (f2_hz / 2.0) <= 9.5):
            pick_f1, pick_source = (f2_hz / 2.0), "yellow"
        else:
            pick_f1, pick_source = (f1_hz if f1_hz is not None else None), ("ridge" if f1_hz is not None else None)

    fvals = {}
    if pick_f1 is not None:
        fvals["F1"] = round(float(pick_f1), 2)
        for i in range(2, 6):
            fvals[f"F{i}"] = round(float(pick_f1) * i, 2)

    # keep the *detected* yellow for overlay dot, independent of harmonics
    if f2_hz is not None:
        fvals["F2_det"] = round(float(f2_hz), 2)

    # Stash the x-offset for overlay dot placement
    fvals["trace_x_offset"] = int(args.trace_x_offset)

    overlay_img = draw_overlay(
        img, ROI, x_now,
        fvals=fvals, draw_debug=args.draw_debug,
        f2_band=(f2_band if args.show_f2_band else None)
    )
    if args.overlay:
        cv2.imwrite(args.overlay, overlay_img)

    payload = {
        "status": "ok",
        "source": "cumiana",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "last_modified": parse_last_modified(last_mod),
        "fundamental_hz": fvals.get("F1", None),
        "harmonics_hz": {k: v for k, v in fvals.items() if not k.endswith("_det")},
        "amplitude_idx": amplitude_idx,
        "spectrogram_bins": spectrogram_bins,
        "freq_start_hz": freq_start_hz,
        "freq_step_hz": freq_step_hz,
        "quality_score": quality_score,
        "usable": usable,
        "quality_reasons": quality_reasons,
        "confidence": "ok-visual",
        "overlay_path": args.overlay,
        "raw": {
            "spectrogram_url": CUMIANA_IMG,
            "x_now_pixel": int(x_now),
            "x_sample_pixel": int(x_sample),
            "plot_roi": {"x0": ROI[0], "y0": ROI[1], "x1": ROI[2], "y1": ROI[3]},
            "y_axis_hz": {"min": AXIS_HZ_MIN, "max": AXIS_HZ_MAX, "top_is_max": True},
            "strategy": "yellow_F2" if pick_source == "yellow" else "ridge_F1",
            "note": "yellow at now" if pick_source == "yellow" else "ridge brightest in F1 band",
            "cumiana_traces": ({"yellow_hz": float(traces.get("yellow_hz"))} if traces.get("yellow_hz") is not None else {}),
            "debug": {
                "guard_px": int(args.guard_px),
                "exclude_right_px": int(args.exclude_right),
                "anchor": args.anchor,
                "x_now_source": x_now_source,
                "f2_probe": {
                    "hue_min": int(args.f2_hue_min),
                    "hue_max": int(args.f2_hue_max),
                    "sat_min": int(args.f2_sat_min),
                    "val_min": int(args.f2_val_min),
                    "band_min_hz": float(args.f2_band_min),
                    "band_max_hz": float(args.f2_band_max)
                }
            }
        }
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if args.verbose:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)