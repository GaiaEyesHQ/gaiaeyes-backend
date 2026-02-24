# Schumann UI (WP + iOS)

## Scope
This document maps the Schumann dashboard implementation across WordPress and iOS.

- **Backend endpoints used**
  - `GET /v1/earth/schumann/latest`
  - `GET /v1/earth/schumann/series_primary?limit=192`
  - `GET /v1/earth/schumann/heatmap_48h`
- **Unchanged endpoint**
  - `GET /v1/earth/schumann/series` is untouched and remains available for existing comparison usage.

## Backend headers
`app/routers/earth.py` now adds cache headers and weak ETags on these routes:

- `/v1/earth/schumann/latest` → `Cache-Control: public, max-age=60`
- `/v1/earth/schumann/series_primary` → `Cache-Control: public, max-age=300`
- `/v1/earth/schumann/heatmap_48h` → `Cache-Control: public, max-age=300`

## WordPress implementation
### Files
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.php`
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.css`
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard-block.js`

### Public entry points
- Shortcode: `[gaiaeyes_schumann_dashboard]`
- Gutenberg block: `gaiaeyes/schumann-dashboard`

### Render pipeline
1. Frontend JS loads a same-origin WP REST proxy: `GET /wp-json/gaia/v1/schumann/dashboard`.
2. Proxy fetches backend Schumann endpoints and caches each response in transients.
3. UI renders cards:
   - Earth Resonance Gauge
   - 48h Heatmap (canvas)
   - 48h Pulse line (canvas)
   - Latest readout row + band trend bars

### WP cache controls
Default transient TTL constants (seconds):

- `GAIAEYES_SCHUMANN_LATEST_TTL` (default `60`)
- `GAIAEYES_SCHUMANN_SERIES_TTL` (default `300`)
- `GAIAEYES_SCHUMANN_HEATMAP_TTL` (default `300`)

Filter hooks:

- `gaiaeyes_schumann_latest_ttl`
- `gaiaeyes_schumann_series_ttl`
- `gaiaeyes_schumann_heatmap_ttl`

### WP UX behaviors
- Scientific/Mystical mode toggle (labeling and density only)
- Quality badge (`OK` vs `Low confidence`)
- Station chip from `quality.primary_source`
- Graceful partial rendering when one endpoint fails
- Optional controls implemented:
  - Heatmap PNG export
  - Harmonic overlay toggle (7.8, 14.1, 20.0 Hz)
  - Quality-aware dimming for low-confidence points
  - High contrast toggle
  - App deep-link button
  - Pro placeholder for `30d history`

## iOS implementation
### Files
- `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift` (navigation hook)

### Navigation
A dedicated Schumann page is linked from home quick links via the Mission menu. It opens as its own sheet view.

### Screen sections
- Top controls: Scientific/Mystical, last updated, quality badge, detail/harmonic/high-contrast toggles
- Section A: gauge + threshold interpretation text
- Section B: interactive heatmap (tooltip + harmonic overlays + PNG export)
- Section C: band bars (7-9 / 13-15 / 18-20) with 2-hour trend arrows
- Section D: 48h pulse line with low-confidence dimming and optional f0 overlay (scientific)
- Pro hook placeholder for `30d history`

### iOS fetch cadence
- On first appear: fetch `latest`, `series_primary?limit=192`, `heatmap_48h`
- Pull-to-refresh: manual full refresh
- Auto refresh while open: every 12 minutes

### iOS caching behavior
An in-app endpoint cache stores decoded payloads with TTLs:
- latest: 60s
- series: 300s
- heatmap: 300s

On fetch failure, stale cached payloads are reused when available.

## Threshold source of truth
Gauge/state thresholds are centralized in `SchumannDashboardView.swift` (`SchumannTuning`) and mirrored in WP JS (`STATE_LEVELS`) so labels can be tuned without backend/schema changes.
