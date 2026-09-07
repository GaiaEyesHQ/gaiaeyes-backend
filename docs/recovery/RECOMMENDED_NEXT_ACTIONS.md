# Gaia Eyes — recommended next actions

Strategy corrected by Jennifer on **2026-09-06**. The governing objective is **build a scalable user-acquisition and engagement system while continuing to improve the product**. Grow the user base, understand user value, support repeated use and advance research/medical capabilities. Revenue/cost are monitored context; immediate profitability and payer counts are not development gates. This replaces the initial audit's revenue-led sequence and blanket pauses.

## Three coordinated priorities

1. **Build a repeatable acquisition and engagement workflow from an encouraging existing channel.** Jennifer reports strong download responses to occasional personal posts in relevant Facebook groups and useful feedback from multiple audiences. Turn preparation, review, authorized distribution, attribution and follow-up into a system that saves her time while preserving relevance and voice. Page/reel automation is only one component.
2. **Continue meaningful product and research development.** Reconcile the iOS/Siri changes, improve symptom/migraine and personal-insight journeys, and progress Android toward a usable release. Define research provenance/reproducibility contracts and viable staged paths for medically meaningful functionality. Select reviewable increments for implementation quality and learning, not because development must earn an immediate monetary return.
3. **Protect the growing product and make learning trustworthy.** Address the audit's specific access-control and per-user freshness findings; improve privacy/identity handling, attribution and engagement measurement. These are concrete responsibilities alongside growth/product work. They constrain affected deployments/data use rather than automatically freezing unrelated local work.

## Near-term acquisition and engagement milestone

**Outcome:** a repeatable workflow operates without Jennifer having to originate and execute every post or engagement step herself. Gaia Eyes has not yet had sustained serious marketing; the objective is to establish that operating capability while learning from real arrivals and feedback.

| Component | Existing foundation / next deliverable | Acceptance |
|---|---|---|
| Audience/channel knowledge | Recover available examples of Jennifer's successful group posts and feedback; record community/topic fit and relevant posting rules | Small useful inventory based on actual context; do not scrape members or infer diagnoses from group membership |
| Content preparation | Reuse existing EarthScope/media capabilities where appropriate; draft audience-specific posts, useful explanations, assets and replies in Jennifer's voice | Review-ready material needs substantially less rewriting than starting from scratch; preserve source/claim accuracy and useful free-product positioning |
| Review and distribution | Prepare a queue with destination, content, link, timing and review status; map available permitted publishing methods | Jennifer can batch-review concrete items. Existing Page tool capability is not assumed to cover personal/group publishing; no public messages sent without authorization |
| Attribution and arrival | Use bounded campaign/source links where available; connect to store/site/new-account observations without overstating joins | Report observable clicks/downloads/new accounts and unknown attribution separately; optional intent rather than sensitive audience profiling |
| Engagement | Reuse relevant onboarding, reminders, notification preferences, product updates and a feedback/reply queue | People can get useful value, choose follow-up and stop it; delivery/quiet hours work; no generic engagement spam |
| Learning and workload | Weekly view of preparation/publication, arrivals, activation/return, feedback and founder minutes | Completed cycles reveal what to repeat/change and whether Jennifer's burden is falling; payment is not required for a cycle to succeed |

Start with a bounded pilot of two suitable community/audience contexts and repeated weekly cycles where authorized; this is a planning default, not a promise to publish or create a schedule now. Establish current founder time and available arrival/activation baselines during the first cycle. Agree any numerical improvement targets before comparison; avoid inventing conversion thresholds without denominators.

The three experiments in [PMF_STATE.md](PMF_STATE.md) test acquisition repeatability/time savings, first-use relevance, and ongoing engagement. They can inform product work while it continues. Failure of a post or metric should change that experiment, not automatically stop feature development.

## Product improvement milestone

**Outcome:** people arriving for environmental understanding, symptom/trigger tracking or a health-context need can get useful free value, control their information, understand the result and return. Multiple audiences remain legitimate; migraine is a developed starting point, not a winner selected by current paid conversion.

- Reconcile the dirty Siri resolver/phrase delta against current main and verify it physically. Continue the planned episode review/edit, structured follow-up, medication/relief history or import work in deliverable increments based on recovered user needs and dependencies. Existing general symptom follow-ups already work; extend the missing behavior.
- Improve onboarding/first-result explanations and contextual personal insights from observed friction and feedback. Support people who do not connect a wearable or buy Plus. Do not weaken free functionality to manufacture conversion.
- Continue Android product/parity work as an acquisition and accessibility path. Existing release requirements—account enrollment, privacy/permissions, reliable sync/push, and purchase/restore if included in the chosen v1 scope—are functional release gates, not proof-of-profitability gates. Do not silently change the agreed v1 scope.
- Preserve iOS/web parity for shared surfaces. Prepare the Apple update and organization-account checklists; physical acceptance and final submission remain separate from source build success.

**Success:** useful first actions are easier, the selected workflows pass technical/device acceptance, users report relevance and repeat use, and known friction is resolved. Use counts/cohort context and qualitative feedback rather than requiring three paying users before proceeding. Continuing development does not imply shipping every feature at once.

## Research and medically meaningful capability milestone

**Outcome:** a documented, technically viable route links useful functionality now with stronger validated capability later.

1. For each proposed capability, specify the user/clinical or research question, intended use, current useful scope and evidence needed for stronger use. Consider logging, longitudinal comparisons, medication/relief history, summaries/exports, candidate inference and prospective evaluation on their own merits.
2. Preserve important raw observations and original/normalized timestamps, units, source, quality/missingness and calculation versions. Make analyses reproducible; separate observed data, interpretation, model output and hypotheses. Add foundations alongside current architecture.
3. Define a bounded prototype with synthetic or appropriately consented data, comparators, failure cases and a validation plan. Existing prediction/community roadmap gates inform relevant launches; development and shadow evaluation can proceed within their appropriate scope.
4. Identify specific domain/scientific/legal/regulatory/product review needed for the intended function before its corresponding claims or release. Do not declare a feature validated, exempt or prohibited based on a generic disclaimer or on the fact that it is medically relevant.

**Success:** selected capabilities have a useful implementation path, explicit evidence/quality criteria and named dependencies. Research preservation and medically meaningful development are not conditional on near-term MRR. Formal consent/access requirements still govern research use; buying Plus or joining a community does not supply research consent.

The source/disclaimer audit in [PROJECT_STATE.md](PROJECT_STATE.md#medical-framing-and-repetitive-disclaimer-review) found no broad generic Android footer pattern, but found iOS/web repetition candidates and overbroad documentation language. Review real journeys, centralize general disclosure in onboarding/policy/help and keep specific measurement, consent, uncertainty and action-related context where useful. Prepare UI changes separately; no copy was edited in this correction.

## Reliability and safeguards in parallel

Prepare scoped remediation for anonymously accessible personal views and privileged mutation functions: consumer inventory, staged anonymous/own-user/other-user/service tests and rollback, followed by approved production application. Reconcile provider entitlements after containment. Do not test a real entitlement mutation in production.

For the five stale gauges observed in the audit, inspect affected-user scoring/refresh, eligibility and input-hash behavior. A complete Chicago-day cohort after an observed completed cycle should have no unexplained eligible lag against newer same-day inputs. Keep weather observation, ingestion and cache timestamps distinct. Actual Render logs/revision and physical HealthKit/Health Connect/push checks remain required for those specific certifications.

Preserve dirty main and detached worktrees; inspect Aurora staging/WordPress failures without automatic retries. Correct analytics account buffering, minimize sensitive diagnostic properties and reconcile actual disclosures with behavior. Security findings are substantive reasons to hold an affected deployment; they do not justify a revenue-based pause across the roadmap.

## Measurement and sustainable capacity

Primary near-term reporting: sustained acquisition cadence, Jennifer's time saved, attributable visits/downloads/new accounts where observable, first meaningful value, D7/D30 return, repeat use, useful feedback and follow-up fatigue/opt-outs. Include free and Plus users and exclude known internal accounts without forcing registration for analytics. Do not equate default tab renders, health-sample rows or server “sent” status with engagement.

Measure MRR, fees/refunds, actual infrastructure/API usage and shared development costs alongside adoption. Use them to plan capacity, detect waste and later refine Plus. There is no current $1,000 MRR gate or requirement to recoup each feature's cost immediately. Actual spend still needs the appropriate budget authorization.

DRAP and other large datasets merit storage/query/backup analysis with the research contract intact. Favor measured lossless optimization and verified archival over irreversible loss of original data. Immediate consumer-screen use is not the full measure of scientific value.

## Default decision rule for new improvements

State the desired benefit, smallest useful implementation, longer-term capability, dependencies, validation and concrete costs/risks. Proceed toward a viable route within the authorized scope. If a substantive constraint blocks that route, explain it and propose an alternative scope, sequence, prototype or validation step. Missing monetization evidence alone is not a sufficient rejection reason.

This replaces blanket pauses on Android expansion, research feeds, AI or Gaia Home. It does not approve purchases, public posts, releases, medical claims or every proposal; those keep their specific existing boundaries. Avoid duplication and broad rewrites where a smaller additive change solves the actual problem.

## Division of work

**Astra can prepare within scope:** source reconciliation, local patches/test reproductions, research/data contracts, reviewable growth workflows/drafts, measurement design, UI disclaimer inventories, release checklists and updated handoffs. Future automation should reduce Jennifer's recurring effort with explicit destination/content/approval controls. Do not create schedules, send messages, publish or enroll accounts merely because a workflow is described here.

**Jennifer is needed for specific external actions and judgments:** production rollout, authenticated account evidence, physical QA, account conversion/enrollment, claim/privacy review, publication/outreach/spend and release submission. Recover existing posts/feedback/configuration first; request only missing examples, access or decisions. Financial reporting is a supporting stream, not a reason to stop useful product or acquisition-system work.
