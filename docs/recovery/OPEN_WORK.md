# Gaia Eyes — open work

Reconciled 2026-09-06 UTC. **No implementation changes were made in this audit.** IDs are for handoff continuity; priority is defined in [RECOMMENDED_NEXT_ACTIONS.md](RECOMMENDED_NEXT_ACTIONS.md). Category labels distinguish user value from exploration.

**Strategy corrected September 6:** acquisition/engagement growth and reduced founder workload proceed alongside product and research/medical development. Revenue is measured context, not a feature-development gate. Older blanket pauses are withdrawn. See the four corrected strategy files before prioritizing this backlog.

## In Progress

| ID / category | Actual stopping point | Next bounded step / acceptance |
|---|---|---|
| W01 — CORE VALUE / RELIABILITY: iOS update | Main builds; local version 1.0.1 build 8; release contents/signing/TestFlight not verified | Reconcile selected changes and prepare one explicit release checklist. Physical HealthKit/account-switch/Siri/paywall/push checks before submission |
| W02 — CORE VALUE: Siri migraine work | Detached `a9cf` voice changes were selectively reconciled into main on 2026-09-07. Natural stop phrases, truthful offline/unconfirmed/failure results, latest-active-migraine selection, auth, duplicate protection, and queued offline starts now have a clean isolated 13-test run with exit 0; generic iOS Debug build succeeds. The prior duplicate-pass/exit-134 Xcode runner failure remains recorded | Complete the physical Siri phrase matrix, including Gaia Eyes-versus-Health routing, and verify the accepted release build before calling the feature shipped |
| W03 — CORE VALUE / ACQUISITION / ACCESSIBILITY: Android | Native app builds and imports Health Connect data; no store release; billing placeholders. A completed-account bootstrap patch now avoids onboarding-only location/tag fetches after required preferences load; local tests/build pass, with repeated physical timing still required | Complete Samsung cold-reopen timing and new-user onboarding regression, then continue product/parity and account/device acceptance; complete purchase/restore for the agreed v1 scope. Current Plus conversion is not a gate on Android development |
| W04 — GROWTH EXPERIMENT: social text normalization | Main has pre-existing modifications to `bots/earthscope_post/gaia_eyes_viral_bot.py` and its stats test, plus Sept 4/6 temporary social audit folders | Review/test the existing small dash/whitespace change; do not overwrite it or add another writer rewrite |

## Ready for focused follow-up

**Prepared optional experiment:** G-002 completed drafts for one bounded migraine/weather-pattern Facebook-group pilot at [growth-prep/2026-09-07/PILOT_PACKET.md](growth-prep/2026-09-07/PILOT_PACKET.md). The structured pilot is an AI proposal, remains unselected, and is not committed Gaia work waiting on a group choice. Jennifer has now deferred migraine-focused outreach until the requested update ships with voice-logging tweaks, follow-up, medicine logging, reports, and import from other migraine apps; see [MIGRAINE_UPDATE_RECONCILIATION.md](MIGRAINE_UPDATE_RECONCILIATION.md). G-003 added a synthetic-only local [cohort report handoff](growth-prep/2026-09-07/PILOT_COHORT_REPORT.md); G-004 now limits its activation/return metrics to qualifying iOS events and prevents report output from replacing an input or existing checkpoint. `Space Weather News - Global` and its owner-supplied response metrics are prior channel evidence, not authorization for a new campaign. Nothing was posted, queried from production, or deployed.

| ID / category | Evidence / task | Done when |
|---|---|---|
| W05 — COMPLIANCE / PRIVACY | Anonymous personal-view access and entitlement mutation grant; exact findings in recovery audit | Consumer/grant inventory, staged own-user/other-user/anonymous/service tests, reviewed migration/rollback and approved containment; provider entitlements reconciled |
| W06 — RELIABILITY | Five actionable gauges still lag newer same-day inputs after repoll | Explain per-user refresh path and input-hash/eligibility behavior; targeted regression; complete eligible cohort current after observed successful cycle |
| W07 — RELIABILITY | Member writer UUID repair now produces current rows for all current Plus identities | Mark historical incident recovered for current delivery; separately decide whether any missed historical member days need a controlled backfill |
| W08 — RELIABILITY | Aurora staging TS assertion and WP publish failures | Read exact job errors/config, identify user-facing impact and propose minimal fix. No job re-run as diagnosis |
| W09 — INFRASTRUCTURE | DRAP ~29.9 GB; primary DB ~39.4 GB | Attribute table growth, consumers, retention and invoice charges; review an optimization plan with reversible validation |
| W10 — MEASUREMENT | iOS analytics exists but sessions/accounts are not a conversion/retention funnel | Minimal event/identity/privacy spec; staging QA; acquisition cohort and meaningful-activation/return report with test accounts excluded |
| W11 — COMPLIANCE / PRIVACY | Live privacy page renders shorter fallback; Health Connect/AI/retention/deletion detail incomplete | Compare actual data flows with approved policy/store declarations; prepare a reviewable draft and deployment-path fix; human approval before publication |
| W12 — RELIABILITY | AppAnalytics logs properties, global queue; no dedicated crash integration found | Test account-switch buffering/redaction; define diagnostics retention and support export consent. Assess store crash tools before adding another paid service |
| W13 — RELIABILITY | Local cache refreshed while embedded weather observation lags; pollen missing for tested ZIP | Attribute source/coverage vs cache age; enforce honest timestamps/unavailable presentation without inventing readings |

## Blocked — human or external acceptance required

| ID | Blocker | Work that can continue |
|---|---|---|
| W14 — Revenue / costs | Stripe/RevenueCat/App Store and vendor invoice data unavailable | Prepare reconciliation template, calculate bounds from grants, inspect config/usage; do not call grants revenue |
| W15 — Production verification | Render requires sign-in; admin analytics bearer missing in monitor | Source/schedule/read-only public/DB checks; actual cron/deploy/error-log certification remains open |
| W16 — Mobile release | Device QA, signing/account dashboards and final release approval | Local tests/builds, metadata/release-note drafts and acceptance matrix |
| W17 — Android enrollment | Jennifer has not created Google Play account; DUNS ready | Organization checklist, legal-name consistency and required app declarations; no enrollment/payment initiated |
| W18 — Apple LLC conversion | Account holder request and business identity verification | Prepare membership-conversion checklist, preserve app/bundle/product continuity |
| W19 — Historical migraine import | Provider-neutral episode model plus a local, unapplied additive persistence migration/repository now exist. Focused scripted-repository tests cover idempotent replay, both linked-run reversal orders, backdated user updates, manual re-link retention, and positive import-origin gating; real rollback/concurrency and the disposable pgTAP RLS suite remain unverified because Docker/Podman is unavailable. No parser, client route, preview UI, or provider adapter exists. Representative redacted exports and permitted mapping decisions remain absent; HealthKit history import is a different path | Review/run the migration and RLS suite against a disposable local Supabase database, then add the Gaia CSV template/parser/preview with canonical event and episode source `import:<run-id>`. Keep ambiguous origin data. Migraine Buddy/Bearable adapters remain blocked until real format evidence; do not fabricate compatibility |
| W20 — PMF evidence | Non-test cohort definition, user intent/feedback, campaign attribution not recoverable from existing data | Draft small experiments and measurement contract; customer outreach/publication needs explicit authorization |

## Planned

- **P01 — CORE VALUE / RETENTION:** structured migraine follow-up in four sections (early symptoms, exposures, medicine/relief, notes), dismissible pinned Home reminder, editing past episodes/times/severity. The provider-neutral typed detail contract and local additive persistence slice now exist; the migration/RLS suite still needs disposable-database acceptance and no client route/UI is connected. General current-symptom updates/deletion, scheduling, follow-up response/dismissal, and timeline editing remain the integration foundation.
- **P02 — RETENTION:** structured medicine taken/time/dose/relief capture, clearer migraine history/charts, user-readable episode reports and comparative summaries. The existing `New supplement or medication` exposure is context, not a medicine-treatment record. Tie each slice to repeated logging or use of a personal insight; avoid building the full list at once.
- **P03 — CORE VALUE:** richer optional health-context profiles after migraine; retain one shared app. Existing baseline/onboarding/gauge weighting does not mean every proposed questionnaire/context exists.
- **P04 — INFRASTRUCTURE / RELEASE:** safe build→test→QA→notes→package preparation with explicit human submission gate. Current iOS CI is not a complete release factory; Android CI/release packaging not established.
- **P05 — ACQUISITION / ENGAGEMENT:** turn Jennifer's promising personal Facebook-group approach into a repeatable content/review/distribution/arrival/follow-up workflow; measure founder time saved, activation, return and feedback. Measure provider revenue/cost alongside growth for later Plus refinement; minimize sensitive event properties.

## Exploratory — preserve, do not silently promote to roadmap

- Prospective Migraine Watch, community/U.S. Health Snapshot and Social Alerts remain shadow/validation work; do not conflate with public EarthScope.
- TEC/ionosphere, lightning/geoelectric expansion, magnetometer-chain coverage and additional environmental predictors.
- Interactive AI Guide/chat beyond deterministic guides and bounded rewrite generation.
- Gaia Home indoor hardware: requirements, Rev A spec, data contract, validation plan and Flux handoff exist; production device/firmware state unverified. Define a viable staged engineering/research path and clarify commitments/budget; no blanket PMF/profitability hold is in force.

## Possibly Abandoned / Superseded — verify before cleanup

- Dirty detached `611c` checkout at June 21 `a1c9830`: `bots/fact_overlay/social_poster.py` and an untracked regression test. Main includes a later IG variable repair (`acdacab`); old uppercase `OR`/IG changes are likely substantially superseded. Compare the test and intended behavior before discarding anything.
- Remote `origin/codex/improve-earthscope-writer-creativity-and-humor` is already merged into main. No open PRs were returned by GitHub. Its branch presence is not stranded implementation.
- Several research/social workflows are manually disabled. No evidence establishes whether each is deliberately paused or abandoned; leave state intact.
- Empty `marts.schumann_telemetry_v2`, `ext.magnetometer_chain`, `ext.gdacs_alerts` may be legacy/experimental paths. Current Schumann/global hazards use other active paths; avoid broad dead-pipeline conclusions.
- Old deployment/schema/open-question docs contain resolved or obsolete assertions. This handoff records the conflicts; do not use old questions as a new implementation backlog.

## Unknown / Needs Investigation

- Second Supabase project's purpose, dependents and billing; provisioned disk/compute and backup settings for the primary project.
- Exact deployed backend commit and cron completion/error traces; scheduled GitHub delays vs disabled/duplicate responsibility.
- Current release/TestFlight build, app crash rates, user-visible regressions and subscription lifecycle correctness.
- WordPress AI Agent runtime/configuration, personal-data exposure, use and incremental cost.
- Account deletion completeness across pending uploads, backups, vendor billing/analytics and partial failure; no destructive test performed.
- Historic tracked `.env` was deleted from Git in July, but history still contains it. Values were not opened. Prior rotation/revocation status needs confirmation; deletion from HEAD alone is insufficient evidence.
- Per-feed request counts, egress and meaningful user use; large data inventory is not demonstrated product value.

## Preservation record

Main HEAD `3a31b5d1aafd4f7c74ed9054509819267c677a38` matched live origin/main. Existing two modified tracked files and two social audit directories were preserved. Both detached worktrees were read only. Nothing was staged, committed, pushed, merged, cleaned or deleted. The new recovery documents and index pointers are the only intended repository changes from this audit.
