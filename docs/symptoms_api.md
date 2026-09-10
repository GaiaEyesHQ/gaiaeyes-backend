# Symptoms API

This document outlines the REST endpoints that power the Gaia Eyes symptom logging
experience. The routes live under the `/v1/symptoms` prefix and require a valid
Bearer token. During development you can supply the `DEV_BEARER` token together
with an `X-Dev-UserId` header to impersonate a user.

## Saved migraine time correction (G-013, local/default-off)

- `GET /v1/symptoms/current/{episode_id}/migraine-times` returns the canonical start/end, validated detail, revision, canonical timestamp token and any inconsistent raw end.
- `POST` to that path uses a UUID `request_id`, `expected_revision`, `expected_canonical_updated_at` and explicit `start` / `end` / `state` changes. Omission retains; end null clears without reopening; start/state null reject. Set timestamps require congruent original wall time, IANA timezone, UTC offset and aware UTC. Repeated local times require an explicit occurrence; invalid gaps/order/future times reject.
- Owner-filtered canonical timing, detail revision/audit and reminder reconciliation commit atomically. Original source events and update rows remain intact. Identical request retries replay the receipt; changed reuse or stale tokens return 409. Invalid values/IDs return 422; not-owned/missing episodes return 404; missing capability returns 503.
- After commit, existing gauge and personal-pattern refresh paths cover affected dates. A separate `refresh.status` reports complete/pending; failure does not undo or conceal a saved correction. Exact retry may repeat downstream refresh without repeating the correction.
- Activation requires `GAIA_MIGRAINE_TIME_EDITING_ENABLED=1` plus the additive migration, both correction-aware read views and audit columns. iOS also requires the Debug-only `-gaia-enable-migraine-time-editing` launch flag within the existing calendar/editor workflow. These flags remain off by default.
- See [MIGRAINE_TIME_CORRECTION_CONTRACT.md](contracts/MIGRAINE_TIME_CORRECTION_CONTRACT.md) for concurrency, provenance, unknown-end/state, reminders, affected readers, legacy report semantics and parity/release boundaries.

## Migraine calendar history (G-012, local/default-off)

`GET /v1/symptoms/migraine/history?start=<aware-ISO8601>&end=<aware-ISO8601>&limit=50&cursor=<opaque>` reads the authenticated user's canonical migraine episodes. It requires `GAIA_MIGRAINE_CALENDAR_ENABLED=1`; absent capability returns 503 (older servers may return route 404). The existing `/current/timeline` remains unchanged. No schema migration or parallel history store is introduced.

- Range is `[start,end)`, at most 62 elapsed days, limit 1–100. iOS constructs calendar month/day boundaries in its explicit display timezone, then sends UTC instants; days may have 23 or 25 hours.
- Include an onset within the range, or an earlier episode with a recorded end strictly after start. A non-resolved episode with no recorded end overlaps through the first page's fixed `as_of` instant. An end exactly at day start does not carry into that day. A zero-duration episode still appears on its onset day.
- `end_status` is `recorded`, `open`, or `unknown`. Resolved episodes without a valid end are onset-only markers; their missing duration is not fabricated. Medicine times and update counts are never episode boundaries.
- Each item has `id`, `started_at`, nullable `ended_at`, `end_status`, `state`, nullable `severity` and `note_preview`. Ordering is `(started_at DESC,id DESC)`. The cursor binds account, range, fixed as-of instant, complete matching-set fingerprint and last ordering tuple. It grants no access: every page applies authenticated owner filtering independently.
- The response data contains `items`, `start`, `end`, `as_of`, `snapshot`, nullable `next_cursor` and `complete`. More than 80 episodes are supported through pagination; stable datasets have no gaps/duplicates. A single PostgreSQL statement computes both fingerprint and page. Fingerprinting uses the existing owner/start index and all matching canonical fields, including update time; it detects insert/delete/edit changes to the matching set between requests. Changed sets return 409 and require a first-page refresh. No durable snapshot or transaction is held across HTTP requests. Completion is as of the last successful page; later changes require refresh, including after acknowledged editing/return from the editor.
- Invalid inputs/cursors return 422; missing capability/storage returns 503; read failures return 500. These are explicit failures, never an empty successful calendar. Clients retain partial entries with an incomplete indication on retryable page failures and discard them on a changed-set conflict. No generic GET retry should join pages from different accounts/ranges.
- iOS shows the display timezone and a visible history-as-of time after complete loading. Activation also defaults off and is Debug-only. Android and member-hub parity are deferred for this local increment. G-013 adds separately gated explicit onset/end correction, described below; calendar navigation alone does not imply that capability is enabled.

## Authentication headers

```
Authorization: Bearer <token>
X-Dev-UserId: <uuid>  # optional helper for the dev bearer path
```

## Response envelope

All symptom routes respond with a predictable JSON envelope:

```json
{
  "ok": true,
  "data": [],
  "error": null,
  "friendly_error": null
}
```

- `ok` is `true` when the request succeeded and `false` on failures.
- `data` is always present. Collection endpoints return an array (possibly empty). The
  POST route returns either the created event payload or `null` on errors.
- `error` is the raw database/driver message on failures. This preserves historic
  behavior so existing clients can surface the original reason codes (for example,
  `"backend DB unavailable"`).
- `friendly_error` contains a stable, documented string that downstream callers can use
  for localization or analytics without depending on low-level driver errors.
- Even on database failures the service replies with HTTP 200 so the iOS client can
  decode the body without throwing transport-level exceptions.

When the database is unreachable the backend logs the stack trace but returns a safe
payload such as:

```json
{
  "ok": false,
  "data": [],
  "error": "backend DB unavailable",
  "friendly_error": "Failed to load today's symptoms"
}
```

## POST `/v1/symptoms`

Create a new symptom event for the authenticated user. When `ts_utc` is omitted
the service automatically stamps the current UTC time.

If `severity` is omitted, the backend now defaults it to `5` as the neutral
midpoint on the `1–10` symptom scale. This keeps quick logs and manual logs from
quietly biasing toward mild severity.

**Request body**

```json
{
  "symptom_code": "nerve_pain",
  "ts_utc": "2024-04-02T14:18:00Z",
  "severity": 4,
  "free_text": "Left arm tingling",
  "tags": ["flare", "post-run"]
}
```

**Normalization rules**

- Incoming codes are normalized before insert: trim whitespace, replace spaces/dashes
  with underscores, and uppercase the result (e.g., `"nerve pain" → "NERVE_PAIN"`).
- If the normalized value does not exist in `dim.symptom_codes`, the service maps it
  to `OTHER` (assuming the catalog contains an `OTHER` entry).
- After a successful insert, the backend immediately recomputes the affected user/day
  gauge row using the same local day boundary as the dashboard (`GAIA_TIMEZONE`,
  default `America/Chicago`).
- Opt-in validation: pass `?strict=1` to reject unknown codes instead of mapping.
  The server responds with HTTP 400 and a payload of the form:

  ```json
  {
    "ok": false,
    "error": "unknown symptom_code",
    "valid": ["HEADACHE", "NERVE_PAIN", "OTHER", ...]
  }
  ```

**Successful response**

```json
{
  "ok": true,
  "id": "7f3e85b1-67d6-4f83-9d63-2a0f1c0e7f6e",
  "ts_utc": "2024-04-02T14:18:00+00:00"
}
```

**Database error response**

```json
{
  "ok": false,
  "data": null,
  "error": "backend DB unavailable",
  "friendly_error": "Failed to record symptom event"
}
```

When the current-symptoms schema is present, creating a symptom event also opens or
reuses a live symptom episode so the event can evolve over time without mutating the
original onset record.

## GET `/v1/symptoms/codes`

Returns the catalog of symptom codes from `dim.symptom_codes` ordered by label.
Codes in the response are normalized to the uppercase underscore format so clients
can reuse them directly when posting events. Responses include a short cache header
(`Cache-Control: public, max-age=300`).

**Response**

```json
{
  "ok": true,
  "data": [
    {
      "symptom_code": "HEADACHE",
      "label": "Headache",
      "description": "Headache, head pain, or pressure",
      "is_active": true
    },
    {
      "symptom_code": "MIGRAINE",
      "label": "Migraine",
      "description": "Migraine attack, aura, light sensitivity, or migraine-specific head pain",
      "is_active": true
    },
    {
      "symptom_code": "NERVE_PAIN",
      "label": "Nerve pain",
      "description": "Pins/needles, burning, or nerve pain",
      "is_active": true
    }
  ],
  "error": null,
  "friendly_error": null
}
```

On transient database errors the endpoint still returns HTTP 200 with:

```json
{
  "ok": false,
  "data": [],
  "error": "backend DB unavailable",
  "friendly_error": "Failed to load symptom codes"
}
```

## GET `/v1/symptoms/today`

Return the events recorded for the signed-in user on the current UTC day. Events
are sorted by most recent first.

**Response**

```json
{
  "ok": true,
  "data": [
    {
      "symptom_code": "nerve_pain",
      "ts_utc": "2024-04-02T14:18:00+00:00",
      "severity": 4,
      "free_text": "Left arm tingling"
    },
    {
      "symptom_code": "headache",
      "ts_utc": "2024-04-02T07:10:00+00:00",
      "severity": 2,
      "free_text": null
    }
  ]
}
}
```

If the query cannot reach the database the response becomes:

```json
{
  "ok": false,
  "data": [],
  "error": "backend DB unavailable",
  "friendly_error": "Failed to load today's symptoms"
}
```

## GET `/v1/symptoms/daily?days=30`

Return aggregated counts for the last `days` worth of data (defaults to 30). Each
row represents a day/symptom-code tuple with the number of events, mean severity,
and the most recent timestamp.

**Response**

```json
{
  "ok": true,
  "data": [
    {
      "day": "2024-04-02",
      "symptom_code": "nerve_pain",
      "events": 2,
      "mean_severity": 3.5,
      "last_ts": "2024-04-02T14:18:00+00:00"
    },
    {
      "day": "2024-04-01",
      "symptom_code": "insomnia",
      "events": 1,
      "mean_severity": null,
      "last_ts": "2024-04-01T05:55:00+00:00"
    }
  ]
}
}
```

Failures respond with an empty list and a descriptive error string while keeping the
HTTP status at 200:

```json
{
  "ok": false,
  "data": [],
  "error": "backend DB unavailable",
  "friendly_error": "Failed to load daily symptom summary"
}
```

## GET `/v1/symptoms/current?window_hours=12`

Return the user’s currently active symptom layer for a recent window. The default
window is 12 hours and the endpoint excludes symptoms already marked `resolved`.

Each item preserves the original onset (`logged_at`, `original_severity`) while also
returning the latest live state (`new`, `ongoing`, `improving`, `resolved`), current
severity, note preview, likely drivers, and compact pattern context.

**Response**

```json
{
  "ok": true,
  "data": {
    "generated_at": "2026-03-23T12:00:00Z",
    "window_hours": 12,
    "summary": {
      "active_count": 1,
      "new_count": 0,
      "ongoing_count": 1,
      "improving_count": 0,
      "last_updated_at": "2026-03-23T11:45:00Z",
      "follow_up_available": true
    },
    "items": [
      {
        "id": "episode-uuid",
        "symptom_code": "HEADACHE",
        "label": "Headache",
        "severity": 7,
        "original_severity": 8,
        "logged_at": "2026-03-23T09:00:00Z",
        "last_interaction_at": "2026-03-23T11:45:00Z",
        "current_state": "ongoing",
        "note_preview": "Worse this afternoon",
        "note_count": 1,
        "likely_drivers": [],
        "pattern_hint": null,
        "gauge_keys": ["pain", "focus"],
        "current_context_badge": "Pattern match"
      }
    ],
    "contributing_drivers": [],
    "pattern_context": [],
    "follow_up_settings": {
      "notifications_enabled": true,
      "enabled": true,
      "notification_family_enabled": true,
      "cadence": "balanced",
      "states": ["new", "ongoing", "improving"],
      "symptom_codes": []
    }
  }
}
```

## GET `/v1/symptoms/current/timeline?days=14`

Return symptom evolution events for the recent timeline, including original logs,
state changes, severity adjustments, and note entries.

**Response**

```json
{
  "ok": true,
  "data": [
    {
      "id": "update-uuid",
      "episode_id": "episode-uuid",
      "symptom_code": "HEADACHE",
      "label": "Headache",
      "update_kind": "state_change",
      "state": "improving",
      "severity": 5,
      "note_text": "Improved after resting",
      "occurred_at": "2026-03-23T14:30:00Z"
    }
  ]
}
```

## POST `/v1/symptoms/current/{episode_id}/updates`

Persist a real update for a current symptom episode. This route never rewrites the
original symptom event; instead it appends a follow-up record that can change state,
adjust severity, add a note, or do all three at once.

**Request body**

```json
{
  "state": "resolved",
  "severity": 2,
  "note_text": "Passed after hydration",
  "ts_utc": "2026-03-23T15:10:00Z"
}
```

Successful updates also trigger the same-day gauge refresh path so improving and
resolved symptoms can reduce current symptom load.

## GET `/v1/symptoms/diag?days=30`

Diagnostic endpoint that mirrors the daily aggregation but only returns row counts
per code together with the most recent timestamp. Use this route during QA to verify
which symptom codes have data available.

**Response**

```json
{
  "ok": true,
  "data": [
    {
      "symptom_code": "nerve_pain",
      "events": 14,
      "last_ts": "2024-04-02T14:18:00+00:00"
    },
    {
      "symptom_code": "insomnia",
      "events": 6,
      "last_ts": "2024-03-30T05:55:00+00:00"
    }
  ]
}
}
```

In case of a database outage:

```json
{
  "ok": false,
  "data": [],
  "error": "backend DB unavailable",
  "friendly_error": "Failed to load diagnostic summary"
}
```

## Nightly refresh

A Render cron (or equivalent scheduler) should invoke the
`scripts/refresh_symptom_marts.py` helper each night. The script runs the
`marts.refresh_symptom_marts()` stored procedure to rebuild
`marts.symptom_daily` and related marts from the raw event table.
