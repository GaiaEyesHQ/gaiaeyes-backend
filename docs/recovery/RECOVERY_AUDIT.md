# Gaia Eyes — recovery, reconciliation and handoff audit

Audit date: **2026-09-06 UTC**, corresponding to the September 5 working session in America/Chicago. Production observations principally cover 03:59–04:32 UTC. Source baseline: `main` at `3a31b5d1aafd4f7c74ed9054509819267c677a38`, matching live origin/main. This is a **local, uncommitted operational report**, with sensitive security/business context; review before distributing publicly.

## Executive assessment

Gaia Eyes is a working iOS product with a real native Android implementation and active personal/environmental pipelines. **Strategic interpretation corrected by Jennifer on September 6:** build scalable user acquisition and engagement while continuing product improvement and development toward research-level data and stronger validated medical capabilities. No sustained serious marketing has occurred; Jennifer reports encouraging download growth from personal Facebook-group posts and useful feedback from several audiences. Current revenue/cost are context, not an immediate profitability test. The dated technical findings below remain unchanged.

The initial audit over-weighted paid conversion and proposed gates/blanket pauses Jennifer did not intend. Those recommendations are superseded by [PROJECT_STATE.md](PROJECT_STATE.md), [PMF_STATE.md](PMF_STATE.md), [DECISION_LOG.md](DECISION_LOG.md) and [RECOMMENDED_NEXT_ACTIONS.md](RECOMMENDED_NEXT_ACTIONS.md). Preserve the substantial free/ad-free offering, reduce founder workload, learn from acquisition/engagement, and pursue viable product/research paths. Specific security, scientific and release requirements still apply; current lack of clinical validation is not a permanent exclusion of medical functionality.

All nine requested files are linked in [README.md](README.md). They reconcile evidence, settled decisions, stranded work, human dependencies, product learning and costs. Nothing in this audit authorizes a production fix, release, account change, public claim, purchase or marketing activity.

## How the project reached this point

The project grew from environmental/space-weather collection and public presentation into personal physiological comparison, native health import, gauges, symptom/check-in history, paid interpretation and a web member surface. Older architecture/schema notes still describe early states; newer source and production data often contradict them.

The public iOS app first appeared April 30, with version 1.0.1 released July 23. The July personalization roadmap articulated one app with optional health contexts, migraine-first staged work, optional health data, preservation of measurement provenance and correlation before prediction. Richer profiles, migraine follow-ups/imports, prospective watch/community concepts and hardware remain at different levels of completion.

Native Android foundations arrived in late July; onboarding and notification work followed in August. August 27's broad update combined many files. August 30 addressed Android location/channel behavior. Current tests and production Health Connect rows establish implementation beyond a mockup, while billing and store release remain incomplete.

Late August/early September focused on two kinds of reliability: daily/member content failures and stale per-user gauges despite healthy infrastructure. The member writer's UUID serialization fix reached main on September 1. This audit confirms successful current member output, closing that historical uncertainty. The separate gauge condition persists for five eligible rows and needs per-user refresh investigation, not an unapproved retry.

Recent social commits address CTAs/readability/writer guards. A small text-normalization patch remains dirty on main. A separate older Siri checkout contains additional phrase/resolver/UI/test work, but main already has overlapping migraine-stop support. A June social-poster checkout is likely superseded in part by later fixes. No open PRs were returned; one remote writer branch is already an ancestor of main. The main recovery failure is fragmented completion evidence and stranded deltas, not absence of substantial implementation.

## Evidence hierarchy and scope

1. Current user corrections define platform/business readiness: iOS released/update underway; Android unreleased; DUNS/docs now available; accounts not yet converted/enrolled.
2. Read-only live API/database/catalog/GitHub observations establish current sampled behavior and aggregate counts.
3. Current source plus local tests/builds establish implementation and buildability, not physical behavior or deployed revision.
4. Recovered task outputs/history and memory are leads. They were cross-checked where practical; historical test claims are identified as historical.
5. Plans and comments describe intent. They are never promoted to shipped functionality without corroboration.

Inspection covered repository docs/history/diffs/worktrees; backend routes/auth/queues/billing/analytics; native apps; relevant schemas/grants/storage; cron/CI; public endpoints; aggregate personal-data/activity/billing counts; authenticated WordPress admin presentation; public store metadata; and official provider documentation. Production SQL was read-only; security HTTP probes requested zero rows. No raw personal symptom/health records or historical secret values were retrieved for the findings. No exploit, write RPC or destructive test was executed.

Unavailable or deliberately limited: authenticated Render logs/revision/bills; App Store Connect/TestFlight/signing/crash analytics; Google Play account (not created); Stripe/RevenueCat/AI invoices; physical-device QA; full WordPress plugin source/config; representative user interviews; correctly attributed Meta/ad metrics; exhaustive route/load testing; historical backfill completeness and backup restore certification. A login screen is not healthy production evidence.

## Security and privacy findings

### S01 — Urgent: anonymously reachable personal-data relations

First verified during this audit around 04:02–04:03 UTC. Live catalog grants and a read-only transaction under the unauthenticated `anon` role showed access to personal derived-health relations and a Stripe customer mapping table. Public REST requests using the existing public anon key, no user JWT, `limit=0` and exact counts returned HTTP 206 and **zero row bodies**:

| Relation | Anonymous visible count | Evidence |
|---|---:|---|
| `public.app_stripe_customers` | 1 | SELECT granted; RLS disabled; anonymous insert privilege also present |
| `marts.symptom_daily` | 18 | Anonymous SELECT/definer exposure; role and public API count agree |
| `marts.symptom_x_space_daily` | 9 | Same |
| `marts.v_daily_features` | 12,073 | Same; underlying personal-feature protection does not make this view safe |
| `marts.camera_health_daily` | 6 | Same |

Raw `gaia.samples` and `raw.user_symptom_events` have RLS and do not grant anonymous/authenticated SELECT in the checked catalog. This illustrates the gap: protecting a base table is insufficient when a view or privileged function bypasses the intended user boundary. Counts alone are not a dump of data, but combined route/grant/definition evidence establishes an inappropriate accessible surface requiring containment. No evidence of prior malicious access was established; historical access logs were not audited.

**Safest next action:** inventory exact clients and database roles, then prepare a minimal migration making personal access explicitly own-user/invoker-filtered or backend-only as appropriate. Test anonymous-without-session, legitimate guest own rows, user A vs user B, and service role. Preserve valid guest functionality. Stage and review rollback before approved production application. Do not broadly revoke every view without understanding dependencies.

### S02 — Urgent: entitlement and environmental mutation privileges

`public.upsert_user_entitlement(uuid,text,text,text,timestamptz)` is SECURITY DEFINER and anonymously executable. Its inspected definition accepts a caller-supplied user ID and unconditionally writes entitlement/event state; no ownership/authorization check was found in that function. It was **not invoked**. This is a critical integrity risk to paid access and to any business analysis based on those grants.

`upsert_magnetosphere_pulse(jsonb)` is another anonymously executable SECURITY DEFINER mutation. It can compromise the integrity of public environmental state if reachable with its current grants; no mutation was attempted. By contrast, `my_entitlements()` uses `auth.uid()` filtering and should not be treated as the same vulnerability merely because it is SECURITY DEFINER.

**Safest next action:** restrict write functions to the legitimate backend/service caller contract, audit search paths and inputs, verify no app depends on direct client writes, and reconcile entitlements with providers after containment. Add staged negative permission tests without modifying real customer access. Publicly documenting an exploitation recipe is unnecessary.

### S03 — High: analytics and diagnostics need a privacy/identity contract

The server allowlist excludes free-text/note payloads, which is useful. It still allows properties such as symptom code, pain type, energy/system-load values and prediction matches. These are health-related observations, not automatically harmless generic telemetry. iOS `AppAnalytics.track` passes normalized properties to `appLog`; `AppLog.swift` prints and forwards them to the in-app log panel without a build-only gate in the inspected implementation.

The iOS pending queue uses one UserDefaults key (`gaia.analytics.pending_events`) and the uploader is configured with current auth. Sign-out clears auth/Keychain values but does not directly clear that queue; no separate use of the queue key was found. This creates a plausible deferred-event cross-account attribution/privacy defect, not a reproduced production leak. Test it with staged identities and offline queues. Keep generic product events minimal, isolate account buffers, redact health properties from diagnostics, and define consent/retention for support bundles.

### S04 — High: published disclosure and data-lifecycle evidence are incomplete

The live [privacy page](https://gaiaeyes.com/privacy-policy/) rendered a short fallback policy, including a “LAST UPDATED” label without a substantive date. It did not establish the fuller Health Connect, AI processing, precise retention or account-deletion details needed to reflect the inspected implementation. Repository `docs/legal/PRIVACY_POLICY.html` is richer. The WordPress deployment workflow copies mu-plugins/theme rather than docs/legal, supporting a likely publication-path mismatch; runtime file configuration was not inspected enough to prove the sole cause.

The account-deletion route requires auth and attempts user-table deletion before a separate Supabase Auth admin action. This is multi-step, not one atomic cross-system deletion. Pending client uploads, backups and billing-provider retention/cancellation are separate concerns. A partial failure and subscription expectations need explicit handling. No account was deleted during the audit. Backup configuration/restore success is unverified.

`PrivacyInfo.xcprivacy` includes the UserDefaults required-reason declaration; that is not the complete App Store privacy questionnaire or a legal compliance certification. Store declarations and Google Health Connect permission/disclosure requirements need review against actual release behavior. An approved privacy draft and verified deployment path should precede publication; this audit did not change the policy.

### S05 — Other material safeguards

- A formerly tracked `.env` was removed from HEAD in July, but Git history retains it. Values were not opened; the audit cannot determine if any historical credential remains valid. Confirm prior rotations/revocations, then plan only approved changes.
- Supabase advisors reported 36 SECURITY DEFINER views, 29 public tables without RLS, three materialized views in the API, 24 functions with mutable search path, one policy on an RLS-disabled table and three anon-executable definer-function findings. They also flagged leaked-password protection and database version advisories. Counts are findings to triage, not proof every object is vulnerable. Guest-sign-in advisories are expected in part because anonymous accounts are intentional.
- Member AI rewrite prompts contain derived personal-health/gauge context. Inspecting one prompt without raw notes does not prove every AI request is non-sensitive. Validate actual provider retention/config, consent and minimization before expansion.
- Pattern comparisons use exposure/outcome history, lag, sample counts, lift/odds/confidence and surfaceability gates. They are not demonstrated causal, diagnostic or prospective clinical prediction. Public/store copy needs a claim review; cached store descriptions disagreed, so no exact current tagline was certified here.

Official reference points: [Supabase RLS-disabled objects](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public), [definer views](https://supabase.com/docs/guides/database/database-linter?lint=0010_security_definer_view), and [anonymous definer-function execution](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable). This report assesses technical evidence, not legal liability or required incident notifications.

## Production health: working vs degraded vs unverified

| Surface | Observation | Verdict and next step |
|---|---|---|
| API / DB / queue | Public liveness/readiness true; direct pool, no waiters; zero backlog at first/final checks; safe local direct probes succeeded in 642/595 ms | Operational sampled baseline. No load/availability SLA or full-route claim |
| Monitor | Backend, today's features and seven-day outlook pass; analytics admin check skipped; bug count reflects old reports | Partial coverage, not all-green. Do not hide skipped checks |
| Personal gauges | 33 current Chicago-day rows; five actionable stale rows at both 04:04 and 04:27; newer gauge writes exist at 04:21 | Persistent downstream freshness gap. Focus affected-user scoring/refresh; Render lane completion itself unverified |
| Local weather | 04:27 check: cache asof 04:16:07, embedded asof/observation 03:55; seven forecast days, zero pollen days | Source/payload lag despite fresh wrapper; no evidence of DB/queue pressure; inspect source age/coverage |
| Core space/current feeds | Fresh space-weather/X-ray/SEP/DRAP/aurora/Schumann/ULF rows around 03:50–04:01 | Active; individual source quality and every view not exhaustively certified |
| Member EarthScope | Sept 5 successful daily job; 19 current-day member rows; all four currently active Plus identities covered | Current paid coverage recovered. Extra rows/history require consumer/backfill review, not automatic deletion |
| Aurora staging workflow | Latest inspected run [34004797857](https://github.com/GaiaEyesHQ/gaiaeyes-backend/actions/runs/34004797857) failed at TS assertion, Sep 6 01:47 | Exact failing step known; root cause and effect on live main imagery not proven |
| WordPress daily publishing | Run [33979063324](https://github.com/GaiaEyesHQ/gaiaeyes-backend/actions/runs/33979063324) failed at Publish to WordPress, Sep 5 16:49 | Read error/config before fix or retry; content generation success is separate from WP delivery |
| Other GitHub jobs | Recent EarthScope rules, push evaluation/send, space visuals and daily/member pipelines succeeded; several research/social jobs disabled | Mixed status. Scheduled frequency does not guarantee exact timely execution |
| Notifications | 1,663 sent in 30 days; no Android token registered in aggregate | Server path working; receipt/open and Android production acceptance unverified |
| Subscriptions | Client/server code and current grants present | End-to-end payment/restore/cancel/refund not certified; S02 raises additional integrity risk |
| Render | Dashboard requires login | Actual service revision, errors and cron results unverified; no deploy/retry performed |
| App stores/devices | Public Apple metadata verified; both local builds pass | TestFlight/signing/crashes/physical QA unverified; Android unreleased |

## Where previous work actually stopped

Main's two dirty tracked files are the public social writer and its stats regression test, covering text normalization. Two temporary social-audit directories also predate this audit. They were preserved. There are no currently open PRs, and the remote writer branch is already merged.

The `a9cf` detached July checkout contains `GaiaExporterApp.swift`, `Models/HomeFeedModels.swift`, `Views/ContentView.swift`, tests and an untracked `Services/HandsFreeSymptomLogger.swift`. The alternate resolver and natural phrases overlap main's existing migraine support. Historical task output reports local tests/build work and physical Siri ambiguity. That output is not a current release certification. Selective reconciliation is needed; do not merge an old app snapshot over newer auth, health and UI work.

The `611c` June checkout contains social-poster and regression-test work. Main has a later IG variable repair, so some changes appear superseded. Preserve/test the intended delta before cleanup. Neither worktree was edited.

Planned-only or partially implemented work includes fuller migraine follow-up/past-episode editing/medication history, real third-party symptom import, richer optional health contexts, advanced predictive/community/shadow analysis, interactive AI Guide and Gaia Home hardware. Existing baseline questionnaires/gauges and HealthKit backfill should not be mislabeled missing just because richer follow-up/import plans remain unfinished.

## Tests and verification performed

No source changes, dependency upgrades, new package declarations or release artifacts were introduced. Builds used existing project dependencies; Xcode may materialize pinned packages/build products in isolated DerivedData. Build success does not prove absence of warnings or physical correctness.

| Check | Command / scope | Result |
|---|---|---|
| Backend regression subset | `venv/bin/python -m pytest -q` for analytics, profile notifications/location, member drivers, gauge job, Render cron, ingest worker, FCM and symptoms; dummy DB URLs, stubbed I/O | **34 passed**, 12 deprecation warnings, 0.74 s |
| Android | Gradle `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug` from Android project | **BUILD SUCCESSFUL**, 76 tests, zero failures/errors/skips; 14 lint warnings; 25 s |
| iOS main | `xcodebuild -project gaiaeyes-ios/ios/GaiaExporter.xcodeproj -scheme GaiaEyes -configuration Debug -destination 'generic/platform=iOS Simulator' -disableAutomaticPackageResolution CODE_SIGNING_ALLOWED=NO build`, isolated DerivedData | **BUILD SUCCEEDED**; current main source, unsigned simulator; no unit/UI suite rerun or physical QA |
| Production monitor | `venv/bin/python scripts/post_launch_monitor.py` at initial/final observation | Core passes; local freshness/pollen warning; analytics admin skipped |
| DB connectivity | Safe wrapper around `diagnose_connectivity(timeout=5)`; only label/ok/latency emitted | Both configured targets label direct, successful; conninfo/errors/config secrets suppressed |
| Gauge closeout | Complete Chicago-day cohort, >60-minute age, exclude calibration, compare newer same-day summaries/features/samples, repeat after elapsed scheduled interval | Five actionable cases persisted. Authenticated successful cron execution not established |
| Anonymous exposure | Read-only role/catalog queries and REST exact counts with `limit=0` | Five accessible relations confirmed; no personal bodies; no write-function invocation |
| Repository preservation | Status/diffs/history/worktree inspection; final doc/link check | Existing source deltas preserved; no stage/commit/push/cleanup |

Full local logs are under `/Users/gennwu/Documents/Codex/2026-09-05/we/work/recovery-audit/`. They are intermediate verification material, not public deliverables. The canonical outputs intentionally contain only summarized operational/aggregate evidence, no bearer tokens, conninfo or personal record bodies.

## Evidence register

| ID | Evidence source | Establishes / limitation |
|---|---|---|
| E01 | User attachment, current platform/DUNS/LLC correction | Mission, scope, human boundaries, estimated finances and account readiness |
| E02 | `git status`, history, remote API/main, branch ancestry, both worktree diffs | Baseline/stranded work; a matching GitHub SHA does not identify Render's deployed revision |
| E03 | [Architecture](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/docs/ARCHITECTURE.md), [roadmap](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/docs/NEXT_PHASE_PERSONALIZATION_ROADMAP.md), [pattern design](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/docs/PATTERN_ENGINE.md), current code | Intent and implemented contracts; older status statements cross-checked |
| E04 | `app/main.py`, `app/routers`, `app/security`, `app/utils/auth.py`, `app/db`, `app/api/webhooks.py`, `scripts/run_render_cron.py`, `render-crons.yaml` | Active architecture/routing/schedule source, not full production certification |
| E05 | `gaiaeyes-ios/ios/GaiaExporter`, Xcode project/Package.resolved, `.github/workflows/ios-ci.yml`; “Add Siri migraine logging” recovered task | Main implementation vs dirty alternate work; historical device feedback separate |
| E06 | Android source/Gradle config and [completion/parity plan](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/docs/android/ANDROID_V1_COMPLETION_AND_PARITY_PLAN.md), build/lint/JUnit results | Native implementation/buildability; billing and release gaps |
| E07 | Supabase connector: read-only schemas, grant/function/view definitions, advisors, applied migrations, bucket/project metadata and aggregates | Current access/data/counts; no exploit or destructive tests; row estimates marked |
| E08 | `health.json`, `monitor-first.txt`, `monitor-final.txt`, safe `db-probe.json`, gauge/local final query | Time-bounded sampled production health |
| E09 | `github.json`, workflow run/job metadata for the two failures | Latest inspected job outcomes and exact failing steps; root-cause logs unavailable |
| E10 | `metrics-evidence.json`, rolling-30-day aggregate queries; WordPress Gaia analytics page | Actual events/accounts/source rows; no install/customer identity equivalence |
| E11 | `anonymous_rest.json`, live role/catalog read-only evidence | API-accessible counts and risky grants; no personal record content retrieved |
| E12 | Public [Apple listing](https://apps.apple.com/us/app/gaia-eyes/id6761451455) and Apple lookup, live privacy page, login-only Render/App Store Connect | Public version/seller/disclosure; no signed-in release/crash evidence |
| E13 | `docs/legal/PRIVACY_POLICY.html`, `wp-content/mu-plugins`, `.github/workflows/wp-deploy.yml`, AppAnalytics/AppLog/auth/profile deletion code | Disclosure publication drift and privacy/lifecycle leads |
| E14 | September stability memory/runbook and dated social/Siri task history | Leads for reconciliation only; member output and migration status refreshed live |

Technical references in the companion files link to actual inspected repository paths or official provider pages. Metrics are scoped to their observation/window; they are not a continuously updating dashboard.

## Remaining human dependencies and continuation

Highest-priority dependencies are access-control rollout approval once a concrete patch is reviewable, authenticated operational/financial evidence, historical credential-remediation status and approved privacy/declaration updates. Account conversion/enrollment and physical acceptance remain Jennifer's actions. Missing these does not block local investigation, test plans, patch preparation, release checklists or experiment drafts.

The audit did not trigger jobs, change production rows/grants, apply migrations, deploy, submit releases, enroll accounts, alter prices/claims/privacy, publish marketing, contact customers, rotate secrets, remove infrastructure, create automations/tasks or modify memory. The only intended repository writes are these recovery documents and navigation pointers. Next work must be explicitly scoped from the evidence and boundaries above.
