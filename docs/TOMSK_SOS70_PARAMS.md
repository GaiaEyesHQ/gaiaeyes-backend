# Tomsk SOS70 Params Extractor

This documents how `bots/schumann/tomsk_sos70_params_extractor.py` converts picked
line positions into numeric values for the SOS70 `F/A/Q` parameter charts.

## Why this exists

The SOS70 parameter images use separate per-series axes (different ranges for
`F1..F4`, `A1..A4`, `Q1..Q4`). A single global `y` normalization is not accurate.

The extractor now:

1. Picks each series in its lane window.
2. Computes per-series `lane_norm` (0..1 inside that series lane).
3. Converts lane-normalized positions to values using per-series axis ranges.

## Lane windows (normalized ROI)

- `F`: `F1(0.02..0.22)`, `F2(0.24..0.42)`, `F3(0.43..0.59)`, `F4(0.60..0.76)`
- `A`: `A1(0.03..0.32)`, `A2(0.20..0.54)`, `A3(0.42..0.76)`, `A4(0.68..0.98)`
- `Q`: `Q1(0.05..0.36)`, `Q2(0.24..0.58)`, `Q3(0.42..0.78)`, `Q4(0.70..0.99)`

## Value ranges (top=max, bottom=min)

- `F`: `F1 7.20..8.40`, `F2 13.10..14.50`, `F3 18.60..20.20`, `F4 24.10..26.50`
- `A`: `A1 1.00..45.00`, `A2 1.00..61.50`, `A3 2.20..12.20`, `A4 1.10..10.20`
- `Q`: `Q1 4.00..38.00`, `Q2 5.00..17.50`, `Q3 7.00..23.00`, `Q4 5.00..30.00`

## JSON output fields

`values` now includes:

- legacy pixel/global fields: `F_norm`, `F_y_px`, `A_norm`, `A_y_px`, `Q_norm`, `Q_y_px`
- lane fields: `F_lane_norm`, `A_lane_norm`, `Q_lane_norm`
- converted values: `F_hz`, `A_value`, `Q_value`
- metadata: `scale_ranges`, `scale_units`

## Supabase channels in `ext.schumann`

Workflow `.github/workflows/schumann.yml` appends SOS70 params to the existing
`ext.schumann` table (no schema change) using dedicated channels:

- `sos70_F1_hz`, `sos70_F2_hz`, `sos70_F3_hz`, `sos70_F4_hz`
- `sos70_A1`, `sos70_A2`, `sos70_A3`, `sos70_A4`
- `sos70_Q1`, `sos70_Q2`, `sos70_Q3`, `sos70_Q4`

This avoids collisions with existing Schumann harmonic channels (`F1..F5`).

## Supabase storage mirror (optional)

The same workflow also mirrors latest JSON/PNG artifacts to Supabase Storage
when credentials are present:

- default bucket: `space-visuals`
- override bucket: repository variable `SUPABASE_SCHUMANN_BUCKET`
- object prefix: `schumann/latest/`
