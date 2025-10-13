# bots/magnetosphere/magnetosphere_collect.py
import os, time, json, math, datetime as dt
import requests
import numpy as np
from supabase import create_client, Client
from typing import Optional, Dict, Any
from urllib.parse import urljoin

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
    sw_now = fetch_solarwind_now()
    hist = latest_n_history()
    # 2) Compute KPIs
    pdyn = dyn_pressure_npa(sw_now["density"], sw_now["speed"])
    r0 = r0_shue98(pdyn, sw_now["bz"])
    symh = fetch_symh_est()
    dbdt_proxy = compute_dbdt_proxy(hist)
    dbdt_tag = dbdt_tag_from_proxy(dbdt_proxy)

    # Optional plasmapause proxy and Kp read
    kp_latest = fetch_kp_latest_from_supabase()
    lpp = plasmapause_L_carpenter_anderson(kp_latest)

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

    # 3) Emit app JSON
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
        "trend": {"r0": trend}
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