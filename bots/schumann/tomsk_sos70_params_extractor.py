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
UTC_TO_TSST_HOURS = 7
TICK_MIN_SEP = 8
TICK_MIN_COUNT = 24
MIN_GUARD_PX = 6

# Series colors (RGB for reading; drawing uses BGR)
SERIES = {
    "F1/A1/Q1": ("white",  (240,240,240), (255,255,255)),
    "F2/A2/Q2": ("yellow", (230,210,30),  (0,255,255)),
    "F3/A3/Q3": ("red",    (200,40,40),   (0,0,255)),
    "F4/A4/Q4": ("green",  (40,160,60),   (0,200,100)),
}

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
    x1_eff = max(x0 + 50, x1 - RIGHT_EXCLUDE_PX)
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
    x0,y0,x1,y1 = sanitize_roi(img_bgr, roi)
    x_day0, x_day1, x_day2, day_w = estimate_day_boundaries(img_bgr, (x0,y0,x1,y1))
    pph_day = day_w/24.0
    pph_tick, tick_count, _ = detect_tick_pph(img_bgr, (x0,y0,x1,y1), verbose=verbose)
    if pp_hour_source == "ticks":
        pph, pph_src = (pph_tick, "ticks") if (pph_tick and tick_count>=tick_min_count) else (pph_day, "day_width (forced)")
    elif pp_hour_source == "day":
        pph, pph_src = pph_day, "day_width"
    else:
        pph, pph_src = (pph_tick, "ticks") if (pph_tick and tick_count>=tick_min_count) else (pph_day, "day_width")
    x_frontier = detect_frontier(img_bgr, (x0,y0,x1,y1))
    guard_px = max(MIN_GUARD_PX, int(round(pph * (guard_minutes/60.0))))
    now_tsst = tsst_now(); hour_now = hour_float(now_tsst); x_time = x_for_hour_in_day(x_day2, pph, hour_now)

    measured_bias_minutes = None; bias_minutes_applied = 0.0
    fresh_ok=False
    if last_modified is not None:
        age_min = (datetime.now(timezone.utc) - last_modified).total_seconds()/60.0
        fresh_ok = age_min < 45.0
    left_guard  = x_day2 + 2
    right_guard = min(x1-2, x_frontier - guard_px)
    if fresh_ok:
        lm_tsst = last_modified.astimezone(timezone(timedelta(hours=UTC_TO_TSST_HOURS)))
        lm_hour = hour_float(lm_tsst)
        x_lm = x_for_hour_in_day(x_day2, pph, lm_hour)
        dx_px = x_frontier - x_lm
        measured_bias_minutes = (dx_px / max(pph,1e-6)) * 60.0
        if abs(measured_bias_minutes) <= float(accept_minutes):
            bias_minutes_applied = float(measured_bias_minutes)

    x_ideal = int(round(x_time + (bias_minutes_applied/60.0)*pph))
    x_now = int(np.clip(x_ideal, left_guard, right_guard))

    age_hours = None
    if last_modified is not None:
        age_hours = (datetime.now(timezone.utc) - last_modified).total_seconds()/3600.0
    status = "ok" if (age_hours is None or age_hours <= float(stale_hours)) else "stale_source"

    dbg = {"x_day0":x_day0,"x_day1":x_day1,"x_day2":x_day2,"day_w":day_w,
           "pph":pph,"pph_source":pph_src,"x_frontier":x_frontier,"guard_px":guard_px,
           "x_time":x_time,"x_ideal":x_ideal,"x_now":x_now,"bias_minutes_applied":bias_minutes_applied,
           "measured_bias_minutes":measured_bias_minutes,"status":status}
    return x_now, dbg

def pick_colored_lines_at_x(img_bgr, roi, x_now, band_px=5):
    x0,y0,x1,y1 = roi
    x = int(np.clip(x_now, x0+1, x1-2))
    lo = max(x0, x - band_px); hi = min(x1, x + band_px + 1)
    crop = img_bgr[y0:y1, lo:hi, :]  # H x W x 3
    if crop.size == 0 or (hi - lo) <= 0:
        # fallback: return midline picks to avoid crashes; caller can detect via y_norm ~0.5
        mid_y = (y0 + y1) // 2
        return { key: {"y_px": int(mid_y), "y_norm": 0.5, "draw": bgr_draw} for key, (_, _, bgr_draw) in SERIES.items() }
    H = crop.shape[0]
    results = {}
    for key, (label, rgb, bgr_draw) in SERIES.items():
        tgt = np.array([rgb[2], rgb[1], rgb[0]], dtype=np.float32)  # BGR
        diff = (crop.astype(np.float32) - tgt)**2
        dist = diff.sum(axis=2).mean(axis=1)  # avg across columns
        y_rel = int(np.argmin(dist))
        y_pix = y0 + y_rel
        y_norm = (y_pix - y0) / max(1.0, (y1 - y0))
        results[key] = {"y_px": int(y_pix), "y_norm": float(y_norm), "draw": tuple(bgr_draw)}
    return results

def draw_overlay_with_picks(img_bgr, roi, x_now, picks, title, freq_max_hz=None, show_units=False):
    out = img_bgr.copy()
    x0,y0,x1,y1 = roi
    # vertical x_now
    cv2.line(out, (x_now, y0), (x_now, y1), (0,0,255), 2)
    # markers + labels
    for key, val in picks.items():
        y = int(val["y_px"]); color = val["draw"]
        cv2.circle(out, (x_now, y), 5, color, -1)
        if show_units and freq_max_hz is not None and key.startswith("F"):
            hz = y_to_unit(y, roi, 0.0, float(freq_max_hz))
            txt = f"{key.split('/')[0]} {hz:.2f} Hz"
        else:
            txt = f"{key.split('/')[0]} y={y}"
        # offset label to avoid overlap
        cv2.putText(out, txt, (min(x_now+8, x1-200), max(y-6, y0+14)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
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

    picksF = pick_colored_lines_at_x(F_img, roiF, xF)
    picksA = pick_colored_lines_at_x(A_img, roiA, xA)
    picksQ = pick_colored_lines_at_x(Q_img, roiQ, xQ)

    # convert F y to Hz
    freq_max = float(args.freq_max_hz)
    F_vals = {k: float(y_to_unit(v["y_px"], roiF, 0.0, freq_max)) for k,v in picksF.items()}

    # A/Q keep normalized (0..1) for now
    A_vals = {k: float(v["y_norm"]) for k,v in picksA.items()}
    Q_vals = {k: float(v["y_norm"]) for k,v in picksQ.items()}

    # overlays
    F_overlay = A_overlay = Q_overlay = None
    if save_overlays:
        F_overlay = os.path.join(args.dir, "tomsk_params_f_overlay.png")
        A_overlay = os.path.join(args.dir, "tomsk_params_a_overlay.png")
        Q_overlay = os.path.join(args.dir, "tomsk_params_q_overlay.png")
        cv2.imwrite(F_overlay, draw_overlay_with_picks(F_img, roiF, xF, picksF, "F params @ x_now", freq_max_hz=freq_max, show_units=True))
        cv2.imwrite(A_overlay, draw_overlay_with_picks(A_img, roiA, xA, picksA, "A params @ x_now"))
        cv2.imwrite(Q_overlay, draw_overlay_with_picks(Q_img, roiQ, xQ, picksQ, "Q params @ x_now"))

    out = {
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "tomsk_sos70_param_charts",
        "freq_max_hz": freq_max,
        "values": { "F_hz": F_vals, "A_norm": A_vals, "Q_norm": Q_vals },
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