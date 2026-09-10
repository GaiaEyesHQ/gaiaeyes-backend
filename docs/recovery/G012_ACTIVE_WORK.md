# G-012 — migraine calendar history

Status: **accepted_complete_local**, September 10, 2026 UTC. Independently accepted by the coordinator; [G-013 time correction](G013_ACTIVE_WORK.md) is now assigned. Sole writer: **Audit Gaia Eyes project state**, task `01a074da-1e28-7772-92b7-2b0163664c13`.

Coordinator accepted G-011 including G-R19 as bounded local implementation before dispatching this increment. The accepted [G-011 evidence](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g011-gr19/HANDOFF.md) and [report snapshot](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g012-calendar-history/accepted-g011-report.json) remain preserved. Their original review-pending wording is historical; the coordinator's subsequent acceptance is recorded separately in this packet.

## Current implementation

- The authenticated `/v1/symptoms/migraine/history` reads canonical episodes by a bounded UTC range with keyset pagination. It preserves the existing update timeline. The [API contract](../symptoms_api.md#migraine-calendar-history-g-012-localdefault-off) defines exclusive range ends, cross-day overlap, unknown/open ends, cursor/account binding and refresh after concurrent change.
- Each SQL statement computes a matching-set fingerprint and a page under the same database snapshot. Subsequent pages reject changed sets with 409. Fingerprinting scans matching canonical rows on each page; the existing owner/start index narrows the candidates. This is a completeness tradeoff, not a constant-cost snapshot system or a production performance certification.
- The existing iOS symptom history links to a month/day calendar when explicitly enabled in Debug. It retains non-migraine history, displays local timezone context, distinguishes empty from incomplete/error data, and opens the existing editor with the selected canonical ID.
- Loading rejects stale account/month generations and checks account scope around authorization awaits. Editing refreshes history after acknowledgement and return. Save inputs and sheet dismissal remain protected while a request is pending.
- Backend activation defaults off (`GAIA_MIGRAINE_CALENDAR_ENABLED`); iOS activation defaults off and is unavailable in Release. No deployment, remote database action, app release, account change, dependency addition or personal export handling is part of G-012.

## Verified handoff

[Complete handoff, changed files, commands and review steps](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g012-calendar-history/HANDOFF.md).

- Fourteen disposable PostgreSQL/API tests and three existing API compatibility tests passed. The actual backend JSON exactly matches the Swift fixture. Ownership, deterministic pagination, concurrent-change handling, overlap semantics and the existing index are covered with synthetic data.
- The primary iPhone checkpoint passed 40 methods / 66 cases. Final-source smaller-iPhone verification passed 23 methods / 34 cases: 19 model cases, nine actual calendar UI flows and six historical-save cases.
- Smaller-phone testing found a severity Stepper that could change after offscreen rows were recreated during a held save. A guarded severity binding now rejects changes while either save is pending. Tests confirm the actual pending state, attempt both controls, and verify editing resumes after success, conflict or cancellation. Individual input locks remain; scrolling stays available.
- The final arm64 Release simulator build passed. Eight Debug fixture/control markers are absent from its binary; default-off and Release opt-in rejection are tested. No physical-device, VoiceOver, Dynamic Type or live-service acceptance is claimed.
- Source hashes, original-source delta, failed/repaired run history, logs, result bundles, screenshots and reproduction commands are preserved in the handoff. No unresolved local finding remains in this increment; the coordinator owns acceptance.

## Remaining committed work

Explicit episode onset/end correction is still missing. The next contract must preserve original/provenance values, validate start/end ordering and timezone intent, require the expected revision, handle conflict/retry, and atomically update canonical history/audit and derived refresh. Browsing dates and backdating new logs do not complete that commitment.

Android and member-hub parity are intentionally deferred for this local iOS increment. D028 continues to place logging, follow-up, medication, editable events and calendar before imports without a new order among those core tasks. Reports and prior release-dependent outreach remain committed. No provider sample was opened or parsed.
