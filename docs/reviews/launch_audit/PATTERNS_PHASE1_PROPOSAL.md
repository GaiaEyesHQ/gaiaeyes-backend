# Patterns Phase 1 Proposal

This is a discussion-first proposal. It is not an implementation plan yet.

Goal:

- make pattern cards feel more believable and less eager
- reduce places where weak evidence becomes strong-sounding product language
- fold the next round of pattern work into one coherent review track
- capture the lunar, sleep-lag, and HRV additions before they get lost

Scope:

- `bots/patterns/pattern_engine_job.py`
- `services/patterns/personal_relevance.py`
- `app/routers/patterns.py`
- `app/routers/lunar.py`
- any dependent pattern surfaces only where wording or ranking is affected

Tags:

- `logic-threshold`
- `logic-weighting`
- `claim-risk`
- `launch-critical`

## 1. What The Review Already Flagged

The launch audit already identified patterns as one of the main logic-risk areas.

Main concerns:

1. Evidence gates may be too permissive.

   Current gates in `bots/patterns/pattern_engine_job.py`:

   - `exposed_n >= 6`
   - `unexposed_n >= 6`
   - `exposed_outcome_n >= 3`
   - `relative_lift >= 1.4`
   - `rate_diff >= 0.10`

2. Some exposure thresholds may surface too many patterns.

   Current examples:

   - pressure swing: `abs >= 6 hPa`
   - temperature swing: `abs >= 6 C`
   - AQI moderate plus: `>= 50`
   - solar wind: `>= 550`
   - southward Bz: `<= -8`
   - Schumann: rolling station `p80`

3. `Emerging` may still feel too meaningful in the UI.

4. Personal relevance may over-amplify otherwise modest patterns.

5. Pattern wording repeats across cards, drivers, and summary surfaces, which can make the product sound more certain than the raw evidence justifies.

## 2. What The Current System Actually Does

The main pattern engine today is mostly:

- environmental or space exposure
- followed by
- symptom or biometric outcome
- with lag checks at `0h`, `12h`, `24h`, and `48h`

Notable current outcomes:

- `headache_day`
- `pain_flare_day`
- `fatigue_day`
- `anxiety_day`
- `poor_sleep_day`
- `focus_fog_day`
- `hrv_dip_day`
- `high_hr_day`
- `short_sleep_day`

Notable current pairings:

- pressure swing -> headache / pain flare / focus fog
- AQI -> fatigue / focus fog / headache
- pollen -> headache / fatigue / focus fog / poor sleep
- solar wind -> fatigue / anxiety / short sleep / high HR / HRV dip
- Schumann -> poor sleep / short sleep / focus fog / anxiety

Important limitation:

- the engine does not currently model outcome-to-outcome chains well
- it is mostly `signal -> outcome`, not `outcome -> later outcome`

That matters for patterns like:

- short sleep -> next-day drained
- sleep deficit -> next-day exhaustion

Those are not naturally expressed in the current design.

## 3. New Additions To Fold Into This Review

These are the additions that should be part of the pattern review now:

1. Lunar should be reviewed as part of the pattern track, especially for:

   - sleep
   - mood / restless-day style outcomes

2. Sleep deficit should be able to relate to next-day tired / drained / exhaustion-style symptoms with a lag.

3. Schumann should be reviewed for a possible HRV relationship if the data quality supports it.

4. The current lunar card on the Body page likely needs its own review because it is not driven by the same system as `/v1/patterns`.

## 4. Important Architectural Note About Lunar

Lunar is currently a separate logic island.

Main pattern engine:

- `bots/patterns/pattern_engine_job.py`
- `services/patterns/personal_relevance.py`
- `app/routers/patterns.py`

Lunar path:

- `app/routers/lunar.py`
- `marts.user_lunar_patterns`

The current lunar route is not just another pattern card. It separately compares:

- HRV
- sleep efficiency
- symptom frequency
- symptom severity

around full-moon and new-moon windows.

That means the current lunar card can be directionally useful while still being inconsistent with the rest of the product’s pattern logic and confidence framing.

So this should be treated as:

- a pattern-adjacent system that needs review
- not as proof that lunar is already fully integrated into patterns

Phase 1 direction:

- lunar should not remain a separate observational sidecard long-term
- the intended direction is to move lunar into the canonical pattern system
- likely future exposure keys:
  - `lunar_full_window_exposed`
  - `lunar_new_window_exposed`
- the current lunar card should be treated as an interim surface until that integration is complete

## 5. Recommended Phase 1 Pattern Priorities

### A. Tighten Evidence Gates Before Adding Many New Pairings

Recommended discussion direction:

- raise confidence requirements before broadening the pattern graph
- especially review whether `relative_lift >= 1.4` is too permissive for real user histories
- review whether `exposed_n >= 6` is enough for pattern cards that users will read as evidence

Why first:

- if the baseline engine is too eager, every new pairing will multiply that problem

Priority: `launch-critical`

### B. Review Exposure Thresholds That Probably Over-Generate

Highest-risk candidates from the audit:

- AQI `>= 50`
- temperature swing `>= 6 C`
- pressure swing `>= 6 hPa`

Why:

- these are common enough to create many candidate patterns
- once they combine with relevance weighting and copy, the app can sound too sure too often

Priority: `launch-critical`

### C. Reduce Certainty In Pattern Wording

Review the wording in:

- `services/patterns/personal_relevance.py`
- `app/routers/patterns.py`

Specific concern:

- phrases like `often matches`, `has shown up before`, and similar lines can sound more confirmed than the evidence state deserves

Why:

- even a reasonable engine can feel overconfident if the language is too direct

Priority: `launch-critical`

### D. Add Outcome-To-Outcome Lag Patterns

This is the biggest missing capability relative to how users will think.

Recommended first addition:

- a derived `sleep_deficit_exposed` signal
- with `short_sleep_day` used only as the first proxy if that is the safest way to ship the first pass
- evaluated against next-day fatigue-style outcomes

Likely first targets:

- `fatigue_day`
- `low_energy` or equivalent fatigue symptom grouping if added
- `drained`
- `wired_tired`

Why:

- this is one of the most intuitive real-world patterns in the product
- users will expect it to appear if the data exists

Important caution:

- this likely needs either:
  - derived outcome-as-exposure logic, or
  - a new explicit sleep-deficit exposure layer inside the pattern engine

Recommended direction:

- do not stop at `short_sleep_day` as the long-term design
- use it only as the bridge if needed
- the better canonical model is a broader sleep-deficit exposure that can later include:
  - short duration
  - reduced efficiency / quality
  - rolling baseline shortfall

Recommended first concrete definition:

- `sleep_deficit_exposed = true` when any `2 of 3` are true:
  - `sleep_total_minutes < 390`
  - `sleep_efficiency < 85`
  - `sleep_total_minutes <= rolling 14-day baseline - 60 minutes`, or roughly `<= 88-90%` of baseline

Recommended severe override:

- expose automatically when:
  - `sleep_total_minutes < 330`
  - or sleep is both clearly short and clearly below baseline

Why:

- this is more faithful to how users experience a true sleep deficit
- it avoids overfiring on one noisy metric
- it gives us a clean path from the current `short_sleep_day` proxy to a better long-term signal

Priority: `launch-critical`

### E. Add Schumann -> HRV As A Stricter Pattern Type

Current state:

- `solar_wind_exposed -> hrv_dip_day` exists
- `schumann_exposed -> hrv_dip_day` does not

Recommendation:

- include `schumann_exposed -> hrv_dip_day` in Phase 1
- but do not use the same looseness as ordinary symptom patterns

Why:

- HRV is noisier and more trust-sensitive than many symptom outcomes
- Schumann is already a specialized logic area and can overfit easily if the thresholds are loose
- observational framing is still appropriate, but the evidence bar should be higher

Recommended handling:

- require more history than ordinary symptom patterns
- prefer stronger lift / sample thresholds than the default engine
- keep wording observational and avoid certainty language

Recommended first-pass thresholds:

- do not surface `schumann_exposed -> hrv_dip_day` as `Emerging`
- first visible level should be `Moderate`
- recommended minimums:
  - `exposed_n >= 10`
  - `unexposed_n >= 10`
  - `exposed_outcome_n >= 4`
  - `observed_weeks >= 3`
  - `relative_lift >= 1.8`
  - `rate_diff >= 0.15`

Recommended `Strong` thresholds:

- `exposed_n >= 14`
- `unexposed_n >= 14`
- `exposed_outcome_n >= 6`
- `observed_weeks >= 4`
- `relative_lift >= 2.2`
- `rate_diff >= 0.20`
- recent outcome within the last 30 days

Recommended wording style:

- use observational lines like:
  - `Schumann variability has coincided with more HRV dip days in your history.`
- avoid direct causal wording like:
  - `Schumann affects your HRV.`

Priority: `launch-critical`

### F. Review Lunar As A Separate Phase 1 Track

Recommended lunar review questions:

1. Is the current lunar card using thresholds and wording that feel proportional?
2. Should lunar continue to live as its own card logic, or should it eventually map into the canonical pattern system?
3. Which outcomes should lunar be allowed to influence first?

My recommendation:

- start with sleep and restless/mood-like outcomes
- do not widen lunar claims beyond that until the current card logic is reviewed

Recommended mood design:

- do not use the current broad `anxiety_day` bucket as the permanent lunar mood bucket
- prefer a narrower restlessness / reactivity grouping instead
- likely shape:
  - `restless`
  - `wired`
  - `irritable`
- likely exclude stronger clinical-feeling symptom codes like `panic`
- likely exclude `low_mood` and `emotionally_sensitive`
- prefer leaving out `anxious` in the first pass unless sample volume is too sparse

Why:

- lunar-related effects, if they exist in user data, are more likely to present as restlessness, reactivity, lighter sleep, or feeling off
- reusing `anxiety_day` would mix together too many different states and make interpretation less clean

Priority: `launch-critical`

## 6. What I Would Not Do In The First Pass

I would not do these all at once:

1. tighten gates, add lunar, add sleep-lag, and add Schumann -> HRV in one implementation pass
2. rewrite all pattern copy and all ranking logic at the same time
3. merge lunar fully into the main pattern engine before we decide whether the current lunar logic is trustworthy enough to preserve

Why:

- too many moving parts will make it hard to tell what improved trust and what made it worse

## 7. Recommended Order If We Implement This Later

1. evidence-gate and threshold review
2. pattern wording / confidence softening
3. outcome-to-outcome lag patterns for sleep deficit -> next-day fatigue
4. lunar card review and sleep / restlessness alignment, with the intent to move lunar into canonical patterns
5. Schumann -> HRV addition with stricter evidence handling

## 8. Review Questions To Resolve Before Implementation

1. Should `sleep_deficit_exposed` use the recommended `2 of 3` rule immediately, or should the first pass ship with the simpler `short_sleep_day` bridge first?
2. Should the lunar restlessness / reactivity bucket be exactly `restless + wired + irritable`, or should `anxious` be included in the first pass for sample-size reasons?
3. Should `schumann_exposed -> hrv_dip_day` be limited to `Moderate` and `Strong` only, or should there ever be a hidden `Emerging` state that is not surfaced in product copy?
4. How quickly should lunar move from the current dedicated card path into the canonical pattern engine once the Phase 1 review is complete?

## 9. What “Better” Should Look Like

If this proposal is right, the pattern system should feel:

- less eager
- less repetitive
- more intuitive on obvious human patterns like bad sleep -> next-day fatigue
- more cautious on niche domains like Schumann and lunar
- more internally consistent across cards, drivers, and detail views
