import glob
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.supabase_storage import upload_file

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "gaiaeyes-media"))
IMAGES_DIR = MEDIA_DIR / "images" / "space"
# Kept for parity with ingest configuration; currently unused in upload flow
SPACE_JSON = Path(os.getenv("OUTPUT_JSON_PATH", MEDIA_DIR / "data" / "space_live.json"))


def map_dest(path: Path) -> str | None:
    name = path.name.lower()

    # ENLIL poster fallback (mp4 step adds the movie separately)
    if "enlil" in name and name.endswith((".jpg", ".png")):
        return "nasa/enlil/latest.jpg"

    # DRAP aliases → single latest
    if name.startswith("drap_") and name.endswith(".png"):
        return "drap/latest.png"

    # Aurora (NH/SH) viewlines
    if name.startswith("ovation_nh") and name.endswith((".jpg", ".png")):
        return "aurora/viewline/tonight-north.png"
    if name.startswith("ovation_sh") and name.endswith((".jpg", ".png")):
        return "aurora/viewline/tonight-south.png"

    # NASA LASCO/AIA/HMI
    if name.startswith(("lasco_c2", "soho_c2")) and name.endswith(".jpg"):
        return "nasa/lasco_c2/latest.jpg"
    if name.startswith("lasco_c3") and name.endswith(".jpg"):
        return "nasa/lasco_c3/latest.jpg"
    # AIA 304 & HMI intensity are now managed via ingest_space_visuals (Helioviewer),
    # so skip local JPGs here to avoid overwriting the Helioviewer-backed latest.jpg aliases.
    if name.startswith(("aia_primary", "aia_304")) and name.endswith(".jpg"):
        return None
    if name.startswith("hmi_intensity") and name.endswith(".jpg"):
        return None

    # Magnetosphere (geospace horizons)
    if name.startswith("geospace_") and name.endswith(".png"):
        try:
            horizon = name.split("_")[1]
        except Exception:  # noqa: BLE001
            horizon = "latest"
        return f"magnetosphere/geospace/{horizon}.png"

    # KP station snapshot
    if name.startswith("kp_station") and name.endswith(".png"):
        return "space/kp_station/latest.png"

    # a_station snapshot
    if name.startswith("a_station") and name.endswith(".png"):
        return "space/a_station/latest.png"

    # CCOR1 video (mp4)
    if name.startswith("ccor1_") and name.endswith(".mp4"):
        return "nasa/ccor1/latest.mp4"

    # CCOR1 poster (jpg)
    if name.startswith("ccor1_") and name.endswith(".jpg"):
        return "nasa/ccor1/latest.jpg"

    # Synoptic map (jpg)
    if name.startswith("synoptic_map") and name.endswith(".jpg"):
        return "nasa/synoptic/latest.jpg"

    # SWPC overview
    if name.startswith("swx_overview_small") and name.endswith(".gif"):
        return "nasa/swx/overview/latest.gif"

    # Fallback: skip unknowns; no legacy images/space fallback
    return None  # skip unknowns; no legacy images/space fallback


def main() -> int:
    if not IMAGES_DIR.exists():
        print(f"[upload] nothing to upload; missing {IMAGES_DIR}", file=sys.stderr)
        return 0

    files = sorted(glob.glob(str(IMAGES_DIR / "*")))
    if not files:
        print(f"[upload] no files in {IMAGES_DIR}", file=sys.stderr)
        return 0

    ok = 0
    fail = 0
    for f in files:
        src = Path(f)
        dest = map_dest(src)
        if not dest:
            print(json.dumps({"src": str(src), "dest": dest, "skipped": True}))
            continue

        try:
            public = upload_file(dest, str(src))
            print(json.dumps({"src": str(src), "dest": dest, "public": public}))
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"src": str(src), "dest": dest, "error": str(e)}))
            fail += 1
    print(f"[upload] done ok={ok} fail={fail}", file=sys.stderr)
    return 0 if ok > 0 else (1 if fail > 0 else 0)


if __name__ == "__main__":
    raise SystemExit(main())
