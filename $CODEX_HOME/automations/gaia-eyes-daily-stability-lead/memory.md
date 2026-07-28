2026-07-26 daily stability lead
- Production health green: /health db=true on direct backend, pool waiting=0, ingest queue depth=0, /health/live ok.
- Freshness verified: /v1/local/check?zip=78754 asof 2026-07-26T13:35:00Z, ext.local_signals_cache asof 2026-07-26T14:01:24Z, marts.daily_features max updated_at 2026-07-26T14:03:05Z, features/today diag updated_at 2026-07-26T14:02:13Z.
- Render signed-in cron history checked: gaiaeyes-critical-ingestion latest success Sunday, July 26, 2026 9:00 AM CDT; gaiaeyes-event-ingestion latest success Sunday, July 26, 2026 7:13 AM CDT; gaiaeyes-daily-derivations latest success Sunday, July 26, 2026 5:35 AM CDT.
- GitHub Actions failures are secondary/non-app-blocking today: Aurora Fetch (Staging) hit SiteGround captcha HTML instead of JSON; space-weather workflow timed out connecting asyncpg and opened issue #170; space-visuals ENLIL upload hit ConnectionResetError during HTTPS upload.
- Outlook monitor warning reproduced: /v1/users/me/outlook top_drivers are space-only for the next two days and empty after that; no local driver keys surfaced, but app freshness remained healthy.
- Small local fix applied: scripts/db_diagnose.py now bootstraps repo root on sys.path; added tests/scripts/test_db_diagnose.py; verified with pytest and direct script run.
- Runtime: ~8 minutes.
