# Web Changelog

## 2025-11-09 – Aurora tracker refresh
- Introduced the `gaia-aurora.php` MU plugin to ingest NOAA OVATION nowcasts, derive live viewlines, expose `/wp-json/gaia/v1/aurora/*` endpoints, and persist payloads to Supabase plus the media repo.
- Replaced the legacy shortcode renderer with a theme partial (`partials/gaiaeyes-aurora-detail.php`) that fetches the REST payloads, draws the live SVG viewline, and surfaces experimental viewline PNGs.
- Added hourly fetchers for NOAA’s experimental viewline PNGs and mirrored the outputs in `public/aurora/viewline/{tonight,tomorrow}.json`.
- Documented diagnostics and Supabase changes, aligning env usage with existing `SUPABASE_*` and `MEDIA_DIR` variables to match production.
