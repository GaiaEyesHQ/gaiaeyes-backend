# Prelaunch Logic And Claims Review

This is the next review track after the main voice cleanup. It is focused on launch trust, not refactoring.

Use it to verify:

- whether thresholds are tuned sensibly
- whether ranking logic overstates what matters
- whether claim strength matches the evidence
- whether notifications and labels feel proportionate

Tags used here:

- `logic-threshold`
- `logic-weighting`
- `claim-risk`
- `launch-critical`
- `safe-for-later`

## Recommended Next Priority

After the public EarthScope caption path is stable, the next highest-value task is a targeted logic and claims pass across:

1. gauges and symptom effects
2. pattern evidence gates and confidence wording
3. driver ranking and override behavior
4. EarthScope and outlook claim strength
5. local/Schumann/notification severity ladders

This is the launch-risk layer that still needs human verification even if the voice layer is working.

## 1. Gauges And Symptom Effects

Primary files:

- `bots/gauges/gauge_scorer.py`
- `bots/gauges/signal_resolver.py`
- `bots/definitions/gauge_logic_base_v1.json`
- `services/mc_modals/modal_builder.py`

What is encoded now:

- symptom-to-gauge effects in `_SYMPTOM_GAUGE_EFFECTS`
- per-gauge symptom caps in `_SYMPTOM_GAUGE_CAPS`
- current-state multipliers in `_CURRENT_SYMPTOM_STATE_MULTIPLIERS`
- solar-wind thresholds in `signal_resolver.py`
  - watch: `>= 550 km/s`
  - high: `>= 650 km/s`
  - very high: `>= 700 km/s`
- Schumann exposure thresholds in `gauge_logic_base_v1.json`
  - elevated when `zscore_30d >= 2.0` or `pct_30d >= 0.9`
- alert severities and signal-state mappings in `gauge_logic_base_v1.json`

Why this is launch-critical:

- symptom logs can materially move the user-facing gauges on the same day
- gauge labels are among the highest-trust outputs in the app
- modal explanations inherit the confidence implied by the gauge state

What to verify manually:

- whether symptom caps feel too aggressive for `pain`, `energy`, and `sleep`
- whether `improving: 0.55` is still the right multiplier for current symptom state
- whether `resolved: 0.0` hides lingering context too abruptly
- whether Schumann `elevated` is being reached too often for ordinary noise days
- whether `watch` vs `high` mappings feel proportionate once rendered in the UI

Claim-risk notes:

- `gauge_logic_base_v1.json` explicitly says scores represent estimated stress/risk load, not outcomes
- review whether the UI still preserves that nuance or if state labels feel more deterministic than the definition intends

Tags: `logic-threshold` `logic-weighting` `claim-risk` `launch-critical`

## 2. Patterns Evidence Gates And Confidence

Primary files:

- `bots/patterns/pattern_engine_job.py`
- `app/routers/patterns.py`
- `services/patterns/personal_relevance.py`

What is encoded now:

- exposed sample minimum: `>= 6`
- unexposed sample minimum: `>= 6`
- exposed outcome minimum: `>= 3`
- relative lift minimum: `>= 1.4`
- absolute rate difference minimum: `>= 0.10`
- lags checked: `0h`, `12h`, `24h`, `48h`
- explicit exposures:
  - pressure swing: `abs >= 6.0`
  - AQI moderate+: `>= 50`
  - AQI unhealthy+: `>= 100`
  - temp swing: `abs >= 6.0`
  - Kp G1+: `>= 5.0`
  - southward Bz: `<= -8.0`
  - solar wind: `>= 550`
  - Schumann: rolling station `p80`

Why this is launch-critical:

- pattern cards are interpreted by users as evidence, not just interesting hints
- low-threshold pattern cards can make the product feel overconfident quickly

What to verify manually:

- whether `relative_lift >= 1.4` is still too permissive for small real-world datasets
- whether AQI `50` and temp swing `6 C` are producing too many patterns
- whether `Emerging` is shown too often on weak but recent signals
- whether the UI language around `Strong`, `Moderate`, and `Emerging` feels proportional to the actual evidence gates

Claim-risk notes:

- `services/patterns/personal_relevance.py` adds extra weighting on top of the raw pattern engine
- review whether driver explanations start sounding more certain than the underlying pattern thresholds justify

Tags: `logic-threshold` `logic-weighting` `claim-risk` `launch-critical`

## 3. Driver Ranking And Override Behavior

Primary files:

- `services/patterns/personal_relevance.py`
- `services/drivers/all_drivers.py`
- `app/routers/dashboard.py`

What is encoded now:

- confidence weights:
  - `Strong`: `2.6`
  - `Moderate`: `1.8`
  - `Emerging`: `1.0`
- severity weights:
  - `high`: `4.0`
  - `watch` / `elevated`: `3.0`
  - `mild`: `2.0`
  - `low`: `1.0`
- hard visibility threshold: `0.9`
- personal weighting combines:
  - signal strength
  - sensitivity boost
  - top pattern-reference scores
- top driver can be overridden and marked as more relevant even when another active signal exists

Why this is launch-critical:

- `What Matters Now` is one of the product’s main trust surfaces
- if ranking feels wrong, the rest of the explanation stack feels wrong too

What to verify manually:

- whether allergen and AQI drivers surface too often because they have both severity and pattern support
- whether solar-wind or Schumann drivers surface too weakly or too strongly for sensitive users
- whether override notes make sense on real days where multiple drivers are active
- whether leading/supporting/background labels match what a user would intuitively expect

Claim-risk notes:

- `_PATTERN_MESSAGE_MAP` in `personal_relevance.py` contains many direct “often matches” or “has shown up before” phrases
- review whether these sound grounded enough when paired with weaker evidence states

Tags: `logic-weighting` `claim-risk` `launch-critical`

## 4. EarthScope And Outlook Claim Strength

Primary files:

- `services/mc_modals/modal_builder.py`
- `bots/earthscope_post/member_earthscope_generate.py`
- `bots/earthscope_post/earthscope_generate.py`
- `services/forecast_outlook.py`
- `services/voice/outlook.py`

What is encoded now:

- semantic guardrails use `claim_strength` values like `may_notice` and `observe_only`
- outlook confidence is derived from top-driver severity and likely domains
- urgency labels still escalate to values like `watch`, `notable`, and `quiet`

Why this is launch-critical:

- daily EarthScope and outlook are often read as product judgment, not just copy
- these are brand-trust layers, not just UI components

What to verify manually:

- whether EarthScope caption/body still imply stronger personal effects than the semantic guardrails intend
- whether outlook windows with only one soft driver are still framed as worth watching
- whether public posts, member posts, and in-app EarthScope all imply similar confidence for the same underlying day

Claim-risk notes:

- public/social copy can sound more certain because it is more compressed
- member EarthScope can sound more authoritative because it is longer and more specific

Tags: `logic-weighting` `claim-risk` `launch-critical`

## 5. Local Weather, AQI, And Allergen Severity

Primary files:

- `services/local_signals/aggregator.py`
- `services/forecast_outlook.py`
- `services/external/pollen.py`
- `services/external/airnow.py`
- `app/routers/local.py`

What is encoded now:

- 3-hour trend tolerance: `1.5`
- rapid pressure drop flag: `<= -3.0 hPa` over short window
- big 24h temp shift: `>= 8.0 C`
- AQI bucket mapping:
  - good / moderate / usg / unhealthy / very_unhealthy / hazardous
- outlook severity from pressure/temp:
  - mild at `>= 6`
  - watch at `>= 8`
  - high at `>= 12`

Why this is launch-critical:

- local conditions are the easiest layer for users to reality-check against their own experience
- if this layer feels off, trust drops quickly

What to verify manually:

- whether `pressure_rapid_drop` fires too often in ordinary daily variation
- whether `big_temp_shift_24h` at `8 C` feels too aggressive or too conservative
- whether AQI `moderate` and pollen `moderate` are over-surfacing as meaningful drivers
- whether the wording on these conditions feels proportionate when the values are only mildly elevated

Tags: `logic-threshold` `claim-risk` `launch-critical`

## 6. Schumann And ULF Confidence

Primary files:

- `services/geomagnetic_context.py`
- `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`

What is encoded now:

- ULF confidence label mapping:
  - `< 0.35`
  - `< 0.65`
  - `>= 0.65` treated as high confidence
- ULF usable threshold:
  - `>= 0.20`
- Schumann thresholds remain partly UI-owned and mirrored across app/web

Why this is launch-critical:

- Schumann is both niche and highly legible to skeptical users
- parallel logic across app and web is a parity risk

What to verify manually:

- whether app and web still show the same state for the same day
- whether the confidence language feels too strong for sparse or noisy data
- whether Schumann states are appearing often enough to feel noisy

Tags: `logic-threshold` `claim-risk` `launch-critical`

## 7. Notifications And Severity Escalation

Primary files:

- `bots/notifications/evaluate_push_notifications.py`
- `services/gauges/alerts.py`

What is encoded now:

- multi-family severity bundling
- event families for CME, Schumann, pressure swing, solar-wind speed, Bz coupling, symptom follow-up, and gauge spikes
- gauge spike thresholds:
  - delta threshold `10` for detailed users
  - delta threshold `12` for normal users
  - high severity at current gauge `>= 80` or delta `>= 15`
- Schumann push severity:
  - high when `zscore >= 3.0`
  - watch otherwise

Why this is launch-critical:

- push is the fastest way to create either trust or annoyance
- users will infer confidence from notification frequency and severity wording

What to verify manually:

- whether gauge spike pushes fire too often on noisy days
- whether Schumann push titles like `spike detected` feel too assertive
- whether symptom follow-up notifications feel appropriate rather than naggy
- whether quiet-hours and sensitivity preferences are behaving as intended

Tags: `logic-threshold` `logic-weighting` `claim-risk` `launch-critical`

## Suggested Review Order

1. `bots/gauges/gauge_scorer.py`
2. `bots/definitions/gauge_logic_base_v1.json`
3. `bots/patterns/pattern_engine_job.py`
4. `services/patterns/personal_relevance.py`
5. `services/forecast_outlook.py`
6. `services/local_signals/aggregator.py`
7. `bots/notifications/evaluate_push_notifications.py`
8. `services/geomagnetic_context.py`

## Best Next Task To Execute After This

If the public EarthScope caption shadow runs continue to look good, the next implementation task should be:

- lock the current simplified caption path for live
- then start a launch-hardening pass on gauges, patterns, and notifications

That pass should be surgical:

- no broad refactors
- no new naming systems
- just verify thresholds, severity ladders, and claim wording against real days

## Safe To Defer

- billing and paywall copy/logic
- guide asset fallback cleanup
- WordPress/static educational copy polish

Those matter, but they are lower launch risk than threshold and claim verification.
