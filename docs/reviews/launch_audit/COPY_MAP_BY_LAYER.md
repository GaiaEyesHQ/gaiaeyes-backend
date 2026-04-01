# Copy Map By Layer

This file is the fastest answer to "where does this wording live?"

## Guide Layer

| Feature | Source file(s) | Copy source type | Notes | Cleanup priority | Tags |
| --- | --- | --- | --- | --- | --- |
| Top-left guide entry and avatar shell | `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideEntryButton.swift`, `GuideAvatarView.swift`, `GuideAssetResolver.swift`, `gaiaeyes-ios/ios/GaiaExporter/Models/UserExperienceProfile.swift` | hard-coded + config-driven | Entry treatment is structural; visible labels are light, but guide identity and asset selection live here. Cat assets appear fully wired; dog/robot fall back. | Medium | `copy-hardcoded` `logic-fallback` |
| Guide Hub | `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift` | hard-coded | Large amount of helper and section copy lives directly in the view: daily check-in, daily poll, EarthScope lead-in, Understanding Gaia Eyes teaser, empty/fallback text. | High | `copy-hardcoded` `repetitive-risk` `launch-critical` |
| Guide prompt framing | `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuidePromptStyle.swift` | centralized | One of the cleaner prompt-style sources. Good candidate to expand if guide tone gets centralized later. | Medium | `copy-centralized` |
| Guide tone vocabulary | `gaiaeyes-ios/ios/GaiaExporter/Models/CopyVocabulary.swift` | centralized | Scientific vs mystical labels and post-processing live here. This is a real centralization point, but much of the app does not consistently route through it. | High | `copy-centralized` `launch-critical` |
| Understanding Gaia Eyes trust layer | `gaiaeyes-ios/ios/GaiaExporter/Models/UnderstandingGaiaEyesContent.swift`, `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/UnderstandingGaiaEyesView.swift` | centralized | Research/context copy is relatively well organized here. Tone is steadier than most app surfaces. | Low | `copy-centralized` `safe-for-later` |

## Drivers Layer

| Feature | Source file(s) | Copy source type | Notes | Cleanup priority | Tags |
| --- | --- | --- | --- | --- | --- |
| Home summary / What Matters Now | `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `gaiaeyes-ios/ios/GaiaExporter/Models/CopyVocabulary.swift`, `app/routers/dashboard.py`, `services/patterns/personal_relevance.py` | mixed: hard-coded wrapper + backend-generated body | Section titles and wrappers live in iOS; leading and supporting driver explanations mainly come from backend ranking services. | High | `copy-generated` `copy-hardcoded` `launch-critical` |
| Driver detail rows / All Drivers screen | `gaiaeyes-ios/ios/GaiaExporter/Views/AllDriversView.swift`, `gaiaeyes-ios/ios/GaiaExporter/Models/AllDriversModels.swift`, `app/routers/drivers.py`, `services/drivers/all_drivers.py` | mixed | Driver names, reasons, science notes, setup hints, and summary notes are mostly backend-computed, but screen-level headings and empty states remain local. | High | `copy-generated` `copy-hardcoded` `repetitive-risk` `launch-critical` |
| Driver modal / gauge explanation crossover | `services/mc_modals/modal_builder.py`, `services/signal_bar.py` | generated | Daily explanation bullets and modal summaries are assembled here. This is a dense hotspot for repetitive phrasing. | High | `copy-generated` `repetitive-risk` `launch-critical` |
| Setup nudges tied to drivers | `services/drivers/all_drivers.py` | generated | "Add location", "Connect health data", and "Log symptoms" style prompts are embedded in backend payload construction. | Medium | `copy-generated` |

## Symptoms Layer

| Feature | Source file(s) | Copy source type | Notes | Cleanup priority | Tags |
| --- | --- | --- | --- | --- | --- |
| Current Symptoms screen | `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift` | mixed: local blocks + some mode-aware resolved copy | Some copy is grouped through `CurrentSymptomsCopy.resolve(...)`, but many labels, buttons, notes, and pattern sentences remain inline. | High | `copy-hardcoded` `repetitive-risk` `launch-critical` |
| Daily Check-In | `gaiaeyes-ios/ios/GaiaExporter/Views/DailyCheckInView.swift` | hard-coded | Major user-facing wording is embedded in the view. Good candidate for future copy centralization. | High | `copy-hardcoded` `launch-critical` |
| Symptom logging payloads and follow-up prompts | `app/routers/symptoms.py` | generated | Backend serializes labels, context badges, and follow-up prompt-related payloads. | High | `copy-generated` `launch-critical` |
| Symptom state / status text around episodes | `app/db/symptoms.py`, `app/routers/symptoms.py` | generated | More logic-heavy than copy-heavy, but it determines what the UI is able to say about active, improving, or resolved episodes. | High | `logic-weighting` `launch-critical` |
| Symptom surfaces inside Guide Hub | `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift` | hard-coded | Symptoms-related helper copy is duplicated at the guide layer rather than shared from one source. | Medium | `copy-hardcoded` |

## Patterns Layer

| Feature | Source file(s) | Copy source type | Notes | Cleanup priority | Tags |
| --- | --- | --- | --- | --- | --- |
| Pattern summaries and explanation lines | `services/patterns/personal_relevance.py`, `app/routers/patterns.py` | generated | This is the main pattern-language stack. It contains reusable explanation maps, short reasons, compact lines, and pattern anchor statements. | High | `copy-generated` `repetitive-risk` `launch-critical` |
| Pattern screen wrappers / empty states | `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift` | hard-coded | The app shells the backend pattern content with its own titles, sections, and empty-state language. | Medium | `copy-hardcoded` |
| Pattern engine technical interpretation | `bots/patterns/pattern_engine_job.py` | generated + threshold-driven | Most copy here is closer to machine interpretation than user-facing prose, but it controls the statements later emitted downstream. | High | `logic-threshold` `launch-critical` |

## EarthScope Layer

| Feature | Source file(s) | Copy source type | Notes | Cleanup priority | Tags |
| --- | --- | --- | --- | --- | --- |
| Home EarthScope summary card | `services/mc_modals/modal_builder.py`, `app/routers/dashboard.py`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift` | generated + UI fallback | Summary lines come from backend, but parsing, cleanup, default titles, and loading copy are also in the iOS layer. | Highest | `copy-generated` `copy-hardcoded` `robotic-risk` `launch-critical` |
| Member EarthScope post | `bots/earthscope_post/member_earthscope_generate.py` | generated | Dedicated member voice system with deterministic template rotation and a rewrite step. Likely the most important launch copy system after gauges. | Highest | `copy-generated` `robotic-risk` `launch-critical` |
| Public/social EarthScope post | `bots/earthscope_post/earthscope_generate.py` | generated | Separate voice/rules from member EarthScope. Strong chance of wording drift versus in-app daily language. | Highest | `copy-generated` `robotic-risk` `launch-critical` |
| EarthScope media/share captions | `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift`, `bots/earthscope_post/gaia_eyes_viral_bot.py`, `bots/earthscope_post/reel_builder.py`, `bots/fact_overlay/fb_reel_poster.py` | generated | Social wording overlaps conceptually with app EarthScope, but is maintained separately. | High | `copy-generated` `repetitive-risk` |
| WordPress member dashboard EarthScope | `wp-content/mu-plugins/gaia-dashboard.js`, `wp-content/mu-plugins/gaia-dashboard.php` | hard-coded + fallback | Web card parsing, "What Matters Now", loading text, and EarthScope fallback content are separate from iOS. | High | `copy-hardcoded` `logic-fallback` `launch-critical` |

## Data Layers

| Feature | Source file(s) | Copy source type | Notes | Cleanup priority | Tags |
| --- | --- | --- | --- | --- | --- |
| Local weather / pressure / temperature context | `app/routers/local.py`, `services/local_signals/aggregator.py`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `wp-content/mu-plugins/gaiaeyes-local-check.php` | mixed | Logic and message snippets are backend-defined; surface labels and helper text remain local to app/web views. | High | `copy-generated` `copy-hardcoded` |
| Air quality / allergens | `services/external/airnow.py`, `services/external/pollen.py`, `services/local_signals/aggregator.py`, local display views/plugins | mixed | AQI/allergen state wording is partly normalized in backend, then surfaced differently in app and web. | High | `copy-generated` `logic-threshold` |
| Space weather / geomagnetic / CME / flare language | `app/routers/space_forecasts.py`, `services/forecast_outlook.py`, `services/geomagnetic_context.py`, `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift` | mixed | Several separate display surfaces pull from the same signal families, but not from one wording source. | High | `copy-generated` `copy-hardcoded` `launch-critical` |
| Schumann / ULF | `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`, `services/geomagnetic_context.py`, `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`, `wp-content/mu-plugins/gaiaeyes-schumann-detail.php` | mixed | Schumann has its own copy/tuning island with dedicated help text and UI state labels. | High | `copy-hardcoded` `logic-threshold` `launch-critical` |
| Health / HealthKit permissions and import status | `gaiaeyes-ios/ios/GaiaExporter/Views/OnboardingFlowView.swift`, `gaiaeyes-ios/ios/GaiaExporter/HealthKitManager.swift`, `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitBackgroundSync.swift` | hard-coded | Permission and import messaging is app-local. Cleaner than EarthScope, but still not centralized. | Medium | `copy-hardcoded` |
| Membership / paywall / checkout | `gaiaeyes-ios/ios/GaiaExporter/Views/SubscribeView.swift`, `Views/Auth/LoginView.swift`, `Services/Billing/CheckoutService.swift`, `app/routers/billing.py`, `wp-content/mu-plugins/ge-checkout.php`, `wp-content/mu-plugins/gaia-subscriptions.php` | hard-coded | Plan descriptions are duplicated between app and web. Backend billing route is mostly logic/config, not marketing copy. | Medium | `copy-hardcoded` |
| About / trust / research context | `gaiaeyes-ios/ios/GaiaExporter/Models/UnderstandingGaiaEyesContent.swift`, `Views/Guide/UnderstandingGaiaEyesView.swift`, `docs/` trust-layer docs | centralized | This area is relatively coherent and should inform future cleanup elsewhere. | Low | `copy-centralized` `safe-for-later` |
