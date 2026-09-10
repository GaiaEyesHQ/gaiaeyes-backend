# G-013 — saved migraine start/end correction

Status: **review_ready — local verification complete**, September 10, 2026 UTC. Sole writer: **Audit Gaia Eyes project state**, task `01a074da-1e28-7772-92b7-2b0163664c13`. Independent coordinator acceptance remains separate.

G-012 is accepted locally. Its handoff, report, acceptance and 17 source hashes are preserved and verified in the [G-013 handoff](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g013-episode-time-editing/HANDOFF.md). This increment corrects canonical saved onset/end, rather than update occurrence time or a newly backdated log.

The [time-correction contract](../contracts/MIGRAINE_TIME_CORRECTION_CONTRACT.md) defines explicit retain/set/clear/state behavior, strict timezone/DST handling, owner/revision/canonical-token protection, exact retry, source-preserving revision audit, atomic reminders and post-commit refresh. The existing iOS editor uses matching receipts, explicit recovery, preserved notes/medicine drafts and shared save/Done guards, including recreated severity controls. Corrected episodes appear on the appropriate calendar days/months.

Verification: **102 backend cases** (39 actual disposable PostgreSQL, 63 contract/mocked API/bot checks); **66 Swift model/store cases and 12 actual UI journeys** (8 new time-editor cases, 4 retained save/calendar compatibility cases). Final UI checks used iPhone 17e/iOS 26.5 and verified visible bounds before interacting. Actual backend JSON ↔ Swift request normalization passed. An unsigned arm64 Release simulator build passed; Debug fixture markers were absent. See the [verification summary](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g013-episode-time-editing/verification-summary.json) for exact evidence, commands and limitations.

Backend and iOS activation remain default off; iOS remains unavailable in Release. No deployment, production SQL, private provider samples, accounts, social-watch edits or new dependencies. Android/member-hub time-edit parity and physical-device/release acceptance remain. The legacy symptom_x_space_daily materialized reporting artifact retains original-event semantics; report integration and realistic historical refresh performance remain explicit follow-on work.

D028 is unchanged: core logging/follow-up/medication/editable events/calendar precede imports, without a new order among those five. Reports and release-dependent outreach remain committed. This handoff does not certify the entire migraine release or dispatch importer work.
