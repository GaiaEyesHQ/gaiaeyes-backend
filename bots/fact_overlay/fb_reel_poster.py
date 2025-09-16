import os, requests
from pathlib import Path

FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
GRAPH = "https://graph.facebook.com/v21.0"

def post_video(path: Path, caption: str):
    url = f"{GRAPH}/{FB_PAGE_ID}/videos"
    with open(path, "rb") as f:
        r = requests.post(url, data={"access_token": FB_ACCESS_TOKEN, "description": caption, "upload_phase":"finish"}, files={"source": f})
    r.raise_for_status()
    return r.json()

def main():
    reel = Path("gaiaeyes-media/video/reels/reel.mp4")
    if not reel.exists():
        print("No reel.mp4 found—run reel_builder.py first.")
        return
    caption = "Today’s EarthScope highlights • #GaiaEyes #Reels"
    res = post_video(reel, caption)
    print("Posted:", res)

if __name__ == "__main__":
    main()