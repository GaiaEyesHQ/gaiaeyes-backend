# Android Agent Log

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
