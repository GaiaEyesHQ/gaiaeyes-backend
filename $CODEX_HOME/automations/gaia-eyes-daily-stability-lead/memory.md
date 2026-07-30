2026-07-30 daily stability lead
- Production health green at 2026-07-30T01:49:40Z: /health db=true on direct backend, pool open=8 free=8 waiting=0, ingest queue depth=0, /health/live previously green.
- Freshness verified at 2026-07-30T01:45:55Z-2026-07-30T01:50:00Z: /v1/local/check?zip=78754 asof 2026-07-30T01:25:00Z with AQI 60 Moderate; ext.local_signals_cache latest asof 2026-07-30T01:45:55.993265Z; marts.daily_features day 2026-07-29 max updated_at 2026-07-29T21:28:17.922417Z; /v1/features/today diag updated_at 2026-07-29T21:11:29.659764Z.
- Render signed-in cron history checked in Chrome: gaiaeyes-critical-ingestion latest success July 29, 2026 4:15 PM CDT and continuing every 15 minutes; gaiaeyes-event-ingestion latest success July 29, 2026 3:13 PM CDT; gaiaeyes-daily-derivations latest success July 29, 2026 5:35 AM CDT.
- Root cause observed but recovered: the critical cron log for July 29, 2026 4:29 PM-4:35 PM CDT showed repeated AirNow 502/timeout failures plus ZIP fallback errors, which temporarily produced AQI null rows for 78754 before later critical runs recovered to AQI 60.
- GitHub Actions checked live at 2026-07-30T01:51Z: latest production-adjacent runs were green; the only current failure in the latest 10 was non-prod Aurora Fetch (Staging), failing step `Basic assertions (fail if no TS)`.
- Small local guard fix added but not deployed: app/routers/local.py now restores missing AQI/allergen sections from the previous cached payload on the /v1/local/check fast path; regression test added in tests/api/test_local_check.py; verified with `venv/bin/pytest tests/api/test_local_check.py` (6 passed).
- Runtime: ~35 minutes.

2026-07-26 daily stability lead
- Production health green: /health db=true on direct backend, pool waiting=0, ingest queue depth=0, /health/live ok.
- Freshness verified: /v1/local/check?zip=78754 asof 2026-07-26T13:35:00Z, ext.local_signals_cache asof 2026-07-26T14:01:24Z, marts.daily_features max updated_at 2026-07-26T14:03:05Z, features/today diag updated_at 2026-07-26T14:02:13Z.
- Render signed-in cron history checked: gaiaeyes-critical-ingestion latest success Sunday, July 26, 2026 9:00 AM CDT; gaiaeyes-event-ingestion latest success Sunday, July 26, 2026 7:13 AM CDT; gaiaeyes-daily-derivations latest success Sunday, July 26, 2026 5:35 AM CDT.
- GitHub Actions failures are secondary/non-app-blocking today: Aurora Fetch (Staging) hit SiteGround captcha HTML instead of JSON; space-weather workflow timed out connecting asyncpg and opened issue #170; space-visuals ENLIL upload hit ConnectionResetError during HTTPS upload.
- Outlook monitor warning reproduced: /v1/users/me/outlook top_drivers are space-only for the next two days and empty after that; no local driver keys surfaced, but app freshness remained healthy.
- Small local fix applied: scripts/db_diagnose.py now bootstraps repo root on sys.path; added tests/scripts/test_db_diagnose.py; verified with pytest and direct script run.
- Runtime: ~8 minutes.
