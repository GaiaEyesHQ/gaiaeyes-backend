# Cleanup Recommendations

This file prioritizes what to review first before launch. It does not propose refactors yet.

## A. Highest-Priority Copy Cleanup Targets

1. EarthScope summary and modal language stack.
   Files: `services/mc_modals/modal_builder.py`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `wp-content/mu-plugins/gaia-dashboard.js`
   Why first: this is the most visible daily voice layer and the easiest place for repetition to show up.
   Tags: `copy-generated` `copy-hardcoded` `robotic-risk` `launch-critical`

2. Member and public EarthScope writers.
   Files: `bots/earthscope_post/member_earthscope_generate.py`, `bots/earthscope_post/earthscope_generate.py`
   Why first: brand voice, trust, and perceived product intelligence all sit here.
   Tags: `copy-generated` `robotic-risk` `launch-critical`

3. Driver explanation stack.
   Files: `services/patterns/personal_relevance.py`, `services/drivers/all_drivers.py`
   Why first: these files influence multiple surfaces and can make the whole product feel repetitive if left unchecked.
   Tags: `copy-generated` `repetitive-risk` `launch-critical`

4. Current Symptoms screen.
   File: `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`
   Why first: symptom flows are intimate and high-trust. Inline wording is still scattered.
   Tags: `copy-hardcoded` `launch-critical`

5. Daily Check-In screen.
   File: `gaiaeyes-ios/ios/GaiaExporter/Views/DailyCheckInView.swift`
   Why first: this is repeated-use copy and will feel stale quickly if not tuned.
   Tags: `copy-hardcoded` `launch-critical`

6. Guide Hub helper language.
   File: `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift`
   Why first: this is supposed to orient the product voice, but much of it is hard-coded and local.
   Tags: `copy-hardcoded`

7. What Matters Now and main shell wrappers.
   File: `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
   Why first: it frames how backend language is perceived.
   Tags: `copy-hardcoded` `logic-fallback`

8. Share caption tone system.
   File: `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift`
   Why first: social voice can drift from in-app voice fast.
   Tags: `copy-generated` `repetitive-risk`

9. Plan and membership descriptions.
   Files: `gaiaeyes-ios/ios/GaiaExporter/Views/SubscribeView.swift`, `wp-content/mu-plugins/ge-checkout.php`
   Why first: duplicated plan positioning across app and web.
   Tags: `copy-hardcoded`

10. Schumann helper wording parity.
    Files: `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`, `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`
    Why first: specialized wording can drift silently because it lives outside the main copy systems.
    Tags: `copy-hardcoded` `launch-critical`

## B. Highest-Priority Logic Review Targets

1. `bots/gauges/gauge_scorer.py`
   Why: symptom weighting, state multipliers, caps, and recovery-like contributor logic are launch-critical.
   Tags: `logic-weighting` `launch-critical`

2. `bots/definitions/gauge_logic_base_v1.json`
   Why: canonical gauge zones, labels, thresholds, and signal associations live here.
   Tags: `logic-threshold` `launch-critical`

3. `bots/gauges/signal_resolver.py`
   Why: live threshold application across pressure, AQI, solar wind, Schumann, and related inputs.
   Tags: `logic-threshold` `launch-critical`

4. `bots/patterns/pattern_engine_job.py`
   Why: evidence gates and exposure thresholds determine how believable patterns are.
   Tags: `logic-threshold` `launch-critical`

5. `services/patterns/personal_relevance.py`
   Why: ranking and explanation logic are tightly coupled here.
   Tags: `logic-weighting` `launch-critical`

6. `services/drivers/all_drivers.py`
   Why: driver ordering and user guidance are built here for a major product surface.
   Tags: `logic-weighting` `launch-critical`

7. `app/db/symptoms.py` and `app/routers/symptoms.py`
   Why: current symptom state and follow-up behavior shape both UI and gauge updates.
   Tags: `logic-weighting` `launch-critical`

8. `services/forecast_outlook.py`
   Why: daily vs multi-day interpretation and severity weighting live here.
   Tags: `logic-threshold` `logic-weighting` `launch-critical`

9. `services/local_signals/aggregator.py`
   Why: local thresholds, messages, deltas, and bucket logic all meet here.
   Tags: `logic-threshold` `launch-critical`

10. `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift` plus `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`
    Why: Schumann thresholds are effectively UI-owned, not purely backend-owned.
    Tags: `logic-threshold` `launch-critical`

## C. Structural Recommendations

1. Centralize shared product vocabulary more aggressively around `CopyVocabulary.swift`, or an equivalent backend-safe vocabulary layer.
2. Separate primary copy from fallback copy.
   Reason: EarthScope and dashboard layers currently blend authored copy with parser fallback text.
3. Centralize gauge explanation ownership.
   Reason: labels, scoring, and explanation bullets currently live in different layers.
4. Reduce driver explanation duplication.
   Reason: `personal_relevance.py`, `all_drivers.py`, and `modal_builder.py` all talk about the same signals.
5. Move plan descriptions into one shared definition if app and web must match.
6. Audit specialized UI-owned logic islands.
   Example: Schumann thresholds in app and WordPress rather than backend config.
7. Treat symptom-flow copy and symptom-flow logic as a joint cleanup track.
   Reason: symptom state changes directly affect gauges and daily summaries.
8. Fix maintainer doc drift around EarthScope writer rule files.
   Reason: navigation friction makes later cleanup slower.

## D. Launch Risk Areas

1. Repetitive EarthScope voice across app, member post, public post, and share content.
2. Inconsistent guide tone because some guide text uses shared vocabulary and some does not.
3. Scattered symptom wording across Current Symptoms, Daily Check-In, Guide Hub, and backend payloads.
4. Duplicated driver explanations that can make the app feel overly certain.
5. Fragile gauge language because state labels, thresholds, and explanation writers are split.
6. Schumann parity risk because state tuning is mirrored in separate UI stacks.
7. App/web membership language drift because plan descriptions are maintained twice.

## Suggested Review Order

1. Gauges and symptom weighting
2. EarthScope daily voice
3. Driver and pattern explanation stack
4. Current Symptoms and Daily Check-In copy
5. Forecast / local condition interpretation
6. Guide Hub and onboarding / paywall consistency
