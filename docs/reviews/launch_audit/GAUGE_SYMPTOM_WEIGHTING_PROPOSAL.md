# Gauge / Symptom Weighting Proposal

This is a discussion-first proposal. It is not an implementation plan yet.

Goal:

- reduce overreaction from symptom logging
- make gauge movement feel more believable day to day
- keep current symptoms visible without making every log feel like a spike
- align gauge states with how the product explains them

Scope:

- `bots/gauges/gauge_scorer.py`
- `bots/gauges/signal_resolver.py`
- `bots/definitions/gauge_logic_base_v1.json`
- related symptom and modal surfaces only where the logic change affects user interpretation

Tags:

- `logic-weighting`
- `logic-threshold`
- `claim-risk`
- `launch-critical`

## 1. Current Weighting Model

The current symptom effect model has four main levers inside `bots/gauges/gauge_scorer.py`:

1. Symptom-to-gauge effect map
   Source: `_SYMPTOM_GAUGE_EFFECTS`

2. Severity bucket conversion
   Source: `_severity_points`

   Current buckets:

   - `0-2 -> 2.0`
   - `3-4 -> 5.0`
   - `5-6 -> 9.0`
   - `7-8 -> 14.0`
   - `9-10 -> 18.0`

3. Recency multiplier
   Source: `_recency_multiplier`

   Current decay:

   - `<= 3h -> 1.0`
   - `<= 8h -> 0.7`
   - `<= 24h -> 0.4`
   - older -> `0.0`

4. Current-state multiplier
   Source: `_CURRENT_SYMPTOM_STATE_MULTIPLIERS`

   Current values:

   - `new -> 1.0`
   - `ongoing -> 1.0`
   - `improving -> 0.55`
   - `resolved -> 0.0`

Additional amplification:

- cluster bonus on `health_status`
  - `+3` for each extra symptom cluster
  - capped at `8.0`

Current symptom caps:

- `pain -> 28`
- `focus -> 18`
- `heart -> 18`
- `stamina -> 20`
- `energy -> 24`
- `sleep -> 22`
- `mood -> 18`
- `health_status -> 26`

## 2. Main Risk In The Current Model

The current model is coherent, but it has a few launch-risk patterns:

1. Severity steps are steep.
   The jump from `9.0` to `14.0` to `18.0` makes upper-end symptom logs dominate quickly.

2. New and ongoing symptoms hit equally hard.
   That may be too blunt. A newly logged spike and a long-running ongoing issue do not always deserve identical current-load behavior.

3. Health status can stack too fast.
   It receives direct symptom effects plus cluster bonus.

4. Pain / energy / sleep are still the most likely to feel “jumpier than life.”
   Their current caps and common symptom mappings make them the highest-risk surfaces for user distrust.

5. The logic and the language can drift apart.
   The logic base says these are exploratory risk-load estimates, but some rendered states can feel more deterministic than that.

## 3. Proposal Principles

This proposal is intentionally conservative.

The goal is not to rewrite the system. The goal is to make it feel:

- less jumpy
- less punitive after one bad log
- more believable on repeat use
- easier to explain in product language

Proposed rule:

- prefer softer weighting and clearer persistence over aggressive spikes

## 4. Recommended Proposal

### A. Flatten Severity Buckets Slightly

Current:

- `2 / 5 / 9 / 14 / 18`

Recommended starting proposal:

- `2 / 4 / 7 / 10 / 13`

Why:

- keeps severity mattering
- reduces the jumpiness at the high end
- lowers the chance that one severe log dominates several gauges at once

Expected effect:

- fewer sudden jumps in `pain`, `energy`, and `sleep`
- more believable step-up from mild/moderate to high severity

Priority: `launch-critical`

### B. Differentiate `new` vs `ongoing`

Current:

- `new -> 1.0`
- `ongoing -> 1.0`

Recommended starting proposal:

- `new -> 1.0`
- `ongoing -> 0.9`
- `improving -> 0.7`
- `resolved -> 0.0` for gauge load, but keep resolved context available in copy/history layers

Why:

- keeps new spikes visible
- stops long-running ongoing symptoms from hitting as hard as brand-new spikes
- makes improving symptoms fade more gradually than `0.55`

Important note:

- `resolved` does not need to keep direct gauge load, but it may still deserve explanation-layer presence for a short window

Priority: `launch-critical`

### C. Steepen Recency Decay Slightly After 3 Hours

Current:

- `1.0 / 0.7 / 0.4 / 0.0`

Recommended starting proposal:

- `1.0 / 0.6 / 0.25 / 0.0`

Why:

- keeps immediate same-day symptom effects
- reduces the sense that an earlier symptom log is still strongly driving the whole day

Priority: `launch-critical`

### D. Reduce Health Status Cluster Bonus

Current:

- `+3` per extra cluster
- capped at `8`

Recommended starting proposal:

- `+2` per extra cluster
- capped at `5`

Why:

- `health_status` already gets direct symptom effects
- the current bonus can make the combined output feel too heavy too quickly

Priority: `launch-critical`

### E. Lower The Highest-Risk Symptom Caps

Recommended starting proposal:

- `pain: 28 -> 24`
- `energy: 24 -> 20`
- `sleep: 22 -> 19`
- `health_status: 26 -> 22`
- leave `focus`, `heart`, `stamina`, `mood` unchanged on first pass unless testing shows they are also noisy

Why:

- these are the domains most likely to feel overstated after logging
- this is a controlled way to soften the system without rewriting symptom mappings

Priority: `launch-critical`

## 5. Proposal I Do Not Recommend Yet

I would not do these before launch unless testing shows the conservative pass is insufficient:

1. rewriting `_SYMPTOM_GAUGE_EFFECTS` extensively
2. changing signal-level thresholds in `gauge_logic_base_v1.json` at the same time as symptom weighting
3. adding new smoothing systems
4. changing gauge zone labels and weighting in the same pass

Why:

- too many variables will make it hard to tell what actually improved trust

## 6. Suggested Implementation Order If Approved

1. tune symptom severity points
2. tune current-state multipliers
3. reduce cluster bonus
4. lower the four highest-risk caps
5. test on real historical days before touching signal thresholds

## 7. Review Dataset To Use Before Any Implementation

Use real user-history days where at least one of these happened:

- high pain symptom logs
- fatigue + brain fog on the same day
- restless sleep followed by next-day energy drop
- improving symptom episodes that still feel present
- multiple same-day symptom clusters

The point is to compare:

- current gauge output
- proposed softer weighting
- whether the UI explanation still feels truthful

## 8. What “Better” Should Look Like

If this proposal is right, the outputs should feel:

- less spiky after one severe log
- more stable across the day
- still responsive when symptoms truly stack
- easier to explain in plain language
- less likely to imply certainty from one symptom entry

## 9. Questions To Resolve Before Implementation

1. Do you want the product to react more strongly to `new` symptoms than `ongoing` ones?
2. Should `improving` still materially affect gauges, or mostly stay visible in copy only?
3. Do you want `resolved` to have zero gauge impact but still appear in context for a short period?
4. Which matters more prelaunch:
   - responsiveness
   - stability

My recommendation:

- bias slightly toward stability for launch

## 10. Recommended Decision

If we implement a first pass, I recommend the conservative proposal:

- flatten severity points
- soften ongoing/improving
- reduce cluster bonus
- lower caps for pain/energy/sleep/health_status

This is the smallest meaningful change set that should reduce “that feels exaggerated” moments without making the app feel dead.
