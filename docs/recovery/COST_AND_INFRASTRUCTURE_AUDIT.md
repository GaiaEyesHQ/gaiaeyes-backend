# Gaia Eyes — cost and infrastructure audit

Reconciled 2026-09-06 UTC. **Verified line-item monthly billing is unavailable.** Jennifer estimates about $500/month all-in against about $50 MRR. The repository describes dependencies and some usage, but does not support a defensible independent monthly total. Do not present a sum of guessed plans as an invoice.

**Strategy corrected September 6:** these figures support capacity planning and sensible efficiency, not an immediate profitability test or monetary gate on development. Acquisition/engagement, continued product improvement and research-level/medical capability development govern. Preserve the substantial free/ad-free product and scientifically important raw observations/provenance under consent/retention obligations. The cost observations remain dated; blanket PMF-based spending/development pauses from the initial audit are withdrawn, while actual purchases still need an authorized budget.

## Service inventory

Classification describes role today: ESSENTIAL, OPTIONAL, UNKNOWN, REDUNDANT, POSSIBLY OPTIMIZABLE. “Possibly optimizable” is not authorization to remove it. No live service is conclusively classified as redundant without a consumer inventory.

| Service / purpose | Cost evidence / usage | Dependency and classification | Optimization, removal risk and scaling |
|---|---|---|---|
| Render API | Live FastAPI endpoint, direct DB pool, five free connections at initial check; invoice/plan unavailable | ESSENTIAL | Inspect CPU/RAM/instance-hours and actual plan before resizing. Removal breaks apps/web. Scales with request concurrency and per-request work |
| Render ingest worker | Continuous durable health queue drain, active-writes limit 2, zero backlog at checks | ESSENTIAL; POSSIBLY OPTIMIZABLE | Measure utilization and batch latency; do not stop because queue happens to be empty. Removal risks stalled native uploads; scales with health samples/active devices |
| Redis/Valkey queue | Live queue/Redis enabled; invoice and size unknown | ESSENTIAL to current queue design | Check retention and retry/backlog policies, not just idle size. Removal risks data loss/retry failures; scales with backlog/burst traffic |
| Render critical/event/daily cron | Three configured lanes, multiple bounded steps | ESSENTIAL functions; POSSIBLY OPTIMIZABLE execution | Attribute duration, overlap, CPU and source duplication from authenticated logs. Removing derivations can leave healthy HTTP with stale gauges |
| Supabase primary project | Organization plan is Pro; DB ~39.4 GB; project compute/provisioned disk/egress/add-ons and bill unknown | ESSENTIAL; POSSIBLY OPTIMIZABLE | DRAP retention and query/index/backup cost are first review targets. Removal breaks identity, health data, API and billing |
| Supabase second project | `space-weather-track` active, independent project | UNKNOWN | Identify owner/consumers/invoice before consolidation. Do not assume redundant; may host an independent dependency |
| Supabase auth/storage/backups | 408 auth identities; public `space-visuals`; backup configuration not verified | ESSENTIAL; POSSIBLY OPTIMIZABLE retention | Review actual MAU, egress, provisioned disk, backup/PITR charges and restore readiness. Public media and private health require different handling |
| GitHub Actions / repositories | Media/social/notification/monitor/iOS jobs; some manual fallbacks and disabled workflows | ESSENTIAL functions; POSSIBLY OPTIMIZABLE overlap | Measure billed minutes/artifact retention and cron responsibility; unsigned macOS iOS builds can differ in cost. Do not duplicate Render jobs |
| WordPress / SiteGround | Public site/member hub, API/legacy media consumers; plan/invoice unavailable | ESSENTIAL to current acquisition/member surface | Review plugin runtime and plan only with traffic data. Removal affects member access/public content/policy URLs |
| Domain / DNS / TLS | `gaiaeyes.com` and hosting references | ESSENTIAL; exact registrar/renewal cost UNKNOWN | Separate annual renewal from monthly operations; protect identity, redirects and callback URLs |
| OpenAI product API / TTS | Public/member text and voice generation; model config exists; usage invoice unavailable | OPTIONAL presentation on essential deterministic content; POSSIBLY OPTIMIZABLE | Measure tokens/audio/calls, model mix, retries and caching by job. Derived personal health context requires review. Scales with generation frequency and users if personalized |
| WordPress AI Agent/chat | Plugin entry seen, runtime/config/traffic not available | UNKNOWN | Establish use, provider, prompts, access controls and actual bill before adding/removing it |
| ChatGPT/Codex/developer subscriptions | Jennifer's all-in cost may include shared tools | OPTIONAL/SHARED DEVELOPMENT, amount UNKNOWN | Allocate actual Gaia share separately from product runtime. Not equivalent to customer-serving API cost; do not recommend model/plan changes without usage evidence |
| RevenueCat | iOS dependency and active sourced grants; account tier/fees unknown | ESSENTIAL to current native billing | Verify billing tier and reconcile store revenue; Android planned integration. Removal breaks paid status/purchases; may scale with tracked revenue |
| Stripe | Web checkout and entitlement records; processing/other fees unknown | ESSENTIAL to web billing | Reconcile gross/net/refunds/tax and webhook delivery. Fees generally relate to transactions; exact contract/region rates unverified |
| Apple Developer | Active personal membership/public app; renewal invoice unavailable | ESSENTIAL to iOS release | Treat annual enrollment as amortized administrative cost using actual invoice. LLC conversion pending; do not create another account by assumption |
| Google Play Developer | Account not created; DUNS ready | UPCOMING platform cost | Enrollment is an account setup cost, separate from recurring operations; verify current fee at action time. No payment made |
| NOAA/NASA/USGS/Schumann sources | Existing public fetch paths | ESSENTIAL selected context; source-by-source commercial terms/cost UNKNOWN | Most burden may be compute/storage rather than access; review each provider's contract/rate limits before cadence changes |
| AirNow/weather/pollen providers | Local context integrations, seven forecast days and no pollen days for checked ZIP | ESSENTIAL weather context; pollen provider access/cost UNKNOWN | Check paid keys, quota and actual coverage. Removal can undermine main trigger hypothesis; never substitute invented data |
| Push / email / monitoring | APNs/FCM, bug alert email paths, repo monitors | ESSENTIAL operational functions; exact fees UNKNOWN | No SMS implementation established. Inspect actual mail/provider and logging invoices; do not add a crash vendor before checking existing store tools |
| Gaia Home hardware | Requirements/specification/handoff exist | EXPLORATORY / separate R&D | No verified current BOM spend or recurring cloud/device cost. Clarify commitments/budget and pursue a viable staged research/engineering path; no blanket profitability prerequisite |

Official plan references checked for context: [Supabase pricing](https://supabase.com/pricing) and [Render pricing](https://render.com/pricing). Supabase advertises Pro from $25/month, additional projects from $10, 8 GB database disk included and $0.125/GB beyond that allowance. These are published starting terms, not this account's invoice or a quote. Compute, provisioned storage, add-ons, egress, credits and project count matter. Check applicable terms again before any purchase or change.

## Measured database footprint

Production catalog around 04:05 UTC: **39,411,371,155 bytes**, about **39.4 GB decimal / 36.7 GiB**. Relation sizes include storage/index/TOAST contributions as reported by PostgreSQL; row estimates below come from statistics and are not exact counts.

| Relation/data family | Measured bytes, rounded | Estimated live rows | Interpretation |
|---|---:|---:|---|
| DRAP environmental grid | 29.90 GB | 122.6 million | ~75.9% of entire DB; review research consumers and lossless storage/archival options before proposing any reduction of original data |
| Aurora nowcast samples | 2.26 GB | 87,865 | Grid/JSON payloads can dominate despite modest row count |
| Coronal-hole forecast | 1.30 GB | 541,000 | Review duplication/retention and actual consumers |
| Native `gaia.samples` | 1.14 GB | 2.44 million | Core user data; retention/deletion governed by consent and product contract, not a casual cost cut |
| X-ray samples | 1.14 GB | 847,000 | High-frequency history; derive required aggregate/research horizons before trimming |
| Schumann data | 681 MB | Not independently restated | Source-quality/coverage needs can justify history; usage still unmeasured |
| Space weather | 607 MB | Not independently restated | Core contextual time series |
| SEP | 593 MB | Not independently restated | Review necessary granularity and historical horizons |
| Pattern results | 384 MB | ~109,560 | Many non-surfaceable/historical rows; investigate lifecycle/expiry and recomputation scope |
| Local cache | 296 MB | ~194,918 | Determine true cache/history role before cleanup |
| Space visuals metadata | 243 MB | ~140,120 | Review metadata/version retention separately from stored media bytes |

These figures do **not** explain a $500 monthly bill by themselves. Actual provisioned/billed storage can differ from logical data size, and compute, continuous worker time, macOS build minutes, AI and shared tools may dominate. Removing rows does not necessarily reduce provisioned disk or immediately reclaim database files. No data was deleted, compressed, vacuumed, archived or moved.

## Highest-value cost investigation

1. Obtain a full recent month and trailing-three-month provider totals where available: gross/net recurring revenue, Render service/cron/queue charges, Supabase compute/storage/egress/add-ons by project, product API/TTS and WordPress/hosting.
2. Separate **customer-serving runtime**, **shared development tools**, **annual administration**, and **one-time/R&D**. Record currency, tax, credits and billing period before comparing totals.
3. Measure DRAP growth/day, write/query load, product and research consumers, provenance and consent/retention requirements. Assess indexing, partitioning, lossless compression and verified archival with restore/reproducibility acceptance. Current chart usage alone does not determine historical value; do not irreversibly downsample or discard original observations to meet near-term economics.
4. Map Render/GitHub/DB cron ownership and duration; eliminate only demonstrated duplication. A DB `schumann-daily-features-rollup` cron exists, but its overlap and necessity were not established.
5. Count member/public AI generations, tokens/audio, cache hit rate and repeated unused outputs. Nineteen current-day member rows versus four current Plus identities warrants consumer/generation-path inspection; it is not proof that fifteen generations were waste.

## Unit economics to compute next

Verified normalized MRR; net collections after fees/refunds; runtime cost per meaningful active account; incremental AI/compute cost per retained payer; acquisition cost per activated/retained payer when attributable; and owner development cash/time separately. At this sample size, present absolute counts and totals alongside ratios. Do not derive lifetime value from an unobserved churn rate.

No service has been removed or repriced. Exact recurring costs, backup retention/restore success and marginal cost at 10× users remain open evidence gaps.
