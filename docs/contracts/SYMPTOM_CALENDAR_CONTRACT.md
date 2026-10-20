# Shared symptom calendar and explicit migraine preference

Follow-up to the migraine active-flow correction; the approved original PR head does not include this follow-up until separately published.

## Availability and preference

- The iOS Home, Symptoms, and Timeline entry is **Symptom calendar**, available independently of condition selections and migraine build flags.
- Basic `MIGRAINE` logging remains in the ordinary symptom picker for everyone. A migraine log never enables advanced tools.
- Enhanced migraine Home, guide, summary, structured detail, time editing, and the post-log exposure prompt require the acknowledged profile tag `migraine_history`, as selected in onboarding (Migraines) or saved Personal Context. The existing build capability still applies.
- The existing authenticated `/v1/profile/tags` GET/PUT is the authority. No parallel preference or migration is introduced. Unknown preferences default off. Unsaved selections or failed save acknowledgements do not enable the feature. Removing the choice hides tools and preserves stored episodes/drafts.
- Preference receipts are bound to account and request generation. Calendar pages and open editors reject stale accounts. Advanced saves validate access again after authentication and before accepting responses.
- The saved preference controls iOS product eligibility and presentation. It is not a server authorization boundary: existing authenticated API clients retain their owner-scoped access. Basic active-state actions, including explicit resolution, remain available after opt-out.

## Read-only range endpoint

`GET /v1/symptoms/history?start=<aware ISO>&end=<aware ISO>&limit=50&cursor=<optional>`

Authentication determines the owner; a caller cannot choose another user. Range is half-open, increasing, and at most 62 days; limit is 1–100. The legacy `/v1/symptoms/migraine/history` endpoint and its flag remain unchanged for old clients. The new endpoint does not depend on `GAIA_MIGRAINE_CALENDAR_ENABLED`.

The page envelope retains `start`, `end`, `as_of`, `snapshot`, `next_cursor`, `complete`, and `items`. Each item adds `record_kind` (`episode` or `event`), `symptom_code`, and `label` to the existing ID, onset, end, state, severity, and note preview. Identity is `(record_kind, id)` because UUIDs belong to separate tables.

- Canonical episodes come from `raw.user_symptom_episodes` for every symptom code. Their source raw events are excluded from the legacy union. Updates do not multiply calendar entries.
- Raw-only logs are retained as `event` records with `end_status=instant`, on their logged local day. Opening one shows a read-only detail; no episode is invented or backfilled.
- Non-migraine `new` records are points (`instant`) until an explicit ongoing/improving/worse state or recorded end establishes a duration. An unresolved canonical migraine is open until explicitly resolved.
- A recorded end is exclusive of the following day. A resolved episode without a valid recorded end remains `unknown`, shown on its onset day without inferring an end from its last interaction.
- Day/month boundaries use the selected device timezone and Calendar date arithmetic, including DST days. Open intervals stop at the page's fixed `as_of`; a 23/25-hour day is not treated as 24 hours.
- Pagination sorts by `(started_at, id, record_kind)` descending and binds the cursor to owner, range, calendar kind, and snapshot. Mid-pagination changes return 409. Errors never become a successful empty calendar.

## Release coordination

Deploy the reviewed backend endpoint before distributing the matching client. Existing canonical symptom storage is required; no new SQL migration, flag change, production backfill, or data mutation is part of this work. Old servers produce a visible unavailable/error state. Enhanced details/time editing still need their separately reviewed existing migrations and capability flags. No release operation is authorized by these local changes.

The shared backend is usable by the website. The new calendar UI and condition gating are iOS changes; website/member-hub UI parity is deferred explicitly and must be reviewed if an equivalent calendar is shipped there. Fibromyalgia, ME/CFS, and POTS flows remain deferred.


Activity clarification: [Symptom activity and earlier-entry review](SYMPTOM_ACTIVITY_REVIEW_CONTRACT.md) supersedes treating every unresolved state as an open duration. Unconfirmed records remain on their recorded onset day until reviewed.
