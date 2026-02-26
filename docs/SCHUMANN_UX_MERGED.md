# Schumann UX (Merged App + Web)

## Purpose
This document describes the unified Schumann experience across:
- iOS: `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`
- WordPress: `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.php|js|css`

The UX removes mode switching and keeps a single always-on presentation for both scientific context and friendly labels.

## Endpoints Used (unchanged)
- `GET /v1/earth/schumann/latest`
- `GET /v1/earth/schumann/series_primary?limit=192`
- `GET /v1/earth/schumann/heatmap_48h`

No endpoint behavior or query params were changed.

## Unified UX Rules
1. No Scientific/Mystical mode toggle.
2. Details and harmonics are always visible.
3. Gauge shows numeric index and state together.
4. A collapsible "How to read this" helper is shown.
5. Band labels are merged:
   - `7-9 Hz • Ground`
   - `13-15 Hz • Flow`
   - `18-20 Hz • Spark`
6. Band bar fill is normalized to the last 48h window:
   - `normalized = (latest - min48h) / (max48h - min48h)`
   - Real percentage values remain visible on the right.
7. Pulse chart always includes dashed `f0` overlay.

## Component Map
- Header:
  - Last updated
  - Quality badge
  - Station chip
  - High contrast toggle
  - "How to read this" disclosure
- Gauge:
  - `index — state`
  - Caption: `Index (0-20 Hz intensity; updates every 15 minutes).`
- Heatmap:
  - Always-on axes (`time`, `0-20 Hz`)
  - Always-on harmonic guide lines (`7.8`, `14.1`, `20.0`)
  - Legend: `Heatmap = time x frequency. Brighter = stronger.`
- Harmonic bands:
  - Combined labels
  - 48h-normalized bar fill
  - Real percentage + trend arrow
- Pulse:
  - `sr_total_0_20` line
  - Dashed `f0` overlay
  - Legend:
    - `Cyan: Intensity (0-20 Hz)`
    - `Yellow dashed: Fundamental (Hz)`

## Caching and refresh
- Existing caching and refresh behavior is unchanged:
  - WP transients for latest/series/heatmap
  - App in-memory endpoint cache and periodic refresh timer
