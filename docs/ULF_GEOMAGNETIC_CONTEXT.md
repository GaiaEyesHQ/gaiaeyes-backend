# ULF Geomagnetic Context

This phase adds a lightweight backend-only ULF context layer derived from USGS 60-second geomagnetic observatory data.

## Scope

- Source:
  - USGS Geomagnetism Data Web Service (`BOU`, `CMO` in v1)
- Cadence:
  - fetch trailing 180 minutes every 5 minutes
  - derive 5-minute rows only
- Storage:
  - `marts.ulf_activity_5m`
  - `marts.ulf_context_5m`
- No raw 1-second storage
- No standalone UI surface in this phase

## Derived Fields

### `marts.ulf_activity_5m`
- Grain:
  - one row per station and 5-minute bucket start
- Core metrics:
  - `dbdt_rms`: RMS of first-difference `dB/dt` from minute samples
  - `ulf_rms_broad`: v1 broad intensity alias of `dbdt_rms`
  - `ulf_band_proxy`: minute-resolution low-frequency proxy
- Normalization:
  - `ulf_index_station`: rolling 7-day percentile of station `dbdt_rms`
  - `ulf_index_localtime`: reserved for optional hour-bucket normalization; usually `NULL` in v1
- Persistence:
  - `persistence_30m`
  - `persistence_90m`
- Quality:
  - `fallback_component`
  - `missing_samples`
  - `low_history`

### `marts.ulf_context_5m`
- Grain:
  - one row per 5-minute timestamp
- Core metrics:
  - `regional_intensity`: mean available station `ulf_index_station`
  - `regional_coherence`: cross-station agreement from aligned derivative traces, with index-similarity fallback
  - `regional_persistence`: mean station persistence
- Classification:
  - `Quiet`
  - `Active (diffuse)`
  - `Elevated (coherent)`
  - `Strong (coherent)`
- Confidence:
  - weighted by station count, coherence, and quality flags

## Important Limits

- `ulf_band_proxy` is a minute-resolution proxy.
- It is not labeled or surfaced as true Pc5 spectral power.
- The signal is observational Earth-context only and is not a medical or symptom-causality claim.

## API

- `GET /v1/earth/ulf/latest`
  - returns the latest regional context plus latest station rows
- `GET /v1/earth/ulf/series?hours=48&mode=context|station`
  - default `mode=context`
  - `hours` clamped to `<= 168`
  - chart-friendly ascending timestamps

## Job Wiring

- Bot:
  - `bots/geomag_ulf/ingest_ulf.py`
- Schedule:
  - wired into `.github/workflows/space-weather.yml`

## Config

- `ULF_STATIONS`
- `ULF_FETCH_MINUTES`
- `ULF_WINDOW_SECONDS`
- `ULF_CONTEXT_MODE`
- `ULF_ENABLE_LOCALTIME_PERCENTILE`
- `ULF_MIN_HISTORY_ROWS`
- shared HTTP settings:
  - `HTTP_TIMEOUT_SECS`
  - `HTTP_RETRY_TRIES`
  - `HTTP_RETRY_BASE_SLEEP`
  - `HTTP_USER_AGENT`

## Future Pattern Hook

Reserved backend signal keys for later pattern/confidence work:

- `geomagnetic_ulf_intensity` -> `marts.ulf_context_5m.regional_intensity`
- `geomagnetic_ulf_coherence` -> `marts.ulf_context_5m.regional_coherence`
- `geomagnetic_ulf_persistence` -> `marts.ulf_context_5m.regional_persistence`
- `geomagnetic_ulf_confidence` -> `marts.ulf_context_5m.confidence_score`

No gauge scoring or user-facing pattern dependency is active in this phase.
