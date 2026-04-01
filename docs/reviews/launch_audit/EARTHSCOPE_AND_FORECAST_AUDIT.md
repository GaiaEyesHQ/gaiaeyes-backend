# EarthScope And Forecast Audit

EarthScope is currently the broadest voice layer in the repo and the one most likely to feel inconsistent if it is not reviewed deliberately before launch.

## Where Daily EarthScope Copy Is Generated

Primary generation layers:

- `services/mc_modals/modal_builder.py`
  - builds dashboard/home summary text and modal explanation content
- `bots/earthscope_post/member_earthscope_generate.py`
  - generates member EarthScope post content
- `bots/earthscope_post/earthscope_generate.py`
  - generates public/social EarthScope content

Primary exposure layers:

- `app/routers/dashboard.py`
- `app/routers/summary.py`
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
- `wp-content/mu-plugins/gaia-dashboard.js`

Related overlapping language layers:

- `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift`
- `bots/earthscope_post/gaia_eyes_viral_bot.py`
- `bots/earthscope_post/reel_builder.py`
- `bots/fact_overlay/fb_reel_poster.py`

## Where Structured Metrics Feed EarthScope

Observed metric and payload feed points:

- dashboard payload assembly: `app/routers/dashboard.py`
- feature/post exposure: `app/routers/summary.py`
- space-weather daily and related marts referenced by EarthScope bots
- driver and pattern relevance layers feeding narrative emphasis:
  - `services/patterns/personal_relevance.py`
  - `services/drivers/all_drivers.py`
  - `services/mc_modals/modal_builder.py`
- local and forecast context affecting related daily guidance:
  - `services/forecast_outlook.py`
  - `app/routers/outlook.py`
  - `app/routers/local.py`

## Where Qualitative Language Is Defined

| Surface | Files | Notes | Tags |
| --- | --- | --- | --- |
| Daily home summary | `services/mc_modals/modal_builder.py` | Deterministic summary phrasing tied to current drivers and patterns. | `copy-generated` `launch-critical` |
| Member longform | `bots/earthscope_post/member_earthscope_generate.py` | Richest in-app-adjacent voice layer, with template rotation and rewrite instructions. | `copy-generated` `robotic-risk` `launch-critical` |
| Public/social longform | `bots/earthscope_post/earthscope_generate.py` | Separate voice model from member post; high drift risk. | `copy-generated` `robotic-risk` `launch-critical` |
| App card/detail fallbacks | `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift` | Cleans and reparses text, adds default titles/loading text, and owns fallback behavior. | `copy-hardcoded` `logic-fallback` |
| WordPress card/detail fallbacks | `wp-content/mu-plugins/gaia-dashboard.js` | Similar cleanup and fallback logic, but maintained separately from iOS. | `copy-hardcoded` `logic-fallback` |
| Social/share hooks | `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift` | Parallel tone system for snapshots, patterns, daily state, events, and outlook. | `copy-generated` `repetitive-risk` |

## Where Repeated Phrasing May Occur

Highest risk repetition chain:

1. current drivers are weighted in `services/patterns/personal_relevance.py`
2. summary is built in `services/mc_modals/modal_builder.py`
3. longer EarthScope is generated in `member_earthscope_generate.py`
4. related social/share line is generated in `ShareCaptionEngine.swift`
5. client fallbacks add their own wrappers in `ContentView.swift` or `gaia-dashboard.js`

Likely outcomes:

- same top driver appears in multiple sentences with slightly different template wording
- repeated "today" framing across home, detail, share, and member post
- drift between app and web when a backend section is missing and local fallback text appears

## Where Daily / Weekly Forecast Styles Diverge

Daily-style sources:

- `services/mc_modals/modal_builder.py`
- `bots/earthscope_post/member_earthscope_generate.py`
- `bots/earthscope_post/earthscope_generate.py`

Forecast / outlook-style sources:

- `services/forecast_outlook.py`
- `app/routers/outlook.py`
- `app/routers/space_forecasts.py`
- `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift` for forecast sharing

Observed divergence:

- EarthScope reads like a branded daily interpretation layer
- outlook reads more like structured multi-day guidance
- share captions compress both styles into punchier lines

Risk:

- if daily EarthScope sounds warm and interpretive, but outlook sounds purely technical, the product voice can feel split
- if share captions are more playful than in-app copy, social and app brand tone may drift

## Where Social-Share Text May Overlap Or Conflict

Potential overlap areas:

- same daily state / driver explanation presented by both EarthScope and share captions
- pattern findings presented in both pattern card copy and social copy
- event wording for geomagnetic/AQI/local-state changes

Primary files:

- `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift`
- `bots/earthscope_post/earthscope_generate.py`
- `bots/earthscope_post/gaia_eyes_viral_bot.py`
- `bots/earthscope_post/reel_builder.py`
- `bots/fact_overlay/fb_reel_poster.py`

## Current EarthScope Voice Assessment

### Robotic / repetitive risk

High.

Why:

- multiple deterministic template systems exist
- several surfaces explain the same drivers and daily state
- client fallbacks add extra framing on top of already-generated text

### Trust level

Moderate, but fragile.

Why:

- pattern and signal grounding appears real
- the risk is not obvious fabrication; it is tonal over-assertion through repetition or stacked explanations

### Readability

Mixed.

Why:

- member EarthScope appears to aim for readability
- dashboard summaries are compact
- public/social and app fallback cleanup may produce inconsistent reading rhythms across surfaces

### Consistency with Gaia Eyes positioning

Partially aligned, not yet fully unified.

Why:

- the repo clearly wants a product that can sound scientific or mystical without changing the truth layer
- that intent is strongest in `CopyVocabulary.swift` and the guide/onboarding framing
- EarthScope still behaves like several adjacent voice systems rather than one controlled product voice

## Highest-Priority Review Questions

- Does home EarthScope, full EarthScope, and share copy describe the same day in compatible language?
- Are driver explanations repeated too many times across summary, modal, detail, and social layers?
- Do client fallbacks ever produce wording that conflicts with backend-generated sections?
- Is the public/social EarthScope more dramatic than the in-app EarthScope?
- Does weekly or 7-day outlook feel like the same product voice as daily EarthScope?

## Highest-Priority Files

1. `services/mc_modals/modal_builder.py`
2. `bots/earthscope_post/member_earthscope_generate.py`
3. `bots/earthscope_post/earthscope_generate.py`
4. `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
5. `wp-content/mu-plugins/gaia-dashboard.js`
6. `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift`
7. `services/forecast_outlook.py`
8. `app/routers/dashboard.py`
9. `app/routers/summary.py`
10. `app/routers/outlook.py`
