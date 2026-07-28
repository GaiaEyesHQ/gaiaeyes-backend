# Gaia Eyes Next-Phase Personalization Roadmap

Date: 2026-07-24

Status: implementation planning with product decisions recorded
Scope: health-context personalization, historical imports, multicausal patterns, predictive notices, charts, signals, Guide evolution, community features, and web direction.

## Executive Decision

Gaia Eyes should remain one shared app with optional **health-context profiles**, not become separate migraine, POTS, fibromyalgia, arthritis, or chronic-fatigue apps.

The shared experience continues to provide:

- body and wearable context,
- symptom and exposure logging,
- local, Earth, and space signals,
- gauges,
- cautious personal patterns,
- Outlook and Guide support.

Health-context profiles change what Gaia Eyes emphasizes:

- onboarding questions,
- suggested symptoms and exposures,
- quick check-ins,
- home modules,
- charts,
- pattern candidates,
- alert wording,
- Guide content.

They do not change the underlying truth layer or hide important current conditions.

Advanced historical imports and historical pattern analysis are planned for
Gaia Eyes Plus. Basic health-context selection, relevant symptom logging, and
the shared dashboard should remain useful without a Plus subscription.

Example:

- A person without migraine context can still find and log `Migraine`.
- A person who selects migraine context can additionally receive migraine-specific suggested symptoms, a short migraine follow-up, relevant charts, and—after validation—a personalized Migraine Watch.
- A person who does not select migraine context should not see migraine-specific onboarding, dashboards, reminders, or Watch features by default.

## Product Principles

1. **Body + environment + personal history**
   - Gaia Eyes should explain combinations, not act like a weather-trigger list.
2. **One app, selectively personalized**
   - Add context-aware modules to shared surfaces before creating separate condition areas.
3. **Association before prediction**
   - Early multicausal findings remain observational and run in shadow mode before they generate user-facing notices.
4. **Personal evidence stays separate from community evidence**
   - “In your history” and “Across consenting members” must never be blended.
5. **Specific without being diagnostic**
   - Prefer “This combination has overlapped with…” over “This will cause…” or “A migraine is coming.”
6. **Raw data is preserved**
   - Imports and backfills retain timestamps, units, source, quality, and provenance. Derived features remain versioned and reproducible.
7. **Missing data is not a negative finding**
   - Lack of HealthKit samples may mean limited authorization, unavailable history, device behavior, or no measurement.
8. **User control is reversible**
   - Health-context profiles, alerts, imports, symptoms, and exposures can be reviewed and changed.

## Existing Foundation

This phase extends current seams rather than introducing a parallel product:

- `services/personalization/health_context.py`
  - already recognizes migraine, chronic pain, arthritis, fibromyalgia, POTS/dysautonomia, sleep disruption, autonomic sensitivity, and related contexts;
  - already applies bounded health-context weighting.
- `app/routers/patterns.py`
  - already uses health-context tags to prioritize relevant pattern outcomes.
- `bots/patterns/pattern_engine_job.py`
  - already creates deterministic, explainable signal-to-outcome associations with lags, sample counts, exposed and unexposed rates, and confidence tiers.
- `raw.user_symptom_events`
  - already supports editing and resolving current symptoms.
- `raw.user_exposure_events`
  - already has update/delete-capable database policies, but the API and app do not yet expose edit/delete workflows.
- `bots/notifications/evaluate_push_notifications.py`
  - already supports notification families, cooldowns, quiet hours, and bundling.
- `app/routers/profile.py`
  - already contains profile, Guide/tone, favorite symptom, and home-feed personalization seams.
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
  - already collects health-context onboarding selections and renders the shared dashboard.
- `docs/research-architecture/ARCHITECTURE_REVIEW.md`
  - already defines the additive raw-to-research direction, provenance requirements, and prospective validation posture.

## Health-Context Profile Model

A profile should be configuration, not a forked UI.

Each profile can define:

- onboarding follow-up questions,
- suggested symptom codes,
- suggested exposure codes,
- one optional quick check,
- prioritized charts,
- candidate multicausal features,
- eligible home modules,
- Guide content,
- alert templates,
- copy constraints.

Users can enable more than one profile. The app must deduplicate overlapping symptoms, exposures, cards, and alerts.

Each enabled profile also carries a self-reported status:

- `diagnosed`
- `suspected`
- `prefer_not_to_say`

This status is not verified and must not be presented as a diagnosis. It may
adjust explanatory copy and, with separate research consent, support
appropriately suppressed cohort analysis. It must not restrict access to
logging or core support features.

### Launch order

1. Migraine
2. POTS / dysautonomia
3. Fibromyalgia / chronic pain
4. Chronic energy / fatigue
5. Arthritis / joint sensitivity

### Initial Profile Matrix

| Profile | Suggested symptoms | Relevant context to watch | Later profile module |
|---|---|---|---|
| Migraine | Migraine, headache, aura, light/sound sensitivity, nausea, dizziness, neck stiffness, brain fog, fatigue | Sleep, HRV, resting HR, pressure, humidity, temperature changes, UV/light, strong smells, stress, hormonal context | Migraine Watch |
| POTS / dysautonomia | Dizziness, rapid heartbeat, near-fainting, fatigue, brain fog, weakness, heat intolerance | Heat, hydration-related logs, standing/exertion, sleep, illness, HRV, resting HR, heart-rate range | Autonomic Load |
| Fibromyalgia / chronic pain | Pain flare, widespread pain, stiffness, nerve pain, fatigue, poor sleep | Sleep, pressure, humidity, temperature changes, exertion, illness, current symptoms | Flare Context |
| Chronic energy / fatigue | Low usable energy, fatigue, post-activity worsening, non-restorative sleep, brain fog | Sleep, exertion, illness, resting HR, HRV, temperature deviation, heat/humidity | Energy Envelope |
| Arthritis / joint sensitivity | Joint pain, stiffness, swelling, reduced mobility, fatigue | Temperature, pressure, humidity, activity/exertion, sleep | Joint Context |

These labels are not diagnoses. They are user-selected contexts that change relevance and wording.

### Base-versus-profile behavior

Always available:

- full symptom search,
- full exposure catalog,
- core gauges,
- body data,
- all-driver and Explore views,
- general patterns,
- safety and limitations copy.

Profile-gated by default:

- condition-specific quick checks,
- condition Watch modules,
- condition-specific alerts,
- specialized chart bundles,
- condition-specific Guide cards.

### Profile-aware Home curation is not prediction

Health-context profiles may personalize the content shown inside the fixed Home
structure before predictive notices are approved.

Allowed initial behavior:

- rank canonical Possible Symptoms so condition-relevant choices appear first;
- emphasize relevant current drivers in Signals to Watch and gauge details;
- tailor explanations, quick checks, Guide support, and logging shortcuts;
- show directly observed changes such as below-usual HRV, short sleep, pressure
  change, heat, or a recently logged exposure;
- explain why an item is shown using the user's selected health context;
- show a qualifying retrospective personal overlap using “In your history”
  language, its evidence level, and the supporting sample counts.

This curation changes relevance and ordering. It does not assert that an
unlogged symptom is present or that a future condition event is likely.
Suggested symptoms remain separate from Active Symptoms, which come only from
the user's logs.

Initial contextual cards may use labels such as:

- `Worth noticing`;
- `Current context`;
- `Relevant to your migraine profile`;
- `Historical overlap`.

They must not use condition risk scores, probabilities, expected timing,
“trigger” claims, or statements such as “A migraine may be coming.” A
contextual card should end with an optional check-in or evidence view, not a
predicted outcome.

## Recommended First Implementation Slice

The next implementation slice should improve control and relevance before adding prediction.

### 1. Centralize health-context profile configuration

Create one versioned configuration contract shared by API responses and iOS presentation logic.

Minimum fields:

- `profile_key`
- `version`
- `enabled`
- `context_status`
- `suggested_symptoms`
- `suggested_exposures`
- `quick_check_key`
- `eligible_home_modules`
- `chart_bundle`
- `alert_families`

Acceptance:

- existing onboarding selections map to the same profile keys already stored;
- each selection records `diagnosed`, `suspected`, or `prefer_not_to_say` without implying verification;
- enabling/disabling a profile is reversible;
- overlapping profiles do not duplicate suggestions;
- the base app remains usable with no profiles selected.

### 2. Make exposure entries editable and removable

Add authenticated update and delete routes for the user’s own exposure events, matching the existing symptom ownership pattern.

Acceptance:

- user can correct type, intensity, timestamp, duration, and note;
- user can delete an accidental entry;
- updates preserve `created_at` and change `updated_at`;
- deleted/edited events no longer affect subsequent derived features after recomputation;
- analytics record the action, not the sensitive note.

### 3. Add custom symptoms and exposures as private user vocabulary

Do not insert arbitrary labels into the global canonical catalogs.

Store:

- user-visible label,
- optional user-selected canonical family,
- user ownership,
- created/updated timestamps,
- active/archived state.

Custom entries may participate in personal timelines immediately. A stable,
private user-scoped identifier may enter personal pattern analysis under the
same evidence gates as a canonical entry. Editing a label must preserve its
identifier and label-version history so an edit does not break earlier events.

Raw custom free text must not enter community aggregates, shared alerts, or
global research exports. A repeated custom concept may be proposed for the
canonical catalog only after:

- at least 25 separately consenting users use equivalent normalized concepts;
- the behavior persists across at least two calendar months;
- a human taxonomy and product/science review approves the mapping.

This is a product-discovery threshold, not evidence that the concept has a
health effect.

Acceptance:

- only the owning user sees the custom label;
- labels can be edited or archived;
- historical events retain their original label reference;
- community aggregates never expose a custom free-text label.

### 4. Improve alert specificity within current alert families

Extend templates before creating new alert infrastructure.

Examples:

- “Your resting heart rate is above your usual range. A steadier recovery day may help.”
- “Sleep and HRV are both below your usual range today.”
- “Pressure is falling and you have previously logged more head symptoms during similar shifts.”

Acceptance:

- every alert names the observed change;
- personal-history language appears only when a qualifying personal association exists;
- no alert diagnoses, guarantees an outcome, or implies causation;
- quiet hours, bundling, cooldowns, and opt-in preferences still apply;
- tapping opens the evidence/details surface that generated the message.

### 5. Add an optional, skippable first-use walkthrough

The walkthrough should explain:

- gauges are current context, not diagnoses;
- logging symptoms and exposures improves personal patterns;
- patterns sharpen with repeated observations;
- the user can change health contexts and alerts later.

Acceptance:

- it can be skipped and reopened from Guide/Settings;
- it does not block HealthKit import or the first dashboard;
- completion and skip events are measured without health details.

### 6. Defer Home customization

Do not add user-facing show/hide, reorder, or compact/expanded layout controls
in this phase.

Health-context profiles may conditionally surface relevant cards within the
existing Home structure. That is content personalization, not user-configured
layout customization. It must not change primary navigation, hide shared
features, or create separate condition-specific versions of the app.

Keep the fixed Home structure centered on:

- the core gauge/status strip;
- Today’s Read, current symptoms, and a log/update path;
- Signals to Watch and its evidence/details destination;
- critical permission, sync, freshness, privacy, and safety notices;
- an active condition Watch card when one is eligible to appear;
- primary navigation and Settings.

Revisit optional Home customization only after the condition-aware features
have stabilized and analytics or direct user research show that layout control
would solve a real problem.

Acceptance for this phase:

- no new layout-preference schema or API;
- no drag-and-drop, show/hide, or compact/expanded controls;
- no profile changes primary navigation or removes access to shared features;
- condition-relevant cards deduplicate and fit within the fixed Home hierarchy.

## Multicausal Pattern Engine

### Goal

Support findings such as:

> In your history, days with both short sleep and below-usual HRV have overlapped more with migraine logs than days without that combination.

This should not begin as an unrestricted search across every possible feature combination. That would create unstable findings and a large multiple-comparison problem.

### Version 1 approach: declared conjunctions

1. Define a small, versioned set of candidate combinations per health-context profile.
2. Build conjunction features in the daily feature layer.
3. Require both inputs to satisfy their own quality and baseline rules.
4. Compare outcome rates for exposed versus unexposed days.
5. Store counts, missingness, lift, absolute difference, lag, and version.
6. Run in shadow mode.
7. Evaluate on later, unseen days before surfacing.

Example declared migraine candidates:

- `hrv_below_usual AND sleep_short`
- `pressure_falling AND sleep_short`
- `pressure_falling AND prodrome_logged`
- `resting_hr_above_usual AND hrv_below_usual`
- `rapid_temperature_change AND prior_migraine_overlap`

Example POTS/dysautonomia candidates:

- `heat_elevated AND resting_hr_above_usual`
- `sleep_short AND heart_rate_range_elevated`
- `illness_exposure AND hrv_below_usual`

Example chronic-energy candidates:

- `sleep_short AND hrv_below_usual`
- `recent_exertion AND resting_hr_above_usual`
- `temperature_deviation AND nonrestorative_sleep`

### Evidence gates

The existing single-signal pattern tiers are not strict enough for proactive
multicausal notices. Version 1 conjunctions should use the following
conservative, versioned gates.

**Shadow-only candidate**

- at least 10 conjunction-exposed days;
- at least 20 comparison days;
- at least 5 outcomes during conjunction-exposed days;
- at least 4 observed weeks.

**Emerging personal card**

- at least 15 conjunction-exposed days and 30 comparison days;
- at least 6 exposed outcomes across at least 6 observed weeks;
- relative lift of at least 1.5 and absolute difference of at least 10
  percentage points;
- no more than 25% missingness for any required input;
- no single rolling 30-day period contributes more than half of exposed days;
- the direction survives a chronological holdout using the latest 20% of days.
  The holdout must contain at least 5 conjunction days and 2 outcomes, and its
  lift must retain at least 60% of the discovery-period lift.

**Moderate alert candidate**

- at least 25 conjunction-exposed days and 40 comparison days;
- at least 10 exposed outcomes across at least 8 observed weeks;
- relative lift of at least 1.75 and absolute difference of at least 15
  percentage points;
- no more than 20% missingness;
- the chronological holdout preserves direction.

**Strong personal evidence**

- at least 40 conjunction-exposed days and 60 comparison days;
- at least 15 exposed outcomes across at least 12 observed weeks;
- relative lift of at least 2.0 and absolute difference of at least 20
  percentage points;
- the result remains directionally stable across two non-overlapping time
  windows.

A proactive notice requires more than a surfaced card:

- the association is Moderate or Strong;
- the current inputs are fresh and complete;
- the relevant outcome is not already logged as active;
- the notice family is explicitly enabled;
- a 7-day condition-specific cooldown and daily limits pass;
- at least 30 prospective days and 5 qualifying conjunction activations have
  occurred after discovery;
- a shadow evaluation has found an acceptable false-positive and relevance
  rate;
- the notice opens an evidence view and displays uncertainty plus the
  contributing observations.

These are product-launch defaults, not permanent scientific constants. Store
the threshold version with every result and require product/science review
before changing it.

### Copy progression

Shadow/research:

> Combination observed; not shown to users.

Early user-facing:

> Today resembles days when you logged more migraine symptoms.

Stronger, validated personal evidence:

> Short sleep and lower HRV are both present. In your history, that combination has often overlapped with migraine days.

Avoid:

> A migraine is coming.

## Historical Data and Import Strategy

### HealthKit

Gaia Eyes can query samples currently available and authorized in the user’s HealthKit store. It must not promise unlimited history:

- authorization is per data type;
- a user can grant a limited recent window rather than full history;
- the app may not be able to distinguish denied access from absent data;
- the earliest authorized date can differ by type.

The import flow should say:

> Import the history you choose to share from Apple Health.

It should show:

- authorized types,
- earliest authorized date per type when available,
- estimated sample count,
- import progress,
- missing/limited types,
- a privacy explanation.

Apple exposes `Headache` and several related HealthKit symptom categories, but not a complete migraine-attack model. HealthKit symptom samples can supplement Gaia Eyes history; they do not replace a migraine-diary import.

### External migraine and illness histories

Build a canonical import event before building app-specific adapters.

Proposed canonical episode fields:

- `external_event_id`
- `event_family`
- `symptom_code`
- `start_time_utc`
- `end_time_utc`
- `original_time` and timezone
- `severity`
- `attributes` such as aura or location
- `medication_response` when present
- `source_provider`
- `source_file_hash`
- `import_run_id`
- `raw_row_ref`
- `mapping_version`

Import requirements:

- preview before commit,
- explicit field mapping,
- idempotent re-import,
- duplicate detection,
- row-level validation errors,
- import summary,
- reversible import run,
- deletion by `import_run_id`,
- a user-facing **Delete imported history / Undo import** control that does not
  require deleting the whole account,
- recalculation or removal of derived features and patterns after deletion.

Retention contract:

- normalized imported events are retained until the user deletes the import or
  account;
- older normalized history may move to archival storage without changing the
  user’s deletion rights;
- the original uploaded file is encrypted, access-restricted, and deleted after
  successful verification plus a 30-day recovery window;
- import jobs are cancelled when deletion begins;
- only a non-sensitive operational receipt may remain after deletion;
- a Plus downgrade pauses Plus-only analysis but does not remove the imported
  history or its deletion controls.

Account deletion remains the final erase-all control, but it is not enough by
itself. A mistaken or unwanted import must be removable without sacrificing the
user’s Gaia Eyes account. The final retention/deletion contract requires
privacy/legal review before production imports.

Sequence:

1. Generic CSV template.
2. Apple Health symptom import.
3. Adapter for a specific migraine app only after obtaining real sample exports and confirming stable format and permitted use.
4. Optional JSON/spreadsheet adapters.

PDF physician reports should not be the first import target because layout extraction is less reliable and provenance is harder to preserve.

Candidate adapter order, based on implementation value rather than a claim
about current market rank:

1. **Migraine Buddy** — high user reach; inspect real exports before promising
   a structured adapter.
2. **Bearable** — important overlap with chronic illness and symptom tracking;
   validate its current CSV shape.
3. **MigraInsight** — advertises CSV import/export and provides a useful
   structured test case.
4. **HeadShot** — collect a redacted current export and verify its format before
   estimating adapter work.
5. **Prevent Headache** — collect a redacted current export and verify its
   format and permitted-use terms before estimating parser complexity.

For each provider, collect a redacted sample, provider/version, export date,
field dictionary, timezone behavior, stable identifiers, and terms-of-use
notes. No adapter should be inferred from a PDF report or marketing copy.

### Historical space weather

NASA OMNI provides a practical source for long-duration near-Earth solar-wind, IMF, plasma, geomagnetic-index, and energetic-particle history. Its low-resolution product is hourly from 1963 to current; its high-resolution products cover a shorter modern period.

Gaia Eyes should backfill to the horizon that creates product value:

1. cover the earliest authorized user-health date;
2. add enough earlier daily history for baselines and climatology;
3. preserve high resolution from Gaia Eyes’ existing collection forward;
4. use hourly/daily historical data where minute-level resolution is unnecessary;
5. retain provider, issue time, observation time, units, quality flags, source URL/product, parser version, and import-run provenance.

Do not choose an arbitrary start year solely because the data exists. Match resolution and date range to hypotheses, user history, storage cost, and reproducibility.

## Charts and Personal History

Charts should help answer a user question, not become a generic data warehouse UI.

### First chart bundle

- HRV, resting HR, sleep duration, respiratory rate, wrist-temperature deviation;
- symptom severity and active-day timeline;
- exposure timeline;
- gauge history;
- selected local/environmental signals;
- overlay toggle for one personal pattern at a time.

### Later comparisons

- exposed versus unexposed outcome rates;
- days matching a multicausal combination;
- pre-event windows such as 24–48 hours before migraine;
- recovery/post-event windows;
- “similar days” with the exact matching features shown.

Every chart should display:

- unit,
- timezone/day boundary,
- missing-data gaps,
- data source,
- baseline window,
- calculation version where derived,
- non-diagnostic language.

## New Signal Evaluation

New signals should be accepted only when they are reliable, explainable, timestamped, and capable of improving a user-facing question.

| Candidate | Priority | Product value | Main implementation concerns |
|---|---|---|---|
| UV Index | High | Relevant to light sensitivity, migraine context, outdoor exposure, skin/sun safety context | Forecast versus observed distinction, ZIP/lat-lon coverage, timezone, freshness, historical availability |
| Lightning / storm proximity | Medium | May add useful storm timing and local sensory context | GOES GLM processing, geospatial aggregation, event volume, latency, historical storage, product interpretation |
| Total Electron Content (TEC) | Research | Adds ionospheric electron-density context for technical/research views | Health relevance is unvalidated, gridded product handling, spatial matching, quality flags |
| New operational solar satellites/products | Medium | Improves continuity and reliability of current space-weather truth | Stable official product access, schema continuity, source transitions, no duplicate truth paths |
| Regional geoelectric field + ground conductivity context | Research | Potential regional Earth-current/grid-research context | Conductivity/resistivity/impedance and modeled geoelectric field must not be conflated with TEC; station/model resolution, provenance, and health hypothesis are unresolved |
| Land-surface temperature / heat anomaly maps | Low–medium | Could improve neighborhood-scale heat context where local weather is insufficient | Distinguish satellite land-surface temperature from air temperature, soil temperature, and personal heat exposure; require historical baselines |
| Volcano thermal context | Research | Could place official volcano status and thermal observations in a broader Earth-signals view | Thermal clusters alone do not predict eruptions; any product must use official USGS status and treat seismic, deformation, gas, and thermal evidence as separate inputs |

### Practical first signal

UV Index is the clearest next candidate. The EPA exposes ZIP/city REST endpoints for hourly and daily UV forecasts, and NOAA publishes gridded forecast products. Gaia Eyes should still run a provider-quality and historical-coverage spike before choosing the production source.

Lightning and TEC should remain research spikes until their user question, spatial resolution, storage plan, and evidence boundary are explicit.

The ground-electric concept is **not TEC**. TEC measures electrons in the
ionosphere. The closest match to “electric capacity of the ground” is regional
electrical conductivity/resistivity/impedance and the geoelectric field modeled
from geomagnetic activity plus Earth conductivity. The first deliverable should
be a research definition and source-quality review, not a health-facing map.

Land-surface temperature is a separate signal family. It may be useful for heat
exposure research after comparison with local air temperature and user
location. Volcano research must remain an Earth-science context project:
surface-temperature anomalies can be one observation, but Gaia Eyes must not
claim eruption detection from heat clusters without official multi-sensor
volcano evidence.

## Community Features

### Recommended sequence

1. **Structured community poll**
2. **Delayed, privacy-protected aggregate result**
3. **Consented community pattern research**
4. **Optional moderated community interaction**

A social feed should not precede the structured poll. A feed introduces:

- user-generated-content moderation,
- report/block workflows,
- abuse and medical-misinformation policies,
- age-rating and App Store capability changes,
- identity and privacy choices,
- operational moderation staffing.

### Community poll contract

Example:

> Did the heat affect your usable energy yesterday?

Result:

> Among 84 consenting responses, 48% reported lower usable energy.

Requirements:

- explicit community/research consent separate from core app consent;
- community consent is not bundled with a Plus purchase;
- overall results display only with at least 25 consenting responses;
- condition/profile subgroup results require at least 50 responses in every
  displayed cell;
- geographic results use broad regions, never ZIP code or city, and require at
  least 100 total responses plus at least 50 in every displayed subgroup;
- complementary/sibling cells are suppressed when one hidden value could be
  derived from the others;
- results use whole-number percentages;
- no free text in the first version;
- result date, response count, and question wording/version shown;
- descriptive wording only;
- late edits and deletions reflected in aggregates;
- withdrawal deletes raw responses and excludes them from future or recomputed
  aggregates;
- the consent contract explicitly states how already-published aggregate
  snapshots are handled.

Personal patterns and community results must be labeled and stored separately.
Community copy should say **aggregated and de-identified**, not promise
anonymity. Free text, fine geography, and sparse condition combinations remain
excluded even when a numerical threshold is met. Privacy/legal review is
required before collection begins.

## Guide Evolution

### Language modes

Technical, balanced, and mystical modes may change presentation, never factual content or confidence.

- **Technical**: data names, baselines, timestamps, evidence limits.
- **Balanced**: plain-language context and practical next steps.
- **Mystical**: reflective metaphor layered on the same verified signal state.

Mystical language must not convert an association into causation.

### Humor

Humor can be a user preference and should be:

- light,
- optional,
- absent during severe symptom states, urgent warnings, failed imports, privacy/consent decisions, or safety copy;
- tested for repetition and accessibility.

### AI Guide assistant

An AI assistant is a later phase, after the Guide’s deterministic evidence objects are stable.

Minimum safeguards:

- answers grounded in Gaia Eyes evidence objects and approved help content;
- visible source/date for current signals;
- no diagnosis, treatment changes, or emergency triage replacement;
- explicit distinction between the user’s data, community aggregates, and general education;
- minimum necessary health context sent to the model;
- documented retention and model-provider terms;
- abuse, prompt-injection, and unsupported-claim testing;
- safe fallback to deterministic Guide content.

## Website Direction

Moving away from WordPress should be a separate discovery project, not a prerequisite for personalization.

Before deciding:

- inventory public pages, member hub, auth, subscriptions, analytics, SEO, redirects, support/privacy/legal content, and WordPress-only workflows;
- identify which app surfaces require web parity;
- define the canonical API/content source;
- compare operating cost and maintenance burden;
- plan staged redirects and rollback.

Until then, app-visible product changes that have a matching member-hub surface should continue to receive parity review.

## Phased Roadmap

### Phase 0 — Contracts and measurement

- versioned health-context profile contract;
- canonical imported-event specification;
- prediction/evidence copy rubric;
- provenance requirements;
- event names for profile, walkthrough, edit/delete, and import flows;
- product/science review of declared multicausal candidates.

### Product/science review panel

Condition-specific Watch features should not be approved by a general product
review alone. Before proactive migraine/POTS/fibromyalgia notices or community
evidence claims launch, use a small paid advisory panel:

- a licensed neurologist or headache specialist, ideally with UCNS Headache
  Medicine certification, for migraine taxonomy, prodrome, and copy;
- an autonomic-disorders clinician for POTS/dysautonomia candidates;
- a biostatistician or epidemiologist experienced in longitudinal,
  repeated-measures, N-of-1, missing-data, and multiple-comparison methods;
- a health-literacy/content reviewer;
- compensated patient advisors representing the relevant conditions.

Reviewer selection should consider active license where applicable, current
condition-specific practice or publications, methods experience, conflicts of
interest, and willingness to provide versioned written sign-off. A degree
alone is not sufficient.

Use directories from recognized specialty organizations and academic headache
or autonomic programs to identify candidates. A scoped milestone review can
start at roughly 5–10 paid hours per specialist using synthetic or
de-identified cases; reviewers should not receive identifiable production
health data. Regulatory/privacy counsel remains a separate role.

#### 2026 planning budget

These are planning ranges, not vendor quotes:

- **Foundation and shadow-only work:** no external approval is required.
  Reserve `$0–$2,000` only if an early clinician or methods checkpoint would
  prevent rework.
- **Lean design checkpoint for Migraine Watch:** budget `$2,500–$5,000` for a
  bounded review by one headache clinician and one biostatistician before the
  feature contract is finalized.
- **Migraine Watch pilot review gate:** budget `$7,500–$15,000` for written
  review from the headache clinician, biostatistician, health-literacy
  reviewer, and compensated patient advisors, including one revision pass.
- **Each later condition profile:** budget roughly `$3,000–$8,000` when the
  methods and review templates can be reused but a condition-specific
  clinician and patient advisors are still needed.
- **All five initial condition areas:** plan roughly `$20,000–$45,000` if they
  are reviewed in stages rather than as one large advisory-board engagement.
- **Privacy or regulatory counsel:** obtain a separate scoped quote. Legal
  review is not included in the ranges above.

The pilot estimate assumes approximately:

- 5–8 hours of headache-specialist review;
- 8–12 hours of biostatistics/epidemiology review;
- 3–5 hours of health-literacy review;
- four patient advisors contributing 2–3 hours each;
- coordination, written revisions, and a modest contingency.

Published benchmarks support using a range rather than a single hourly rate:
Tulane currently lists external biostatistics consulting at `$180/hour` and a
core principal investigator at `$280/hour`; the Advisory Board Centre reports
`$1,000–$2,500` as the most common half-day advisor rate; and the Institute for
Healthcare Advancement lists non-medical plain-language consulting at
`$375/hour`. Gaia Eyes should request fixed-fee milestone quotes wherever
possible so the deliverables and revision limit are explicit.

This review is not a prerequisite for profile selection, editable exposures,
custom private labels, import mechanics, or shadow-only computation. It is a
gate for condition-specific prediction language, proactive outcome alerts, and
community claims. It is also not a prerequisite for profile-aware Home
curation or contextual cards limited to current observations, user-selected
relevance, and qualifying retrospective personal overlap. That boundary
matters because software framed as diagnosing, preventing, or treating a
condition has a different risk posture than a low-risk general-wellness
experience.

### Phase 1 — Personal control and relevance

- centralized profile configuration;
- editable/removable exposures;
- private custom symptoms/exposures;
- specific alert templates;
- optional walkthrough;
- condition-aware suggested symptom/exposure ordering;
- profile-aware Home driver ordering and explanations;
- non-predictive Context Watch cards using current observations and qualifying
  retrospective personal overlap.

### Phase 2 — History and shadow intelligence

- HealthKit authorized-history import UX;
- generic CSV import;
- historical space-weather backfill at selected resolutions;
- personal charts and overlays;
- declared conjunction features;
- shadow scoring and prospective evaluation.

### Phase 3 — Validated predictive Watch experiences

- Migraine Watch pilot;
- POTS/autonomic or chronic-energy pilot chosen from user demand and data coverage;
- evidence-based in-app notices;
- opt-in proactive alerts;
- clear “why today?” details and feedback loop.

### Phase 4 — Structured community layer

- consent flow;
- community poll;
- cohort suppression and aggregation;
- clearly separated community pattern cards;
- research export/audit controls.

### Phase 5 — Larger platform bets

- moderated community interaction;
- grounded AI Guide assistant;
- deeper new-signal research products;
- optional Home customization if later user research supports it;
- web-platform migration if discovery supports it.

## Cross-Cutting Risks

### Scientific

- combinatorial false positives,
- multiple comparisons,
- confounding from season, illness, medication, behavior, and missingness,
- confusing correlation with prediction,
- using current symptom logs as both input and outcome without temporal separation.

### Medical and product

- alarming users with premature notices,
- over-personalizing sparse data,
- implying a diagnosis from an onboarding selection,
- generic recovery advice appearing medical,
- too many condition modules making the app feel fragmented.

### Privacy

- importing more history than the user expects,
- exposing custom free text in analytics or aggregates,
- community cohort re-identification,
- unclear AI data handling,
- retaining original import files without a defined policy.

### Operational

- historical backfills competing with current ingest,
- high-volume lightning/grid data increasing storage and cron duration,
- too many derived combinations slowing daily patterns,
- profile logic diverging between backend, iOS, and web.

## Release and Research Gates

A new health-context feature is ready for general release only when:

- it can be enabled, disabled, and explained;
- its source data and freshness are visible;
- missing-data behavior is tested;
- base-app behavior remains intact;
- profile combinations deduplicate correctly;
- analytics omit health notes and custom free text;
- copy passes non-diagnostic review;
- iPhone and iPad layouts pass;
- matching member-hub parity is implemented or explicitly deferred.

A predictive notice is ready only when:

- the underlying association passes declared evidence gates;
- it survives prospective evaluation;
- current inputs are fresh;
- the user opted in;
- the alert opens an evidence view;
- feedback can mark it helpful, not relevant, or incorrect;
- alert quality and false-positive rates are monitored.

## Recorded Product Decisions and Remaining Review Gates

1. **Profile order**: migraine, POTS/dysautonomia,
   fibromyalgia/chronic pain, chronic energy/fatigue, then arthritis.
2. **Selection meaning**: each context records `diagnosed`, `suspected`, or
   `prefer_not_to_say`. All are self-reported and Gaia Eyes does not verify or
   imply a diagnosis.
3. **Multicausal evidence**: use the conservative versioned thresholds in this
   document. Proactive notices require prospective/shadow evaluation in
   addition to a Moderate or Strong historical association.
4. **Import retention**: normalized history is retained until import/account
   deletion and may be archived. Raw files have a 30-day recovery window.
   Users receive import-specific deletion controls. Privacy/legal review remains
   required.
5. **Custom entries**: stable private custom labels enter individual pattern
   analysis under the same evidence gates. Raw custom text never enters
   community aggregation. A repeated custom concept may be proposed for a
   canonical global code only after at least 25 consenting users use it across
   two months and human taxonomy/content review approves the mapping.
6. **Home customization**: deferred. The next phase keeps a fixed Home layout.
   Health-context profiles may conditionally surface relevant cards, but users
   will not receive hide, reorder, drag-and-drop, or compact/expanded controls.
   Revisit layout customization only after condition-aware features stabilize
   and user evidence demonstrates a need.
7. **Ground and heat signals**: treat regional geoelectric field plus ground
   conductivity as separate from ionospheric TEC. Treat land-surface
   temperature/heat anomalies as separate from volcano monitoring. Both remain
   research-only until hypotheses and providers are approved.
8. **Community safeguards**: separate opt-in; 25-response overall minimum;
   50-response condition/profile cell minimum; broad-region results only at
   100 total with 50 per displayed subgroup; no free text or fine geography;
   privacy/legal review before collection.
9. **Import adapters**: prioritize Migraine Buddy and Bearable samples, followed
   by MigraInsight, HeadShot, and Prevent Headache. Implementation still waits
   for redacted real exports and permitted-use review.
10. **External review**: specialist, methods, health-literacy, and compensated
    patient review is required before condition-specific predictive notices or
    community evidence claims, but not before private configuration,
    profile-aware Home curation, non-predictive Context Watch cards, or
    shadow-only foundations.

## Recommended Next Action

Start Phase 0 and the first two Phase 1 items:

1. write the versioned health-context profile contract;
2. select the first declared profile-specific suggestion sets;
3. add exposure update/delete API coverage and iOS editing;
4. define analytics and acceptance tests;
5. keep multicausal patterns in design/shadow scope until those inputs are stable.

This sequence delivers immediate user control and better personalization without making unvalidated predictive claims or creating a parallel condition-specific architecture.

## Primary External References

- [Apple HealthKit authorization](https://developer.apple.com/documentation/healthkit/authorizing-access-to-health-data)
- [Apple HealthKit data queries](https://developer.apple.com/documentation/healthkit/reading-data-from-healthkit)
- [Apple HealthKit symptom identifiers](https://developer.apple.com/documentation/healthkit/symptom-type-identifiers)
- [Apple HealthKit headache symptom](https://developer.apple.com/documentation/healthkit/hkcategorytypeidentifier/headache)
- [NASA OMNI data documentation](https://omniweb.gsfc.nasa.gov/omniweb/html/ow_data.html)
- [NOAA NCEI geomagnetic indices](https://www.ncei.noaa.gov/products/geomagnetic-indices)
- [EPA UV Index web services](https://www.epa.gov/enviro/web-services)
- [NOAA Global UV forecast fields](https://www.cpc.ncep.noaa.gov/products/stratosphere/uv_index/uv_global.shtml)
- [NOAA GOES Geostationary Lightning Mapper overview](https://www.nesdis.noaa.gov/s3/2025-12/GLM_Fact_Sheet_lightning.pdf)
- [NOAA US Total Electron Content product description](https://www.swpc.noaa.gov/sites/default/files/images/u2/USTEC_PDD.pdf)
- [USGS National Impedance Map](https://www.usgs.gov/programs/geomagnetism/science/mapping-grid-united-states-magnetotelluric-array)
- [USGS satellite volcano monitoring](https://www.usgs.gov/publications/forecasting-detecting-and-tracking-volcanic-eruptions-space)
- [HHS guidance on de-identification](https://www.hhs.gov/hipaa/for-professionals/special-topics/de-identification/index.html)
- [FDA general-wellness guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/general-wellness-policy-low-risk-devices)
- [UCNS certification programs](https://www.ucns.org/Online/Online/Certification_Home.aspx)
- [UCNS diplomate directory](https://www.ucns.org/Online/Online/Diplomate_Directory.aspx)
- [Tulane biostatistics consulting rates](https://bsbic.tulane.edu/pricing/)
- [Advisory Board Centre advisor-rate briefing](https://www.advisoryboardcentre.com/insight/wrap-up-advisor-rates-engagement-briefing/)
- [Institute for Healthcare Advancement consulting rates](https://betterhealthinfo.org/product/consulting-services-hourly/)
- [Migraine Buddy Help Center](https://migrainebuddy.com/help-center/)
- [Bearable data export information](https://bearable.app/medical-professionals/)
- [MigraInsight CSV import/export information](https://migrainsight.com/)
