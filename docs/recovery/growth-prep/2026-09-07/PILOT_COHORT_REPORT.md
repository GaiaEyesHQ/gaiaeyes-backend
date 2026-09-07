# Pilot cohort report handoff

`scripts/pilot_cohort_report.py` creates one aggregate, privacy-preserving pilot report from explicitly supplied account and analytics-event JSON exports. It is local and standard-library only. It does not connect to Supabase, the backend, App Store Connect, or Facebook.

## Measurement semantics

- A **new account** comes only from an account row whose `created_at` is inside `[pilot_start, pilot_end)`. A first-seen analytics event never turns an older account into a new account.
- A **known iOS account** is a new, non-excluded account with at least one `platform=ios` analytics event during its first 24 hours. Accounts without enough event coverage are censored; accounts with a complete window but no iOS event stay platform-unclassified.
- **First meaningful use** is one of `symptom_logged`, `exposure_logged`, `daily_checkin_completed`, or `guide_opened` during `[account_created_at, account_created_at + 24 hours)`.
- `first_insight_viewed` is excluded because the current iOS app emits it automatically when onboarding changes to the activation step. `onboarding_completed` is also completion evidence, not meaningful use by itself.
- **D7 return** means another meaningful event during `[first_meaningful_use + 6 days, first_meaningful_use + 9 days)`. Only accounts whose entire return window is covered appear in the denominator.
- Rates use fully observed denominators. Incomplete export coverage and immature windows are counted as censored or emitted as `null`/unknown, never silently converted to zero.
- Exact duplicate retries are removed by `(user_id, client_event_id)`. Rows without a client ID use the exact user/event/timestamp/platform/session tuple.
- Source attribution remains `unknown`; this report does not manufacture a Facebook-to-account join.
- Aggregate output contains counts only—no user IDs, symptom text, notes, or other health content.

## Required export shape

Account fixture:

```json
{
  "coverage": {"through": "2026-09-11T00:00:00Z"},
  "accounts": [
    {"id": "account-id", "created_at": "2026-09-10T00:10:00Z"}
  ]
}
```

The export must include all accounts created through `coverage.through`. `id` may be named `user_id`. The report total is `null` when coverage does not reach the pilot's exclusive end.

Analytics-event fixture:

```json
{
  "coverage": {
    "from": "2026-09-10T00:00:00Z",
    "through": "2026-09-20T12:00:00Z"
  },
  "events": [
    {
      "user_id": "account-id",
      "client_event_id": "stable-event-id",
      "event_name": "symptom_logged",
      "event_ts_utc": "2026-09-10T00:20:00Z",
      "platform": "ios",
      "session_id": "session-id"
    }
  ]
}
```

Required event fields are `user_id`, `event_name`, `event_ts_utc`, and `platform`. `client_event_id` and `session_id` are strongly recommended for retry deduplication. Coverage must be continuous across the declared interval; the script cannot detect an undisclosed gap.

Supply every known internal/test account with repeatable `--exclude-user-id` flags or a newline-delimited `--exclude-user-ids-file`. Do not commit a real identifier file or production export.

## Exact synthetic example

```sh
venv/bin/python scripts/pilot_cohort_report.py \
  --accounts docs/recovery/growth-prep/2026-09-07/fixtures/accounts.synthetic.json \
  --events docs/recovery/growth-prep/2026-09-07/fixtures/events.synthetic.json \
  --pilot-start 2026-09-10T00:00:00Z \
  --pilot-end 2026-09-11T00:00:00Z \
  --as-of 2026-09-20T12:00:00Z \
  --exclude-user-id synthetic-internal
```

Expected aggregate:

```json
{
  "cohort": {
    "known_ios_accounts": 2,
    "new_external_accounts_total": 2,
    "observed_new_external_accounts": 2,
    "internal_or_test_accounts_excluded": 1,
    "old_accounts_excluded": 1
  },
  "first_meaningful_use_24h": {
    "numerator": 1,
    "matured_denominator": 2,
    "rate": 0.5,
    "censored_accounts": 0
  },
  "d7_return": {
    "numerator": 1,
    "matured_denominator": 1,
    "rate": 1.0,
    "censored_activated_accounts": 0
  },
  "deduplication": {
    "input_events": 8,
    "unique_events": 7,
    "duplicates_removed": 1
  },
  "pilot": {"source_attribution": "unknown"},
  "unknowns": []
}
```

The CLI emits additional coverage and privacy fields. The shortened expected block above contains the review-critical values.

## Runtime limits

The implementation loads both supplied JSON files in memory and groups events by account. It is intended for one bounded pilot export, not as a production analytics framework or large-history warehouse job. For a larger cohort, produce a minimized authorized export containing only the documented fields and necessary coverage window. No production export or user history was read while implementing this tool.
