import os, requests, datetime as dt
from pathlib import Path

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "gaiaeyes-media"))
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
IG_ID = os.getenv("IG_BUSINESS_ID") OR OS.GETENV("IG_USER_ID")  # IG_BUSINESS_ID is preferre
GRAPH = "https://graph.facebook.com/v21.0"

def latest(kind: str) -> Path:
    folder = MEDIA_ROOT / "images" / "facts"
    imgs = sorted(folder.glob(f"*-{kind}.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return imgs[0] if imgs else None

def fb_post_photo(path: Path, caption: str):
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    with open(path, "rb") as f:
        r = requests.post(url, files={"source": f}, data={"access_token": FB_ACCESS_TOKEN, "caption": caption})
    r.raise_for_status()
    return r.json()

def ig_post_photo(path: Path, caption: str):
    # Simple feed image (not Reel). IG Reels are constrained; we’ll handle FB Reels separately.
    # Step 1: create container
    create_url = f"{GRAPH}/{IG_BUSINESS_ID}/media"
    with open(path, "rb") as f:
        upload = requests.post(create_url, data={"caption": caption, "access_token": FB_ACCESS_TOKEN}, files={"image_file": f})
    upload.raise_for_status()
    container_id = upload.json()["id"]
    # Step 2: publish
    publish = requests.post(f"{GRAPH}/{IG_BUSINESS_ID}/media_publish", data={"creation_id": container_id, "access_token": FB_ACCESS_TOKEN})
    publish.raise_for_status()
    return publish.json()

def main():
    square = latest("square")
    tall = latest("tall")
    if not square and not tall:
        print("No fact images found to post.")
        return
    caption = "Daily frequency fact • #GaiaEyes #spaceweather #earthenergy"
    if square:
        print("Posting to Facebook:", square)
        fb_post_photo(square, caption)
    if tall and IG_BUSINESS_ID:
        print("Posting to Instagram:", tall)
        ig_post_photo(tall, caption)
    print("Done.")

if __name__ == "__main__":
    main()