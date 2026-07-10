# Gaia Eyes Architecture Review

Date: 2026-07-09
Scope: backend, Supabase schema, ingestion jobs, iOS client, WordPress/web surfaces, and existing documentation.
Mode: recommendation-only. No code or database schema changes were made for this review.

## Executive Summary

Gaia Eyes is already closer to a research-grade observatory than a typical health app. The repo has a natural layered architecture:

1. Raw user observations in `gaia.*` and `raw.*`.
2. External environmental observations in `ext.*`.
3. Derived daily/hourly/5-minute marts in `marts.*`.
4. Deterministic interpretation layers in bots and services.
5. API surfaces consumed by iOS and WordPress.
6. Public/social EarthScope content generated from the same signal families.

The best next step is not a rewrite. It is to formalize the research contract that already exists implicitly, then add a canonical event/research layer beside the current schema. The platform should evolve by additive migration, backfill, and validation, preserving all existing raw data and current product behavior.

The core architectural principle should become:

> Every engineering decision should maximize future scientific value while preserving user trust, privacy, and product usefulness. Raw observations are irreplaceable; derived interpretations can always be regenerated.

## Current Strengths

### 1. Raw and Derived Layers Already Exist

The current database split is directionally correct:

- `gaia.samples` stores HealthKit/device samples with `start_time`, `end_time`, `type`, `value`, `unit`, `source`, and idempotent uniqueness.
- `raw.user_symptom_events` stores user-reported symptoms with UTC timestamps, severity, free text, tags, and source.
- `raw.user_exposure_events` stores manual/context exposure events with intensity, UTC timestamp, source, and notes.
- `raw.app_analytics_events` stores app behavior events with event timestamp, platform, version, session, surface, and sanitized properties.
- `ext.*` tables act as external source landing tables for space weather, hazards, forecasts, visuals, quakes, Schumann/ULF-related data, and more.
- `marts.*` tables/views contain rollups and derived features, including `marts.daily_features`, `marts.user_daily_features`, `marts.user_daily_outcomes`, and `marts.user_pattern_associations`.

This is a strong foundation for research because it already separates observation from interpretation.

### 2. Timestamps Are Usually First-Class

Most important user and environmental records include time fields:

- Health samples: `start_time`, `end_time`.
- Symptoms: `ts_utc`.
- Exposure events: `event_ts_utc`.
- Analytics: `event_ts_utc`, `received_at`.
- Space/weather/ext tables: `ts_utc`, `issued_at`, `published_at`, `event_time`, `forecast_time`, or similar.
- Pattern rollups: `day`, `lag_hours`, `first_seen_at`, `last_seen_at`, `updated_at`.

This makes later time-series and lag analysis feasible.

### 3. Deterministic Pattern Engine Is Explainable

`bots/patterns/pattern_engine_job.py` is a good research starting point because it stores explicit:

- signal definitions,
- exposure thresholds,
- outcome definitions,
- lag windows,
- sample counts,
- exposed/unexposed rates,
- relative lift,
- rate difference,
- confidence buckets,
- surfaceability flags.

It also stores all computed lag rows, not only the best visible pattern. That matters. Researchers need to inspect the misses, weak associations, and alternate lags, not just the winning cards.

### 4. Product Copy Already Avoids Hard Causation

The docs and APIs repeatedly frame patterns as observational and non-diagnostic. This is exactly the posture needed for scientific credibility:

- "appears,"
- "tends to,"
- "has overlapped more,"
- "may contribute,"
- "does not diagnose, prove causes, or replace medical care."

The language can be tightened, but the philosophy is already sound.

### 5. iOS Health Ingestion Is Architecturally Valuable

The iOS HealthKit pipeline stores granular samples, uses background observers, backfill, anchors, upload batching, retries, and cached app-state recovery. This is not just useful for the app; it is the beginning of a longitudinal person-day/person-sample research dataset.

### 6. WordPress and iOS Share Many Backend Truth Sources

The app and web increasingly consume the same API/mart layers. WordPress still has more JSON fallback paths, but the documented direction says Supabase/backend is the universal source of truth and JSON snapshots are fallbacks.

## Main Gaps

### 1. The Research Mission Is Not Yet a Top-Level Architecture Contract

Existing docs describe Gaia Eyes as a personalized environmental signal interpretation engine. That is accurate, but incomplete. The docs do not yet clearly state that the backend is also a long-term scientific observatory designed to support reproducible, time-synchronized research.

Agents need a durable rule:

- preserve raw observations,
- preserve original and normalized time,
- preserve source/provenance,
- preserve units,
- preserve quality/confidence flags,
- version derived calculations,
- never collapse raw history into only daily summaries.

### 2. There Is No Canonical Event Model Yet

Many tables already look event-like, but there is no single schema or specification that says what an event is.

Gaia Eyes should define a canonical event abstraction:

- `event_id`
- `event_type`
- `event_family`
- `subject_type` (`user`, `earth`, `space`, `location`, `platform`)
- `user_id` when applicable
- `start_time_utc`
- `end_time_utc`
- `observed_time_utc`
- `original_time`
- `original_timezone`
- `location`
- `source`
- `source_id`
- `unit`
- `value`
- `confidence`
- `quality_flags`
- `raw_ref`
- `derived_from`
- `schema_version`
- `created_at`

This should be additive. Existing tables should remain operational. A canonical event layer can be populated from them.

### 3. Provenance Is Present but Not Uniform

Some domains preserve raw payloads and source metadata well. Others only preserve normalized fields or source labels. For future publication-grade methods, provenance needs a consistent contract:

- upstream provider,
- upstream URL/product,
- fetch time,
- provider issue/valid time,
- parser version,
- processing version,
- raw payload location or hash,
- units before and after normalization,
- quality flags,
- missing-data policy.

### 4. Time Normalization Needs a Formal Spec

The code often normalizes to UTC, but the rule is not documented as a universal standard. Gaia Eyes should explicitly store:

- normalized UTC timestamps for computation,
- original upstream timestamp when available,
- original timezone/offset when available,
- local day only as a derived view,
- user-local day bucket with the timezone used to compute it.

The current use of `America/Chicago` as a default is operationally useful, but research methods should distinguish app default timezone from each user's actual local context.

### 5. Derived Tables Are Not Fully Versioned

`src` and `updated_at` exist in several marts, which helps. But research reproducibility needs stronger versioning:

- algorithm name,
- algorithm version,
- code commit SHA,
- input table versions or snapshot hashes,
- parameters/thresholds used,
- calculation run ID.

This is especially important for `marts.daily_features`, gauge scoring, pattern associations, ULF context, and forecast parsing.

### 6. Hypotheses Are Computed but Not Registered

The pattern engine computes associations, but Gaia Eyes does not yet have a durable hypothesis registry. To be taken seriously by researchers, every meaningful relationship should eventually have a record:

- title,
- status (`exploratory`, `locked`, `prospective`, `supported`, `weakened`, `unsupported`, `retired`),
- variables,
- population,
- inclusion/exclusion criteria,
- lag window,
- statistical method,
- created date,
- locked date,
- model version,
- prospective predictions,
- negative results,
- reviewer notes.

This is the bridge between product patterns and publishable methods.

### 7. Prospective Validation Is Missing

The engine is currently strongest as exploratory pattern detection. The next credibility step is prospective validation:

- discover pattern on historical data,
- freeze parameters,
- record future predictions before outcomes occur,
- evaluate against chance/baseline,
- publish successes and failures.

This should be a separate layer from the user-facing app so the product can remain useful while research claims stay cautious.

### 8. WordPress JSON Fallbacks Can Drift From Canonical Data

WordPress still uses several JSON-only or partial-parity datasets. That is okay operationally, but research docs should state:

- API/Supabase is canonical for research.
- JSON/media snapshots are presentation/fallback artifacts.
- Any JSON snapshot used for analysis must record generation time, source data, and commit/hash.

## Recommended Target Architecture

Use the existing system as the base and formalize this pipeline:

```text
Raw Observation
  -> Normalized Observation
  -> Event
  -> Feature
  -> Model
  -> Prediction
  -> Hypothesis
  -> Publication / Report
```

### Raw Observation

The exact source record or closest available equivalent.

Examples:

- HealthKit sample from iOS.
- Symptom log.
- Exposure log.
- NOAA/SWPC row.
- USGS quake event.
- GDACS alert.
- Schumann station row.
- ULF 5-minute station/context row.

Rule: never overwrite or discard raw observations for convenience.

### Normalized Observation

A cleaned version with standardized units and UTC time, while preserving the original timestamp/unit/source metadata.

Rule: normalization must be documented and versioned.

### Event

A time-bounded semantic object on a shared timeline.

Examples:

- X-class flare.
- Kp >= 5 window.
- sustained southward Bz.
- pressure drop.
- allergen exposure.
- migraine onset.
- sleep session.
- HRV dip.
- M7+ earthquake.
- volcanic eruption/report.

Rule: events are the common language for cross-domain alignment.

### Feature

A derived variable used in scoring, analysis, or product rendering.

Examples:

- `pressure_swing_exposed`
- `sleep_deficit_exposed`
- `schumann_variability_proxy`
- `ulf_regional_intensity`
- `hrv_dip_day`
- `migraine_day`

Rule: features must list inputs, methods, thresholds, and version.

### Model

The algorithm used to score, classify, rank, or detect patterns.

Examples:

- gauge scorer,
- pattern engine v1,
- personal relevance weighting,
- forecast/outlook parser,
- ULF context classifier.

Rule: model output must be reproducible from stored inputs and versioned parameters.

### Prediction

A time-stamped, pre-outcome record of what a model expected.

Examples:

- "After qualifying X-class flare, monitor M7+ quake probability in 4-6 days."
- "User's migraine risk is elevated in the next 24 hours after pressure drop."

Rule: predictions must be stored before outcomes and evaluated later.

### Hypothesis

A durable research object that binds variables, lag windows, methods, and validation status.

Rule: hypotheses should include both positive and negative results.

## Database Direction

### Do Not Rewrite Current Tables

The current schema is operational and already research-useful. Replacing it would create unnecessary risk.

Recommended strategy:

1. Keep existing tables as source-of-truth.
2. Add research metadata tables beside them.
3. Add a canonical event layer.
4. Backfill from existing raw/ext/marts tables.
5. Validate row counts, timestamps, and source references.
6. Run old and new paths in parallel.
7. Only move product reads after the new layer proves parity.

### Candidate Additive Tables

These should be designed later, not rushed into this review:

- `research.data_sources`
- `research.ingest_runs`
- `research.raw_observation_index`
- `research.events`
- `research.event_links`
- `research.feature_definitions`
- `research.feature_values`
- `research.model_versions`
- `research.model_runs`
- `research.hypotheses`
- `research.hypothesis_versions`
- `research.predictions`
- `research.validation_results`
- `research.analysis_runs`

### Backfill Feasibility

Existing data can be migrated without loss if the migration is additive.

Likely clean mappings:

- `gaia.samples` -> health observation events.
- `raw.user_symptom_events` -> symptom events.
- `raw.user_symptom_episodes` and updates -> symptom episode/duration events.
- `raw.user_exposure_events` -> exposure events.
- `raw.app_analytics_events` -> app interaction events.
- `ext.donki_event` -> solar flare/CME/event observations.
- `ext.global_hazards`, `ext.gdacs_alerts`, quake tables -> hazard events.
- `marts.ulf_context_5m` -> derived geomagnetic context events.
- `marts.user_pattern_associations` -> exploratory model outputs.

Potentially lossy or needs review:

- JSON-only media datasets.
- WordPress-only fallback displays.
- derived daily rows without raw upstream reference.
- any `marts.*` row where `src` does not identify enough calculation detail.

## Documentation Recommendations

Create a new canonical folder:

```text
docs/research-architecture/
  README.md
  ARCHITECTURE_REVIEW.md
  RESEARCH_PLATFORM_VISION.md
  ENGINEERING_PRINCIPLES.md
  EVENT_ENGINE_SPEC.md
  TIME_STANDARDIZATION.md
  DATA_PROVENANCE.md
  RAW_DATA_POLICY.md
  OBSERVATION_EVENT_FEATURE_MODEL.md
  HYPOTHESIS_REGISTRY.md
  ANALYSIS_ENGINE.md
  STATISTICAL_FRAMEWORK.md
  PROSPECTIVE_VALIDATION.md
  PRIVACY_ETHICS.md
  MIGRATION_STRATEGY.md
  CURRENT_SCHEMA_ASSESSMENT.md
  CODEX_AGENT_GUIDE.md
```

Do not try to write 200 pages in one pass. Build this as a living specification, starting with the documents that directly prevent architectural drift:

1. `ENGINEERING_PRINCIPLES.md`
2. `EVENT_ENGINE_SPEC.md`
3. `TIME_STANDARDIZATION.md`
4. `DATA_PROVENANCE.md`
5. `MIGRATION_STRATEGY.md`
6. `CURRENT_SCHEMA_ASSESSMENT.md`

## Migration Strategy

### Phase 0: Freeze the Rule

Add documentation only:

- raw observations are never discarded,
- UTC is canonical for analysis,
- original timestamps/timezones are preserved when available,
- derived features must be versioned,
- research claims require prospective validation.

### Phase 1: Current Schema Assessment

Create a detailed table-by-table map:

- current table,
- grain,
- raw vs derived,
- timestamp fields,
- timezone/original timestamp support,
- source/provenance fields,
- raw payload fields,
- quality/confidence fields,
- maps to observation/event/feature/model,
- migration risk.

### Phase 2: Add Research Metadata

Before adding a big event table, add low-risk metadata tables:

- data source registry,
- ingest run registry,
- model/version registry,
- feature definition registry.

These can describe current behavior without disrupting it.

### Phase 3: Add Canonical Events

Add `research.events` and populate it from one or two low-risk domains first:

- symptoms,
- exposures,
- app analytics,
- selected external events such as DONKI flares or USGS quakes.

Validate counts and timestamps before widening.

### Phase 4: Backfill and Parallel Run

Backfill the past 9 months of API/health/environment data into research tables.

Validation must include:

- row counts by source table,
- min/max timestamps,
- user counts,
- event counts by event type,
- duplicate checks,
- timezone conversion checks,
- sample hash/source-reference checks.

### Phase 5: Analysis Engine

Only after events and metadata are stable, build research analysis tooling:

- lag explorer,
- permutation/randomization tests,
- bootstrap confidence intervals,
- multiple-comparison correction,
- prospective prediction registry,
- report generator.

## Research Claims Policy

Gaia Eyes should keep three layers separate:

1. Product guidance: useful, personalized, non-diagnostic.
2. Exploratory findings: interesting associations, clearly labeled as exploratory.
3. Research claims: methods-locked, versioned, prospectively validated, reproducible.

No user-facing or public research copy should say a signal causes an outcome unless there is appropriate evidence. The platform can say it is testing relationships, observing overlaps, and tracking whether patterns hold over time.

## Highest-Value Near-Term Work

1. Add the research architecture docs and make future agents read them.
2. Complete `CURRENT_SCHEMA_ASSESSMENT.md`.
3. Define canonical event schema without implementing it yet.
4. Define timestamp/provenance rules.
5. Add model/feature versioning to future derived outputs.
6. Add a hypothesis registry design.
7. Later, implement additive research tables and backfill.

## What Not To Do

- Do not rewrite the current database around events immediately.
- Do not replace `gaia.samples`, `raw.*`, `ext.*`, or `marts.*`.
- Do not collapse granular data into daily summaries only.
- Do not let JSON snapshots become research source-of-truth without provenance.
- Do not publish correlation claims without methods, negative results, and prospective validation.
- Do not let Codex invent schema changes before a table-by-table assessment.

## Bottom Line

Gaia Eyes does not need a new identity so much as a formalized one.

The current product is a personalized environmental health app. The backend is already becoming a time-synchronized Earth systems and human physiology observatory. The right architecture path is evolutionary:

- preserve the working app,
- preserve all existing data,
- document the scientific contract,
- add a canonical event/research layer beside current tables,
- backfill carefully,
- validate prospectively,
- and let findings become stronger only when the data continues to support them.

