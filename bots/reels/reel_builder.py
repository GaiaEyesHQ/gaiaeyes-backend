import os
from pathlib import Path
from moviepy.editor import ImageClip, concatenate_videoclips

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "gaiaeyes-media"))
OUT = MEDIA_ROOT / "video" / "reels"
OUT.mkdir(parents=True, exist_ok=True)

def build_reel(image_paths, seconds_per=3.5, size=(1080,1920)) -> Path:
    clips = []
    for p in image_paths:
        clip = ImageClip(str(p)).set_duration(seconds_per).resize(newsize=size)
        clips.append(clip.crossfadein(0.3))
    video = concatenate_videoclips(clips, method="compose")
    out = OUT / "reel.mp4"
    video.write_videofile(str(out), fps=30, codec="libx264", audio=False)
    return out

def main():
    tall_imgs = sorted((MEDIA_ROOT/"images"/"facts").glob("*-tall.png"))[-3:]
    if len(tall_imgs) < 3:
        print("Need >=3 tall images to build a reel.")
        return
    out = build_reel(tall_imgs)
    print("Built:", out)

if __name__ == "__main__":
    main()