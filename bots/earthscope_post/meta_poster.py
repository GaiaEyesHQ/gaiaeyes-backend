def derive_caption_and_hashtags(post: dict) -> (str, str):
    """Return (caption, hashtags) preferring structured sections from metrics_json; fallback to plain fields."""
    cap = (post.get("caption") or "").strip()
    tags = (post.get("hashtags") or "").strip()

    # 1) Prefer sections from metrics_json when available
    try:
        metrics = post.get("metrics_json")
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        if isinstance(metrics, dict):
            sec = metrics.get("sections") or {}
            if isinstance(sec, dict):
                cap2 = sec.get("caption")
                if cap2 and str(cap2).strip():
                    cap = str(cap2).strip()
    except Exception:
        pass

    # 2) If the (fallback) caption looks like a JSON blob with "sections", parse it
    if cap.startswith("{") and '"sections"' in cap:
        try:
            j = json.loads(cap)
            sec = j.get("sections") or {}
            if isinstance(sec, dict) and sec.get("caption"):
                cap = sec["caption"].strip()
        except Exception:
            pass

    # 3) Append hashtags
    if tags:
        return cap + "\n\n" + tags, tags
    return cap, tags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["post-square", "post-carousel"], help="What to publish")
    ap.add_argument("--date", default=today_in_tz().isoformat(), help="YYYY-MM-DD (defaults to GAIA_TIMEZONE today)")
    ap.add_argument("--platform", default="default", help="daily_posts.platform (default)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = dt.date.fromisoformat(args.date)
    post = sb_select_daily_post(day, platform=args.platform)
    if not post:
        logging.warning("No content.daily_posts found for day=%s platform=%s; trying latest", day, args.platform)
        post = sb_select_latest_post(platform=args.platform)
        if not post:
            logging.error("No content.daily_posts available to post (date or latest)")
            sys.exit(2)
        else:
            try:
                day = dt.date.fromisoformat(post.get("day")) if isinstance(post.get("day"), str) else day
            except Exception:
                pass

    logging.info("Post day=%s platform=%s caption[0:80]=%s", day, args.platform, (post.get("caption") or "")[:80])

    urls = default_image_urls()

    if args.cmd == "post-square":
        caption, _ = derive_caption_and_hashtags(post)
        logging.info("Derived caption (len=%d): %s", len(caption), caption[:160])
        resp_fb = fb_post_photo(urls["square"], caption, dry_run=args.dry_run)
        logging.info("FB resp: %s", resp_fb)
        # For IG, you can optionally re-post the same square as a photo post:
        # (uncomment to enable)
        ig_photo = session.post(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
            data={"image_url": urls["square"], "caption": caption, "access_token": FB_ACCESS_TOKEN},
            timeout=30
        ).json()
        if not args.dry_run and "id" in ig_photo:
            session.post(f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
                         data={"creation_id": ig_photo["id"], "access_token": FB_ACCESS_TOKEN}, timeout=30)
        return

    if args.cmd == "post-carousel":
        caption, _ = derive_caption_and_hashtags(post)  # reuse long caption/hashtags if desired
        logging.info("Derived caption (len=%d): %s", len(caption), caption[:160])
        image_urls = [urls["stats"], urls["affects"], urls["play"]]
        resp_ig = ig_post_carousel(image_urls, caption, dry_run=args.dry_run)
        logging.info("IG resp: %s", resp_ig)
        return

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Post failed")
        sys.exit(1)
