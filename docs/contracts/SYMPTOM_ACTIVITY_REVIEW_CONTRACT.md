# Symptom activity and earlier-entry review

This additive contract separates recorded observations from confirmed ongoing episodes. An unresolved legacy state does not prove that a symptom is still occurring. Reads never resolve, reopen, rewrite, or backfill an episode.

| Canonical record | Activity | Current presentation | Calendar duration |
| --- | --- | --- | --- |
| Resolved | `resolved` | History | Recorded interval, or onset day when end is unknown |
| Non-migraine `new` / raw point | `recorded` | Recently logged | Onset/log day only |
| Unresolved migraine or non-migraine ongoing/improving/worse, without confirmation | `needs_review` | Earlier symptoms need review | Onset day only; duration unknown |
| Same ongoing states with confirmation | `active` | Confirmed active until explicitly ended/resolved | Onset through current time |

Confirmation is an owned audit update with `metadata.activity_contract = persistent_v1`. A newly inserted canonical episode receives it. Retrying an old raw event does not add it. An intentional state response/review or time-editor state change adds it; a note, severity report, detail edit, or onset-only correction does not. Age, migration timestamp, source name, and earlier state words are insufficient provenance. Consequently, even a recent pre-contract log may need one review. No guessed historical end times or bulk health-data mutation is part of this change.

`GET /v1/symptoms/current` keeps `items` and `summary` for confirmed activity and adds `review_items` and `recorded_items`. Each item adds `activity_status` and an exact `updated_at` revision string. Same-code episodes retain independent identities. The history API adds activity status; only confirmed active records receive `end_status=open`. Missing status from an older server must not be inferred as active by new clients.

`POST /v1/symptoms/current/{episode_id}/status-review` accepts:

```json
{
  "request_id": "77777777-7777-4777-8777-777777777777",
  "expected_updated_at": "2026-09-10T04:00:00.123456+00:00",
  "decision": "resolved",
  "reported_at": "2026-09-12T12:00:00Z",
  "ended_at": null
}
```

The other decision is `ongoing`. No choice is preselected. A known end must be between onset and review time. An absent end with `resolved` leaves `resolution_ts` null and records review time separately in audit metadata. Review does not edit a previously resolved episode; the explicit time editor handles those corrections. The transaction locks the owned episode and checks `updated_at`. Stale decisions return 409. Retries keep their request ID, revision, timestamps, and decision. A replay returns the latest authoritative item, so it never overwrites a later intentional change. Reminders use that latest state.

The iOS and website flows preserve the pending request on an uncertain receipt and offer exact retry or explicit reload. Confirmed resolution removes the active/review card but preserves history. Unknown records are excluded from active reminders, active labels, and continuous calendar spans. Existing pending prompts are also filtered at delivery selection.

## Pain gauge semantics

Pain is estimated load on a 0–100 scale, with a model baseline of 20. Reported symptom severity is a separate 0–10 observation. The baseline, weights, and established dashboard floors are unchanged.

Current scoring uses the latest explicit severity report and its time, with rolling 24-hour freshness across midnight. Notes do not make an older severity fresh; `worse` is supported. Missing and zero severity add no inferred pain. Raw and canonical copies count once, and an empty decayed boost is not reconstructed. Current resolved and unconfirmed legacy episodes do not contribute as active symptoms.

Historical local-day/DST boundaries remain intact. Historical scoring retains observations and state at the report even if the episode was later resolved or remains unreviewed today. The initial logged severity follows a corrected canonical onset, while later severity observations keep their own timestamps. Raw source timestamps stay unchanged.

Status-review and current-update save acknowledgements are independent of expensive scoring; create, detail and follow-up routes retain their existing awaited scoring behavior. A subsequent `GET /v1/dashboard?refresh_symptoms=1` bypasses stale dashboard cache, completes a rescore before building its response, and can report refresh failure independently of the saved episode. Mutation scoring and this refresh share the process-local dashboard lock. Cross-worker scoring overlap remains a deployment consideration; no distributed locking change is included.

## Review and release

Jennifer approved this policy on October 20, 2026: offer a one-time, deliberate review of entries with unconfirmed status, retaining an unknown end when she chooses ended without a known time. After confirmation, keep the active-episode card available until explicitly ended/resolved; ongoing, improving and worse updates retain activity. Foreground activation refreshes the data; it does not present an additional reopening check-in popup. The review remains available from an explicit tap, with no preselected answer. This product approval does not authorize publication, deployment, or installation.

This contract requires coordinated backend/client review. Validate old and newly logged episodes, same-code multiples, known and unknown ends, same-request retry, stale-version conflict, timezone boundaries, historical start correction, and account replacement using synthetic fixtures. Keep user screenshots private. No migration, production record rewrite, automatic end, publication, or device installation is implied by this document.
