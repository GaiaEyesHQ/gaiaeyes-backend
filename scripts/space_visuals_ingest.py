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
    # 1) GOES SUVI (131Å) + Solar flares (XRS) + Proton flux (GOES)
    suvi_latest = env_urls("SUVI_URLS", [
        "https://services.swpc.noaa.gov/images/animations/suvi/primary/131/latest.jpg",
        "https://services.swpc.noaa.gov/images/animations/suvi/primary/131/latest.png",
        "https://services.swpc.noaa.gov/images/suvi/primary/131/latest.jpg",
        "https://services.swpc.noaa.gov/images/suvi/primary/131/latest.png"
    ])
    xrs_7d = "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json"
    protons_7d = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json"

    # 2) Aurora (Ovation) maps (NH/SH)
    ov_nh = "https://services.swpc.noaa.gov/images/aurora-forecast-northern-hemisphere.jpg"
    ov_sh = "https://services.swpc.noaa.gov/images/aurora-forecast-southern-hemisphere.jpg"

    # 3) CME coronagraph imagery (SOHO C2 & GOES CCOR-1)
    soho_c2 = "https://soho.nascom.nasa.gov/data/realtime/c2/1024/latest.jpg"
    goes_cc1 = env_urls("CCOR1_URLS", [
        "https://services.swpc.noaa.gov/images/goes-ccor1/latest.jpg",
        "https://services.swpc.noaa.gov/images/goes-ccor1/latest.png",
        "https://services.swpc.noaa.gov/images/animations/goes-ccor1/latest.jpg",
        "https://services.swpc.noaa.gov/images/animations/goes-ccor1/latest.png"
    ])

    # 4) HMI intensitygram (sunspot context). If you prefer SDO AIA 193Å (coronal holes), swap a stable endpoint later.
    hmi_img = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIIC.jpg"

    # 5) Magnetometer plots (Kiruna/CANMOS/Hobart) — replace with your preferred latest endpoints if you have better sources
    kiruna = "https://www.irf.se/Observatory/?download=magplot&site=kir"
    canmos = env_urls("CANMOS_URLS", [
        "https://www.spaceweather.gc.ca/auto_generated_products/magnetometers/013.png",
        "https://www.spaceweather.gc.ca/auto_generated_products/magnetometers/013.jpg",
        "https://www.spaceweather.gc.ca/auto_generated_products/magnetometers/000.png"
    ])
    hobart = env_urls("HOBART_URLS", [
        "https://www.sws.bom.gov.au/Images/HF%20Systems/IPS%20Magnetometer%20Data/Hobart.png",
        "https://www.sws.bom.gov.au/Images/HF%20Systems/IPS%20Magnetometer%20Data/hobart.png",
        "https://www.sws.bom.gov.au/Images/HF%20Systems/IPS%20Magnetometer%20Data/HOBART.png"
    ])

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    imgs = {
        "suvi_131_latest": ("suvi_131_latest.jpg", suvi_latest),
        "ovation_nh": (f"ovation_nh_{stamp}.jpg", ov_nh),
        "ovation_sh": (f"ovation_sh_{stamp}.jpg", ov_sh),
        "soho_c2": (f"soho_c2_{stamp}.jpg", soho_c2),
        "goes_ccor1": (f"goes_ccor1_{stamp}.jpg", goes_cc1),
        "hmi_intensity": (f"hmi_intensity_{stamp}.jpg", hmi_img),
        "mag_kiruna": (f"mag_kiruna_{stamp}.png", kiruna),
        "mag_canmos": (f"mag_canmos_{stamp}.png", canmos),
        "mag_hobart": (f"mag_hobart_{stamp}.png", hobart),
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
