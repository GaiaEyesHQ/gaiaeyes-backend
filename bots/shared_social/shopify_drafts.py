"""Draft-only Shopify product adapter for Mod Panic.

Accepts Shopify Admin product JSON exported by an authorized catalog reader.
No Shopify credentials, Meta credentials, or publishing calls are required.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

SHOP_DOMAIN = "modpanic.com"
PRODUCT_PREFIXES = (
    "modcore_coaster-", "stone_coaster-", "sticker-", "magnet-",
    "mug-", "koozie-", "wall_print-", "towel-", "tea_towel-",
)


def design_key(product):
    handle = str(product.get("handle") or "").strip().lower()
    for prefix in PRODUCT_PREFIXES:
        if handle.startswith(prefix):
            return handle[len(prefix):]
    title = str(product.get("title") or "").lower()
    title = re.sub(r"\\b(modcore coaster|stone coaster|wall print|sticker|magnet|mug|koozie|tea towel|kitchen towel)\\b", "", title)
    return re.sub(r"[^a-z0-9]+", "-", title).strip("-")


def product_image(product):
    media = product.get("featuredMedia") or {}
    return (((media.get("preview") or {}).get("image") or {}).get("url") or "").strip()


def make_drafts(products, previously_used=()):
    used = set(previously_used)
    drafts = []
    for product in products:
        if str(product.get("status", "")).upper() != "ACTIVE":
            continue
        key = design_key(product)
        handle = str(product.get("handle") or "").strip()
        image = product_image(product)
        if not key or not handle or key in used or not image.startswith("https://"):
            continue
        if urlparse(image).hostname not in ("cdn.shopify.com", "modpanic.com", "www.modpanic.com"):
            continue
        used.add(key)
        title = str(product.get("title") or "").strip()
        url = f"https://{SHOP_DOMAIN}/products/{handle}"
        drafts.append({
            "brand": "mod_panic",
            "design_key": key,
            "draft_id": hashlib.sha256(("mod_panic:" + key).encode()).hexdigest()[:20],
            "product_id": product.get("id"),
            "product_title": title,
            "product_url": url,
            "image_url": image,
            "facebook_caption": f"{title}. A little personality for the everyday. Explore it at {url}",
            "instagram_caption": f"{title}. Original Mod Panic design. Shop via the link in our bio. #ModPanic",
            "status": "needs_review",
            "approved": False,
        })
    return drafts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, help="JSON array of Shopify Admin product objects")
    parser.add_argument("--output", required=True)
    parser.add_argument("--used-keys", help="JSON array of design keys already published")
    args = parser.parse_args()
    products = json.loads(Path(args.catalog).read_text())
    used = json.loads(Path(args.used_keys).read_text()) if args.used_keys else []
    if not isinstance(products, list) or not isinstance(used, list):
        raise ValueError("Expected JSON arrays")
    drafts = make_drafts(products, used)
    Path(args.output).write_text(json.dumps(drafts, indent=2) + "\\n")
    print(f"Generated {len(drafts)} review-only drafts")


if __name__ == "__main__":
    main()
