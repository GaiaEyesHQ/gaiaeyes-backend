# Android Agent Log

## 2026-08-09 - Foreground session and Health Connect reliability

- Kept the authenticated Android surface and cached dashboard visible during
  temporary Supabase session initialization or refresh failures; a confirmed
  sign-out still clears account-scoped state normally.
- Added a rate-limited, two-day Health Connect import when the signed-in app
  resumes or Body opens, while preserving the existing manual 30-day import.
- Refreshes the real account-scoped health retry-queue count before foreground
  imports so a previously displayed pending count does not remain stale.
- Did not add background Health Connect reading permission. Existing WorkManager
  jobs continue to deliver already queued batches in the background.

## 2026-07-31 - Journal background drain

- Added a network-constrained WorkManager drain for the existing account-scoped
  symptom, exposure, and daily check-in queue.
- Failed foreground delivery schedules immediate background work; a unique
  15-minute periodic job provides a safety drain.
- Foreground and background drains share a mutex so the same queued write is not
  posted concurrently.
- Missing or expired sessions exit without repeated retries; transient failures
  use WorkManager backoff.
- Health Connect import remains the next vertical slice. HRV stays deferred
  until the backend explicitly distinguishes RMSSD from `hrv_sdnn`.
