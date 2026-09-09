# Gaia Eyes — requested migraine update reconciliation

Reconciled **2026-09-07** from current main, the detached `a9cf` iOS worktree, backend symptom/follow-up code, and the personalization roadmap. This document records implementation state; it does not claim that local source is in TestFlight or the released App Store build.

## Owner-directed release sequence

Migraine-focused community outreach remains deferred until an update ships with all five requested priorities:

1. voice-logging tweaks;
2. follow-up;
3. medicine logging;
4. reports;
5. import from other migraine apps.

All five remain priorities. “Ships” requires reviewed source, relevant automated checks, physical acceptance, and the normal release/submission process. A roadmap entry or local build is not release evidence.

## Current implementation matrix

| Priority | Current status | Existing evidence | Missing before the requested update is complete |
|---|---|---|---|
| Voice logging tweaks | **Source delta reconciled; physical acceptance pending** | Main `HandsFreeSymptomLogger.swift` has background start/stop App Intents, default severity 5, authenticated canonical submission, offline queueing for starts, duplicate protection, refresh notifications, analytics, expanded natural stop phrases, truthful offline/unconfirmed/failure results, and latest-active-migraine selection. A clean isolated run passed 13 focused tests with exit 0, and a generic iOS Debug build succeeded on 2026-09-07. | Complete the physical Siri phrase matrix, including the known Gaia Eyes-versus-Health routing ambiguity, and verify the accepted release build separately from local source. |
| Follow-up | **Local iOS client integrated; inactive pending review/deployment** | G-011 extends the existing iOS follow-up sheet/models/API payload for optional early signs, medicine/relief, and notes, plus later editing from symptom history. It preserves drafts on errors/conflicts, scopes drafts to the signed-in account, reuses stable retry timestamps, and requires structured readback for ambiguous save recovery. The path is Debug-only and explicitly gated. | Review the local interaction, deploy the accepted G-010 migration/backend through the normal release path, then run authenticated device tests for reminder preference, snooze/dismiss, account isolation, and network failure/retry behavior before activation. Context/exposure selection remains a later UI addition; the contract already supports it. |
| Medicine logging | **Local iOS capture/edit integrated; inactive pending review/deployment** | G-011 captures medicine name/time, optional dose/unit, and explicit relief in the existing follow-up UI. It keeps missing medicine distinct from “No medicine taken,” and unknown relief distinct from “No relief.” Unchanged values retain stored state and explicit clears remain explicit. | Complete authenticated device testing against the deployed capability before enabling it. Do not reinterpret the generic `New supplement or medication` exposure as proof that a medicine was taken or effective. A reusable personal medicine list can follow the canonical episode record. |
| Reports | **Partial; history exists, migraine report does not** | iOS has a symptom timeline and historical symptom editor; Gaia Eyes also has general pattern/history surfaces. | Build a user-readable migraine episode summary/history from the structured follow-up and medicine model, then add the explicitly chosen share/export form. Do not label a generic timeline a physician report or imply causal conclusions. |
| Import from other migraine apps | **Provider-neutral design only; provider adapters blocked** | The roadmap defines a canonical episode/import contract, provenance, preview, validation, idempotency, de-duplication, reversible import runs, and import-specific deletion. HealthKit history import is separate. | Implement the generic Gaia CSV template/parser/preview with synthetic fixtures. Migraine Buddy, Bearable, and other provider adapters require representative redacted current exports and permitted-use/format review. No provider compatibility should be promised before that evidence exists. |

## Dependency-aware implementation order

1. **Voice delta:** locally reconciled on 2026-09-07; physical Siri and release acceptance remain.
2. **Canonical migraine episode detail contract:** define early signs, context, medicine/relief, notes, timing, edit history, provenance, and deletion behavior once so follow-up, reports, and imports share one model.
3. **Structured follow-up plus medicine capture:** extend the existing follow-up scheduler/API/UI rather than creating a parallel reminder system.
4. **Migraine history/report:** render the canonical episode data with honest missing fields and non-causal language; decide the first share/export format as a bounded follow-up.
5. **Generic import foundation:** Gaia CSV template, local parsing, preview, row errors, de-duplication, reversible commit, and synthetic tests.
6. **Provider adapters:** add one at a time only after redacted real-format evidence, beginning with Migraine Buddy and Bearable as previously prioritized.
7. **Release acceptance:** automated checks, iPhone physical phrase/follow-up/import tests, privacy/retention review for imports, App Store metadata, and explicit submission approval.

## G-006 voice-delta disposition

- **Already present and preserved:** background start intent, severity-5 canonical payload, authenticated submission, queued offline start writes, duplicate protection, refresh/analytics behavior, start/end support, account isolation through the current token, and selection of the most recently logged active migraine.
- **Ported selectively from `a9cf`:** clearer “stop” wording and six additional natural stop phrases. G-007 then split actual `notConnectedToInternet`, transport failures with an unconfirmed result, and generic failures so Siri does not claim success or definite non-persistence without evidence.
- **Rejected:** the alternate generic resolver's first-match behavior because it could resolve an older active migraine; unrelated Home personalization changes; blanket cherry-picking of the dirty detached worktree; and an unnecessary intent-type rename.
- **Automated evidence:** the original G-006 run printed 24 pass lines for 12 distinct cases and then exited 134 on a simulator `launchSession` assertion; that failing-run evidence remains preserved. G-007 ran one bounded retry with parallel testing disabled and an isolated result bundle: 13 tests in two suites passed once, `xcodebuild` exited 0, and the result bundle is `/tmp/gaiaeyes-g007-focused-1788825048.xcresult`. The separate generic iOS Debug build also succeeded and generated App Intents metadata.

## Shared episode foundation

G-007 added the local provider-neutral typed model, validator, mapping document, and two synthetic fixtures described in [MIGRAINE_EPISODE_CONTRACT.md](../contracts/MIGRAINE_EPISODE_CONTRACT.md). It covers existing episode/event linkage, UTC and original timezone provenance, early signs, context/exposures, user-entered medicine and reported relief, notes, revision/deletion state, and reversible import provenance. Focused Python checks pass. It does not add persistence, routes, client UI, a real import parser, or provider compatibility.

G-008 added a local, unapplied additive persistence migration and repository.
The existing symptom event/episode remains canonical; structured details use
optimistic revisions plus atomic audit snapshots. Import runs and links retain
preview/commit/reversal provenance while clinical de-duplication is independent
of file hash and run ID. A durable identity registry survives reversal when an
episode is retained, and repeat commits reuse existing detail without
overwriting user edits. Reversal preserves another run's link, structured edits,
and every non-import note/state/follow-up recorded through the existing
canonical symptom update table regardless of its reported timestamp or linked
run order. Reversal deletes a canonical onset only when durable origin evidence
shows that the same import lifecycle created both canonical rows with the exact
`import:<run-id>` source; a pre-existing manual episode or missing proof is
preserved. This proof is derived during commit, not accepted as a caller
boolean. Focused scripted-repository tests pass, but they do not prove real
database rollback or concurrency. The disposable local
pgTAP RLS suite was written but could not run in that slice because
Docker/Podman was unavailable. At the end of G-008 there was no applied
migration, route, client UI, parser, or provider claim.

G-010 extends that same repository into the existing authenticated symptom
workflow. It adds owner-filtered migraine-detail read/edit routes and an
optional nested structured payload on the existing follow-up response; legacy
follow-up requests still work when the unapplied detail migration is absent.
Canonical state/note projection, detail snapshot, revision audit, and prompt
changes are atomic, and affected-user gauge refresh is deferred until commit.
Omitted fields retain stored values, explicit empty lists clear list fields,
and explicit null clears notes; missing medicine/relief remains distinct from
an explicit negative report. Exact retries are idempotent and stale conflicting
edits fail without duplicating medicine entries or erasing newer data. The
request transaction now closes the dependency's settings-only transaction,
owns the outer write transaction, and commits before refresh. Structured prompt
responses serialize the episode/detail revision and prompt row, including
concurrent identical retries. Returned canonical note preview/count is reloaded
after structured note projection and explicit clear.

The reusable `scripts/run_migraine_postgres_tests.sh` runner builds/uses a
user-local PostgreSQL 17 runtime, creates a private disposable Unix-socket-only
cluster, rejects non-test/remote DSNs, verifies a disposable marker after
connection, preserves exact logs, and tears the cluster down. The accepted
G-010 review-verification run passed 63 tests, including request-shaped
sequential/concurrent retries, committed visibility from the refresh
connection, projected note save/clear readback, forced detail-audit rollback,
and deferred outer-commit failure rollback without refresh. No
hosted migration, deployment, client activation, or real user data was used.

## Next-ready implementation slice

G-011 completed the bounded local iOS integration through the existing
`APIClient.respondSymptomFollowUp`, `SymptomFollowUpResult` model,
`CurrentSymptomFollowUpSheet`, and historical symptom editor. The next step is
review and release sequencing: accept G-010/G-011 together, apply the additive
migration and backend route through the normal controlled process, then test an
authenticated Debug client against that capability before any activation.
Android parity, website/member-hub presentation, reports, context/exposure UI,
and generic import parsing remain later consumers of the same model.

## Explicit blockers and non-blockers

- Provider-specific import adapters are blocked by missing representative redacted exports and format/permission evidence. The provider-neutral contract, template, parser, preview, and synthetic tests are not blocked.
- Import reversal persistence has passed a disposable PostgreSQL 17 database test, including both two-run reversal orders, import-origin deletion, manual and backdated-user-history retention, rollback, and competing connections. End-to-end provider import remains blocked until the future generic importer creates canonical event/episode rows with the reviewed `import:<run-id>` origin source inside the same outer transaction as commit. Ambiguous origin intentionally preserves data.
- Physical Siri and release verification remain required, but they do not block local source/test work.
- Community outreach is intentionally deferred; it is not waiting on Jennifer to supply another group or repeat the existing statistics.
- `Space Weather News - Global` and the owner-supplied 8,800 views / 163 likes / 83 comments / 15 shares are channel evidence only. They do not establish unique viewers, installs, a time window, or repeatability and do not authorize another campaign.
