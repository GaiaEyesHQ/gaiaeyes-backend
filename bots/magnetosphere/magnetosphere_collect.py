# bots/magnetosphere/magnetosphere_collect.py
import os, time, json, math, datetime as dt
import requests
import numpy as np
from supabase import create_client, Client
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
import matplotlib
matplotlib.use("Agg")  # headless render for CI
import matplotlib.pyplot as plt
import hashlib

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
WP_BASE_URL = os.environ.get("WP_BASE_URL")           # already in your env
WP_USERNAME = os.environ.get("WP_USERNAME")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
EARTHSCOPE_WEBHOOK_URL = os.environ.get("EARTHSCOPE_WEBHOOK_URL")  # optional JSON webhook for app/site alerts
SOCIAL_WEBHOOK_URL = os.environ.get("SOCIAL_WEBHOOK_URL")          # optional JSON webhook to your social poster
GEOSPACE_FRAME_URL = os.environ.get("GEOSPACE_FRAME_URL")          # optional direct image URL for dayside cut
SYMH_URL = os.environ.get("SYMH_URL")                              # optional endpoint returning latest SYM-H value
# Support writing JSON for the website repo
MEDIA_OUT_DIR = os.environ.get("MEDIA_OUT_DIR")  # e.g., /home/runner/work/.../media/data

def dyn_pressure_npa(n_cm3, v_kms):
    if n_cm3 is None or v_kms is None: return None
    return 1.6726e-6 * n_cm3 * (v_kms**2)


# === Helper functions and webhooks ===
def supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def sb_select_one(table: str, order: str = "ts", desc: bool = True, offset: int = 0) -> Optional[Dict[str, Any]]:
    sb = supabase_client()
    schema_name = None
    tbl = table
    if "." in table:
        schema_name, tbl = table.split(".", 1)
    builder = sb.schema(schema_name).table(tbl) if schema_name else sb.table(tbl)
    q = builder.select("*").order(order, desc=desc).limit(1)
    if offset:
        # use range to offset into the result set
        q = q.range(offset, offset)
    data = q.execute().data
    if data:
        return data[0]
    return None

def fetch_symh_proper() -> Optional[int]:
    """
    Try to fetch a real SYM-H value if SYMH_URL is provided.
    Expect the endpoint to return either JSON with a 'symh' field,
    or plain text with the numeric value. Returns int nT or None.
    """
    if not SYMH_URL:
        return None
    try:
        r = requests.get(SYMH_URL, timeout=10)
        r.raise_for_status()
        try:
            jj = r.json()
            if isinstance(jj, dict) and "symh" in jj:
                return int(round(float(jj["symh"])))
            if isinstance(jj, list) and jj and isinstance(jj[-1], dict) and "symh" in jj[-1]:
                return int(round(float(jj[-1]["symh"])))
        except Exception:
            txt = r.text.strip()
            for token in reversed(txt.replace(",", " ").split()):
                try:
                    return int(round(float(token)))
                except:
                    continue
    except Exception:
        return None
    return None

def fetch_kp_latest_from_supabase() -> Optional[float]:
    """
    Prefer reading Kp from a `marts.space_weather_latest` view (exposed via PostgREST).
    Falls back to ext via raw REST if available. Returns float or None.
    """
    # Try marts view first
    try:
        sb = supabase_client()
        resp = sb.schema("marts").table("space_weather_latest").select("kp,kp_index").order("ts", desc=True).limit(1).execute()
        if resp.data:
            row = resp.data[0]
            if row.get("kp") is not None:
                return float(row["kp"])
            if row.get("kp_index") is not None:
                return float(row["kp_index"])
    except Exception:
        pass
    # Fallback: direct REST to ext.space_weather (service role often allowed)
    try:
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/ext.space_weather?select=kp,kp_index,ts&order=ts.desc&limit=1"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        r = requests.get(url, headers=headers, timeout=10)
        if r.ok:
            rows = r.json()
            if rows:
                row = rows[0]
                if row.get("kp") is not None:
                    return float(row["kp"])
                if row.get("kp_index") is not None:
                    return float(row["kp_index"])
    except Exception:
        pass
    return None

def plasmapause_L_carpenter_anderson(kp: Optional[float]) -> Optional[float]:
    """
    Carpenter & Anderson (1992) empirical plasmapause proxy:
    Lpp ≈ 5.6 - 0.46*Kp_max (simplified). Uses current/recent Kp as heuristic.
    Returns L in Earth radii.
    """
    if kp is None:
        return None
    return max(2.0, 5.6 - 0.46*kp)

def post_json_webhook(url: Optional[str], payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not url:
        return None
    try:
        r = requests.post(url, json=payload, timeout=15)
        try:
            return r.json()
        except Exception:
            return {"status_code": r.status_code, "text": r.text[:200]}
    except Exception as e:
        return {"error": str(e)}

def set_wp_banner(title: str, content_html: str, slug: str = "storm-mode-banner") -> Optional[Dict[str, Any]]:
    """
    Idempotent: tries to update if a page/post with ?slug= exists; otherwise creates.
    """
    if not (WP_BASE_URL and WP_USERNAME and WP_APP_PASSWORD):
        return None
    base = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/"
    for kind in ("pages", "posts"):
        try:
            q = requests.get(base + f"{kind}?slug={slug}", auth=(WP_USERNAME, WP_APP_PASSWORD), timeout=15)
            j = q.json()
            if isinstance(j, list) and j:
                pid = j[0]["id"]
                return requests.post(
                    base + f"{kind}/{pid}",
                    auth=(WP_USERNAME, WP_APP_PASSWORD),
                    json={"title": title, "content": content_html, "status": "publish"},
                    timeout=15
                ).json()
        except Exception:
            pass
    try:
        return requests.post(
            base + "pages",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json={"title": title, "slug": slug, "content": content_html, "status": "publish"},
            timeout=15
        ).json()
    except Exception as e:
        return {"error": f"banner create failed: {e}"}

def wp_alert_post(title: str, content_html: str, unique_tag: str) -> Optional[Dict[str, Any]]:
    """
    Create a short alert post. Unique tag (e.g., 'magnetosphere-r0') helps later filtering.
    """
    if not (WP_BASE_URL and WP_USERNAME and WP_APP_PASSWORD):
        return None
    url = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/posts"
    try:
        return requests.post(
            url,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json={"title": title, "content": content_html, "status": "publish", "tags": [unique_tag]},
            timeout=20
        ).json()
    except Exception as e:
        return {"error": f"WP alert failed: {e}"}

def fetch_last24_for_chart() -> List[Dict[str, Any]]:
    """
    Read last 24h series for r0_re and kp_latest from marts.magnetosphere_last_24h.
    Requires the view:
      create or replace view marts.magnetosphere_last_24h as
      select ts, r0_re, kp_latest from ext.magnetosphere_pulse
      where ts > now() - interval '24 hours' order by ts asc;
    """
    try:
        sb = supabase_client()
        resp = sb.schema("marts").table("magnetosphere_last_24h") \
            .select("ts,r0_re,kp_latest").order("ts", desc=False).execute()
        return resp.data or []
    except Exception:
        return []

def color_level(level: str) -> str:
    # Suggested hex colors; frontend can ignore/override
    return {
        "success": "#2e7d32",  # green
        "info":    "#0277bd",  # blue
        "warning": "#ef6c00",  # amber
        "danger":  "#c62828",  # red
        "muted":   "#546e7a"   # gray
    }.get(level, "#546e7a")

def badge(label: str, value: str, level: str) -> Dict[str, Any]:
    return {"label": label, "value": value, "level": level, "color": color_level(level)}

def badge_from_r0(r0: Optional[float]) -> Dict[str, Any]:
    if r0 is None:
        return badge("r₀", "—", "muted")
    if r0 < 6.6:
        return badge("r₀", f"{r0:.1f} Rᴇ", "danger")
    if r0 < 8.0:
        return badge("r₀", f"{r0:.1f} Rᴇ", "warning")
    return badge("r₀", f"{r0:.1f} Rᴇ", "success")

def badge_from_geo(geo_risk: str) -> Dict[str, Any]:
    level = {"low":"success", "watch":"warning", "elevated":"danger"}.get(geo_risk, "muted")
    return badge("GEO", geo_risk, level)

def badge_from_storm(kpi_bucket: str) -> Dict[str, Any]:
    level = {
        "quiet":"success",
        "active":"warning",
        "storm":"danger",
        "strong_storm":"danger"
    }.get(kpi_bucket, "muted")
    return badge("Storm", kpi_bucket.replace("_", " "), level)

def badge_from_grid(dbdt_tag: str) -> Dict[str, Any]:
    level = {"low":"success", "moderate":"warning", "high":"danger"}.get(dbdt_tag, "muted")
    return badge("Grid", dbdt_tag, level)

def build_explainer(r0, symh, dbdt_tag, kp):
    # State bucket from r0 and GEO risk
    if r0 is None:
        state = "Unknown"
    elif r0 < 6.6:
        state = "Compressed (GEO-cross risk)"
    elif r0 < 8.0:
        state = "Moderately compressed"
    else:
        state = "Expanded / typical"

    if symh is None:
        storm = "unknown"
    elif symh < -100:
        storm = "strong storm"
    elif symh < -50:
        storm = "storm"
    elif symh < -20:
        storm = "active"
    else:
        storm = "quiet"

    impacts = []
    if r0 is not None and r0 < 8.0:
        impacts.append("Dayside field compressed; aurora potential up at high latitudes.")
    if symh is not None and symh < -50:
        impacts.append("Geomagnetic storming may disturb GPS/HF radio.")
    if dbdt_tag == "high":
        impacts.append("Grid-current stress elevated; sensitive folks may feel symptoms.")
    if not impacts:
        impacts.append("No major impacts expected.")

    tips = []
    if storm in ("storm", "strong storm"):
        tips += ["Expect occasional GPS/comm glitches.", "Prioritize sleep hygiene; reduce late blue-light."]
    if dbdt_tag == "high":
        tips += ["Delay firmware updates on critical gear.", "Ground & hydrate; keep routines simple."]
    if not tips:
        tips = ["Steady day; normal routines are fine."]

    return {
        "state": f"{state} • Storminess: {storm} • Grid stress: {dbdt_tag}",
        "impacts": impacts,
        "tips": tips
    }

def write_sparkline_png(rows: List[Dict[str, Any]], out_path: str) -> bool:
    """
    Sparkline over last 24h with:
      • Absolute r0 view when span ≥ 0.15 Rᴇ (auto y-lims around min/max, clamped 6–10)
      • Anomaly view when span < 0.15 Rᴇ (Δr0 with amplification if tiny)
      • GEO baseline (light gray), UTC/date ticks, watermark
      • Kp drawn on a RIGHT axis (0–9) so it’s legible and not mixed into r0 scale
    """
    try:
        if not rows:
            return False

        xs  = list(range(len(rows)))
        r0s = [ (row.get("r0_re") if row.get("r0_re") is not None else float("nan")) for row in rows ]
        kps = [ (row.get("kp_latest") if row.get("kp_latest") is not None else float("nan")) for row in rows ]

        # timestamps
        t_objs = []
        end_stamp = None
        for row in rows:
            t = row.get("ts")
            try:
                t_parsed = dt.datetime.fromisoformat(str(t).replace("Z",""))
                t_objs.append(t_parsed); end_stamp = t_parsed
            except Exception:
                t_objs.append(None)

        finite_r0 = [v for v in r0s if v == v]
        if not finite_r0:
            return False
        r0_lo, r0_hi = min(finite_r0), max(finite_r0)
        span   = r0_hi - r0_lo
        mean   = float(np.nanmean(finite_r0))

        plt.figure(figsize=(6.8, 2.0))
        ax = plt.gca()

        legend_lines, legend_labels = [], []
        mode_label = "absolute"

        use_absolute = (span >= 0.15)
        if not use_absolute:
            dr0 = [ (v - mean) if v == v else float("nan") for v in r0s ]
            all_zero = all((abs(v) < 1e-12) for v in dr0 if v == v)
            if all_zero:
                use_absolute = True
                span = 0.0  # force tight window

        if use_absolute:
            # --- Absolute r0 view ---
            # Auto window padded around min/max, clamped into 6–10
            pad = max(0.03, span*0.25)
            ymin = max(6.0, min(10.0, r0_lo - pad))
            ymax = min(10.0, max(6.0, r0_hi + pad))
            if span < 0.01:
                # Truly constant → tight window around mean + highlight band
                ymin, ymax = mean - 0.15, mean + 0.15
                mode_label = "absolute_tight"
                ax.axhspan(mean - 0.05, mean + 0.05, alpha=0.08, zorder=0)
            else:
                mode_label = "absolute"

            # Context shading + GEO baseline
            ax.axhspan(8.0, 10.0, alpha=0.08)
            ax.axhspan(6.6, 8.0, alpha=0.12)
            ax.axhline(6.6, color="#9e9e9e", linestyle="--", linewidth=0.8, zorder=1)

            ln_r0, = ax.plot(xs, r0s, marker="o", markersize=2.5, linewidth=1.7, zorder=4)
            legend_lines.append(ln_r0); legend_labels.append("r₀ (Rᴇ)")
            ax.set_ylim(ymin, ymax)
            ax.set_ylabel("r₀ (Rᴇ)", fontsize=7)

            # Kp on the right axis (0–9)
            if any(k == k for k in kps):
                ax2 = ax.twinx()
                ln_kp, = ax2.plot(xs, kps, linewidth=1.0, zorder=3)
                legend_lines.append(ln_kp); legend_labels.append("Kp")
                ax2.set_ylim(0, 9)
                ax2.set_ylabel("Kp", fontsize=7)
                ax2.tick_params(axis="y", labelsize=6)
                # Lighten right axis spines/ticks
                for sp in ("right",):
                    ax2.spines[sp].set_visible(False)
        else:
            # --- Anomaly Δr0 view ---
            dr0 = [ (v - mean) if v == v else float("nan") for v in r0s ]
            std = float(np.nanstd(dr0)) if len(dr0) else 0.0
            amp = 1.0
            if std < 0.005:
                amp = min(20.0, 0.06 / (std + 1e-6))
            dr0a = [ (d*amp if d == d else float("nan")) for d in dr0 ]
            ax.axhspan(-0.25, 0.25, alpha=0.10, zorder=1)
            ax.axhline(0.0, color="#9e9e9e", linestyle="--", linewidth=0.8, zorder=1)
            ln_r0, = ax.plot(xs, dr0a, marker="o", markersize=2.5, linewidth=1.7, zorder=4)
            legend_lines.append(ln_r0); legend_labels.append("Δr₀ (Rᴇ from mean)" + (f" ×{int(round(amp))}" if amp > 1.01 else ""))
            mode_label = "anomaly"
            # y from ±3σ (post-amp) min span
            std_a = float(np.nanstd(dr0a)) if len(dr0a) else 0.0
            halfspan = max(3.0*std_a, 0.06)
            ax.set_ylim(-halfspan, halfspan)
            ax.set_ylabel("Δr₀ (Rᴇ)", fontsize=7)

            # Kp on right axis (0–9) for correlation
            if any(k == k for k in kps):
                ax2 = ax.twinx()
                ln_kp, = ax2.plot(xs, kps, linewidth=1.0, zorder=3)
                legend_lines.append(ln_kp); legend_labels.append("Kp")
                ax2.set_ylim(0, 9)
                ax2.set_ylabel("Kp", fontsize=7)
                ax2.tick_params(axis="y", labelsize=6)
                for sp in ("right",):
                    ax2.spines[sp].set_visible(False)

        # Minimal chrome + UTC ticks
        for sp in ("top", "right", "left", "bottom"):
            ax.spines[sp].set_visible(False)

        if any(t is not None for t in t_objs) and len(xs) >= 2:
            idxs = [0, max(1, len(xs)//4), len(xs)//2, min(len(xs)-2, 3*len(xs)//4), len(xs)-1]
            labels = []
            for j, i in enumerate(idxs):
                t = t_objs[i]
                if t is None: labels.append("")
                else:
                    labels.append(t.strftime("%H:%M\n%d %b UTC") if j == 0 else t.strftime("%H:%M"))
            ax.set_xticks(idxs)
            ax.set_xticklabels(labels, fontsize=7, linespacing=0.9)
        else:
            ax.get_xaxis().set_visible(False)

        ax.tick_params(axis="y", labelsize=6)

        if legend_lines:
            ax.legend(legend_lines, legend_labels, loc="upper left", fontsize=7, frameon=False)

        # Watermark for cache-busting / provenance
        try:
            ax.text(0.01, 0.98, "UTC", transform=ax.transAxes, ha="left", va="top", fontsize=6, alpha=0.6)
            if end_stamp:
                ax.text(0.99, 0.02, end_stamp.strftime("%Y-%m-%d %H:%M UTC"), transform=ax.transAxes,
                        ha="right", va="bottom", fontsize=6, alpha=0.55)
        except Exception:
            pass

        # Debug
        try:
            yl = ax.get_ylim()
            print(f"[sparkline] saving -> {out_path} | mode={mode_label} rows={len(rows)} ylim=({yl[0]:.3f},{yl[1]:.3f})")
        except Exception:
            pass

        plt.tight_layout()
        plt.savefig(out_path, dpi=170, bbox_inches="tight")
        plt.close()
        return True
    except Exception:
        return False


def analyze_chart_mode(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive sparkline chart mode and amplification from the latest rows."""
    out = {"mode": "absolute", "amp": 1.0}
    if not rows:
        return out
    r0s: List[float] = []
    for row in rows:
        v = row.get("r0_re")
        try:
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                r0s.append(float(v))
        except Exception:
            continue
    if not r0s:
        return out
    lo, hi = min(r0s), max(r0s)
    span = hi - lo
    if span >= 0.15:
        out["mode"] = "absolute"
        out["amp"] = 1.0
        return out
    mean = float(np.nanmean(r0s))
    dr0 = [v - mean for v in r0s]
    if all(abs(v) < 1e-12 for v in dr0):
        out["mode"] = "absolute_tight"
        out["amp"] = 1.0
        return out
    std = float(np.nanstd(dr0)) if len(dr0) else 0.0
    amp = 1.0
    if std < 0.005:
        amp = min(20.0, 0.05 / (std + 1e-6))
    out["mode"] = "anomaly"
    out["amp"] = float(amp)
    return out

def r0_shue98(pdyn_npa, bz_nt):
    if pdyn_npa is None or bz_nt is None: return None
    term = 10.22 + 1.29 * math.tanh(0.184 * (bz_nt + 8.14))
    return term * (pdyn_npa ** (-1/6.6))

def bucket_geo_risk(r0):
    if r0 is None: return "unknown"
    if r0 < 6.6: return "elevated"
    if r0 < 8.0: return "watch"
    return "low"

def bucket_kpi(symh_est):
    if symh_est is None: return "unknown"
    if symh_est >= -20: return "quiet"
    if symh_est >= -50: return "active"
    if symh_est >= -100: return "storm"
    return "strong_storm"

def coachy_caption(r0, geo_risk, kpi, dbdt_tag):
    bits = []
    if r0 is not None:
        bits.append(f"r₀≈{r0:.1f} Rᴇ ({'compressed' if r0<8 else 'expanded'})")
    bits.append(f"GEO risk: {geo_risk}")
    bits.append(f"Storminess: {kpi}")
    bits.append(f"GIC feel: {dbdt_tag}")
    lead = "Magnetosphere status"
    return lead + " — " + " • ".join(bits)

def dbdt_tag_from_proxy(val):
    if val is None: return "unknown"
    if val < 0.5: return "low"
    if val < 1.5: return "moderate"
    return "high"

def fetch_solarwind_now():
    """
    Replace these with your preferred L1 mirrors.
    Expect most-recent point with keys: 'density', 'speed', 'bz', 'timestamp'
    """
    # Example placeholder (you’ll swap in your real endpoint)
    # resp = requests.get("https://<your-proxy>/solarwind/latest.json", timeout=10).json()
    # Mock shape for dev:
    return {
        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "density": 7.5,     # cm^-3
        "speed": 480.0,     # km/s
        "bz": -6.2          # nT
    }

def fetch_symh_est():
    """
    Prefer real SYM-H if available via SYMH_URL; otherwise fall back to heuristic estimate.
    """
    real = fetch_symh_proper()
    if real is not None:
        return int(real)
    sw = fetch_solarwind_now()
    pdyn = dyn_pressure_npa(sw["density"], sw["speed"])
    bz = sw["bz"]
    est = -int(max(0, (pdyn - 1.0)*6 + max(0, -bz)*5))
    return max(-200, min(20, est))

def compute_dbdt_proxy(history):
    """
    history: list of dicts with bz, pdyn, ts (last ~60–120 min).
    Proxy = normalized(Pdyn) * |dBz/dt| (nT/min).
    """
    if len(history) < 3: return None
    times = []
    bzs = []
    pdyns = []
    for p in history:
        try:
            t = dt.datetime.fromisoformat(p["timestamp"].replace("Z",""))
        except:
            continue
        times.append(t)
        bzs.append(p["bz"])
        pdyns.append(dyn_pressure_npa(p["density"], p["speed"]))
    if len(times) < 3: return None
    # simple slope over last ~30 min
    tmins = np.array([(t - times[0]).total_seconds()/60 for t in times])
    bzs = np.array(bzs, dtype=float)
    pdyns = np.array(pdyns, dtype=float)
    # finite differences
    dbz = np.gradient(bzs, tmins, edge_order=1)
    dbz_abs = np.nanmean(np.abs(dbz[-5:]))  # nT/min over the most recent samples
    pd_norm = np.nanmean(pdyns[-5:]) or 0.0
    proxy = (pd_norm/2.0) * (dbz_abs/1.0)
    return float(max(0.0, proxy))

# bots/magnetosphere/magnetosphere_collect.py (upsert_supabase using RPC)
def upsert_supabase(rec):
    """
    Insert/update ext.magnetosphere_pulse via a PUBLIC RPC, because PostgREST
    is configured to expose only {public, storage, content, marts}.
    """
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        # Preferred: RPC through supabase-py
        sb.rpc("upsert_magnetosphere_pulse", {"rec": rec}).execute()
        return
    except Exception:
        # Fallback: direct REST RPC
        url = SUPABASE_URL.rstrip("/") + "/rest/v1/rpc/upsert_magnetosphere_pulse"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "tx=commit"
        }
        r = requests.post(url, headers=headers, json={"rec": rec}, timeout=15)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"RPC upsert failed {r.status_code}: {r.text[:200]}")

def latest_n_history(n_points=8, step_min=10):
    # Replace with your real rolling fetch; here we synthesize a short history.
    base = fetch_solarwind_now()
    hist = []
    now = dt.datetime.fromisoformat(base["timestamp"].replace("Z",""))
    for i in range(n_points):
        t = now - dt.timedelta(minutes=step_min*(n_points-1-i))
        jitter = np.random.randn()*0.3
        hist.append({
            "timestamp": t.isoformat()+"Z",
            "density": max(2.0, base["density"] + np.random.randn()*0.5),
            "speed": base["speed"] + np.random.randn()*5,
            "bz": base["bz"] + jitter
        })
    return hist

def post_to_wp(title, content_html, status="publish"):
    if not (WP_BASE_URL and WP_USERNAME and WP_APP_PASSWORD):
        return None
    url = WP_BASE_URL.rstrip("/") + "/wp-json/wp/v2/posts"
    resp = requests.post(
        url,
        auth=(WP_USERNAME, WP_APP_PASSWORD),
        json={"title": title, "content": content_html, "status": status, "categories": [], "tags": []},
        timeout=20
    )
    try:
        return resp.json()
    except:
        return {"error": f"WP post failed: {resp.status_code}"}

def main():
    # 1) Pull current & short history
    base_sw = fetch_solarwind_now()
    hist = latest_n_history()
    # Use the latest jittered history point as "now" when available so r0 varies over time.
    if hist:
        sw_now = hist[-1]
    else:
        sw_now = base_sw
    # 2) Compute KPIs
    pdyn = dyn_pressure_npa(sw_now["density"], sw_now["speed"])
    r0 = r0_shue98(pdyn, sw_now["bz"])
    symh = fetch_symh_est()
    dbdt_proxy = compute_dbdt_proxy(hist)
    dbdt_tag = dbdt_tag_from_proxy(dbdt_proxy)

    # Optional plasmapause proxy and Kp read
    kp_latest = fetch_kp_latest_from_supabase()
    lpp = plasmapause_L_carpenter_anderson(kp_latest)
    # Human-friendly explainer
    explainer = build_explainer(r0, symh, dbdt_tag, kp_latest)

    # Prepare last-24h rows for sparkline + chart metadata
    rows24 = fetch_last24_for_chart()
    chart_meta = analyze_chart_mode(rows24)

    # Build 24h r0 series for front-end charting
    series_r0 = []
    for row in rows24:
        t = row.get("ts")
        v = row.get("r0_re")
        if t is None or v is None:
            continue
        try:
            # Normalize timestamp to ISO string if not already
            t_str = str(t)
            series_r0.append({"t": t_str, "v": float(v)})
        except Exception:
            continue

    # Read previous from marts view (create view: marts.magnetosphere_history)
    prev = sb_select_one("marts.magnetosphere_history", order="ts", desc=True, offset=1)
    prev_r0 = prev.get("r0_re") if prev else None
    prev_symh = prev.get("symh_est") if prev else None
    prev_dbdt = prev.get("dbdt_proxy") if prev else None
    prev_dbdt_tag = dbdt_tag_from_proxy(prev_dbdt) if prev_dbdt is not None else None

    # r0 trend
    r0_hist = []
    for p in hist:
        p_pdyn = dyn_pressure_npa(p["density"], p["speed"])
        r0_hist.append(r0_shue98(p_pdyn, p["bz"]))
    trend = "flat"
    if len(r0_hist) >= 2 and r0_hist[-1] is not None and r0_hist[-3] is not None:
        if r0_hist[-1] < r0_hist[-3] - 0.2: trend = "falling"
        elif r0_hist[-1] > r0_hist[-3] + 0.2: trend = "rising"

    geo_risk = bucket_geo_risk(r0)
    kpi_bucket = bucket_kpi(symh)

    # Badges for front-end (color suggestions included)
    badges = {
        "r0": badge_from_r0(r0),
        "geo": badge_from_geo(geo_risk),
        "storm": badge_from_storm(kpi_bucket),
        "grid": badge_from_grid(dbdt_tag)
    }

    ts = sw_now["timestamp"]
    rec = {
        "ts": ts,
        "n_cm3": sw_now["density"],
        "v_kms": sw_now["speed"],
        "bz_nt": sw_now["bz"],
        "pdyn_npa": pdyn,
        "r0_re": r0,
        "symh_est": symh,
        "dbdt_proxy": dbdt_proxy,
        "trend_r0": trend,
        "geo_risk": geo_risk,
        "kpi_bucket": kpi_bucket,
        "lpp_re": lpp,
        "kp_latest": kp_latest
    }
    upsert_supabase(rec)

    # === Event-driven rules (edge-triggered) ===
    alerts_fired = []

    def should_fire(prev_bool, curr_bool) -> bool:
        if prev_bool is None:
            return curr_bool  # first run: allow fire so users see state
        return curr_bool and not prev_bool  # only on rising edge of condition

    cond_r0 = (r0 is not None and r0 < 7.0)
    prev_cond_r0 = (prev_r0 is not None and prev_r0 < 7.0) if prev_r0 is not None else None
    if should_fire(prev_cond_r0, cond_r0):
        caption = f"Dayside compressed: r₀≈{r0:.1f} Rᴇ — GEO risk elevated"
        img_html = f'<p><img src="{GEOSPACE_FRAME_URL}" alt="Geospace dayside cut" /></p>' if GEOSPACE_FRAME_URL else ""
        html_alert = f"<p><strong>{caption}</strong></p>{img_html}"
        alerts_fired.append({"type":"r0_lt_7", "caption": caption})
        wp_alert_post("Magnetosphere Alert: r₀ < 7 Rᴇ", html_alert, unique_tag="magnetosphere-r0")
        post_json_webhook(EARTHSCOPE_WEBHOOK_URL, {"kind":"magnetosphere_alert","rule":"r0_lt_7","payload":{"ts": ts}})
        post_json_webhook(SOCIAL_WEBHOOK_URL, {"text": f"⚠️ Magnetosphere compressed: r₀≈{r0:.1f} Rᴇ. GEO risk elevated. #spaceweather #aurora"})

    cond_symh = (symh is not None and symh < -50)
    prev_cond_symh = (prev_symh is not None and prev_symh < -50) if prev_symh is not None else None
    if should_fire(prev_cond_symh, cond_symh):
        banner_html = f"<h3>Storm Mode</h3><p>SYM-H {symh} nT — heightened geomagnetic activity.</p>"
        if GEOSPACE_FRAME_URL:
            banner_html += f'<p><img src="{GEOSPACE_FRAME_URL}" alt="Geospace dayside cut" /></p>'
        set_wp_banner("Storm Mode", banner_html, slug="storm-mode-banner")
        alerts_fired.append({"type":"symh_lt_50", "caption": f"Storm mode: SYM-H {symh} nT"})
        post_json_webhook(EARTHSCOPE_WEBHOOK_URL, {"kind":"magnetosphere_alert","rule":"symh_lt_50","payload":{"ts": ts}})

    cond_dbdt = (dbdt_tag == "high")
    prev_cond_dbdt = ((prev_dbdt_tag == "high") if prev_dbdt_tag is not None else None)
    if should_fire(prev_cond_dbdt, cond_dbdt):
        tip = "Grid stress / sensitivity tip: simplify, ground, avoid big firmware updates."
        alerts_fired.append({"type":"dbdt_high", "caption": tip})
        wp_alert_post("Sensitivity Tip (GIC risk)", f"<p>{tip}</p>", unique_tag="magnetosphere-dbdt")
        post_json_webhook(EARTHSCOPE_WEBHOOK_URL, {"kind":"magnetosphere_alert","rule":"dbdt_high","payload":{"ts": ts}})

    # 3) Emit app JSON (with visuals + explainer)
    app_json = {
        "ts": ts,
        "kpis": {
            "r0_re": None if r0 is None else round(r0, 1),
            "geo_risk": geo_risk,
            "storminess": kpi_bucket,
            "dbdt": dbdt_tag,
            "lpp_re": None if lpp is None else round(lpp, 1),
            "kp": kp_latest
        },
        "sw": {"n_cm3": sw_now["density"], "v_kms": sw_now["speed"], "bz_nt": sw_now["bz"]},
        "trend": {"r0": trend},
        "chart": {
            "mode": chart_meta.get("mode"),
            "amp": chart_meta.get("amp")
        },
        "series": {
            "r0": series_r0
        },
        "explain": explainer,
        "images": {
            "sparkline": "data/magnetosphere_sparkline.png",
            "geospace": GEOSPACE_FRAME_URL
        },
        "badges": badges
    }
    print(json.dumps(app_json))

    # 3b) Write a single JSON file for the website repo
    if MEDIA_OUT_DIR:
        try:
            os.makedirs(MEDIA_OUT_DIR, exist_ok=True)
            latest_path = os.path.join(MEDIA_OUT_DIR, "magnetosphere_latest.json")
            with open(latest_path, "w") as f:
                json.dump(app_json, f, indent=2)
        except Exception:
            # non-fatal: continue; the action step will handle commits if files exist
            pass

    # 3c) Sparkline image for website (reuse rows24)
    if MEDIA_OUT_DIR:
        try:
            spark_path = os.path.join(MEDIA_OUT_DIR, "magnetosphere_sparkline.png")
            if write_sparkline_png(rows24, spark_path):
                try:
                    with open(spark_path, "rb") as _f:
                        sha = hashlib.sha256(_f.read()).hexdigest()[:16]
                    print(f"[sparkline] wrote {spark_path} sha256={sha}")
                except Exception:
                    pass
        except Exception:
            pass

    # 4) Optional WP short card (idempotent posting is in your other bot; here we just compose)
    caption = coachy_caption(r0, geo_risk, kpi_bucket, dbdt_tag)
    html = f"""
    <h2>Magnetosphere Status</h2>
    <p><strong>{caption}</strong></p>
    <ul>
      <li>Solar wind: n={sw_now['density']:.1f} cm⁻³, V={sw_now['speed']:.0f} km/s, Bz={sw_now['bz']:.1f} nT</li>
      <li>Dynamic pressure: {pdyn:.2f} nPa</li>
      <li>r₀ (Shue98): {(f"{r0:.1f}" if r0 is not None else "—")} Rᴇ ({trend})</li>
      <li>SYM-H: {symh} nT</li>
      <li>dB/dt proxy: {dbdt_tag}</li>
      <li>Plasmapause L (proxy): {(f"{lpp:.1f}" if lpp is not None else "—")} Rᴇ</li>
    </ul>
    {"<p><img src='"+GEOSPACE_FRAME_URL+"' alt='Geospace dayside cut' /></p>" if GEOSPACE_FRAME_URL else ""}
    """
    # Uncomment if you want it to post:
    # post_to_wp("Magnetosphere Status (Auto)", html)

if __name__ == "__main__":
    main()
