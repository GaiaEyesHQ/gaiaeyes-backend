# Notification delivery operations

The evaluator requests quarter-hour GitHub runs. The sender follows evaluator
completion through `workflow_run`, including partial evaluator failures, so
fresh queued work does not wait for a second independent cron. Both jobs have
concurrency groups; only trusted main executions can use the sender secrets.
Manual fallbacks remain available. No diagnostic/test workflow is part of this
chain.

This removes the evaluator-to-sender scheduling gap, but does not guarantee
quarter-hour evaluation. The October 7–14, 2026 audit found 35 evaluator and 36
sender scheduled runs, with creation gaps approaching ten hours. October 15
still showed multi-hour gaps. GitHub documents that scheduled events can be
delayed or dropped. Moving the requested minute away from :00 is a mitigation,
not a cadence repair.

## Eligibility and safety

- Quiet-hour evaluation does not queue a reminder or set `delivered_at`. The
  next evaluation checks it again. Push acceptance never sets that field; the
  existing in-app presentation path owns it. Historical markers are unchanged.
- Prompt dedupe uses the prompt ID across dates. A queued, accepted, or failed
  attempt suppresses another event for that prompt. Pending/snoozed reminders
  are eligible within 24 hours of their actual scheduled/snoozed due time.
- Before sending, re-read master opt-in, categories, family toggles,
  sensitivity, quiet hours/timezone, enabled devices, and prompt status. A
  snoozed prompt stays queued until due, even if the app recorded a previous
  presentation before the snooze. Answered, disabled, expired, or already
  presented pending prompts are skipped. Each prompt still gets at most one
  accepted push; snoozing does not replay a previously accepted push. Digests
  are skipped if any child is disallowed.
- Environment/gauge events older than one hour are skipped. APNs expiration
  and Android TTL are five minutes. These limits prevent stale backlog bursts;
  sparse evaluator triggers can still mean an eligible reminder is missed.
- Each evaluator holds a per-user transaction advisory lock. Each sender
  atomically changes `queued` to `failed/delivery_unconfirmed` before any
  provider request. Only the claim winner may send, and an interrupted or
  ambiguous attempt is not automatically replayed. Failed attempts also count
  toward family cooldowns, including across time-bucket boundaries.
- Explicit 429/500/503 rejections may retry at most three attempts, with at
  least 15 minutes then 30 minutes between attempts and a longer Retry-After
  respected. Acceptance, transport ambiguity, and permanent rejection never
  retry. If any device accepts, the event becomes terminal: another device's
  failure cannot cause the accepted device to receive a duplicate.
- Quiet, future-snoozed, and unconfigured events are deferred. Internal queue
  metadata stores next-check time/attempt count and rotates deferred work
  behind untouched rows. Metadata is excluded from provider payloads. A batch
  processes at most 100 events.

The existing `sent` status and `sent_at` mean **provider acceptance**, not phone
delivery or presentation. Logs use `provider_accepted` and
`device_receipt=unconfirmed`. `failed/delivery_unconfirmed` is deliberately
conservative: a crash even just before the request can lose that event rather
than risk duplicate delivery. Do not bulk reset failed or historical rows.
Configuration failures and provider rejections exit nonzero for visibility.

## Reliable scheduler cutover: blocked on credential provisioning

The existing Render `gaiaeyes-critical-ingestion` cron runs every 15 minutes.
Its masked environment key inventory on October 16 has Supabase access but no
APNs settings. The web service also lacks APNs configuration. This change does
not enable a second sender, copy credentials, create a paid service, or change
Supabase schema or auto-migration settings.

Before activating notifications there:

1. Obtain specific approval for credential provisioning on that existing cron.
   Have the credential owner supply `APNS_TEAM_ID`, `APNS_KEY_ID`,
   `APNS_BUNDLE_ID`, and `APNS_PRIVATE_KEY` directly through Render's secret
   controls. Never extract GitHub secrets. Provision FCM only if Android sends
   are required and separately authorized.
2. Prepare and test a bounded evaluator/sender step after source/gauge refresh.
   Measure combined runtime and database pressure against the 15-minute lane.
   If it does not fit, revisit the design before activation; a new paid service
   needs separate approval.
3. Stop the GitHub evaluator schedule and automatic sender trigger, wait for
   old runs to finish, then activate the Render step. Keep manual fallback
   controlled; do not have two routine schedulers active.
4. Observe at least four automatic cycles, recording source revision, start/end
   times, aggregate evaluated/queued/skipped/accepted/failed counts and absence
   of overlapping senders. No extra test notifications are needed. Provider
   acceptance alone cannot prove phone display.

## Verification

Unit regressions in `tests/bots/test_notification_delivery_safety.py` cover quiet
hours, preferences, expiry, snoozing, bounded retries, ambiguous outcomes and
partial multi-device acceptance. `tests/integration/test_notification_claims.py`
uses the existing disposable numeric-loopback PostgreSQL fixture to verify
concurrent claims, durable crash state, deferred queue fairness, prompt dedupe,
and cooldowns across bucket boundaries. The Backend refresh reliability CI
workflow runs both; no production records or APNs/FCM calls are used.
