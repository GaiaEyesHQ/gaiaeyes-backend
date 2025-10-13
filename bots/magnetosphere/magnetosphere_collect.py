# bots/magnetosphere/magnetosphere_collect.py
import os, time, json, math, datetime as dt
import requests
import numpy as np
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
WP_BASE_URL = os.environ.get("WP_BASE_URL")           # already in your env
WP_USERNAME = os.environ.get("WP_USERNAME")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")

def dyn_pressure_npa(n_cm3, v_kms):
    if n_cm3 is None or v_kms is None: return None
    return 1.6726e-6 * n_cm3 * (v_kms**2)

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
    If live SYM-H isn’t available, derive a rough estimate:
    more negative when Bz south & Pdyn high. This is an intentionally
    conservative placeholder so the UI stays consistent.
    """
    sw = fetch_solarwind_now()
    pdyn = dyn_pressure_npa(sw["density"], sw["speed"])
    bz = sw["bz"]
    # crude estimate: not for science, just UX-consistent gatekeeping
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

# bots/magnetosphere/magnetosphere_collect.py (only the upsert helper changed)

def upsert_supabase(rec):
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Target the ext schema table
    sb.table("ext.magnetosphere_pulse").upsert(rec, on_conflict="ts").execute()

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
    sw_now = fetch_solarwind_now()
    hist = latest_n_history()
    # 2) Compute KPIs
    pdyn = dyn_pressure_npa(sw_now["density"], sw_now["speed"])
    r0 = r0_shue98(pdyn, sw_now["bz"])
    symh = fetch_symh_est()
    dbdt_proxy = compute_dbdt_proxy(hist)
    dbdt_tag = dbdt_tag_from_proxy(dbdt_proxy)

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
        "kpi_bucket": kpi_bucket
    }
    upsert_supabase(rec)

    # 3) Emit app JSON
    app_json = {
        "ts": ts,
        "kpis": {
            "r0_re": None if r0 is None else round(r0, 1),
            "geo_risk": geo_risk,
            "storminess": kpi_bucket,
            "dbdt": dbdt_tag
        },
        "sw": {"n_cm3": sw_now["density"], "v_kms": sw_now["speed"], "bz_nt": sw_now["bz"]},
        "trend": {"r0": trend}
    }
    print(json.dumps(app_json))

    # 4) Optional WP short card (idempotent posting is in your other bot; here we just compose)
    caption = coachy_caption(r0, geo_risk, kpi_bucket, dbdt_tag)
    html = f"""
    <h2>Magnetosphere Status</h2>
    <p><strong>{caption}</strong></p>
    <ul>
      <li>Solar wind: n={sw_now['density']:.1f} cm⁻³, V={sw_now['speed']:.0f} km/s, Bz={sw_now['bz']:.1f} nT</li>
      <li>Dynamic pressure: {pdyn:.2f} nPa</li>
      <li>r₀ (Shue98): {r0:.1f if r0 is not None else '—'} Rᴇ ({trend})</li>
      <li>SYM-H (est.): {symh} nT</li>
      <li>dB/dt proxy: {dbdt_tag}</li>
    </ul>
    """
    # Uncomment if you want it to post:
    # post_to_wp("Magnetosphere Status (Auto)", html)

if __name__ == "__main__":
    main()