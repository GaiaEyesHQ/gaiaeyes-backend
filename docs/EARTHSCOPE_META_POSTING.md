# EarthScope Meta Posting

This document covers the EarthScope Facebook/Instagram publishing path used by
`.github/workflows/gaia_eyes_daily.yml` and `bots/earthscope_post/meta_poster.py`.

## Flow overview

### Image flow
1. `generate` writes the latest `content.daily_posts` row in Supabase.
2. `render` builds the EarthScope cards and uploads them to Supabase public
   storage under `/storage/v1/object/public/space-visuals/social/earthscope/latest/`.
3. `post` waits for propagation, mirrors `default` content to `ig` when needed,
   then calls `python bots/earthscope_post/meta_poster.py post-carousel ...` for:
   - Facebook multi-image feed publish
   - Instagram carousel publish

### Reel flow
1. `reel` stages the latest cards from Supabase public storage.
2. `reel_builder.py` builds `reel.mp4`.
3. The workflow validates the local MP4 with `ffprobe`, uploads it to Supabase
   public storage under `/storage/v1/object/public/space-visuals/social/earthscope/reels/latest/latest.mp4`,
   then calls `meta_poster.py post-reel` for:
   - Instagram reel publish
   - Facebook video publish

## What changed

The posting path now uses one shared Meta poster implementation instead of split
logic between Python and inline workflow `curl`.

### Hardening added
- Media URL preflight before every Meta publish call.
- Shared Graph API retry logic for transient Meta failures.
- Shared IG container polling with a longer processing window and clearer states.
- Reel container recreation when Meta moves a reel container from
  `IN_PROGRESS` to `ERROR`.
- Carousel child retry with pacing between child container creates.
- Explicit carousel fallback to single-image IG publish when configured.
- Structured result logging for every FB/IG publish attempt.
- Workflow summaries for partial-success cases instead of silent degradation.

## Current Meta assumptions

The workflow and poster now use a single Graph API version via `META_GRAPH_VERSION`
and default to `v24.0`.

The current implementation assumes:
- Instagram reels use `POST /<IG_USER_ID>/media` with `media_type=REELS` and
  `video_url=<PUBLIC_MP4_URL>`, then poll the returned container until
  `status_code=FINISHED`, then call `POST /<IG_USER_ID>/media_publish`.
- Instagram carousel children are still created through `POST /<IG_USER_ID>/media`
  with `image_url` and `is_carousel_item=true`.
- Instagram carousel parent containers are still created through
  `POST /<IG_USER_ID>/media` with `media_type=CAROUSEL` and `children=...`.
- Facebook reels/videos are still posted through `POST /<FB_PAGE_ID>/videos`
  with `file_url=<PUBLIC_MP4_URL>`.

## Retry and fallback policy

### Retries
The poster retries requests that are plausibly transient:
- HTTP `429`
- HTTP `500`, `502`, `503`, `504`
- Graph `OAuthException` responses with `is_transient=true`
- Graph error code `2`

Retries use exponential backoff with jitter.

### IG poll behavior
- Polling requests ask for `id,status_code,status`.
- `FINISHED` means publish-ready.
- `ERROR` and `EXPIRED` are treated as terminal for that container.
- Reels can recreate a fresh container after a terminal poll result, up to
  `IG_REEL_CREATE_CYCLES`.
- Timeout is controlled by `META_POLL_TIMEOUT_SEC`.
- Defaults are tuned to a 5-minute window with slower backoff than the old
  workflow so IG gets more processing time without hammering `status_code`.

### Fallbacks
- If Instagram carousel child creation fails after retries and
  `IG_CAROUSEL_SINGLE_IMAGE_FALLBACK=true`, the pipeline falls back to posting the
  first image as a single IG post.
- The GitHub Actions workflow allows one platform to fail while the other
  succeeds, writes the partial result to `GITHUB_STEP_SUMMARY`, and only fails
  the job when both platforms fail.

## Media validation

### Remote URL preflight
Before sending any image or video URL to Meta, `meta_poster.py` checks:
- public reachability (`HEAD`, then `GET` fallback when needed)
- HTTP `200`/`206`
- JPEG content type for images, MP4/QuickTime for reels
- content length when provided

### Local reel validation
Before reel upload, the workflow validates the built MP4 with `ffprobe` and
requires:
- at least one video stream
- at least one audio stream
- duration of at least 3 seconds
- non-zero file size

## Logging

The poster logs:
- Graph API version
- final media URL(s), sanitized to drop query strings
- media preflight status, content type, and size
- create container responses
- every IG poll payload
- retry attempts and backoff timing
- fallback decisions
- final publish response payloads

Secrets are masked in structured request logging.

## Environment

### Required secrets
- `FB_ACCESS_TOKEN`
- `FB_PAGE_ID`
- `IG_USER_ID`
- `SUPABASE_URL`
- `SUPABASE_REST_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

### Optional tuning envs
- `META_GRAPH_VERSION` (default `v24.0`)
- `META_CREATE_RETRY_ATTEMPTS`
- `META_PUBLISH_RETRY_ATTEMPTS`
- `META_POLL_TIMEOUT_SEC`
- `META_POLL_INTERVAL_SEC`
- `META_POLL_MAX_INTERVAL_SEC`
- `IG_CAROUSEL_CHILD_PACING_SEC`
- `IG_CAROUSEL_SINGLE_IMAGE_FALLBACK`
- `IG_REEL_CREATE_CYCLES`
- `META_PUBLISH_RETRY_TRANSPORT_ERRORS`

## Safe rerun guidance

When rerunning after a transient Meta failure:
- Review the prior run summary to see which platform already succeeded.
- Prefer rerunning the workflow only after the media URLs are reachable and the
  render/upload stages succeeded.
- Avoid adding blind publish retries around `media_publish`; the shared poster
  retries only explicit transient response classes and does not treat every
  ambiguous transport failure as safe to replay.

## Where to look first in logs

- Workflow: `.github/workflows/gaia_eyes_daily.yml`
- Poster: `bots/earthscope_post/meta_poster.py`
- Reel build: `bots/earthscope_post/reel_builder.py`
- Reel artifact validation: `Validate reel artifact (ffprobe)`
- Partial-success summary: `Evaluate EarthScope image post outcomes` and
  `Evaluate EarthScope reel post outcomes`
