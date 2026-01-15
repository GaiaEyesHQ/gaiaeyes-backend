# Supabase

## What lives in Supabase
- **Postgres schemas**: `gaia`, `raw`, `dim`, `ext`, `marts`.
- **Auth**: Supabase JWTs validated in backend (see `SUPABASE_JWT_SECRET`).
- **Storage**: Used for media assets (space visuals), via `SUPABASE_SERVICE_ROLE_KEY` and bucket name.

## Schema management
- Schema changes live in `supabase/migrations/*.sql` and are expected to be applied via Supabase migrations.
- Supabase local config is at `supabase/config.toml`.

## RLS overview
- `gaia` tables are protected with RLS and `auth.uid()` checks (e.g., `gaia.samples`, `gaia.daily_summary`).
- Symptoms domain uses RLS on `raw.user_symptom_events` (insert/select/delete require `auth.uid() = user_id`).

## Required env vars
- `DATABASE_URL` (backend DB connection string)
- `DIRECT_URL` (optional direct Postgres fallback)
- `SUPABASE_JWT_SECRET` (backend JWT verification)
- `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (storage uploads)

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
- `marts.daily_features` — per-user daily features (health + space)
- `marts.schumann_daily` — Schumann daily aggregated series
- `marts.symptom_daily`, `marts.symptom_x_space_daily` — materialized views for symptom analytics
- `ext.enlil_forecast` + `marts.cme_arrivals` — CME simulation and arrivals
- `ext.sep_flux` — SEP proton flux
- `ext.radiation_belts` + `marts.radiation_belts_daily` — radiation belt metrics
- `ext.aurora_power` + `marts.aurora_outlook` — aurora/hemispheric power outlook
- `ext.ch_forecast` — coronal hole forecasts
- `ext.cme_scoreboard` — CME arrival scoreboard
- `ext.drap_absorption` + `marts.drap_absorption_daily` — D-RAP absorption (lat/lon grid extension)
- `ext.solar_cycle_forecast` + `marts.solar_cycle_progress` — solar cycle forecast summaries
- `ext.magnetometer_chain` + `marts.magnetometer_regional` — magnetometer chain rollups

## Storage buckets
- Bucket name defaults to `space-visuals` for visual assets and JSON payloads.
