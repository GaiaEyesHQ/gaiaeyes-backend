# Gauge / Driver / Symptom / Pattern Audit

This file covers the highest-risk launch surfaces where product meaning, user-facing wording, and ranking logic intersect.

## Snapshot

- Gauge thresholds are not owned by one file.
- Gauge labels and modal explanations are not owned by one file.
- Symptom severity and current-episode state can immediately move gauge outputs.
- Driver ranking is strongly influenced by pattern-history weighting, not just current raw signal intensity.
- Pattern wording is partly centralized in backend, but repeated in several layers.

## Gauge Audit

| Gauge / surface | What it appears to represent | State labels come from | Explanatory copy comes from | Weighting / calculation likely lives in | Audit notes | Tags |
| --- | --- | --- | --- | --- | --- | --- |
| Energy | Current vitality / drain / recoverability | `bots/definitions/gauge_logic_base_v1.json` -> `zone_labels`, resolved by `services/gauges/zones.py` | dashboard/modal stack via `services/mc_modals/modal_builder.py`; driver relevance via `services/patterns/personal_relevance.py`; UI wrappers in `ContentView.swift` | `bots/gauges/gauge_scorer.py`, `bots/gauges/signal_resolver.py`, definition JSON | High-impact gauge with symptom boosts from fatigue/drained/brain fog and environmental contributors. Review for over-layered explanations. | `logic-threshold` `logic-weighting` `launch-critical` |
| Pain | Current pain pressure / flare load | Definition JSON zone labels | modal builder, current body-load explanations, pattern anchors | `bots/gauges/gauge_scorer.py` maps headache, migraine, pain, nerve pain, joint pain, stiffness, sinus pressure, light sensitivity, zaps heavily into pain | Pain is one of the clearest symptom-linked gauges and one of the easiest to overstate. Review both thresholds and explanation tone. | `logic-weighting` `launch-critical` |
| Sleep / recovery surfaces | Sleep strain, sleep disruption, and the broader recovery story shown around daily body state | Sleep zone labels are in definition JSON; recovery-style contributor messaging also appears in scorer output and summaries | modal builder, dashboard summaries, driver/pattern relevance, check-in flows | `bots/gauges/gauge_scorer.py` for sleep boosts from insomnia/restless sleep/wired; additional "recovery" contributor kind appears in scorer logic | Sleep is explicit as a gauge; recovery is partly a narrative layer on top of score contributors. Review both together before launch. | `logic-threshold` `logic-weighting` `launch-critical` |
| Mood / strain / status style surfaces | Emotional load, agitation, or regulation difficulty | Mood zone labels in definition JSON; some presentation wording also comes from UI | modal builder + pattern relevance + UI wrappers | `bots/gauges/gauge_scorer.py` symptom mappings for anxious, wired, fatigue crossover; current signal weighting in resolver/scorer | Risk is less the math alone and more mixed interpretation tone: too medical in one place, too mystical or vague in another. | `logic-weighting` `repetitive-risk` `launch-critical` |
| Focus | Brain fog / attention / vigilance | Definition JSON zone labels | modal builder, patterns, ContentView wrappers | scorer mappings for brain fog, focus drift, headache/migraine crossover | Focus is highly cross-wired with energy and pain. Review to ensure explanations do not repeat the same idea across multiple cards. | `logic-weighting` `repetitive-risk` |
| Heart / autonomic | Palpitations, chest tightness, autonomic strain | Definition JSON zone labels | modal builder, daily brief, pattern relevance | scorer mappings for palpitations, chest tightness, respiratory irritation, anxious crossover | This gauge may be sensitive to claims wording. Review how strongly implications are stated. | `logic-weighting` `launch-critical` |
| Stamina | Output capacity / endurance reserve | Definition JSON zone labels | mostly downstream summaries rather than dedicated screen copy | scorer and signal resolver | Stamina is present as a gauge domain even if user attention may land first on energy and sleep. Review for hidden duplication with energy. | `logic-weighting` |

## Where Gauge Logic Is Split

- Base labels and thresholds: `bots/definitions/gauge_logic_base_v1.json`
- Threshold application to live signals: `bots/gauges/signal_resolver.py`
- Symptom and recovery weighting: `bots/gauges/gauge_scorer.py`
- Display zone resolution: `services/gauges/zones.py`
- Daily explanation bullets and summaries: `services/mc_modals/modal_builder.py`
- Driver emphasis around gauges: `services/patterns/personal_relevance.py`

Primary finding:

- the gauges are not just score objects; they are a compound layer of thresholds + symptom weighting + explanation templates + UI wrappers

## Driver Detail Audit

Primary sources:

- `services/drivers/all_drivers.py`
- `services/patterns/personal_relevance.py`
- `app/routers/drivers.py`
- `app/routers/dashboard.py`
- `gaiaeyes-ios/ios/GaiaExporter/Views/AllDriversView.swift`

Observed structure:

- current-state driver ranking is shaped in backend
- driver detail payload includes short reason, personal reason, science note, what-it-is, active-now text, and setup nudges
- iOS mostly renders these payloads, but with its own headings and wrappers

Risk assessment:

- duplication risk is high because the same underlying driver can be explained in multiple places:
  - short reason
  - personal reason
  - summary note
  - pattern summary
  - modal effects/help bullets
- the generated wording is useful, but likely to feel repetitive after repeated use

Recommended launch review focus:

- compare top pressure / AQI / solar-wind / Kp explanations side by side
- look for repeated sentence shapes across driver cards and modal bullets
- confirm "what matters now" prioritization matches the visible explanations

Tags: `copy-generated` `repetitive-risk` `launch-critical`

## Symptom Follow-Up Audit

Primary sources:

- `app/db/symptoms.py`
- `app/routers/symptoms.py`
- `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/DailyCheckInView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift`

What appears to be wired:

- symptom logging
- current episode state
- current / improving / resolved transitions
- notes / journal
- likely-driver context and history/pattern references
- follow-up prompts

Copy assessment:

- current symptoms copy is more structured than many app surfaces, but not centralized enough
- follow-up and note-related wording is spread across multiple views
- likely-driver / history phrasing can feel formulaic

Logic assessment:

- same-day symptom weighting in `bots/gauges/gauge_scorer.py` is launch-critical
- current episode updates appear to trigger the same gauge refresh path, so symptom-state wording and score changes are tightly linked

Recommended launch review focus:

- compare active vs improving vs resolved symptom messaging
- verify severity impact feels proportional across pain, fatigue, anxiety, and sleep-related symptoms
- review whether history-based pattern lines overstate causality

Tags: `copy-hardcoded` `logic-weighting` `launch-critical`

## Pattern Summary Audit

Primary sources:

- `bots/patterns/pattern_engine_job.py`
- `services/patterns/personal_relevance.py`
- `app/routers/patterns.py`
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`

What appears to be happening:

- backend computes exposure/outcome relationships using explicit evidence gates
- personal relevance then chooses which patterns matter more today
- API payloads expose those statements
- UI adds section titles, wrappers, and empty-state wording

Wording assessment:

- pattern language is better grounded than EarthScope language, but still at risk of sounding repetitive
- the repo already tries to soften claims in some places, but that softening is not uniformly enforced everywhere

Claim-risk assessment:

- biggest risk is not wild language; it is subtle overstatement through repetition
- if the same pattern relationship appears in summary, driver reason, and symptom context on the same day, the app may feel more certain than the underlying evidence actually is

Recommended launch review focus:

- review one strong pattern and one weak pattern through all surfaces on the same day
- confirm confidence wording stays proportional to evidence count and lift
- verify patterns read as "signals worth watching" rather than implied proof

Tags: `copy-generated` `logic-threshold` `repetitive-risk` `launch-critical`

## Highest-Priority Files In This Audit

1. `bots/gauges/gauge_scorer.py`
2. `bots/definitions/gauge_logic_base_v1.json`
3. `bots/gauges/signal_resolver.py`
4. `services/mc_modals/modal_builder.py`
5. `services/patterns/personal_relevance.py`
6. `services/drivers/all_drivers.py`
7. `app/routers/symptoms.py`
8. `app/db/symptoms.py`
9. `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`
10. `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
