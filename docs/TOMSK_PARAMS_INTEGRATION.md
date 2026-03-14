# Tomsk Params Integration

This document covers the Tomsk SOS70 `F/A/Q` parameter integration across the
FastAPI backend, iOS app, and WordPress dashboard.

## Endpoints

### `GET /v1/earth/schumann/tomsk_params/latest`

Returns the latest Tomsk parameter snapshot for a station (default `tomsk`).

Query params:

- `station_id` — optional, defaults to `tomsk`

Response shape:

- `generated_at`
- `station_id`
- `usable`
- `usable_for_fusion`
- `quality_score`
- `frequency_hz.F1..F4`
- `amplitude.A1..A4`
- `q_factor.Q1..Q4`
- `trend_2h`
- `coherence`

Cache policy:

- `Cache-Control: public, max-age=60`
- weak `ETag`

### `GET /v1/earth/schumann/tomsk_params/series`

Returns the time-ascending Tomsk parameter series for the requested window.

Query params:

- `hours` — optional, defaults to `48`
- `station_id` — optional, defaults to `tomsk`

Response shape:

- `station_id`
- `count`
- `points[]`
  - `ts`
  - `F1..F4`
  - `A1..A4`
  - `Q1..Q4`
  - `usable`
  - `quality_score`
  - `quality_flags`

Cache policy:

- `Cache-Control: public, max-age=300`
- weak `ETag`

## Public Read Access

These routes are on the default public allowlist:

- `/v1/earth/schumann/tomsk_params/latest`
- `/v1/earth/schumann/tomsk_params/series`

`PUBLIC_READ_PATHS` still overrides the default list if you need a custom
deployment allowlist.

## Fusion Rules

Tomsk is display-fused into the unified Schumann dashboard only when all of the
following are true:

- `SCHUMANN_FUSE_TOMSK=true`
- `usable=true`
- `quality_score >= SCHUMANN_TOMSK_MIN_QUALITY_SCORE`

Current fusion behavior:

- Primary displayed `F0` becomes Tomsk `F1`
- Cumiana `f0` remains the secondary reference
- Cumiana gauge numeric remains unchanged
- Cumiana heatmap and band bars remain unchanged
- Tomsk `A1..A4` and `Q1..Q4` stay inside the Tomsk detail accordion

The backend exposes this as `fusion` inside `/v1/earth/schumann/latest` so
clients can display the same decision consistently.

## Coherence Chip

When Tomsk is fusion-usable, the backend computes a `coherence` label from the
latest `Q1` percentile over the last 48 hours:

- `high` — percentile >= 0.67
- `medium` — percentile >= 0.34 and < 0.67
- `low` — percentile < 0.34

Clients surface this as the `Coherence` chip.

## iOS UI

`gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift` now:

- fetches Tomsk latest with the existing Schumann load
- lazy-loads Tomsk 48h series when the accordion expands
- shows `Tomsk Details (F/A/Q)` as an accordion
- displays `F1..F4`, `A1..A4`, `Q1..Q4` with server-side 2h trend arrows
- shows three mini sparklines for `F1`, `A1`, `Q1`
- dims low-confidence Tomsk points in the sparklines
- uses the backend fusion state for the displayed fundamental when available

## WordPress UI

`wp-content/mu-plugins/gaiaeyes-schumann-dashboard.*` now:

- fetches Tomsk latest in the existing dashboard proxy
- lazy-loads Tomsk series through `GET /wp-json/gaia/v1/schumann/tomsk-series`
- adds a `Tomsk Details (F/A/Q)` accordion with F/A/Q trend rows
- adds mini Tomsk sparklines for `F1`, `A1`, `Q1`
- keeps Cumiana heatmap and band bars as the main dashboard visuals
- adds Tomsk status/timestamp text to the PNG export footer

## Troubleshooting

### Tomsk shows unavailable

Check:

- `usable` in `ext.schumann.meta`
- `quality_score` in `meta` or `meta.raw`
- `SCHUMANN_FUSE_TOMSK`
- `SCHUMANN_TOMSK_MIN_QUALITY_SCORE`

If `usable=false` or the score is below threshold, the dashboard intentionally
falls back to Cumiana-only display.

### Low-quality series points are dimmed

The series endpoint adds `quality_flags`:

- `unusable`
- `low_quality`
- `missing_quality_score`

Clients dim these points instead of hiding them.

### `mask_scores` or picker diagnostics look poor

If Tomsk ingest marks a frame as poor-quality in the extractor diagnostics,
`usable` should stay false or `quality_score` should remain below threshold.
That keeps fusion off while still letting the accordion show the raw Tomsk
snapshot for inspection.
