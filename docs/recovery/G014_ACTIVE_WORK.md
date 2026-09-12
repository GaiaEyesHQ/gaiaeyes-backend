# G-014 — edit any saved medicine entry

Status: **accepted_complete_local**, September 11, 2026 UTC. The coordinator recorded independent [G-014 acceptance](/Users/gennwu/Documents/Codex/2026-09-06/turn-my-astra-strategy-planning-conversation/outputs/jennifer-os-starter-kit/operations/checkpoints/20260911-G-014-acceptance.json). G-015 scoring batch-date compatibility is a separately dispatched continuation. Sole writer: **Audit Gaia Eyes project state**. G-013 was independently accepted locally in [the acceptance receipt](/Users/gennwu/Documents/Codex/2026-09-06/turn-my-astra-strategy-planning-conversation/outputs/jennifer-os-starter-kit/operations/checkpoints/20260910-G-013-acceptance.json). Deployment and device acceptance remain separate.

## Draft/list contract recorded before implementation

The shared follow-up/history medicine component will expose every saved entry, select any entry, add separate entries and remove one selected entry. Draft rows have local UUID identities; no backend ID, sorting or deduplication is added. Stored array order and all untouched original values remain authoritative. Repeated names/times remain separate rows. Selection changes retain raw unsaved text, including invalid input, for later correction.

An entry's fields retain its original timestamp/provenance, exact decimal, optional relief/relief timestamp and note whenever untouched. Missing relief, explicit unknown and explicit no relief remain distinct. Individual removal changes the local draft only; the parent save must be acknowledged before any server deletion is described as saved. Whole-list clearing remains an explicit separate choice. An empty draft does not by itself claim that the user took no medicine.

The full changed array uses the existing expected revision and acknowledgement contract. All list/field actions share parent save and account guards. G-R23 preserves exact pending structured requests; uncertainty never rebases an add. Separate legacy note and time acknowledgements may advance only their established baselines while retaining unsaved medicine rows. Follow-up retries must retain the whole submitted response, including list edits, until confirmed or deliberately resolved.

After a definitive conflict, explicit reload can rebase only when the affected original entries can be matched unambiguously. Match recorded identity/context conservatively and preserve canonical order, untouched latest metadata and local row identity. Ambiguous external removal/identity changes retain the original draft for deliberate review; never guess an edited row from an array index alone.

## Verification and boundaries

Use synthetic arrays with at least three entries, repeated names/times, middle/last edits, two additions, one removal, invalid name/dose correction, optional/unknown/no-relief preservation, exact payload/ack comparison and stable row identities. Exercise actual shared UI in follow-up and history, including held requests, conflict/lost-response/cancellation/account behavior and time correction with unsaved medicine changes. Recheck affected Release boundaries and record failed/passing evidence separately.

No personal catalog, dose guidance, reminders, new dependencies, backend/schema changes, production SQL, deployments, account work or exports/imports. Android/member-hub parity is intentionally deferred. D028 and reports/outreach commitments remain. Only the coordinator updates portfolio registers.

## Local verification completed

The shared component now edits any saved entry and retains pending changes through selection, multiple additions and individual removal. Exact whole-request recovery, account isolation and conservative explicit conflict review preserve the accepted G-R23 behavior. Empty-name wording, populated-note accessibility and historical Form button-action isolation were repaired during actual UI testing.

**62 model/workflow cases, 12 new actual editor journeys and three compatibility journeys passed.** The broad mixed bundle contained 60 passing model/workflow cases and two failed UI journeys; two additional model cases passed later. Unique UI passes span the recorded repaired runs, with all five final affected reruns passing. Earlier failed bundles remain preserved.

All 12 UI scenarios passed independent full-array assertions; 17 actual UI request bodies passed the existing backend normalization/matcher/patch contract. Five earlier workflow scenarios/ten bodies also passed. No unchanged PostgreSQL suite was rerun. The unsigned arm64 Release build and 11 Debug fixture-marker exclusions passed. Five actual smaller-phone screenshots were inspected; full Dynamic Type, VoiceOver and physical-device acceptance remain separate.

The [review handoff](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g014-medicine-entry-editing/HANDOFF.md) links the scoped diff, before/after source hashes, commands, captures, screenshots and failed-run ledger. Local UUIDs and pending requests are in memory for the open editor; no durable queue or persistent entry IDs were introduced. Existing Swift Decimal decoding is unchanged; unsupported overprecise new input is rejected. G-014 does not complete the overall migraine release or authorize imports. Governing acquisition/product/research strategy is unchanged.
