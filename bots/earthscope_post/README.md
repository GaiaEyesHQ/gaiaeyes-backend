# Codebase overview written by Codex:
Overview
The primary backend is a FastAPI application defined in app/main.py, which wires together CORS, health checks, bearer-token auth, feature/space-weather routers, and HMAC-protected webhooks.
Authentication & middleware: /v1/* endpoints depend on require_auth, which validates a Bearer token from settings.DEV_BEARER and optionally propagates a UUID user id from X-Dev-UserId. /hooks/* routes skip bearer auth but are wrapped in WebhookSigMiddleware to enforce an x-signature HMAC using WEBHOOK_SECRET.
Ingestion: app/routers/ingest.py exposes /samples/batch, accepting either {samples:[...]} or a raw array. It validates physiological ranges, allows a dev header override for user IDs, inserts records into gaia.samples, and returns structured counts plus sampled errors instead of failing the whole batch.
Summaries: app/routers/summary.py powers the frontend cards:
/v1/features/today pulls the latest marts.daily_features, augments it with sleep-stage rollups, real-time space-weather readings, Earthscope content, and optional media URLs derived from MEDIA_BASE_URL.
/v1/space/forecast/summary cleans the latest SWPC forecast into headline/bullets.
/v1/space/series returns 30-day (clamped) series for space weather, Schumann resonance, and—when authenticated with a user id—heart rate daily metrics and 5-minute buckets.
Webhooks: /hooks/earthscope and /hooks/social accept alert and social payloads (currently stubbed with TODOs) and share the same HMAC secret for verification, complementing the middleware.
Health: /health gives a build marker and UTC timestamp, which is useful for deployments and uptime monitors.
Data access & configuration
app/db.py centralizes configuration via pydantic_settings, creating a PgBouncer-friendly AsyncConnectionPool and providing FastAPI dependencies to yield psycopg3 connections.
The service leans on domain-specific rule and constant files—gaia_rules.yaml describes alert conditions and recommended practices, while gaia_guide_constants.py captures thresholds, vocabulary, and helper utilities for EarthScope content—worth skimming to understand the product context.
Supabase configuration and migrations are organized under supabase/, reflecting how schema changes are tracked alongside code.
Background jobs & automations
Worker scripts in workers/ (e.g., aggregate.py) recompute daily summaries per user, aggregating heart rate, HRV, SpO2, blood pressure, and sleep-stage metrics, then upserting into gaia.daily_summary. Running these requires DATABASE_URL in the environment and AsyncPG access.
The bots/ directory houses specialized automation agents (Earthscope posts, magnetosphere tracking, research collectors, etc.); familiarize yourself with the relevant bot before extending it.
Key things to know on day one
Set up .env values for DATABASE_URL, DEV_BEARER, and WEBHOOK_SECRET before running the API; these control authentication and database access paths.
Authenticated requests can supply X-Dev-UserId to scope data queries, especially for personalized HR charts—vital for reproducing user-specific issues.
Webhook consumers should keep HMAC secrets in sync with the deployment environment; mismatches manifest as 401 responses from the middleware before hitting your handlers.
Next steps for deeper understanding
Run the stack locally with a sample .env, seed the database (check supabase/migrations), and explore responses from /v1/features/today and /v1/space/series to see the data model in practice.
Inspect data pipelines by reading other worker scripts (e.g., aggregate_range.py, backfill_last_7_days.py) and how they orchestrate aggregation windows across users.
Dive into domain rules via gaia_rules.yaml and gaia_guide_constants.py to understand how EarthScope messaging is generated; this informs both backend logic and bot content.
Review automation bots relevant to your focus area (e.g., bots/earthscope_post or bots/space_news_collector) to see how downstream communications consume the backend data.
Plan observability by deciding how to monitor worker runs and webhook deliveries; consider adding logging around TODO sections in api/webhooks.py once actual integrations are introduced.

# Earthscope Post Bot (LLM)

- Reads `marts.space_weather_daily` (+ optional `ext.donki_event`)
- Fetches 2–3 trending references (SolarHam, SpaceWeather, NASA, HeartMath)
- Calls OpenAI to generate rich Daily Earthscope (sections + hashtags)
- Upserts into `content.daily_posts` (idempotent)
- Dry run: set `DRY_RUN=true`

## Env
- `SUPABASE_DB_URL` (pooled, ssl)
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-4o-mini`)
- `PLATFORM` (default `instagram`)
- `USER_ID` (optional UUID; empty = global)
- (optional) `TREND_*` URLs to override default sources

### CLI helpers
- `python bots/earthscope_post/gaia_eyes_viral_bot.py --mode stats --dry-run --kp 4 --bz -6.8 --sw 650 --outdir ./out`
  renders only the stats overlay, skips git pushes/CSV writes, and pipes the JPG to `./out` for deterministic tests.
- Bz is sourced from `/v1/features/today` when `GAIA_API_BASE_URL` is set, falling back to Supabase `ext.space_weather`
  (latest row) before resorting to historic marts; negative values automatically trigger the alert color scheme.

# Gaia Eyes App

**Decode the unseen.**

Gaia Eyes is an iOS app (SwiftUI) that combines **health metrics**, **space weather**, and **Earthscope insights** into a comprehensive daily dashboard with enhanced visualizations and detailed insights.

---

## Features

### Sleep
- Displays total sleep in hours and minutes (e.g. `7h 9m total`).
- Detailed stage breakdowns including REM, Core, Deep, and In Bed times.
- Auto-sync fallback: if today’s sleep equals 0, triggers a 2-day sleep sync and refetch.

### Health Stats
- Shows Steps, Heart Rate minimum and maximum, HRV, SpO₂, and average Blood Pressure.
- Color-coded cues for quick assessment:
  - Steps ≥ 8000 → green
  - Heart Rate min ≤ 50 → blue
  - Heart Rate max ≥ 120 → red
  - HRV ≥ 80 → green
  - SpO₂ < 95% → red
  - Blood Pressure averages outside normal range → yellow/red as appropriate

### Space Weather
- Organized into clear sections with compact **StatPills** for readability:
  - Kp index: current and maximum values
  - Bz component: current and minimum values
  - Solar Wind speed: average and current
  - Flares and CMEs counts
  - Schumann resonance frequencies f0 through f4

### Earthscope
- **Card view**:
  - Uses a daily random square background image selected from `/backgrounds/square/manifest.json`.
  - Background blur set to 8 with opacity 0.45 for subtle visual effect.
  - “Read more” link is larger, bold, and spaced below content for better accessibility.
  - Thumbnails have added padding for improved breathing room.
- **Detail (Read More) view**:
  - Displays a daily random tall background from `/backgrounds/tall/manifest.json` with a fallback image `earth_space_tall.jpg`.
  - Background blur set to 2 with opacity 0.70 and a subtle vignette overlay.
  - Body text softened with rgba(220,220,235,0.88) and line height of 1.6 for comfortable reading.
  - Markdown content is converted to HTML with enhanced styling:
    - Headings: `##` → `<h2>`, `###` → `<h3>`
    - Lists:
      - Numbered (`1.`) → `<ol>`
      - Dashed (`- item`) and asterisk (`* item`) → `<ul>`
  - All hashtags are stripped from the detail view content for clarity.

### Space Alerts
- Small card displays warnings prominently when solar flares count is greater than 0 or Kp index is 5 or higher, alerting users to significant space weather events.

### Weekly Trends
- Provides graphical representations of key metrics over the past week:
  - Heart Rate timeseries with min/max and average lines
  - Kp index trends
  - Bz component trends
  - Schumann resonance frequency f0 trends
- Includes legends, counts, and indicators of improvements or declines for easy interpretation.

### Debug / Status
- The Status card has been removed from the main view for a cleaner interface.
- Now accessible under the Debug panel within a DisclosureGroup labeled "Status".
- Debug panel also contains Logs and manual sync buttons for developer use.

---

## Fonts
Custom fonts are loaded via `/fonts/` (hosted on GitHub Pages):
- AbrilFatface-Regular.ttf
- BebasNeue.ttf
- ChangaOne-Regular.ttf
- Oswald-VariableFont_wght.ttf
- **Poppins-Regular.ttf** (corrected from previous typo with extra `t` in the filename)

---

## Dev Notes
- Background images rotate daily using `manifest.json` files.
- Earthscope card backgrounds use square images; the Read More detail view uses tall images.
- Markdown parsing has been improved for better HTML conversion and styling.
- When starting a new ChatGPT conversation, include this README at the top to maintain context.

---

## Roadmap / Next
- [ ] Sync square and tall backgrounds by matching names (e.g. `aurora_square` → `aurora_tall`).
- [ ] Improve Markdown parser or migrate to server-side HTML generation for enhanced formatting.
- [ ] Add pinch-zoom functionality for the Earthscope image viewer.
- [ ] Display updated timestamps on cards to indicate data freshness.