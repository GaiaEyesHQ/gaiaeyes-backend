#!/usr/bin/env python3
import os
import json
import datetime as dt
import urllib.request
import urllib.parse


# Helper to read env overrides and split by comma
def env_urls(key: str, defaults):
    v = os.getenv(key, "").strip()
    if not v:
        return defaults
    return [u.strip() for u in v.split(",") if u.strip()]

OUT_JSON = os.getenv("OUTPUT_JSON_PATH", "space_live.json")
MEDIA_DIR = os.getenv("MEDIA_DIR", "gaiaeyes-media")
IMG_DIR = os.path.join(MEDIA_DIR, "images", "space")
DATA_DIR = os.path.join(MEDIA_DIR, "data")
os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


def dl(url_or_urls, dest):
    """Download first successful URL into dest. url_or_urls can be str or list[str]."""
    urls = url_or_urls if isinstance(url_or_urls, (list, tuple)) else [url_or_urls]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0 (+https://gaiaeyes.com)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                with open(dest, "wb") as f:
                    f.write(r.read())
            return True
        except Exception as e:
            print(f"[dl] {url} -> {e}")
    return False


def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0 (+https://gaiaeyes.com)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[json] {url} -> {e}")
        return None


def http_get(url, as_json=False, ua="GaiaEyes/1.0 (+https://gaiaeyes.com)"):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        return json.loads(data.decode("utf-8")) if as_json else data
    except Exception as e:
        print(f"[get] {url} -> {e}")
        return None

def latest_from_dir(base_url: str, suffix_filter: str = ".jpg", contains: str = "ccor1"):
    """Scrape a simple directory index and return the latest matching file URL by name sort.
    base_url should end with '/'. We match links containing `contains` and ending with `suffix_filter`.
    """
    html = http_get(base_url, as_json=False)
    if not html:
        return None
    try:
        text = html.decode("utf-8", "ignore") if isinstance(html, (bytes, bytearray)) else str(html)
    except Exception:
        text = str(html)
    import re
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
    cands = [h for h in hrefs if h.lower().endswith(suffix_filter) and contains in h]
    if not cands:
        return None
    cands = sorted(set(cands))
    last = cands[-1]
    if not last.startswith("http"):
        return urllib.parse.urljoin(base_url.rstrip('/') + '/', last)
    return last


def main():
    # 1) Solar imagery + Solar flares (XRS) + Proton flux (GOES)
    suvi_latest = env_urls("SUVI_URLS", [
        "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0193.jpg",  # SDO AIA 193Å (coronal holes proxy)
        "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0304.jpg"   # SDO AIA 304Å (prominences/filaments)
    ])
    xrs_7d = "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json"
    protons_7d = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json"

    # 2) Aurora (Ovation) maps (NH/SH)
    ov_nh = "https://services.swpc.noaa.gov/images/aurora-forecast-northern-hemisphere.jpg"
    ov_sh = "https://services.swpc.noaa.gov/images/aurora-forecast-southern-hemisphere.jpg"

    # 3) CME coronagraph imagery (SOHO C2 & LASCO C3)
    soho_c2 = "https://soho.nascom.nasa.gov/data/realtime/c2/1024/latest.jpg"
    lasco_c3 = env_urls("LASCO_C3_URLS", [
        "https://soho.nascom.nasa.gov/data/realtime/c3/1024/latest.jpg"
    ])

    # CCOR-1 directory scrape for latest JPEG, and pick known MP4 names
    ccor_jpegs_dir = "https://services.swpc.noaa.gov/products/ccor1/jpegs/"
    ccor_mp4s_dir  = "https://services.swpc.noaa.gov/products/ccor1/mp4s/"
    ccor1_jpeg_url = latest_from_dir(ccor_jpegs_dir, suffix_filter=".jpg", contains="ccor1")
    ccor1_mp4_url = None
    for name in [os.getenv("CCOR1_MP4_NAME", "ccor1_last_24hrs.mp4"), "ccor1_last_7_days.mp4", "ccor1_last_27_days.mp4"]:
        test = ccor_mp4s_dir.rstrip('/') + '/' + name
        if http_get(test, as_json=False):
            ccor1_mp4_url = test
            break

    # 4) HMI intensitygram (sunspot context). If you prefer SDO AIA 193Å (coronal holes), swap a stable endpoint later.
    hmi_img = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIIC.jpg"

    # GEOSPACE plots and station indices / DRAP / synoptic / overview
    geospace_1d = "https://services.swpc.noaa.gov/images/geospace/geospace_1_day.png"
    geospace_3h = "https://services.swpc.noaa.gov/images/geospace/geospace_3_hour.png"
    geospace_7d = "https://services.swpc.noaa.gov/images/geospace/geospace_7_day.png"
    kp_station  = "https://services.swpc.noaa.gov/images/station-k-index.png"
    a_station   = "https://services.swpc.noaa.gov/images/station-a-index.png"
    drap_global = "https://services.swpc.noaa.gov/images/drap_global.png"
    drap_npole  = "https://services.swpc.noaa.gov/images/drap_n-pole.png"
    drap_spole  = "https://services.swpc.noaa.gov/images/drap_s-pole.png"
    synoptic_map = "https://services.swpc.noaa.gov/images/synoptic-map.jpg"
    swx_small    = "https://services.swpc.noaa.gov/images/swx-overview-small.gif"

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    imgs = {
        "aia_primary": (f"aia_primary_{stamp}.jpg", suvi_latest),
        "ovation_nh": (f"ovation_nh_{stamp}.jpg", ov_nh),
        "ovation_sh": (f"ovation_sh_{stamp}.jpg", ov_sh),
        "soho_c2": (f"soho_c2_{stamp}.jpg", soho_c2),
        "lasco_c3": (f"lasco_c3_{stamp}.jpg", lasco_c3),
        "ccor1_jpeg": (f"ccor1_{stamp}.jpg", [ccor1_jpeg_url] if ccor1_jpeg_url else []),
        "hmi_intensity": (f"hmi_intensity_{stamp}.jpg", hmi_img),
        "geospace_1d": (f"geospace_1d_{stamp}.png", geospace_1d),
        "geospace_3h": (f"geospace_3h_{stamp}.png", geospace_3h),
        "geospace_7d": (f"geospace_7d_{stamp}.png", geospace_7d),
        "kp_station": (f"kp_station_{stamp}.png", kp_station),
        "a_station": (f"a_station_{stamp}.png", a_station),
        "drap_global": (f"drap_global_{stamp}.png", drap_global),
        "drap_n_pole": (f"drap_n_pole_{stamp}.png", drap_npole),
        "drap_s_pole": (f"drap_s_pole_{stamp}.png", drap_spole),
        "synoptic_map": (f"synoptic_map_{stamp}.jpg", synoptic_map),
        "swx_overview_small": (f"swx_overview_small_{stamp}.gif", swx_small)
    }
    saved = {}
    missing = []
    for key, (fn, url) in imgs.items():
        dest = os.path.join(IMG_DIR, fn)
        if dl(url, dest):
            saved[key] = f"images/space/{fn}"
        else:
            missing.append(key)

    # Download CCOR-1 MP4 video if available
    video = {}
    if ccor1_mp4_url:
        try:
            mp4_name = f"ccor1_{stamp}.mp4"
            mp4_dest = os.path.join(IMG_DIR, mp4_name)
            if dl([ccor1_mp4_url], mp4_dest):
                video["ccor1_mp4"] = f"images/space/{mp4_name}"
            else:
                missing.append("ccor1_mp4")
        except Exception as e:
            print("[dl] ccor1 mp4 ->", e)
            missing.append("ccor1_mp4")
    else:
        missing.append("ccor1_mp4")

    xrs = fetch_json(xrs_7d) or []
    p7d = fetch_json(protons_7d) or []

    out = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "images": saved,
        "video": video,
        "missing": missing,
        "series": {
            "xrs_7d": xrs,
            "protons_7d": p7d,
        },
        "notes": "Visuals cached for detail pages. Use with [gaia_space_visuals] or [gaia_space_detail].",
    }

    with open(OUT_JSON if os.path.isabs(OUT_JSON) else os.path.join(MEDIA_DIR, OUT_JSON), "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("[space_visuals] wrote images and space_live.json")


if __name__ == "__main__":
    main()
