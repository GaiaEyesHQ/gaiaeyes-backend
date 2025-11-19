import glob
import json
import os
import sys
from pathlib import Path

from scripts.supabase_storage import upload_file

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "gaiaeyes-media"))
IMAGES_DIR = MEDIA_DIR / "images" / "space"
# Kept for parity with ingest configuration; currently unused in upload flow
SPACE_JSON = Path(os.getenv("OUTPUT_JSON_PATH", MEDIA_DIR / "data" / "space_live.json"))


def map_dest(path: Path) -> str:
    name = path.name.lower()
    if "d-rap" in name or "drap" in name:
        return "drap/latest.png"
    if "lasco" in name and name.endswith(".jpg"):
        return "nasa/lasco_c2/latest.jpg"
    if ("aia_304" in name or "sdo_aia_304" in name) and name.endswith(".jpg"):
        return "nasa/aia_304/latest.jpg"
    if "tonight" in name and "viewline" in str(path.parent).lower():
        return "aurora/viewline/tonight-north.png"
    if "tomorrow" in name and "viewline" in str(path.parent).lower():
        return "aurora/viewline/tomorrow-north.png"
    return f"images/space/{path.name}"


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
