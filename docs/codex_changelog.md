# Codex Change Log

Document noteworthy backend/front-end changes implemented via Codex tasks. Keep the newest entries at the top.

## 2025-12-02 — Pause Tomsk ingestion and fix aurora timestamps

- Disabled `scripts/tomsk_visuals_ingest.py` by default so we stop pulling placeholder
  SOS70 assets. Set `TOMSK_VISUALS_ENABLED=1` only after explicit permission to ingest
  is received.
- Hardened `_parse_timestamp` in `scripts/space_visuals_ingest.py` to attach UTC to
  timezone-less aurora forecast timestamps (e.g., `2024-11-16 04:20:00`) so ingestion
  no longer crashes when the feed omits a trailing `Z`.

## 2025-12-01 — Tomsk ingestion now reads SOS70 provider directory

- Extended `scripts/tomsk_visuals_ingest.py` so it scrapes the SOS70 `provider.php`
  listing, downloads the canonical `shm/srf/sra/srq` chart images directly, and skips
  known placeholder/site-icon assets before falling back to the WordPress media API or
  HTML parsing. The ingest now writes deterministic keys for the provider-backed rows
  to keep `/v1/space/visuals` stocked with the real Tomsk charts.
- Added provider-specific regression tests plus doc updates in `docs/SCRIPTS_GUIDE.md`.
  Run `python scripts/tomsk_visuals_ingest.py` (with `SUPABASE_DB_URL`/`MEDIA_DIR`
  exported) so Supabase refreshes the `tomsk_*` rows with the direct provider assets.

## 2025-11-30 — Tomsk scraper now fetches real media assets

- Updated `scripts/tomsk_visuals_ingest.py` to call the SOS70 WordPress media API when a
  `page_id` is available (falling back to HTML parsing otherwise) and to prefer the raw
  image URLs before any normalization. This ensures we ingest the actual Schumann charts
  instead of placeholder icons when Supabase rows are refreshed.
- Added regression tests covering the new API helper + URL ordering, refreshed
  `docs/SCRIPTS_GUIDE.md`, and noted that operators should rerun the Tomsk ingestion so
  `/v1/space/visuals` exposes the corrected imagery set.

## 2025-11-29 — Tomsk scraper now pulls embedded image URLs

- Updated `scripts/tomsk_visuals_ingest.py` so it parses inline `style="background-image:url(...)"`
  attributes and any other embedded `jpg/png` references within the SOS70 pages, ensuring
  the script follows the nested image URLs rather than attempting to ingest the HTML pages
  themselves. Added regression tests that cover the background-image and inline-script
  parsing helpers.
- Operators should rerun `python scripts/tomsk_visuals_ingest.py` after exporting
  `SUPABASE_DB_URL`/`MEDIA_DIR` to refresh Supabase rows with the corrected Tomsk imagery
  metadata before wiring the overlays into WordPress/iOS.

## 2025-11-28 — Fix OVATION aurora feed source

- Updated `scripts/space_visuals_ingest.py` to pull hemispheric power samples from
  `https://services.swpc.noaa.gov/json/ovation_aurora_latest.json` (the currently
  maintained NOAA endpoint) so aurora telemetry ingestion resumes without 404s.
- No front-end behavior changed, but Step 2 operators should re-run the ingestion
  script so Supabase receives fresh aurora power series from the corrected feed.

## 2025-11-27 — Cumiana VLF visuals ingestion

- Added `scripts/cumiana_visuals_ingest.py`, which downloads the latest Cumiana VLF / Schumann charts from VLF.it, caches them under `gaiaeyes-media/images/cumiana`, and upserts the imagery into `ext.space_visuals` so `/v1/space/visuals` (and downstream WordPress/iOS overlays) can surface the new sources alongside NASA + Tomsk feeds.
- Documented the script, its environment knobs, and expected destinations inside `docs/SCRIPTS_GUIDE.md`, keeping the Step 2 ingestion docs aligned with the growing imagery set.

## 2025-11-26 — Tomsk SOS70 visuals ingestion

- Added `scripts/tomsk_visuals_ingest.py`, which scrapes the requested SOS70 pages, normalizes the base/original image URLs, downloads the visuals into `gaiaeyes-media/images/tomsk`, and upserts them into `ext.space_visuals` so the `/v1/space/visuals` API (and WordPress/iOS overlays) can surface the Tomsk charts alongside the NASA imagery.
- Documented the new script + environment knobs inside `docs/SCRIPTS_GUIDE.md` so operators know how to run it and which env vars (`MEDIA_DIR`, `SUPABASE_DB_URL`, `TOMSK_VISUALS_*`) to supply.

## 2025-11-26 — Interactive NASA overlays & `/v1/space/visuals`

- Extended `scripts/space_visuals_ingest.py` to normalize GOES X-ray/proton/electron and aurora hemispheric-power samples, emit the enriched series inside `space_live.json`, and upsert imagery + telemetry rows into `ext.space_visuals` (backed by a new migration adding metadata/series columns and an updated-at trigger).
- Added the `/v1/space/visuals` FastAPI router plus regression tests so WordPress/iOS clients can request synchronized imagery, time-series samples, and overlay feature flags with cached CDN URLs.
- Refreshed `wp-content/mu-plugins/gaiaeyes-space-visuals.php` to call the new API (with bearer support), render Chart.js overlays on solar-disc and aurora imagery, and rely on structured telemetry before falling back to NOAA JSON.
- Documented the ingestion + overlay flow (`docs/SCRIPTS_GUIDE.md`, `docs/web/SITE_OVERVIEW.md`) so future operators know about the Supabase requirement and shortcode behavior; captured the change here per instructions.
- Patched the Supabase ingestion helper to wrap `meta`, `series`, and `feature_flags` payloads in proper JSON adapters before `executemany` so psycopg can persist the overlay data without `can't adapt type 'dict'` errors when `SUPABASE_DB_URL` is configured.

## 2025-11-25 — DRAP grid parsing + solar-cycle mapping

- Updated `scripts/ingest_space_forecasts_step1.py` so the D-RAP text product is parsed
  as a latitude/longitude grid with flattened rows stored in `ext.drap_absorption`
  and corresponding daily rollups in `marts.drap_absorption_daily`.
- Corrected the solar-cycle ingest to map `time-tag` to first-of-month dates and to
  read the `predicted_ssn` and `predicted_f10.7` fields from the live SWPC JSON feed,
  ensuring rows land consistently in `ext.solar_cycle_forecast` and `marts.solar_cycle_progress`.
- Documented the new parsing behavior in `docs/SCRIPTS_GUIDE.md`.

## 2025-11-24 — Fix initial symptom mart refresh

- Updated `20251019140000_setup_symptom_domain.sql` to run the first `symptom_daily` and
  `symptom_x_space_daily` refreshes without the `CONCURRENTLY` clause so Supabase can
  populate the newly created materialized views before enabling concurrent refreshes.
- Keeps subsequent refresh jobs (including the helper function) untouched, since once
  populated the views support `CONCURRENTLY` as before.

## 2025-11-23 — Restore daily_features mart dependency

- Added an idempotent Supabase migration (`20251019135900_create_marts_daily_features.sql`) that materializes
  `marts.daily_features` with the health, space-weather, and Schumann columns required by the symptom analytics
  views, guaranteeing the mart exists before `marts.symptom_x_space_daily` is created during deploys.
- Documented the migration in the scripts guide so future operators know the mart is provisioned automatically.

## 2025-11-22 — Backfill Schumann mart dependency

- Added an idempotent Supabase migration that defines the `ext.schumann_*` landing tables and the `marts.schumann_daily`
  materialized view so downstream analytics (e.g., `marts.symptom_x_space_daily`) can rely on the relation existing during
  deploys.
- Documented the required `marts.schumann_daily` refresh step alongside the Schumann ingestion script for ongoing operations.

## 2025-11-21 — Step 1 ingestion follow-ups

- Updated the Step 1 ingestion pipeline so the CME arrival and D-RAP upserts use the actual Supabase primary-key constraints,
  preventing runtime failures caused by generated columns in the conflict targets.
- Backfilled the missing `ext.magnetosphere_pulse` table inside the legacy magnetosphere migration so the dependent
  `marts.magnetosphere_last_24h` view can be created successfully during Supabase deploys.

## 2025-11-20 — Step 1 predictive datasets & outlook API

- Delivered the Step 1 ingestion orchestrator (`ingest_space_forecasts_step1.py`) covering Enlil CME runs, SEP/radiation belts, aurora power, coronal holes, D-RAP, solar-cycle forecasts, and magnetometer indices with Supabase upserts.
- Added Supabase schema migrations for the new `ext.*` landing tables and `marts.*` rollups (CME arrivals, radiation belts, aurora outlook, D-RAP, solar cycle, regional magnetometers).
- Exposed `/v1/space/forecast/outlook` so clients can query consolidated predictive datasets alongside the existing forecast summary card.
- Documented cron guidance and dataset details inside `docs/SCRIPTS_GUIDE.md`.

## 2025-11-17 — iOS/Backend Operational Stabilization and Sync Fixes

- Restored full functionality of the iOS dashboard and backend data pipeline after repeated DB timeout and user scoping issues.
- Corrected developer token handling and ensured `X-Dev-UserId` is always included in app API requests, resolving the `branch: "anonymous"` diagnostics.
- Moved the backend connection from pgBouncer (port 6543) to the direct Postgres pooler (port 5432) for stable connectivity and to eliminate `PoolTimeout` and `Tenant not found` errors.
- Validated the fallback logic for `/v1/features/today` and `/v1/samples/batch`, confirming live mart refresh and scoped responses.
- Fixed snake_case encoding for Symptom POSTs (`symptom_code`, `free_text`, etc.), resolving 422 validation errors and ensuring user events upload successfully.
- Resolved frontend hangs by reducing redundant refresh loops and improving async background scheduling.
- Verified database health monitor stability (`db:true`, sticky age > 5min) and consistent scoped responses.
- Outstanding work: add sleep/spO₂ integration tests to verify missing metrics in `marts.daily_features` are populating as expected.

## 2025-11-16 — Health-monitored failover and safe refresh scheduling

- Introduced a background database health monitor with hysteresis so `/health`
  and downstream routes stop flapping during transient outages while still
  surfacing `db:false` after two consecutive probe failures.
- Hardened the async pool by automatically failing over to the configured
  `DIRECT_URL` after repeated `PoolTimeout` errors, logging the backend switch
  so operators can confirm when the service is pinned to direct Postgres.
- Gated `/v1/samples/batch` on the monitor’s status, added a single delayed
  mart refresh (2s delay, ≥20s debounce per user) after successful inserts, and
  documented the new diagnostics exposed by `/v1/features/today` and
  `/v1/diag/db`.

## 2025-11-15 — Reuse resilient DB dependency for features

- Updated the `/v1/features/today` connection helper to reuse the shared
  `get_db` dependency so the endpoint now benefits from the same retry and
  failover logic as the rest of the API.
- Ensure the helper forwards normal and exceptional exit back to `get_db`
  so connections are returned to the pool instead of leaking after a
  successful request or handled failure.
- Eliminated ad-hoc pool acquisition that was surfacing repeated
  `pool_timeout` diagnostics and forcing the app to serve cached data even
  while ingestion succeeded.
- No front-end changes are required; the fix keeps diagnostics consistent
  while restoring live snapshots once a connection becomes available.

## 2025-11-14 — Harden `/db/ping` failover handling

- Taught the `GET /db/ping` endpoint to retry connection attempts while invoking the
  same failover helpers used by `/v1/features/today`. The ping now promotes the direct
  Postgres fallback when pgBouncer stalls instead of returning `db:false` forever.
- Added defensive retry logging and distinct `db_timeout` errors so operations can see
  whether the failure was due to pool exhaustion or a deeper connectivity issue.
- No front-end changes are required; the mobile client will automatically resume
  refreshes once the ping reports `db:true`.

## 2025-11-13 — Add database connectivity diagnostics helper

- Added a `scripts/db_diagnose.py` utility that pings both the configured
  pgBouncer endpoint and the direct fallback, mirroring the service's failover
  logic so operators can confirm connectivity before restarting workloads.
- Exposed the pool configuration and probe helpers inside `app.db` for reuse,
  letting the script (and future tooling) share a single source of truth for
  connection targets and latency measurements.
- Documented the new troubleshooting flow in `docs/OPERATIONS.md` so on-call
  engineers know how to verify database health before relying on cache
  fallbacks.

## 2025-11-12 — Allow extending last-good feature cache TTL

- Introduced a `FEATURES_CACHE_TTL_SECONDS` setting so operations can retain
  `/v1/features/today` snapshots for outages lasting longer than the previous
  six-hour ceiling.
- The cache layer now validates and logs the override at startup, keeping
  negative/invalid values harmless while calling out the active TTL in logs.
- Updated the operational notes below so oncall engineers know how to keep the
  feature tiles populated during prolonged database disruptions.

## 2025-11-10 — Document anonymous diagnostic troubleshooting

- Added a troubleshooting note to `docs/DIAG_FEATURES.md` explaining how to interpret
  `branch: "anonymous"` / `source: "empty"` diagnostics and pointing developers to the
  required `X-Dev-UserId` header when using the developer bearer token. This prevents
  confusing "empty" feature payloads when the app fails to scope requests to a user id.

## 2025-11-09 — Trace features fallbacks and cache state

- Added a timestamped `diagnostics.trace` log to `/v1/features/today` so engineers can copy
  the execution path (mart lookups, cache fallbacks, refresh scheduling) from the mobile
  debug console without relying on screenshots.
- Surface lightweight `cache_snapshot_initial`, `cache_snapshot_final`, and
  `payload_summary` blocks that call out which sections (health, sleep, space weather,
  Schumann, posts) contained non-null data before and after the request.
- Flag when the last-good cache is rewritten via `diagnostics.cache_updated` and update the
  feature docs to explain the new fields.

## 2025-11-08 — Rehydrate empty feature payloads from cache

- When the mart returns an empty snapshot but the last-good cache still holds data,
  `/v1/features/today` now reuses that cached payload so the health, sleep, and space
  weather tiles keep showing the latest known values instead of resetting to zeros.
- Surface the new `diagnostics.cache_rehydrated` flag so operators can tell when the
  handler coalesced an empty DB response with cached data.
- Ensure the background refresh scheduler always targets the current local day after a
  cache rehydration so a stale snapshot cannot lock refreshes onto yesterday.
- Documented the behavior update in `docs/FEATURES_ROUTE.md` and `docs/DIAG_FEATURES.md`.
  No front-end changes are required beyond optionally reading the new diagnostic flag.

## 2025-11-07 — Cache diagnostics and scheduled refreshes for features

- Track cached snapshot age inside `/v1/features/today` diagnostics so clients can see
  exactly when the last-good payload was recorded.
- Force a mart refresh whenever the cached data is older than 15 minutes and otherwise
  throttle background refresh scheduling to once every five minutes per user.
- Document the new diagnostics fields and refresh cadence in `docs/FEATURES_ROUTE.md`
  and `docs/DIAG_FEATURES.md`. No front-end changes are required beyond optionally
  reading the new diagnostic flags.

## 2024-04-17 — Fix fallback activation regression

- Restore the global bookkeeping inside the async pool failover helper so Python
  no longer treats `_pool_active_label` as a local variable. The regression was
  preventing the watchdog, `/health`, and feature handlers from switching to the
  configured fallback backend after connection failures, leaving the service
  stuck in cache-only mode with `db:false` responses.
- Ensure the primary `open_pool` helper also updates the shared `_pool`
  reference when the fallback opens during startup retries so future
  acquisitions use the replacement pool.
- Documented the fix here; diagnostics and response envelopes are unchanged, so
  no mobile/front-end updates are required.

## 2024-04-16 — Fail over when pgBouncer stalls

- Treat `PoolTimeout` events during connection acquisition as connectivity failures and
  automatically switch the async pool to the direct Postgres fallback so the backend
  recovers instead of staying in cache-only mode when pgBouncer is saturated or stops
  accepting connections.
- Allow the `/health` probe, feature handler, and ingestion pipeline to request the
  fallback proactively so mobile clients stop seeing repeated `db:false` responses and
  ingestion resumes without manual intervention after a stall.
- Document the new behavior in `docs/OPERATIONS.md`. No front-end changes are required
  because diagnostics already surface `cache_fallback` and `pool_timeout` for awareness.

## 2024-04-15 — Auto-failover after pgBouncer disconnects

- Detect connection-level failures ("server closed the connection unexpectedly", etc.)
  and automatically swap the async pool to the configured direct Postgres fallback so
  repeated pgBouncer outages no longer exhaust the pool or leave the service in cache-only mode.
- Extend the watchdog probe to trigger the same failover logic and centralize pool creation
  helpers so both startup and runtime recovery paths reuse the hardened configuration.
- Documented the behavior updates in `docs/OPERATIONS.md`. No front-end changes are needed
  because the `/health` envelope and diagnostics contracts remain unchanged.

## 2024-04-14 — Stabilize health checks and cache fallbacks

- Replaced the `/health` probe's `asyncio.wait_for` wrapper with a pool-scoped timeout so
  pgBouncer handshakes no longer get cancelled mid-flight, eliminating the false
  `db:false` responses that were putting the mobile app into cache-only mode while the
  database remained healthy.
- Extended the sticky grace window and surfaced `db_latency_ms` in the health response so
  operators can see the most recent probe latency and avoid flapping during transient
  slowdowns.
- Documented the revised health contract in `docs/OPERATIONS.md`; the existing mobile
  client can consume the new metadata without changes.

## 2024-04-13 — Clamp feature enrichment timeouts

- Wrapped the feature mart lookups and enrichment queries in short asyncio timeouts so
  `/v1/features/today` fails over to cached data instead of stalling clients when the
  database hangs. Diagnostics now record the timed-out components so engineers can see
  which feeds were skipped.
- Reused the freshened context for enrichment to avoid redundant queries and added
  guardrails that fall back to cached or snapshot payloads after timeout events.
- Documented the new `enrichment_errors` diagnostics field for mobile teams reviewing
  `/v1/features/today` responses.
- Ensured the database pool no longer infers pgBouncer mode purely from the port so
  explicit `pgbouncer` flags remain the only trigger for that backend selection.

## 2024-04-12 — Stop fabricating direct DB fallbacks

- Roll back the inferred port-5432 fallback: when pgBouncer is unreachable we now only
  switch to a direct connection if `DIRECT_URL` (or an explicit alternate DSN) is
  configured. This avoids hanging connection attempts to hosts that do not expose the
  primary Postgres port.
- Explicitly require `DIRECT_URL` to be set before wiring any fallback so pgBouncer
  connection strings without explicit ports no longer trigger a fabricated direct DSN.
- Added regression coverage ensuring pgBouncer mode skips the fallback when `DIRECT_URL`
  is missing, while still honoring an explicit direct connection when provided.

## 2024-04-11 — Harden database connectivity and symptom fallbacks

- Update the async pool bootstrapper to respect the original `DATABASE_URL` port, only switch to pgBouncer when explicitly
  requested, and automatically fall back to a direct connection when the pgBouncer endpoint is unreachable. Diagnostics now
  expose the active backend and whether a fallback is available so the mobile client can make informed refresh decisions.
- Keep optional direct connection strings sanitized and reusable, ensuring refresh tasks and cache warmers share a single,
  self-healing pool configuration without fighting the front end.
- Fix the symptom tracker endpoints to capture the raised exception objects so error envelopes remain populated instead of
  crashing with `NameError`, restoring friendly errors in the iOS debug console.

## 2024-04-10 — Restore raw symptom errors with friendly fallbacks

- Bring back the database-provided error strings in the `error` field so existing
  clients stop looping during backend outages.
- Add a `friendly_error` companion field that carries the documented message for
  analytics/localization while keeping the envelope stable.
- Updated the Symptoms API docs and regression tests to cover the dual-error
  contract. No front-end work is required.

## 2024-04-09 — Stabilize symptom error envelopes

- Replace raw database exception messages across the symptom API with documented, user-facing strings so the mobile client receives consistent fallback payloads.
- Expand the symptom normalization regression tests to assert the safe errors for both read and write failures.
- No front-end updates required because the iOS app already expects the documented strings in `/docs/symptoms_api.md`.

## 2024-04-08 — Persist fallback errors without tripping the UI

- Added `diagnostics.last_error` and now clear `diagnostics.error` whenever cached/yesterday data is served successfully so existing clients stop treating fallbacks as hard failures.
- Updated the `/v1/features/today` docs and iOS follow-up checklist to consume the new field while keeping banners/debug copy informative.
- Extended the regression suite to lock in the adjusted diagnostics contract.

## 2024-04-07 — Cache fallback diagnostics

- Flag mart query failures as cache fallbacks so mobile clients throttle refreshes while still showing cached tiles.
- Ensure the diagnostics payload carries the triggering error (and pool timeout flag when relevant) when cached data is returned.
- Document the updated behavior for the iOS Codex assignee.

## 2024-04-06 — Cache fallback envelope tweaks

- Updated `/v1/features/today` to always return a populated data block (with defaults when necessary) while surfacing outage causes via `diagnostics.error`, preventing the iOS dashboard from entering a refresh loop during database timeouts.
- Added regression coverage ensuring error paths fall back to the cached snapshot and remain `ok:true`.
- Refreshed the iOS follow-up notes to call out that `ok` stays true during cache usage so the app must read the diagnostics flags.

## 2024-04-05 — Features endpoint cache hardening

- Guarded `/v1/features/today` against pgBouncer pool exhaustion by attempting a manual connection acquisition and falling back to the last-good cache snapshot when the pool is saturated.
- Extended diagnostics with `cache_fallback`, `pool_timeout`, and `error` markers so client teams can detect when cached data was served.
- Added automated tests covering the new cache fallback branch and updated docs describing the behavior.
