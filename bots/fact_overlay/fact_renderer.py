import os, random, textwrap, datetime as dt
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import requests  # for Supabase REST if you prefer; swap to supabase-py if used

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "gaiaeyes-media"))
FOOTER = os.getenv("BRAND_FOOTER_TEXT", "Gaia Eyes")
BG_SQUARE = Path("backgrounds/square")   # 1:1
BG_TALL = Path("backgrounds/tall")       # 9:16

HOOKS = [
  "Cosmic fact:", "Space weather insight:", "Earth’s hidden signal:",
  "Mind & frequency:", "Quick cosmic tip:", "Signal from Gaia:",
  "Science spotlight:", "Today’s resonance:", "Frequency fact:",
  "Something to ground you:"
]

def _extract_text(record: dict) -> str:
    """
    Try common fields for text; also check nested JSON like {output:{text:...}}.
    """
    if not isinstance(record, dict):
        return ""
    # flat possibilities
    for key in ("text", "content", "body", "summary", "fact_text", "message"):
        v = record.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # nested common containers
    for container in ("output", "data", "payload"):
        v = record.get(container)
        if isinstance(v, dict):
            for key in ("text", "content", "body", "summary", "fact"):
                vv = v.get(key)
                if isinstance(vv, str) and vv.strip():
                    return vv.strip()
    return ""

def sb_select_facts(limit=10):
    # Expecting table `article_outputs` with: id, output_type, content, created_at
    # Pull only facts not yet rendered (left-join to research_fact_images)
    url = f"{SUPABASE_URL}/rest/v1/rpc/fetch_unrendered_facts"
    # If you don't have the RPC, you can emulate with a view or do it client-side.
    # For simplicity, we do a naive select (replace with your SDK if available).
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    # Fallback: select facts from last 7 days (using created_at)
    from_date = (dt.datetime.utcnow() - dt.timedelta(days=7)).isoformat()
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/article_outputs",
        headers=headers,
        params={
            "output_type": "ilike.fact",
            "created_at": f"gte.{from_date}",
            "select": "id,output_type,content,created_at",
            "order": "created_at.desc",
            "limit": str(limit)
        }
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"[facts] HTTP error from Supabase: {e} — {getattr(resp, 'text', '')[:300]}")
        return []
    try:
        data = resp.json()
    except Exception as e:
        print(f"[facts] Failed to parse JSON: {e}")
        return []
    # Supabase returns a list on success; dict usually indicates an error object
    if isinstance(data, dict):
        print(f"[facts] Unexpected dict payload from Supabase: {str(data)[:300]}")
        return []
    if not isinstance(data, list):
        print(f"[facts] Unexpected payload type: {type(data)}")
        return []
    return data

def pick_bg(folder: Path) -> Image.Image:
    folder.mkdir(parents=True, exist_ok=True)
    imgs = [p for p in folder.glob("*") if p.suffix.lower() in {".jpg",".jpeg",".png"}]
    if not imgs:
        # create a simple gradient if no bg file exists
        img = Image.new("RGB", (1080, 1920 if folder is BG_TALL else 1080), (10, 12, 16))
        return img
    return Image.open(random.choice(imgs)).convert("RGB")

def draw_text(img: Image.Image, title: str, body: str) -> Image.Image:
    W, H = img.size
    draw = ImageDraw.Draw(img)
    # Load fonts (bundle your own in /assets/fonts)
    font_title = ImageFont.truetype("assets/fonts/Inter-Bold.ttf", size=int(W*0.075)) if Path("assets/fonts/Inter-Bold.ttf").exists() else ImageFont.load_default()
    font_body  = ImageFont.truetype("assets/fonts/Inter-Regular.ttf", size=int(W*0.045)) if Path("assets/fonts/Inter-Regular.ttf").exists() else ImageFont.load_default()
    font_footer= ImageFont.truetype("assets/fonts/Inter-SemiBold.ttf", size=int(W*0.035)) if Path("assets/fonts/Inter-SemiBold.ttf").exists() else ImageFont.load_default()

    pad = int(W*0.08)
    y = pad

    # overlay panel
    overlay = Image.new("RGBA", img.size, (0,0,0,0))
    ImageDraw.Draw(overlay).rectangle([(pad//2, pad//2), (W-pad//2, H-pad//2)], fill=(0,0,0,90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    # Title
    draw.text((pad, y), title, font=font_title, fill=(255,255,255))
    y += int(font_title.size*1.6)

    # Body wrap
    max_w = W - pad*2
    wrapped = []
    for line in body.splitlines():
        wrapped += textwrap.wrap(line, width=40) if font_body is ImageFont.load_default() else textwrap.wrap(line, width=34)
    for line in wrapped:
        draw.text((pad, y), line, font=font_body, fill=(230,230,230))
        y += int(font_body.size*1.35)

    # Footer
    fb = FOOTER
    fw, fh = draw.textlength(fb, font=font_footer), font_footer.size
    draw.text((pad, H - pad - fh*1.2), fb, font=font_footer, fill=(200,200,200))

    return img

def seeded_hook():
    seed = int(dt.datetime.utcnow().strftime("%Y%m%d"))
    random.seed(seed)
    return random.choice(HOOKS)

def ensure_dirs():
    (MEDIA_ROOT / "images" / "facts").mkdir(parents=True, exist_ok=True)

def insert_fact_image_row(output_id, kind, image_url):
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type":"application/json"}
    payload = {"output_id": output_id, "kind": kind, "image_url": image_url}
    requests.post(f"{SUPABASE_URL}/rest/v1/research_fact_images", headers=headers, json=payload, params={"return":"minimal"})

def render_one(kind: str, output) -> Path:
    # kind: "square" or "tall"
    bg = pick_bg(BG_TALL if kind=="tall" else BG_SQUARE)
    hook = seeded_hook()
    text = _extract_text(output)
    if not text:
        text = "No fact text available."
    body = text if len(text) < 600 else text[:600] + "…"
    composed = draw_text(bg, hook, body)
    ensure_dirs()
    rec_id = str(output.get("id", "unknown"))
    fn = f"{dt.datetime.utcnow().strftime('%Y%m%d')}-{rec_id}-{kind}.png"
    out_path = MEDIA_ROOT / "images" / "facts" / fn
    composed.save(out_path, "PNG")
    # URL resolution: if MEDIA_ROOT is a repo synced to a public CDN or WP media, replace with public URL builder
    image_url = str(out_path)
    insert_fact_image_row(output.get("id"), kind, image_url)
    return out_path

def main():
    facts = sb_select_facts(limit=5)
    if not facts or not isinstance(facts, list):
        print("No facts to render (empty or unexpected payload).")
        return
    # Render only first new fact per day to avoid spam
    try:
        out = facts[0]
        if not _extract_text(out):
            print("Top fact has no usable text; skipping render.")
            return
    except (IndexError, KeyError, TypeError):
        print("No usable fact item found.")
        return
    sq = render_one("square", out)
    tl = render_one("tall", out)
    print("Rendered:", sq, tl)

if __name__ == "__main__":
    main()