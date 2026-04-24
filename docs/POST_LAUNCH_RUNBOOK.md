# Gaia Eyes Post-Launch Runbook

Last updated: 2026-04-24

This runbook is for the first production window after iOS launch. It keeps the daily check short enough to run consistently while still covering the surfaces most likely to affect user trust: auth, backend health, freshness, local forecast/pollen, Outlook, analytics, notifications, and bug reports.

## Cadence

First 72 hours after launch:
- Morning check before workday traffic picks up.
- Evening check after a normal day of use.
- Immediate check after any backend deploy or app release.

After the first 72 hours:
- One daily automated check.
- Manual review of bug reports and analytics at least once per weekday.

## Daily Checklist

| Area | Healthy signal | Action if unhealthy |
| --- | --- | --- |
| Backend health | `/health` returns `ok=true`, `db=true`, no pool wait spike. | Check Render logs and DB pool state before investigating app-side issues. |
| DB monitor | `db=true`, `consec_fail=0`, and `last_probe` stays recent. `sticky_age_ms` may grow while DB state remains healthy. | Treat repeated DB monitor failures as launch-critical. |
| Auth/session | No burst of `401 Missing or invalid Authorization header` from normal signed-in app use. | Inspect auth diagnostics and token refresh logs; avoid creating duplicate anonymous users. |
| Health ingest | Test account Health Sync freshness advances after app activity; `heart_rate` derived values stay present. | Check `/v1/samples/batch`, mart refresh logs, and `marts.daily_features` for that user/day. |
| Local/pollen | `/v1/local/check?zip=...` returns current allergens and forecast pollen rows when provider data exists. | Check Google Pollen/API key, local cache merge, and forecast row preservation. |
| Outlook | Daily Outlook starts at Tomorrow, keeps all daily drivers, and surfaces possible symptoms when matching patterns exist. | Clear app snapshot/cache, then verify backend payload directly from `/v1/users/me/outlook`. |
| Analytics | `tab_viewed`, driver taps, check-in, share, and onboarding events appear in admin analytics. | Check app analytics queue, `/v1/analytics/events`, and admin summary. |
| Notifications | Disabled notification settings do not produce new alerts. | Check iOS local scheduling/cancellation and push notification eligibility jobs. |
| Bug reports | New reports can submit with or without login and alert routing succeeds. | Review `/v1/profile/bug-reports`; fix alert email/webhook config if reports land without alerting. |

## Automated Monitor

Run the daily monitor locally:

```bash
python scripts/post_launch_monitor.py
```

Useful environment variables:

| Env var | Purpose |
| --- | --- |
| `GAIA_MONITOR_BASE_URL` | Backend base URL. Defaults to `https://gaiaeyes-backend.onrender.com`. |
| `GAIA_MONITOR_ZIP` | ZIP for local weather/pollen smoke check. Defaults to `78754`. |
| `GAIA_MONITOR_TZ` | Timezone used for feature and analytics checks. Defaults to `America/Chicago`. |
| `GAIA_MONITOR_AUTH_BEARER` | Optional Supabase/dev bearer for authenticated smoke checks. Falls back to `DEV_BEARER`, then the first token in `WRITE_TOKENS`. |
| `GAIA_MONITOR_DEV_USER_ID` | Optional dev user header for `DEV_BEARER` based checks. Falls back to `GAIA_MONITOR_USER_ID`, `DEV_USER_ID`, `TEST_USER_ID`, `TEST_USER_UUID`, then `APP_REVIEW_USER_ID`. |
| `GAIA_MONITOR_ADMIN_BEARER` | Optional admin bearer for analytics summary checks. Falls back to `GAIAEYES_API_ADMIN_BEARER`, `GAIAEYES_ADMIN_BEARER`, `ADMIN_TOKEN`, then `DEV_BEARER`. |
| `GAIA_MONITOR_ANALYTICS_MIN_EVENTS_24H` | Minimum 24h analytics event count before warning. Defaults to `1`. |
| `GAIA_MONITOR_LAST_PROBE_WARN_MS` | DB monitor last-probe warning threshold. Defaults to `60000`. |

The GitHub Action `.github/workflows/post-launch-monitor.yml` runs this script daily and can be run manually. Add the optional secrets above when production smoke checks should include user-specific Outlook, Features, Analytics, and Bug Report checks.

## GitHub Secret Setup

Set these in GitHub. These are GitHub Actions secrets/variables; they do not require adding new Render environment variables.

Repository > Settings > Secrets and variables > Actions > Secrets

| GitHub secret | Value to use | Where to find it |
| --- | --- | --- |
| `DEV_BEARER` | Copy the existing production Render `DEV_BEARER`. The monitor uses it for authenticated and admin smoke checks. | Render service > Environment. |
| `GAIA_MONITOR_AUTH_BEARER` | Optional override if you do not want the monitor to use `DEV_BEARER`. | Render service > Environment, or create a long random token and add it to Render `WRITE_TOKENS`. |
| `GAIA_MONITOR_ADMIN_BEARER` | Optional override if you do not want admin checks to use `DEV_BEARER`. | Render service > Environment: use `GAIAEYES_API_ADMIN_BEARER`, `GAIAEYES_ADMIN_BEARER`, or `ADMIN_TOKEN` if present. |

Recommended personal/test account setup:

- Secret `DEV_BEARER`: production Render `DEV_BEARER`.
- Variable `TEST_USER_UUID`: the UUID for the personal/test account that has real HealthKit, local settings, sensitivities, and patterns.
- Optional secret `GAIA_MONITOR_ADMIN_BEARER`: only needed if you want admin checks to use something other than `DEV_BEARER`.

Use the personal/test account UUID for launch monitoring if that is the account you actively use for QA. Use the App Review account UUID only when you specifically want to smoke-check the review account. The monitor needs one stable UUID so `/v1/features/today`, `/v1/users/me/outlook`, analytics, and bug-report checks hit a real account instead of an empty anonymous profile.

Avoid using a copied Supabase access token for `GAIA_MONITOR_AUTH_BEARER` in the daily workflow. Supabase access tokens expire, so the monitor would start failing for the wrong reason. Use a backend allowlisted token plus `GAIA_MONITOR_DEV_USER_ID` for stable smoke checks.

Set these as non-secret repository variables if desired:

Repository > Settings > Secrets and variables > Actions > Variables

| GitHub variable | Suggested value |
| --- | --- |
| `GAIA_MONITOR_BASE_URL` | `https://gaiaeyes-backend.onrender.com` |
| `GAIA_MONITOR_ZIP` | A launch test ZIP such as `78754` |
| `GAIA_MONITOR_TZ` | `America/Chicago` |
| `TEST_USER_UUID` | The personal/test account UUID to monitor |
| `GAIA_MONITOR_ANALYTICS_MIN_EVENTS_24H` | `1` during test/review, then raise after launch traffic is real |

## Triage Order

1. Confirm the phone is on the latest build and the backend is deployed.
2. Check `/health` before diagnosing app symptoms.
3. If a feature looks stale in-app, verify the backend payload directly before changing iOS.
4. If the backend payload is correct, suspect persisted app snapshot/cache next.
5. If analytics or bug reports are missing, check auth status and endpoint status before changing reporting UI.
6. If notifications fire while disabled, inspect pending local notifications and push eligibility separately.

## First Update Intake

Use the first week to collect issues into a `1.0.1` backlog with these buckets:

- Launch-critical: auth loss, duplicate users, broken submissions, data loss, notification preference violations.
- High-value polish: stale copy, confusing Outlook/Guide states, layout issues, missing diagnostics.
- Monitoring/reporting: analytics gaps, admin report gaps, bug-report routing.
- Product depth: patterns, NOAA data expansion, social/event bot, Android planning.

Do not mix product-depth work into an emergency launch fix unless it directly resolves a launch-critical issue.
