# Scripts Guide

This guide documents the maintenance and data-processing scripts located in [`/scripts`](../scripts). Each entry summarizes the script's purpose, primary outputs, and required environment variables so you can run or automate them confidently.

## Running scripts

* All Python scripts target Python 3.10+ and assume dependencies from `requirements.txt` (notably `httpx`, `asyncpg`, and `requests`). Activate the project virtual environment before running any script.
* Invoke scripts directly with `python scripts/<name>.py`. Most scripts also include a shebang and executable bit, so you can run them via `./scripts/<name>.py` on Unix-like systems.
* Several scripts interact with Supabase. Provide the pooled Postgres connection string via `SUPABASE_DB_URL` (include `sslmode=require` and `pgbouncer=true` when available).
* Scripts that write JSON or image artifacts default to the sibling [`gaiaeyes-media`](../gaiaeyes-media) checkout. Override paths with `MEDIA_DIR` or `OUTPUT_JSON_PATH` when running locally.

## Data ingestion jobs

| Script | Purpose & Outputs | Key environment variables |
| --- | --- | --- |
| `ingest_alerts_us.py` | Pulls active severe-weather alerts from the NWS API and emits `alerts_us_latest.json`. | `MEDIA_DIR`, `OUTPUT_JSON_PATH` |
| `ingest_gdacs.py` | Parses the GDACS RSS feed for global hazard alerts and writes `gdacs_latest.json`. | `MEDIA_DIR`, `OUTPUT_JSON_PATH`, `GDACS_RSS` |
| `ingest_nasa_donki.py` | Fetches NASA DONKI flare and CME events (plus GOES flux summaries), upserts them into `ext.donki_event`, and optionally emits `flares_cmes.json`. | `SUPABASE_DB_URL`, `NASA_API_KEY` (required); `START_DAYS_AGO`, `OUTPUT_JSON_PATH`, `OUTPUT_JSON_GZIP`, retry tuning vars |
| `ingest_schumann_github.py` | Pulls Schumann resonance telemetry from the `gaiaeyes-media` GitHub repo, upserts station readings into `ext.schumann_*`, and should be followed by `psql "$SUPABASE_DB_URL" -c "refresh materialized view marts.schumann_daily"` so the daily mart stays current. | `SUPABASE_DB_URL` or `DATABASE_URL` |
| `ingest_space_news.py` | Aggregates space-weather RSS/JSON feeds (NASA, SWPC, DONKI) into a news digest JSON file. | `OUTPUT_JSON_PATH`, `MEDIA_DIR`, `LOOKBACK_DAYS`, plus DONKI API key via `NASA_API_KEY` when provided |
| `ingest_space_weather_custom.py` | Streams high-resolution Kp, solar-wind plasma, and magnetometer data into `ext.space_weather`. | `SUPABASE_DB_URL` (required); optional overrides for `KP_URL`, `SW_URL`, `MAG_URL`, `HTTP_USER_AGENT`, `SINCE_HOURS` |
| `ingest_space_weather_swpc.py` | Fetches SWPC summary feeds (Kp, speed, Bz), merges timestamps, upserts into `ext.space_weather`, and can emit a dashboard JSON snapshot. | `SUPABASE_DB_URL` (required); `SINCE_HOURS`, `OUTPUT_JSON_PATH`, `OUTPUT_JSON_GZIP`, `NEXT72_DEFAULT`, `HTTP_USER_AGENT` |
| `ingest_space_forecasts_step1.py` | Consolidated Step 1 ingestion covering Enlil CME runs, SEP/radiation belts, OVATION aurora power (`ext.aurora_power` + `marts.aurora_outlook`), coronal-hole forecasts, D-RAP text absorption (`ext.drap_absorption` + `marts.drap_absorption_daily`), SuperMAG magnetometer indices (`ext.magnetometer_chain` + `marts.magnetometer_regional`), and solar-cycle predictions. | `SUPABASE_DB_URL` (required unless `--dry-run`), `NASA_API`, `SUPERMAG_USERNAME`; optional `--days`, `--only`, `SUPERMAG_STATIONS` |
| `ingest_usgs_quakes.py` | Collects USGS day/week feeds, curates recent M5+ events, optional PostgREST upserts, and writes `quakes_latest.json`. | `MEDIA_DIR`, `OUTPUT_JSON_PATH`; optional `SUPABASE_REST_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY` |
| `ingest_usgs_history.py` | Builds historical quake trend series (daily/monthly) and emits `quakes_history.json`. | `OUTPUT_JSON_PATH`, `HISTORY_DAYS`, `HISTORY_MONTHS` |
| `space_visuals_ingest.py` | Downloads imagery for the live “Space Weather” section (SUVI, aurora, LASCO, CCOR, geospace plots), normalizes GOES X-ray/proton/electron and aurora-power telemetry, writes `space_live.json`, and upserts the latest imagery + series into `ext.space_visuals` for the `/v1/space/visuals` API. | `MEDIA_DIR`, `OUTPUT_JSON_PATH`, optional `SUPABASE_DB_URL` for idempotent upserts, plus numerous URL overrides such as `SUVI_URLS`, `LASCO_C3_URLS`, `CCOR1_MP4_NAME` |
| `tomsk_visuals_ingest.py` | Scrapes SOS70 Tomsk pages for Schumann-resonance charts, grabs the base/original image URLs, downloads them into `gaiaeyes-media/images/tomsk`, and upserts the visuals into `ext.space_visuals` so the `/v1/space/visuals` API can expose them. | `MEDIA_DIR`, `SUPABASE_DB_URL`; optional `TOMSK_VISUALS_UA`, `TOMSK_VISUALS_TIMEOUT` |
| `cumiana_visuals_ingest.py` | Downloads the latest Cumiana VLF / Schumann charts from VLF.it (direct image URLs), stores them under `gaiaeyes-media/images/cumiana`, and upserts rows into `ext.space_visuals` so `/v1/space/visuals` can surface the Cumiana overlays. | `MEDIA_DIR`, `SUPABASE_DB_URL`; optional `CUMIANA_VISUALS_UA`, `CUMIANA_VISUALS_TIMEOUT` |

## Rollups and marts

| Script | Purpose & Outputs | Key environment variables |
| --- | --- | --- |
| `rollup_space_weather_daily.py` | Aggregates `ext.space_weather` telemetry and DONKI counts into `marts.space_weather_daily`. | `SUPABASE_DB_URL`; `DAYS_BACK` |
| `rollup_health_daily.py` | Summarizes Gaia health samples into `gaia.daily_summary` using a configurable timezone. | `SUPABASE_DB_URL`; `DAYS_BACK`; `USER_TZ` |
| `rollup_daily_features.py` | Joins health summaries with space-weather and Schumann mart data into `marts.daily_features`. | `SUPABASE_DB_URL`; `DAYS_BACK` |

> **Note:** Supabase migration `20251019135900_create_marts_daily_features.sql` provisions the `marts.daily_features` mart and supporting indexes so the rollup script and dependent symptom views have a guaranteed target.
| `refresh_symptom_marts.py` | Invokes the `marts.refresh_symptom_marts()` stored procedure. | `SUPABASE_DB_URL` |

## Publishing & derived artifacts

| Script | Purpose & Outputs | Key environment variables |
| --- | --- | --- |
| `build_compare_series.py` | Combines quake and space-weather history into `compare_series.json` for overlay charts. | `MEDIA_DIR`, `OUTPUT_JSON_PATH` |
| `build_space_history.py` | Queries Supabase REST for `marts.space_weather_daily` records and emits `space_history.json`. | `SUPABASE_REST_URL`, `SUPABASE_SERVICE_KEY`/`SUPABASE_ANON_KEY`; `OUTPUT_JSON_PATH`, `HISTORY_DAYS`, `SW_DAILY_TABLE`, `SW_DAILY_FIELDS` |
| `earthscope_rules_emit.py` | Blends ingest outputs into `earthscope.json`, providing guidance strings and combined Schumann insights. | `MEDIA_DIR`, `OUTPUT_JSON_PATH` |
| `pulse_emit.py` | Produces the `pulse.json` card deck summarizing flares, CMEs, aurora outlooks, quakes, and alerts. | `MEDIA_DIR`, `OUTPUT_JSON_PATH` |
| `space_visuals_ingest.py` | (See ingestion table) feeds dashboard imagery/telemetry and now seeds `ext.space_visuals` for website + app overlays. | Same as above |

## Auditing & maintenance

| Script | Purpose & Outputs | Key environment variables |
| --- | --- | --- |
| `audit_workflows.py` | Audits GitHub Actions workflows for configured repos, reporting latest runs, failures, and secret references. | `GITHUB_TOKEN` (repo + workflow scopes) |
| `check_site_assets.py` | HEAD/GET checks third-party assets listed in `docs/web/ASSET_INVENTORY.json` and reports failures. | `inventory` CLI arg (defaults internally) |
| `scan-secrets.sh` | Greps workflow files (or supplied paths) for `${{ secrets.* }}`/`${{ vars.* }}` references using `rg`. | None (requires `rg` in PATH) |

## Scheduling notes

* Long-running ingestion jobs (DONKI, SWPC, Schumann, USGS) are designed to be idempotent and tolerate reruns; set `DAYS_BACK`/`SINCE_HOURS` conservatively when backfilling.
* Publishing scripts expect the latest ingestion JSON files in `gaiaeyes-media/data`. Run ingestors first or point `MEDIA_DIR` to a directory containing fresh source files.
* Shell out `scan-secrets.sh` as part of workflow reviews, and run `check_site_assets.py` periodically to catch stale vendor URLs.
* **Step 1 Cron** – schedule `ingest_space_forecasts_step1.py` every 30 minutes with staggered retries. Recommended flags: `--days 3` for routine operation, and `--only enlil solar` for ad-hoc backfills. Ensure Supabase write credentials are scoped to the new schemas.

> SuperMAG magnetometer data are provided courtesy of SuperMAG, Johns Hopkins University Applied Physics Laboratory. Cite their contribution on dashboards or downstream artifacts that surface the indices.

### Step 1 dataset notes

**D-RAP absorption grid** – `ingest_space_forecasts_step1.py` fetches `https://services.swpc.noaa.gov/text/drap_global_frequencies.txt`, extracts the “Product Valid At” timestamp, longitude header, and every latitude row, and flattens the lat/lon grid into `ext.drap_absorption`. Each grid cell is labeled as the `global` region with the 10 MHz carrier (or the frequency declared in the header) plus the parsed absorption dB value; the script then rolls the day’s grid into `marts.drap_absorption_daily` (max + average absorption per day/region).

**Solar-cycle predictions** – The same script ingests `https://services.swpc.noaa.gov/json/solar-cycle/predicted-solar-cycle.json`, treating each object’s `time-tag` (`YYYY-MM`) as the first day of that month for `forecast_month`. The feed’s `predicted_ssn` and `predicted_f10.7` fields populate `sunspot_number` and `f10_7_flux` respectively, with the `issued_at` column filled from `issueTime` when present (or left NULL otherwise) in both `ext.solar_cycle_forecast` and `marts.solar_cycle_progress`.

## Adding new scripts

When adding to `/scripts`:

1. Include a module docstring summarizing the script, expected outputs, and key environment variables.
2. Prefer async `httpx`/`asyncpg` clients for network and database work to keep tooling consistent.
3. Emit machine-readable JSON or database updates only after a successful run; log errors to stderr.
4. Update this guide so teammates know how to operate the new script.

