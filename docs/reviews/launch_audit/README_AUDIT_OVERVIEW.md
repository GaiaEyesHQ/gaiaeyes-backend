# Launch Audit Overview

## Scope

This review pack is a read-only map of Gaia Eyes' current product language, presentation layers, and logic/config hotspots.

It was built from repo inspection only:

- required docs first, starting with `docs/NEW_AGENT_GUIDE.md`
- iOS app views/models/services
- FastAPI routers/services/db helpers
- bots and content writers
- WordPress `mu-plugins`

No product code was changed. The only additions are these audit documents.

## How To Use This Pack

Start here if the question is:

- "Where does this wording live?" -> `COPY_MAP_BY_LAYER.md` and `COPY_MAP_BY_FILE.md`
- "Where is this gauge or ranking logic coming from?" -> `LOGIC_MAP_BY_LAYER.md`
- "Which launch areas are most fragile?" -> `GAUGE_DRIVER_SYMPTOM_PATTERN_AUDIT.md`, `EARTHSCOPE_AND_FORECAST_AUDIT.md`, `DATA_LAYER_AUDIT.md`
- "What should be cleaned up first?" -> `CLEANUP_RECOMMENDATIONS.md`
- "What should I manually review before launch?" -> `HIGH_PRIORITY_REVIEW_CHECKLIST.md`

## Main Findings

1. Copy is not centralized. It is spread across iOS views, backend payload builders, EarthScope bots, and WordPress surfaces.
2. EarthScope has the most voice fragmentation. The app, backend modal summary, member writer, public writer, share captions, and WordPress all carry related but separate wording systems. Tags: `copy-generated` `repetitive-risk` `robotic-risk` `launch-critical`
3. Driver and pattern explanations are partly centralized in backend services, but they are surfaced through several layers with different wrappers and fallbacks. Tags: `copy-generated` `logic-weighting` `launch-critical`
4. Gauge thresholds and state labels are split across JSON definitions, scorer code, signal resolver code, and some UI-specific tuning for Schumann. Tags: `logic-threshold` `logic-weighting` `launch-critical`
5. Symptoms are a launch-critical bridge between copy and logic. The current symptom state model, follow-up handling, and same-day gauge weighting are spread across backend and iOS. Tags: `copy-hardcoded` `logic-weighting` `launch-critical`
6. Onboarding, permissions, and membership copy are mostly view-local. They are readable, but not yet centralized. Tags: `copy-hardcoded` `safe-for-later`

## Quick Layer Map

| Layer | Primary files | Notes |
| --- | --- | --- |
| Guide | `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift`, `GuidePromptStyle.swift`, `GuideAvatarView.swift`, `GuideAssetResolver.swift`, `gaiaeyes-ios/ios/GaiaExporter/Models/UnderstandingGaiaEyesContent.swift`, `gaiaeyes-ios/ios/GaiaExporter/Models/CopyVocabulary.swift` | Mixed centralized + hard-coded copy; asset wiring is only fully populated for cat assets. |
| Drivers | `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `AllDriversView.swift`, `app/routers/dashboard.py`, `app/routers/drivers.py`, `services/drivers/all_drivers.py`, `services/patterns/personal_relevance.py`, `services/mc_modals/modal_builder.py` | Ranking and explanations mainly come from backend, then get wrapped in UI copy. |
| Symptoms | `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`, `DailyCheckInView.swift`, `app/routers/symptoms.py`, `app/db/symptoms.py`, `bots/gauges/gauge_scorer.py` | State transitions and symptom-to-gauge weighting are key launch logic. |
| Patterns | `app/routers/patterns.py`, `services/patterns/personal_relevance.py`, `bots/patterns/pattern_engine_job.py`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift` | Core thresholds are backend-defined; UI headings and empty states are local. |
| EarthScope | `services/mc_modals/modal_builder.py`, `bots/earthscope_post/member_earthscope_generate.py`, `bots/earthscope_post/earthscope_generate.py`, `app/routers/dashboard.py`, `app/routers/summary.py`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `wp-content/mu-plugins/gaia-dashboard.js` | Highest copy divergence in the repo. |
| Local + forecast | `app/routers/local.py`, `services/local_signals/aggregator.py`, `services/external/nws.py`, `services/external/airnow.py`, `services/external/pollen.py`, `services/forecast_outlook.py`, `app/routers/outlook.py`, `app/routers/space_forecasts.py` | Data plumbing is backend-heavy, with several UI and web display surfaces downstream. |
| Health + permissions | `gaiaeyes-ios/ios/GaiaExporter/HealthKitManager.swift`, `Services/HealthKitBackgroundSync.swift`, `OnboardingFlowView.swift`, `SubscribeView.swift`, `CheckoutService.swift`, `app/routers/billing.py`, `wp-content/mu-plugins/ge-checkout.php` | Health and billing are mostly clear, but copy is still local to the surfaces. |

## Highest-Risk Review Areas

- EarthScope writing stack. Files: `services/mc_modals/modal_builder.py`, `bots/earthscope_post/member_earthscope_generate.py`, `bots/earthscope_post/earthscope_generate.py`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `wp-content/mu-plugins/gaia-dashboard.js`
- Driver ranking + explanation stack. Files: `services/patterns/personal_relevance.py`, `services/drivers/all_drivers.py`, `app/routers/dashboard.py`, `services/mc_modals/modal_builder.py`
- Symptom weighting and current-episode behavior. Files: `app/db/symptoms.py`, `app/routers/symptoms.py`, `bots/gauges/gauge_scorer.py`
- Gauge thresholds and state labels. Files: `bots/definitions/gauge_logic_base_v1.json`, `bots/gauges/signal_resolver.py`, `services/gauges/zones.py`
- Schumann state presentation. Files: `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`, `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`, `services/geomagnetic_context.py`

## Tag Legend

- `copy-hardcoded`: user-facing text lives directly in a view, plugin, or route
- `copy-centralized`: wording is intentionally collected in a content/vocabulary source
- `copy-generated`: wording is assembled from logic or templates
- `logic-threshold`: file contains cutoffs, bands, labels, or trigger thresholds
- `logic-weighting`: file changes ranking, importance, or score composition
- `logic-fallback`: file contains fallback content or behavior used when richer data is absent
- `repetitive-risk`: repeated structure or duplicated explanation patterns are likely
- `robotic-risk`: deterministic template wording may feel stiff or repetitive
- `launch-critical`: should be reviewed before launch
- `safe-for-later`: useful cleanup target, but not the first blocker

## Notable Doc Drift

- `bots/earthscope_post/README.md` still references `gaia_rules.yaml` and `gaia_guide_constants.py`, but those files were not present in `bots/earthscope_post/` during this audit.
- That is not a product-code issue, but it is a navigation and maintenance issue. Tag: `logic-fallback` `safe-for-later`
