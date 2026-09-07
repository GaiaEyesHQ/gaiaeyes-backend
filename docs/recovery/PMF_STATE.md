# Gaia Eyes — business and product-market-fit state

Strategy corrected by Jennifer on 2026-09-06. **Build a scalable user-acquisition and engagement system while continuing to improve Gaia Eyes.** Grow the user base, learn what people value, support repeated use and develop the research/medical vision. Revenue and costs remain measured context; immediate profitability or a payer threshold is not the primary gate for development. The original audit's paid-user gate and revenue-led experiment sequence are superseded.

## Governing growth context

Jennifer reports that Gaia Eyes has not yet received sustained serious marketing. Some of its strongest download growth followed occasional posts she personally made in relevant Facebook groups. Several target audiences have shown promising interest and provided useful product feedback. Her limited time prevents continuous manual repetition. These are legitimate qualitative/channel signals supplied by the owner, not assumptions to dismiss because attribution is incomplete. Exact historical lift, sample sizes and comparative channel rates remain unverified.

The next system should reproduce the relevance and usefulness of that approach with less recurring founder effort: suitable community/channel inventory → tailored content and review queue → authorized distribution → optional lightweight attribution → relevant onboarding → continued value/feedback → another iteration. Existing Page/reel automation is an asset but does not by itself reproduce successful personal group participation.

Gaia Eyes intentionally provides substantial functionality **free and without advertising**. Free users receiving value and returning are successful outcomes. Low Plus conversion can reflect product generosity, limited acquisition scale, audience mix and an offer still being refined; current evidence does not isolate the cause. Develop useful capabilities now and later refine Plus value/gating from user understanding. Do not infer that free users lack value or that paid gating should tighten to make today's numbers look better.

Research-level data and increasingly medically meaningful functionality are also strategic value. A feature can be justified by user benefit, acquisition/engagement, data quality, scientific learning, accessibility or a necessary technical foundation. Evaluate a viable path, including appropriate validation and review, before recommending delay. No payer count is required to justify foundational research or medically relevant product work.

## Current business state

| Measure | Current evidence | Interpretation |
|---|---|---|
| MRR | Jennifer's estimate: approximately $50 | Context to reconcile over time; not a development gate or standalone measure of value in the deliberately generous free product |
| Operating cost | Jennifer's estimate: approximately $500/month all-in | Track for capacity/budget planning and sensible efficiency; includes possibly shared tools; not an instruction to demand immediate monetary ROI |
| Current Plus access | Four active grants: manual/yearly 1; RevenueCat/monthly 1; RevenueCat/yearly 1; Stripe/monthly 1 | Three provider-sourced grants plus one manual. Not necessarily three currently paying customers; reconcile provider records, especially after entitlement access-control remediation |
| Inactive grants | Four RevenueCat monthly records inactive | Not a churn cohort or cancellation-reason distribution |
| Distribution | Public iOS app; Android unreleased | Android activity reflects development/internal use, not a public launch |
| Public store signal | US Apple lookup: zero ratings; version 1.0.1 | No verified download, impression, conversion or global review data |
| Acquisition | Existing social/content/site infrastructure; Jennifer reports particularly encouraging download growth from personal posts in relevant Facebook groups | The manual channel has promising qualitative evidence. Sustained serious marketing and a repeatable low-effort distribution/engagement workflow have not yet been established |
| Audience feedback | Jennifer reports promising interest and useful product feedback from several target audiences | Recover available feedback examples and channel context as evidence; absence of a structured repository dataset does not mean absence of feedback |

The near-term milestone is an operating, repeatable acquisition-and-engagement loop with reduced founder workload and improving product value. Define baselines, cadence, ownership and feedback capture; compare downloads/new accounts, meaningful activation, return and user-reported usefulness across repeated cycles. The earlier ten-account/three-payer gate is withdrawn. $1,000 MRR may remain a later financial milestone if Jennifer chooses, but it does not govern what can be built now.

## Current audience and value-proposition hypotheses

| Hypothesis / job | Supporting evidence | Contradicting evidence or uncertainty | Product/message fit |
|---|---|---|---|
| Migraine/headache: “Help me keep a usable episode history and notice what repeatedly coincides with it.” | Existing migraine logs, Siri work, planned follow-up; 13 migraine/headache events from five IDs in 30 days; consistent with the audiences Jennifer says are showing interest | Small measured sample; internal users unknown; comparative response and clinical/predictive validation not established | Developed workflow worth improving now; progress from useful history and evidence toward reviewed stronger capabilities without overstating current validation |
| Trigger/pattern seekers: “Help me compare how I feel with my health and local environment over time.” | 57 symptom events from nine IDs; patterns engine and exposure/check-in UI; 15 IDs viewed Patterns | Logs sparse vs dashboard activity; no evidence that surfaced correlations drove return/payment | Strong mission fit; activation must explain logging, adequate data and uncertainty before promising insight |
| Earth/space/environment interest: “Help me understand today's conditions and compare them with my own observations.” | Home dominates observed tab views; active visuals/environmental content and social distribution | Home is default and repeatedly instrumented; visits do not establish a personal job, subscription intent or value of every feed | Easy curiosity entry, weak proven path to paid repeated personal value; test against a concrete tracking message |

The audience rows are overlapping working hypotheses, not a requirement to pick one winner before growing. Jennifer's reported multi-audience interest/feedback is evidence across the program; its exact mapping to these rows still needs recovery. Scientific/mystical preference is presentation, not a proven customer segment. Do not infer medical conditions or beliefs from browsing or group membership. Optional job-intent choices can distinguish relevant needs without collecting diagnosis histories for marketing.

Historical positioning ranges from space/Earth environmental context to body/environment insights and symptom/trigger patterns. Public store sources returned differing cached descriptions; current exact copy requires a signed-in/live metadata review. Do not infer that a newer tagline improved conversion merely because it appears in a search result. The website and both clients support much of the product story, but their first-use path and message consistency have not been validated with new users.

## Known user signals

Read-only production aggregates were taken around 04:00 UTC on September 6. Unless stated otherwise, the window is rolling 30 days, approximately August 7–September 6. Account IDs are not unique people, installs or confirmed customers; QA/founder/anonymous identities are not excluded. The WordPress calendar dashboard uses August 8–September 6 and therefore shows different totals; those are not contradictory measurements of the same interval.

| Signal | Observed count | Limit |
|---|---|---|
| App analytics | 3,555 events, 44 distinct account IDs, 2,936 session IDs; seven-day active IDs 31 | All events were iOS; a session UUID is per process and instrumentation can fire repeatedly; not certified foreground sessions |
| Tab views | Home 3,035 / 44 IDs; Explore 90 / 16; Body 63 / 14; Patterns 57 / 15; Outlook 23 / 13 | Default Home exposure and duplicate lifecycle activity bias frequency; not intent or dwell time |
| Return activity | 37/44 IDs appeared on at least two calendar days; 28 on at least seven; median 11 distinct days | Observed returning activity in a selected active cohort, **not D7 retention**, and no acquisition cohort/test exclusion |
| Onboarding events | Started 53 events / 15 IDs; completed 5 / 5 IDs; first insight 5 / 5 IDs | Repeated starts and observation-window censoring mean 5/15 is not a valid full conversion rate |
| Daily check-in analytics | Started 25 / 10 IDs; completed 14 / 6 IDs | Actual canonical table contains 15 rows / 7 IDs; telemetry and source records differ |
| Symptom analytics | `symptom_logged` 18 / 8 IDs; form submitted 11 / 7; log opened 21 / 7 | Multiple event names/paths and voice/import behavior mean events do not equal all logs |
| Canonical symptom data | 57 events / 9 IDs; migraine/headache subset 13 / 5 | Best evidence of logging volume, but clinical category and internal cohort still matter |
| Guide/driver exploration | Guide opened 6 / 5 IDs; all drivers opened 48 / 14 | Small samples; no attached comprehension/usefulness signal |
| Health connection events | HealthKit started/completed 4 / 4 IDs each; backfill started/completed 3 / 3 each | Event pairs not yet verified as a complete funnel |
| Native samples | HealthKit 337,099 / 26 IDs; Health Connect 2,136 / 1 ID | Row volume reflects sampling frequency, not engagement; Android latest August 29, iOS recent on audit day |
| All-time profiles | 94 profiles, 53 marked onboarding complete, 55 HealthKit-request timestamps, 19 backfill markers | Different populations/timeframes; do not divide by total auth IDs and call it activation |
| Auth inventory | 408 account IDs, 384 anonymous; 24 created and 25 last-signed-in during 30 days | Auth refresh/sign-in is not active use; anonymous account churn may create duplicates |
| Push | 1,663 sent, 1,282 skipped, one queued in 30 days; all 33 stored device tokens are iOS | “Sent” is server status, not device receipt/open. No Android token proof |
| Bug reports | 12 total, latest April 28; zero new during 30 days | Existing monitor's “recent_reports=12” should not be mistaken for 12 fresh issues; silence does not mean satisfaction |

Pattern storage contains a large non-surfaceable/null-confidence population and 64 surfaceable rows across emerging/moderate confidence groups; per-group distinct-ID counts overlap. Do not add them to infer total users receiving good insights. There are more historical pattern identities than current auth accounts, which warrants lifecycle/retention reconciliation rather than presenting all rows as current product value.

## What can and cannot be answered

| Business question | Current answer / missing minimum |
|---|---|
| Who is using it? | Pseudonymous account activity and platform known; non-test people, job-to-be-done and acquisition cohort unknown |
| Why did they install? | Unknown; no reliable intent/source linkage. Add optional bounded job choice and source code |
| What do they do first / where drop off? | Events exist, but repeat starts, missing paths and session semantics undermine funnel claims. Validate ordered first-use milestones |
| What predicts subscription or retention? | Unknown; verified provider lifecycle plus completed acquisition cohorts and meaningful-use definitions missing |
| Which feature creates repeated use? | Home dominates observed activity; causal value/retention contribution unknown. Compare meaningful return after feature use, with confounding disclosed |
| Which audience/message brings relevant users who engage? | Jennifer identifies personal Facebook-group posts as an encouraging download source; comparative rates and repeatability remain unmeasured. Add attribution without making measurement a prerequisite for all useful outreach preparation |
| Trials, purchases, refunds, churn/cancellations? | No trial/paywall/purchase funnel in observed analytics; grant records alone insufficient. Provider reports and idempotent lifecycle reconciliation required |
| Migraine vs other use? | Limited canonical counts possible; no reliable segment retention/WTP comparison. Minimize health-sensitive segmentation |
| Health-linked users retain better? | Technically linkable but not a tested cohort analysis; requires test exclusions, time-ordering and account lifecycle validation |
| Notifications create engagement? | Cannot tell; send status only. Track permission/result/open safely, without symptom payloads |
| Chat adds value or just cost? | Unknown. No native chat identified; WordPress AI Agent use/config/cost unavailable |
| Installs, store conversion, ads, referrals, landing-page conversion? | No verified App Store Connect, ad campaign or site funnel data. WordPress's Gaia analytics page is app analytics, not website traffic |
| Reviews/support sentiment? | Jennifer reports useful feedback and interest from several audiences. The audit found no structured representative feedback dataset; old bug-report/US-rating counts do not negate that owner-reported evidence |
| Which data feeds matter to people? | Tab/driver activity is insufficient for per-feed usefulness. Use selective safe exposure/usefulness events, not a new exhaustive surveillance system |

Meta browser figures were excluded because the inspected asset identity was not established as Gaia Eyes. That exclusion does not contradict Jennifer's separate report about personally posted Facebook-group acquisition. Earlier social QA artifacts establish content work, not complete group-channel attribution. No active ad spend or attributed paid-campaign return was verified; sustained serious marketing has not yet occurred according to Jennifer.

## Minimum measurement work

1. Define cohort start, first meaningful activity, foreground session and meaningful D7 return. Include accepted log/check-in or completed health sync followed by a personal result; a default tab render alone should not count as activation.
2. Record platform/version, bounded acquisition source/job intent and a controlled internal-account exclusion. Do not collect names, precise location, diagnoses or notes solely for analytics.
3. Reuse existing analytics routes with a small reviewed taxonomy: onboarding milestone, meaningful activity accepted, personal insight viewed/usefulness, paywall exposure and notification open. Avoid symptom detail/severity/medication properties in generic telemetry.
4. Bind queued events to the correct account, handle guest→registered continuity and sign-out, and test retries/deduplication. Client analytics currently uses a global pending-events key; fix attribution before adding more events.
5. Reconcile server/provider payment lifecycle, manual grants, refunds, renewals and annual normalization. Event-driven purchase UI analytics cannot substitute for provider records.
6. Produce a weekly growth/engagement report: eligible opportunities, content prepared/approved/published, visits/downloads/new accounts where observable, meaningful activation/return, feedback, and Jennifer's preparation/review minutes. Label unattributed gaps. Track revenue/runtime cost alongside it on an appropriate financial cadence; do not let them dominate the weekly product decisions.

## Current growth experiments

Recovered repository work centers on EarthScope social delivery, stronger hooks/CTAs, copy/renderer quality and reel/gallery QA, with a small text-normalization change uncommitted. The master guide explicitly identifies Facebook as a growth channel. Jennifer's occasional personal group posts add a stronger practical acquisition lead than the initial audit captured. Their effectiveness has not yet been converted into a sustained system because she cannot continuously do the work herself.

The missing program is repeatable, relevant distribution plus engagement, not proof that marketing deserves to begin. Preserve Jennifer's voice and the context that made her posts useful. Prepare community-specific reusable drafts and assets, rules/permission notes, an approval queue, lightweight links, onboarding context and a feedback/reply queue. Automate safe preparation, measurement and reminders only within an authorized workflow; do not assume Page-publishing tools authorize posting to groups, impersonating personal participation, scraping member health information or contacting people. Public posting/outreach remains subject to existing authorization boundaries.

## Next three highest-value PMF experiments

These are **proposals**, not campaigns launched by this correction. They learn how to grow and improve Gaia Eyes while development continues. Each decision rule concerns that workflow or experiment, not permission for the whole product to keep developing. Customer contact, publishing and spend need authorization. Estimates are implementation effort, not elapsed recruitment time.

| Experiment | Hypothesis / smallest test | Required implementation and effort | Metric / expected learning / decision rule |
|---|---|---|---|
| E1 — repeat the successful acquisition method with less founder effort | A prepared, relevant community-content workflow can reproduce promising group-post acquisition while saving Jennifer time. Start with two community/audience contexts already supported by available examples and two repeated publication cycles when authorized | Recover prior posts/feedback where available; make tailored drafts/assets, community-rule notes, approval queue and distinct optional source links. About 1–2 days for a first reusable workflow | Measure Jennifer's minutes per approved post/cycle, visits/downloads/new accounts where attributable and meaningful responses. Keep the workflow if it reduces her effort while preserving relevance and encouraging acquisition signals; revise content/placement if response weakens. Missing attribution triggers measurement repair, not a declaration that the audience failed |
| E2 — make arrival and first useful action match the message | People arriving for migraine/trigger tracking or environmental understanding engage more when first-use guidance matches that job | Use lightweight source/optional intent context, existing free functionality and one focused onboarding/first-result improvement; compare successive cohorts with confounding noted. About 1–3 days for measurement and a bounded product slice | Measure first meaningful activity, time-to-value, completion/drop-off and brief voluntary usefulness feedback. Keep improvements that reduce friction or improve useful activation without undermining privacy/accessibility; iterate ambiguous results. No purchase or profitability threshold |
| E3 — repeat engagement without continuous personal follow-up | Useful, consented reminders/digests, relevant product updates and a manageable feedback queue can increase return while reducing Jennifer's work | Reuse notification preferences/quiet hours where suitable; prepare an engagement cadence and response/feedback triage. Validate delivery and permissions; use only authorized channels. About 1–3 days for a pilot workflow, plus observation | Compare meaningful D7/D30 return, repeat logging/review, notification opt-outs and usefulness feedback alongside founder minutes. Continue if return/usefulness improves without unacceptable fatigue; tune frequency/content if opt-outs or complaints grow. Learn Plus opportunities from requests, without making conversion the success gate |

## Working interpretation

The measured account activity supports improving the arrival→useful action→return loop; Jennifer's reported group-post growth and audience feedback support building a sustained acquisition program now. The main operational bottleneck is dependence on her manual effort. Product improvements, multiple audience learning, Android access, useful health capabilities and research foundations can advance together. Measurement should guide those improvements and later Plus refinement, while preserving the deliberate free/ad-free value proposition.
