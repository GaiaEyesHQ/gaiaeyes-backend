#!/usr/bin/env python3
import os
import json
import datetime as dt
import urllib.request


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

    # 4) HMI intensitygram (sunspot context). If you prefer SDO AIA 193Å (coronal holes), swap a stable endpoint later.
    hmi_img = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIIC.jpg"

    # Magnetometers (global and three US stations via SWPC)
    geomag_global = env_urls("GEOMAG_GLOBAL_URLS", [
        "https://services.swpc.noaa.gov/images/geomag/1-minute.png"
    ])
    geomag_boulder = env_urls("GEOMAG_BOULDER_URLS", [
        "https://services.swpc.noaa.gov/images/geomag/Boulder_mag_1m.png"
    ])
    geomag_fredericksburg = env_urls("GEOMAG_FRED_URLS", [
        "https://services.swpc.noaa.gov/images/geomag/Fredericksburg_mag_1m.png"
    ])
    geomag_college = env_urls("GEOMAG_COLLEGE_URLS", [
        "https://services.swpc.noaa.gov/images/geomag/College_mag_1m.png"
    ])

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    imgs = {
        "aia_primary": (f"aia_primary_{stamp}.jpg", suvi_latest),
        "ovation_nh": (f"ovation_nh_{stamp}.jpg", ov_nh),
        "ovation_sh": (f"ovation_sh_{stamp}.jpg", ov_sh),
        "soho_c2": (f"soho_c2_{stamp}.jpg", soho_c2),
        "lasco_c3": (f"lasco_c3_{stamp}.jpg", lasco_c3),
        "hmi_intensity": (f"hmi_intensity_{stamp}.jpg", hmi_img),
        "geomag_global": (f"geomag_global_{stamp}.png", geomag_global),
        "geomag_boulder": (f"geomag_boulder_{stamp}.png", geomag_boulder),
        "geomag_fredericksburg": (f"geomag_fredericksburg_{stamp}.png", geomag_fredericksburg),
        "geomag_college": (f"geomag_college_{stamp}.png", geomag_college)
    }
    saved = {}
    missing = []
    for key, (fn, url) in imgs.items():
        dest = os.path.join(IMG_DIR, fn)
        if dl(url, dest):
            saved[key] = f"images/space/{fn}"
        else:
            missing.append(key)

    xrs = fetch_json(xrs_7d) or []
    p7d = fetch_json(protons_7d) or []

    out = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "images": saved,
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
