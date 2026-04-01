# Voice Implementation Plan

This is the concrete rollout plan for unifying Gaia Eyes' voice without collapsing its intentional multiple-voice design.

## Objective

Build one shared meaning layer and multiple controlled renderers.

That means:

- one semantic truth contract
- one guardrail system for confidence and fear-language
- multiple renderers for app, guide/persona, and social

## Guiding Rule

Do not migrate everything at once.

The safe long-term path is:

1. introduce the shared contract
2. migrate the highest-value dynamic surfaces
3. retire duplicated fallback prose later

## Phase 1: Foundation

### Goal

Create the shared voice and semantic foundation in code, then adopt it in one high-value backend surface without trying to solve every screen at once.

### Scope

- add shared voice profile definitions
- add shared semantic payload models
- add one first semantic producer for EarthScope summary
- keep current visible behavior close to existing output

### Files

- new: `services/voice/`
- update: `services/mc_modals/modal_builder.py`
- new tests for the foundation

### Success criteria

- the repo has a code-level concept of:
  - mode
  - tone
  - guide/persona
  - channel
  - claim strength
  - semantic payload
- `build_earthscope_summary()` can be expressed as:
  - semantic payload production
  - renderer

### Explicit non-goals

- no big-bang rewrite of EarthScope
- no client migration yet
- no social migration yet
- no change to app profile storage yet

## Phase 2: Dynamic Daily Surfaces

### Goal

Move the most visible daily interpretation surfaces onto the shared semantic layer.

### Target files

- `services/mc_modals/modal_builder.py`
- `services/patterns/personal_relevance.py`
- `services/drivers/all_drivers.py`

### Deliverables

- driver explanation renderer inputs become structured
- modal copy and What Matters Now can consume the same meaning contract
- repeated phrasing starts shrinking because multiple surfaces render from one payload

## Phase 3: Social + Public Voice

### Goal

Adopt the same semantic layer for social/public content, but keep a separate public narrator profile.

### Target files

- `bots/earthscope_post/member_earthscope_generate.py`
- `bots/earthscope_post/earthscope_generate.py`
- `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift`

### Deliverables

- one `public_playful` voice profile
- same truth layer as app/member content
- no dependence on user profile mode/guide choices for public social output

## Phase 4: App Surface Migration

### Goal

Move app wrappers and fallback prose off local islands where possible.

### Target files

- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/AllDriversView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift`

### Deliverables

- fewer inline strings for high-value dynamic surfaces
- client fallbacks become packaging-only, not competing voice systems

## Phase 5: Specialized Islands

### Goal

Clean up narrower copy/logic islands after the main narrative stack is stable.

### Target files

- `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`
- `gaiaeyes-ios/ios/GaiaExporter/Views/OnboardingFlowView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/SubscribeView.swift`
- `wp-content/mu-plugins/ge-checkout.php`

### Deliverables

- Schumann parity review
- onboarding / membership tone consistency

## Transitional Rule

During Phase 1 and early Phase 2, seed text from legacy systems is allowed only as a compatibility bridge.

Examples:

- daily brief text generated elsewhere can be passed as a seed
- action labels can remain literal if they are not yet normalized

But the direction should always be:

- fewer seed strings
- more structured meaning

## Priority Order

1. EarthScope summary
2. What Matters Now
3. driver short reason / personal reason
4. share captions
5. member EarthScope detail
6. current symptoms
7. guide hub
8. onboarding / paywall

## Reviewer Checklist For Each Phase

- same facts across all renderers
- confidence wording does not drift
- humor does not add urgency
- mystical wording does not overstate certainty
- social stays playful without becoming alarmist
- persona changes flavor, not evidence
