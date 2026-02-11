# Supabase

## What lives in Supabase
- **Postgres schemas**: `gaia`, `raw`, `dim`, `ext`, `marts`.
- **Auth**: Supabase JWTs validated in backend (see `SUPABASE_JWT_SECRET`).
- **Storage**: Used for media assets (space visuals), via `SUPABASE_SERVICE_ROLE_KEY` and bucket name.
- **Subscriptions (public tables)**: Stripe/RevenueCat linkage and entitlements mapping (`public.app_stripe_customers`, `public.app_user_entitlements`, `public.app_price_map`).

## Schema management
- Schema changes live in `supabase/migrations/*.sql` and are expected to be applied via Supabase migrations.
- Supabase local config is at `supabase/config.toml`.

## RLS overview
- `gaia` tables are protected with RLS and `auth.uid()` checks (e.g., `gaia.samples`, `gaia.daily_summary`).
- Symptoms domain uses RLS on `raw.user_symptom_events` (insert/select/delete require `auth.uid() = user_id`).

## Required env vars
- `SUPABASE_DB_URL` (preferred Postgres connection string for server/bots; falls back to `DATABASE_URL` if unset)
- `DATABASE_URL` (backend DB connection string)
- `DIRECT_URL` (optional direct Postgres fallback)
- `SUPABASE_JWT_SECRET` (backend JWT verification)
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (storage uploads & server-side REST)
- `SUPABASE_REST_URL` (explicit REST base; used by WP and bots)

## Local dev
- This repo includes `supabase/config.toml` for local Supabase CLI usage.
- If you use the Supabase CLI, run migrations from `supabase/migrations` to build the local schema.

## Schema summary (from migrations)
### `gaia` schema
- `gaia.users` — user records (uuid + email)
- `gaia.devices` — registered devices per user
- `gaia.samples` — raw sensor samples (HealthKit/BLE)
- `gaia.sessions` — session summaries (e.g., BLE)
- `gaia.daily_summary` — aggregated daily health metrics per user

### `dim` + `raw` schemas (symptoms)
- `dim.symptom_codes` — allowed symptom codes used by the client
- `raw.user_symptom_events` — user symptom event log (with RLS)

### `ext` + `marts` schemas (space/earth)
- `ext.magnetosphere_pulse` — magnetosphere time-series feed
- `marts.magnetosphere_last_24h` — view for last 24h magnetosphere data
- `marts.space_weather_daily` — unified daily snapshot (kp_max/bz_min/sw_speed_avg + *now* fields and derived metrics)
- `marts.daily_features` — per-user daily features (health + space)
- `marts.schumann_daily` — Schumann daily aggregated series
- `marts.symptom_daily`, `marts.symptom_x_space_daily` — materialized views for symptom analytics
- `ext.space_forecast` — SWPC bulletins (3‑day forecast, weekly, discussion, advisory)
- `ext.enlil_forecast` + `marts.cme_arrivals` — CME simulation and arrivals
- `ext.sep_flux` — SEP proton flux
- `ext.radiation_belts` + `marts.radiation_belts_daily` — radiation belt metrics
- `ext.aurora_power` + `marts.aurora_outlook` — aurora/hemispheric power outlook
- `ext.drap_absorption` + `marts.drap_absorption_daily` — D‑RAP absorption (global & regional rollups)
- `ext.ch_forecast` — coronal hole forecasts
- `ext.cme_scoreboard` — CME arrival scoreboard
- `ext.gdacs_alerts` + `ext.global_hazards` — GDACS RSS events (floods, storms, quakes, fires, drought, volcano, etc.)
- `ext.drap_absorption` + `marts.drap_absorption_daily` — D-RAP absorption (lat/lon grid extension)
- `ext.solar_cycle_forecast` + `marts.solar_cycle_progress` — solar cycle forecast summaries
- `ext.magnetometer_chain` + `marts.magnetometer_regional` — magnetometer chain rollups
- `ext.zip_centroids` + `ext.local_signals_cache` — local weather/AQI snapshot cache keyed by ZIP (feeds Local Health Check)

### public schema (subscriptions)
- `public.app_stripe_customers` — Stripe customer ↔ user_id mapping (service‑role writes)
- `public.app_user_entitlements` — normalized entitlements (key/term/source, is_active); RLS grants users read of their own rows
- `public.app_price_map` — product/price → entitlement mapping (admin/service‑role managed)

## Maintenance functions (batch/cron)
- `marts.refresh_space_weather_daily(p_start date, p_end date)` — aggregates daily maxima/minima
- `marts.refresh_space_weather_now(p_start date, p_end date)` — stamps latest KP/Bz/SW *now* values
- `marts.refresh_space_weather_aurora(p_start date, p_end date)` — rolls hemispheric power (GW) into daily table
- `marts.refresh_space_weather_cme_ed(p_start date, p_end date)` — counts Earth‑directed CME arrivals (from `ext.cme_scoreboard`)

## Storage buckets
- `space-visuals` — visual assets and social media renders (e.g., `social/earthscope/latest/daily_stats.jpg`)
- (Optional) other buckets as configured for app assets; public paths are served via Supabase Storage public URLs
