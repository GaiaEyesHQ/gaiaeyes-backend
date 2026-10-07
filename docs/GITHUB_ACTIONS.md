# GitHub Actions

This repo relies heavily on GitHub Actions for scheduled ingestion, JSON snapshot generation, and WordPress publishing. Render is used for hosting the backend, but most recurring jobs run here.

## Where to look
- Workflows live in `.github/workflows/`.
- The audit helper is `docs/github-actions-audit.md` + `scripts/audit_workflows.py`.

## Workflow inventory (by file)
> **Note:** Cron schedules are defined inside each workflow file. Update schedules there.

### Space + earth data ingest
- `space-weather.yml` — independent jobs for NOAA ingestion/rollup/JSON publication and USGS ULF geomagnetic context derivation.
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
- `evaluate_push_notifications.yml` — evaluate current user state into queued push events every 15 minutes.
- `send_push_notifications.yml` — send queued APNs or FCM notifications by registered platform and disable invalid tokens every 5 minutes. Requires GitHub Actions secrets `SUPABASE_DB_URL`, `APNS_TEAM_ID`, `APNS_KEY_ID`, `APNS_BUNDLE_ID`, `APNS_PRIVATE_KEY`, `FCM_PROJECT_ID`, and `FCM_SERVICE_ACCOUNT_JSON`.

### Content + social
- `gaia_eyes_daily.yml` — daily Earthscope pipeline (Supabase + media JSON + hardened FB/IG posting via `bots/earthscope_post/meta_poster.py`; see `docs/EARTHSCOPE_META_POSTING.md`).
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

### iOS
- `ios-ci.yml` — remote iOS Simulator build with optional manual test run (`workflow_dispatch`).

## Space-weather failure isolation

The `run` job ingests NOAA data, refreshes the daily/current rollup, and publishes
JSON to the media repository. The `ulf` job independently fetches USGS BOU/CMO
data and derives ULF context. Neither job depends on the other. Both retain hard
failures: a USGS outage still fails the ULF job and the overall workflow, but does
not prevent NOAA publication or create a misleading NOAA failure issue. A media
checkout or push failure likewise does not skip ULF ingestion.

Each job creates its own failure issue with the exact run URL, attempt, job,
commit, and ingestion outcomes. Open that run and inspect the named job; setup
failures can leave ingestion outcomes as `not run` or `skipped`.

### September 11, 2026 incident (#171–#173)

| Issue | Actions run | Confirmed failure |
| --- | --- | --- |
| [#171](https://github.com/GaiaEyesHQ/gaiaeyes-backend/issues/171) | [34550248375](https://github.com/GaiaEyesHQ/gaiaeyes-backend/actions/runs/34550248375) | BOU and CMO exhausted three attempts with `httpx.ReadTimeout` |
| [#172](https://github.com/GaiaEyesHQ/gaiaeyes-backend/issues/172) | [34569850536](https://github.com/GaiaEyesHQ/gaiaeyes-backend/actions/runs/34569850536) | Same USGS timeout pattern |
| [#173](https://github.com/GaiaEyesHQ/gaiaeyes-backend/issues/173) | [34595205663](https://github.com/GaiaEyesHQ/gaiaeyes-backend/actions/runs/34595205663) | Same USGS timeout pattern |

All three runs successfully ingested NOAA rows (1347, 1346, and 1348 respectively),
wrote the JSON locally, and completed the rollup. The subsequent ULF step raised
`ULF ingest produced no fresh derived rows` and skipped publication. The logs
establish a USGS read timeout, but do not establish whether USGS or the runner's
network caused it. Changing credentials, schema, or NOAA parsing is not indicated.

Commit `5c9ac3d` already moved publication ahead of ULF. As of this investigation,
the latest run, [35348305153](https://github.com/GaiaEyesHQ/gaiaeyes-backend/actions/runs/35348305153)
on September 18 at 13:06 UTC, succeeded: 1416 NOAA rows, JSON pushed on the first
attempt, 70 ULF station rows and 35 context rows. The independent jobs complete
the isolation and distinguish future provider failures; they do not claim to
prevent an external USGS outage.

Verify locally without database credentials or publication:

```bash
SUPABASE_DB_URL=postgresql://unused:unused@127.0.0.1:1/unused \
python -m pytest -q tests/scripts/test_space_weather_workflow.py \
  tests/bots/test_ulf_ingest.py tests/scripts/test_ingest_space_weather_swpc.py
```

The dummy DSN satisfies the NOAA module's import-time configuration check;
these tests do not connect to it.

The workflow tests cover NOAA, rollup, media, ULF, setup, and simultaneous failures.
The ULF timeout regression uses a mock HTTP transport and database connection to
verify bounded retries, a non-success result, no derived writes, and connection
cleanup. After an approved merge, inspect the next scheduled run's two job
results and issue links. Manual dispatch writes production data and publishes
media; it is not a dry run.

## Open questions
See `docs/OPEN_QUESTIONS.md` for missing Render cron details; however, most scheduled work lives in these GitHub Actions workflows.
