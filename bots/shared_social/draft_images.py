"""Local social layouts from actual Shopify media; never upload or invent products."""
import hashlib
import io
from pathlib import Path
import warnings

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
import requests

from bots.shared_social.shopify_drafts import safe_url

SIZES = {"facebook": (1200, 630), "instagram": (1080, 1350)}
MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 25_000_000


class ImageError(RuntimeError):
    pass


def download_image(url, *, session=None):
    if not safe_url(url, image=True):
        raise ImageError("Image URL is outside the Mod Panic Shopify media directory")
    client = session or requests.Session()
    client.trust_env = False
    try:
        with client.get(url, timeout=(10, 45), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise ImageError("Product image download failed or redirected")
            if response.headers.get("Content-Type", "").split(";")[0] not in {
                "image/jpeg", "image/png", "image/webp"
            }:
                raise ImageError("Unsupported image content type")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ImageError("Product image exceeds the download limit")
                chunks.append(chunk)
        return b"".join(chunks)
    except requests.RequestException:
        raise ImageError("Product image transport failed") from None
    finally:
        if session is None:
            client.close()


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def render_images(draft, output_dir, *, downloader=download_image):
    data = downloader(draft["image_url"])
    if len(data) > MAX_BYTES:
        raise ImageError("Product image exceeds the download limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > MAX_PIXELS:
                    raise ImageError("Product image format or dimensions are unsafe")
                source.load()
                source = ImageOps.exif_transpose(source).convert("RGBA")
                clean = Image.new("RGBA", source.size, "white")
                clean.alpha_composite(source)
                clean = clean.convert("RGB")
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ImageError("Product image could not be safely decoded") from None
    assets = {}
    directory = Path(output_dir) / "images"
    directory.mkdir(parents=True, exist_ok=True)
    for platform, size in SIZES.items():
        canvas = Image.new("RGB", size, "#f3eee4")
        draw = ImageDraw.Draw(canvas)
        if platform == "facebook":
            box = (500, 54, 1150, 576)
            draw.text((48, 176), "MOD\nPANIC", font=_font(76), fill="#182626", spacing=2)
            draw.text((52, 395), "Personality for\nthe everyday.", font=_font(31), fill="#182626", spacing=8)
            draw.text((52, 556), "modpanic.com", font=_font(22), fill="#182626")
        else:
            box = (64, 204, 1016, 1140)
            draw.text((64, 64), "MOD PANIC", font=_font(72), fill="#182626")
            draw.text((64, 1190), "Personality for the everyday.", font=_font(38), fill="#182626")
            draw.text((64, 1256), "modpanic.com", font=_font(27), fill="#182626")
        fitted = ImageOps.contain(clean, (box[2]-box[0], box[3]-box[1]), Image.Resampling.LANCZOS)
        canvas.paste(fitted, (box[0]+(box[2]-box[0]-fitted.width)//2,
                              box[1]+(box[3]-box[1]-fitted.height)//2))
        buffer = io.BytesIO()
        canvas.save(buffer, format="JPEG", quality=92, optimize=True)
        content = buffer.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        relative = f"images/{draft['draft_id']}-{platform}-{digest[:16]}.jpg"
        target = Path(output_dir) / relative
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            target.write_bytes(content)
        assets[platform] = {"path": relative, "sha256": digest, "width": size[0], "height": size[1]}
    return assets
