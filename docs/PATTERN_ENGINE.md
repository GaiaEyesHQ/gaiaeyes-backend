# Pattern Engine v1

Pattern Engine v1 is Gaia Eyes' first deterministic personal pattern layer. It does not use ML or LLM scoring.

## Scope

- Reuses `marts.daily_features` as the canonical user/day base.
- Enriches each day with:
  - `marts.user_gauges_day`
  - `marts.user_gauges_delta_day`
  - symptom totals grouped from self-reported logs
  - current sensitivity + health-context flags
  - local weather / AQI daily joins when cached local signals exist
  - quick camera health summaries when available
- Derives daily outcomes in `marts.user_daily_outcomes`.
- Computes user-specific associations in `marts.user_pattern_associations`.

## Storage

- `marts.user_daily_features`
  - Materialized by the batch job from `marts.daily_features` plus user/day joins.
- `marts.user_daily_outcomes`
  - Binary grouped outcomes such as `headache_day`, `pain_flare_day`, `fatigue_day`, `poor_sleep_day`, and biometric flags like `high_hr_day`, `short_sleep_day`, and `hrv_dip_day` when enough history exists.
- `marts.user_pattern_associations`
  - Stores all computed lag rows, including unsurfaced rows.
- `marts.user_pattern_associations_best`
  - Best lag only per user, signal, and outcome using the v1 tie-break rules.

## Scoring Rules

- Time grain: daily.
- Lags:
  - `0h` => same day
  - `12h` => next-day proxy because v1 is still daily-grain
  - `24h` => next day
  - `48h` => day + 2
- Minimum evidence to surface:
  - `exposed_n >= 6`
  - `unexposed_n >= 6`
  - `exposed_outcome_n >= 3`
  - `relative_lift >= 1.4`
  - `rate_diff >= 0.10`
- Confidence buckets:
  - `Emerging`
  - `Moderate`
  - `Strong`

The batch job documents the concrete thresholds inline in `bots/patterns/pattern_engine_job.py`.

## Refresh

- Batch script: `python bots/patterns/pattern_engine_job.py --days-back 180`
- GitHub Actions:
  - `.github/workflows/gauges_and_member_writer_daily.yml`
- Default lookback:
  - 180 days for v1 so stale relationships age out naturally and deeper history can stay a later premium expansion.

## API + App Surface

- Backend route:
  - `GET /v1/patterns`
  - Pattern cards now include `usedToday` / `usedTodayLabel` when that association is actively shaping current guidance.
- iOS surface:
  - `YourPatternsView` inside the Insights flow
  - Sections:
    - Clearest Patterns
    - Still Taking Shape
    - Body Signals

## Pattern-Aware Guidance Integration

- The dashboard and Mission Control surfaces consume stored pattern rows without changing the underlying scoring math.
- Deterministic personal-relevance weighting combines:
  - current driver severity
  - pattern confidence + lift
  - health-context relevance
  - recent outcome history
- Outputs are exposed through `GET /v1/dashboard` as:
  - `primary_driver`
  - `supporting_drivers`
  - `pattern_relevant_gauges`
  - `active_pattern_refs`
  - `today_personal_themes`
  - `today_relevance_explanations`
- These fields let the app:
  - reorder today's drivers by personal relevance
  - use explicit personal pattern language in gauge and driver modals
  - lead the EarthScope / daily brief with the user's strongest current pattern match
  - explain when a personally relevant driver outranks a globally louder signal
  - use live-state phrasing (`right now`, `currently`, `at the moment`) on refresh-driven surfaces

## Language + Privacy

- Wording stays observational:
  - "appears"
  - "tends to"
  - "more often"
- The feature is non-diagnostic and relies on self-reported context plus recent sensor history.
