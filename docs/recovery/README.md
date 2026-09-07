# Gaia Eyes — recovered project handoff

Reconciled **September 6, 2026 UTC / September 5 CDT**. The audit is complete within available access; unresolved production and human gates are explicitly recorded. **Local operational report: review security/business details before public distribution.** No production fixes, deployments, releases, account changes or external communications were made.

**September 6 strategic correction:** Jennifer's governing objective is to build scalable acquisition and engagement while continuing product improvement and development toward research-level data/validated medical capabilities. Substantial free functionality and no advertising are deliberate. Current revenue/cost do not impose profitability or paid-user development gates. The four strategy files below have been revised; original technical observations remain dated audit evidence.

## Executive report

**Where we left off:** iOS is released with an update in progress. Android is a substantial native app, still unreleased. Main contains recent mobile, member-content and social fixes; additional Siri work is stranded in an older dirty checkout. The DUNS number and LLC documents are now ready, but Apple membership conversion and Google organization enrollment have not happened.

**What works:** both current source trees build; Android's 76 unit tests/lint/debug build and 34 focused backend tests pass. API/database/queue checks pass, native HealthKit and Health Connect rows exist, and member EarthScope has current output for all four currently active Plus account IDs. These results do not certify devices, TestFlight or billing lifecycle.

**Broken or risky:** anonymous access reaches personal derived-health relations and a billing mapping table; an entitlement-writing function is anonymously executable. Five gauges still lag newer same-day inputs. Local weather payload freshness, Aurora staging and WordPress publishing have warnings/failures. Live privacy disclosure, diagnostic/analytics handling, historical secret remediation and deletion/backup guarantees need review. No malicious access was established and no personal record bodies were fetched for the access probes.

**Partial or forgotten:** Android purchase/restore is not implemented; device notification acceptance and store setup are outstanding. Siri phrase/resolver changes need selective reconciliation. Richer migraine follow-up/import/medication work and several speculative/hardware concepts remain partial or planned. Older notes incorrectly leave member-writer deployment and an Android database migration unresolved; both now have live completion evidence for their stated scope.

**What users appear to value:** Jennifer reports promising interest and useful feedback from multiple audiences, with some of the strongest download growth following her personal posts in relevant Facebook groups. The audit also found repeated Home activity across 44 account IDs, with canonical symptom logging from nine, including five with migraine/headache logs. These metrics are not unique customer counts. Free-user value is a successful outcome; low Plus conversion is not a standalone verdict on the product.

**What we cannot yet know:** installs, acquisition-message conversion, valid D7 retention, cohort churn, notification engagement, chat value/cost and exact MRR/runtime cost. Provider invoices, signed-in Render/App Store evidence and physical-device checks remain unavailable. Meta metrics without confirmed Gaia Eyes asset identity were excluded.

**Business health:** approximately $50 MRR against approximately $500 monthly all-in cost, both owner estimates. The database's largest item is DRAP at about 29.9 GB of 39.4 GB; that merits a retention/cost investigation but does not explain the whole bill. No infrastructure removal is recommended without a dependency review.

**Biggest bottlenecks:** growth and engagement still depend heavily on Jennifer's time, sustained serious marketing has not happened, and feedback/attribution need a repeatable workflow. Product improvement, Android access and research/medical development can continue alongside that work. Access control and per-user freshness remain specific technical priorities.

**Top three coordinated priorities:** build a repeatable acquisition/engagement workflow that reduces Jennifer's workload; continue useful product and research/medical capability development; resolve concrete security/reliability and measurement gaps. Pursue viable implementations with appropriate evidence/review, without a three-payer or $1,000 MRR prerequisite. Review repetitive disclaimers as UX, not a substitute for feature validation.

**Astra can prepare:** local source/consumer reviews, test reproductions, reviewable patches/rollback plans, release checklists, safe aggregate reports and unpublished experiment drafts. **Jennifer is needed for:** production rollout approval, authenticated operational/financial evidence, prior credential-remediation status, privacy/store review, business cohort choices, organization account actions, physical QA and any release/outreach/spend. These are collected explicitly in the human-input file.

## Canonical files

| File | Read it for |
|---|---|
| [PROJECT_STATE.md](PROJECT_STATE.md) | Architecture, both platforms, pipeline matrix, production and release state |
| [DECISION_LOG.md](DECISION_LOG.md) | Settled/working/experimental/superseded decisions and reasons to reconsider |
| [OPEN_WORK.md](OPEN_WORK.md) | Actual stopping points, dirty worktrees, ready/blocked/planned work |
| [HUMAN_INPUT_NEEDED.md](HUMAN_INPUT_NEEDED.md) | Exact prioritized human questions, defaults, blocked work and risks |
| [RECOMMENDED_NEXT_ACTIONS.md](RECOMMENDED_NEXT_ACTIONS.md) | Acquisition/engagement system, continued product/research work and specific dependencies |
| [RECOVERY_AUDIT.md](RECOVERY_AUDIT.md) | Narrative, precise security/freshness evidence, checks and limitations |
| [PMF_STATE.md](PMF_STATE.md) | Business evidence, measurement gaps, audience hypotheses and three experiments |
| [COST_AND_INFRASTRUCTURE_AUDIT.md](COST_AND_INFRASTRUCTURE_AUDIT.md) | Services, measured storage, unknown bills and safe optimization sequence |
| [MISSED_OPPORTUNITIES_AND_GAPS.md](MISSED_OPPORTUNITIES_AND_GAPS.md) | Material missing safeguards and learning opportunities without scope expansion |

Repository canonical location: `/Users/gennwu/Documents/GitHub/gaiaeyes-backend/docs/recovery/`. The user-facing output copy is in the current task's `outputs/gaia-eyes-recovery/`. Both copies are identical at handoff; update the repository set first in future work and refresh the exported copy when needed. Nothing has been staged, committed or pushed.
