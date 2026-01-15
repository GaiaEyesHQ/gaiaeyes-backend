# GitHub Actions

This repo relies heavily on GitHub Actions for scheduled ingestion, JSON snapshot generation, and WordPress publishing. Render is used for hosting the backend, but most recurring jobs run here.

## Where to look
- Workflows live in `.github/workflows/`.
- The audit helper is `docs/github-actions-audit.md` + `scripts/audit_workflows.py`.

## Workflow inventory (by file)
> **Note:** Cron schedules are defined inside each workflow file. Update schedules there.

### Space + earth data ingest
- `space-weather.yml` — ingest space weather + JSON export.
- `space-weather-daily-rollup.yml` — daily rollup of space weather marts.
- `ingest_space_forecasts.yml` — Step 1 space forecast ingestion.
- `space-visuals.yml` — space visuals ingest + storage upload.
- `magnetosphere.yml` — magnetosphere KPIs + JSON/media updates.
- `schumann-ingest.yml` — ingest Schumann data (in repo).
- `schumann.yml` — Schumann processing pipeline.
- `quakes_ingest.yml` — ingest quake data.
- `quakes-history.yml` — build quake history JSON.
- `quakes-backfill.yml` — quake backfill.
- `compare-series.yml` — build compare_series + space history JSON.
- `earthscope-rules.yml` — build earthscope rules JSON.
- `earthscope_post.yml` — Earthscope daily post bot.
- `aurora_fetch.yml` — aurora fetch/nowcast cron.
- `volcanoes-ingest.yml` — weekly volcano ingestion.

### Health + features rollups
- `health-daily-rollup.yml` — daily health rollups.
- `daily-features-rollup.yml` — rolling daily features refresh.

### Content + social
- `gaia_eyes_daily.yml` — daily Earthscope pipeline (Supabase + media JSON).
- `space_news.yml` — space news pipeline + WP publish.
- `news-ingest.yml` — news JSON ingest.
- `research_lane.yml` — research collection lane.
- `research_watch.yml` — research watch pipeline.
- `social.yml` — social fact render + post.
- `wp_post.yml` — WordPress daily publish.
- `wp-deploy.yml` — deploy `wp-content` to SiteGround.

### Site maintenance + linting
- `lint-links.yml` — ensure legacy owner links don’t appear.
- `workflow-yamllint.yml` — lint workflow YAML.
- `site-assets-check.yml` — validate external assets listed in docs.
- `review.yml` — PR review automation.
- `pulse.yml` — pulse JSON output.

## Open questions
See `docs/OPEN_QUESTIONS.md` for missing Render cron details; however, most scheduled work lives in these GitHub Actions workflows.
