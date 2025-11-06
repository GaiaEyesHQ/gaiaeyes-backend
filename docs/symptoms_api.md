# Symptoms API

This document outlines the REST endpoints that power the Gaia Eyes symptom logging
experience. The routes live under the `/v1/symptoms` prefix and require a valid
Bearer token. During development you can supply the `DEV_BEARER` token together
with an `X-Dev-UserId` header to impersonate a user.

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
  "raw_error": null,
  "friendly_error": null
}
```

- `ok` is `true` when the request succeeded and `false` on failures.
- `data` is always present. Collection endpoints return an array (possibly empty). The
  POST route returns either the created event payload or `null` on errors.
- `error` carries the documented fallback string to present to users and analytics
  pipelines.
- `raw_error` captures the original database/driver message so internal tooling can
  inspect the root cause without surfacing it to end users.
- `friendly_error` currently mirrors `error` for backwards compatibility while clients
  migrate to the richer contract.
- Even on database failures the service replies with HTTP 200 so the iOS client can
  decode the body without throwing transport-level exceptions.

When the database is unreachable the backend logs the stack trace but returns a safe
payload such as:

```json
{
  "ok": false,
  "data": [],
  "error": "Failed to load today's symptoms",
  "raw_error": "backend DB unavailable",
  "friendly_error": "Failed to load today's symptoms"
}
```

## POST `/v1/symptoms`

Create a new symptom event for the authenticated user. When `ts_utc` is omitted
the service automatically stamps the current UTC time.

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
  "error": "Failed to record symptom event",
  "raw_error": "backend DB unavailable",
  "friendly_error": "Failed to record symptom event"
}
```

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
      "description": "Headache or migraine",
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
  "raw_error": null,
  "friendly_error": null
}
```

On transient database errors the endpoint still returns HTTP 200 with:

```json
{
  "ok": false,
  "data": [],
  "error": "Failed to load symptom codes",
  "raw_error": "backend DB unavailable",
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
  "error": "Failed to load today's symptoms",
  "raw_error": "backend DB unavailable",
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
  "error": "Failed to load daily symptom summary",
  "raw_error": "backend DB unavailable",
  "friendly_error": "Failed to load daily symptom summary"
}
```

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
  "error": "Failed to load diagnostic summary",
  "raw_error": "backend DB unavailable",
  "friendly_error": "Failed to load diagnostic summary"
}
```

## Nightly refresh

A Render cron (or equivalent scheduler) should invoke the
`scripts/refresh_symptom_marts.py` helper each night. The script runs the
`marts.refresh_symptom_marts()` stored procedure to rebuild
`marts.symptom_daily` and related marts from the raw event table.
