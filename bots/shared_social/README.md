# Multi-brand social publishing (isolated development)

This directory is the starting point for a brand-aware Meta publisher. The existing Gaia Eyes production workflow and `bots/earthscope_post/meta_poster.py` remain unchanged.

## Brand isolation
- `GAIA_EYES_FB_PAGE_ID`, `GAIA_EYES_IG_USER_ID`, `GAIA_EYES_FB_ACCESS_TOKEN`
- `MOD_PANIC_FB_PAGE_ID`, `MOD_PANIC_IG_USER_ID`, `MOD_PANIC_FB_ACCESS_TOKEN`

These are **proposed new names**; existing production `FB_PAGE_ID`, `IG_USER_ID`, and `FB_ACCESS_TOKEN` are untouched. Add secrets only after the appropriate Page and Instagram account permissions are verified. Never copy Gaia Eyes Page tokens into Mod Panic settings.

## Implementation sequence
1. Extract the Graph API transport, media validation, and publish logic from the EarthScope poster into this shared package, preserving behavior and tests.
2. Make brand/account context explicit at every publish call; avoid mutable process-global credentials.
3. Introduce a Mod Panic product-to-social adapter reading approved Shopify product imagery and captions. Keep Gaia Eyes' Supabase daily content adapter separate.
4. Add an approval queue, per-brand deduplication keys, dry-run previews, and independent publishing logs.
5. Add a separate, initially manual-only Mod Panic GitHub Actions workflow with distinct secrets.
6. Validate Facebook and Instagram credentials with read-only calls, test previews, then obtain explicit approval for the first live posts.
7. Migrate Gaia Eyes to the shared transport only after regression tests; do not change the live workflow until then.

## Safety
No scheduled Mod Panic posts are enabled. This branch does not publish anything or alter Gaia Eyes deployment.
