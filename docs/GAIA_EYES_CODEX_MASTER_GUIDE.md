# Gaia Eyes — Codex Master Guide
_Last updated: 2026-03-23_

This document is the high-level operating guide for Codex agents working on Gaia Eyes. It explains how to think about the product, what the product is trying to do, what has already been implemented, what principles must guide future work, and how to prioritize decisions around onboarding, engagement, retention, personalization, and growth.

## 1) Product Identity

Gaia Eyes is not just:
- a space weather app
- a health tracker
- a symptom logger
- a mystical oracle
- a generic wellness dashboard

Gaia Eyes is:

> A personalized environmental signal interpretation engine.

It helps people understand how environmental conditions may relate to how they feel, how they function, and what patterns repeat for them over time.

The app connects:
- space weather
- Earth and environmental conditions
- body-state signals
- user-reported symptoms
- self-reported sensitivities and health context
- pattern detection
- current outlook and future outlook

The goal is not to make hard medical claims.
The goal is to help users answer:
- Why do I feel like this right now?
- What patterns seem to repeat for me?
- What might be worth watching next?

## 2) Core Product Loop

Every feature should reinforce this loop:

Signal → Feeling → Log → System responds → Insight → Repeat

Expanded:
1. The environment changes
2. The user feels something
3. The user logs symptoms or body state
4. Gaia Eyes responds immediately
5. Gaia Eyes accumulates evidence
6. Gaia Eyes detects patterns
7. Gaia Eyes improves current and future guidance
8. The user trusts the system more
9. The user returns

If a feature does not strengthen this loop, it is probably secondary.

## 3) Product Promise

Gaia Eyes should feel like:
- a guide
- a translator
- a pattern finder
- a calming intelligence layer

It should not feel like:
- a panic machine
- a cluttered dashboard
- a random stream of disconnected metrics
- a one-size-fits-all alert app

## 4) Audience Model

Gaia Eyes serves at least two overlapping audience styles.

### Scientific mode users
These users want:
- metrics
- precise wording
- signal names
- neutral explanation
- confidence and evidence language
- clean cause and context separation

Examples:
- doctors
- data-minded users
- engineers
- researchers
- quantified-self users
- health-minded skeptics

### Mystical mode users
These users want:
- meaningful interpretation
- understandable translation
- emotional resonance
- symbolic language
- guidance without jargon

Examples:
- spiritually curious users
- intuitive wellness users
- chronic illness communities who want understandable guidance
- people who want the data translated

### Non-negotiable rule
Both modes must be based on the same underlying truth layer.
Only the presentation layer changes.

## 5) Dual Mode Translation Layer

The app should support a user-facing mode switch.

### Scientific mode
Use:
- Kp
- Bz
- solar wind
- Schumann
- ULF
- AQI
- pressure delta
- temp swing
- structured labels
- neutral, factual tone

### Mystical mode
Translate concepts into friendlier or more symbolic language.

Examples:
- Schumann resonance → Earth’s heartbeat / Resonant Earth
- ULF activity → Energy waves / Energy field motion
- Solar wind → Cosmic pressure / Solar flow
- Kp / geomagnetic activity → Magnetic storm intensity
- Environmental drivers → Energy influences / Conditions shaping today

The scientific mode and mystical mode must map cleanly to the same real signals.

## 6) Personality / Guide System

Gaia Eyes should feel configurable and alive.

Planned personalization choices should be available during onboarding and editable later in settings.

### 1. Mode
- Scientific
- Mystical

### 2. Guide
Examples:
- Cat
- Robot
- Dog

These are visual and helper personas, not different products.

### 3. Tone
- Straight
- Balanced
- Humorous

The product should support these without becoming inconsistent or unserious.

### Important product principle
Personality should make the app more engaging, not less trustworthy.

## 7) Free / Plus / Pro Framing

Gaia Eyes should use access levels that map to value, not arbitrary lockouts.

### Free
Purpose:
- discovery
- curiosity
- general signal awareness
- product hook

Suggested free experience:
- Home may default to Insights / overview experience
- core cards visible
- generic current conditions
- generic EarthScope
- sample patterns or preview patterns
- limited or teaser personalization
- limited forecast
- visible upsell where personalization would appear

### Plus
Purpose:
- unlock current-state personalization

Suggested Plus:
- personalized gauges
- personalized drivers
- symptom-based responsiveness
- Your Patterns
- better What Matters Now
- richer current EarthScope
- more meaningful alerts

### Pro
Purpose:
- become daily-use intelligence layer

Suggested Pro:
- 24h / 72h / 7d outlook
- advanced pattern history
- deeper trend charts
- guide customization + tone controls
- advanced notifications / follow-up loops
- more historical comparisons
- premium research views / deeper insights

### Rule
Free should still feel useful.
Paid should feel clearly more personal and more intelligent.

## 8) Core Product Principles for Codex

When designing or editing Gaia Eyes, Codex should optimize for:
1. Clarity over completeness
2. Signal truth before personalization
3. Personal relevance over general facts
4. Trust over cleverness
5. Feedback loops over static pages
6. Emotional usability over feature density
7. Structured guidance over walls of text
8. Responsiveness after user input
9. Consistency across notifications → modals → gauges → patterns → outlook
10. Calm authority, not fear

## 9) What Gaia Eyes Has Already Implemented

### A. Core signal domains already implemented or in progress

#### Space / geomagnetic
- Kp
- Bz
- solar wind
- flare data
- CME data
- DRAP / radio absorption context
- SWPC 3-day forecast ingested in `ext.space_forecast`
- ULF layer added

#### Resonance
- Schumann (Tomsk + Cumiana)
- expanded A / F / Q style work and visual interpretation
- modern dedicated Schumann page exists

#### Local environmental
- local weather
- pressure
- temp swings
- AQI
- allergens / pollen added
- local conditions page redesigned
- 3-day local forecast added
- 7-day local forecast not fully complete yet

#### Health / personal
- HealthKit integration
- HR
- HRV
- sleep
- sleep quality scoring
- respiratory rate added
- resting HR added
- menstrual cycle added as optional context
- quick health check using camera / PPG
- symptom logging
- self-reported sensitivities / health context

### B. UI systems already built
- Mission Control
- gauges
- What Matters Now
- EarthScope
- Patterns page
- Outlook page
- Local Conditions page
- Schumann page
- Insights restructure in progress / implemented in parts

### C. Intelligence layers already built or being built
- deterministic driver logic
- pattern engine (deterministic, not ML)
- personalization weighting
- notifications
- alerts with deep-link / modal open
- initial forecast scaffolding

## 10) Signal Truth Rule (Critical)

This is one of the most important rules in the system:

> High signals can never be hidden by personalization.

Signal truth must always come first.

That means:
- strong solar wind must show up
- active geomagnetic conditions must show up
- meaningful local drivers must show up
- elevated allergens must show up
- strong current context must show up

Personalization can:
- reorder relevance
- change explanatory emphasis
- affect user-specific what-matters-most

Personalization must not:
- hide strong objective signals
- force a calm label like Quiet when meaningful signals are active
- suppress real elevated drivers from display

## 11) State vs Signal vs Meaning vs Action

Codex must always keep these separate in UI and logic.

### A. Signal
What is happening in the environment?

Examples:
- solar wind 656 km/s
- pressure dropped 9 hPa
- AQI moderate
- tree pollen high
- Schumann variability elevated
- ULF elevated

### B. State
What is Gaia Eyes saying about the current condition?

Examples:
- Quiet
- Watch
- Active
- Elevated
- Storm
- Updated from your recent logs

### C. Meaning
What may this mean for the user?

Examples:
- Energy may feel heavier
- Focus may drift
- Pain may be easier to trigger
- Sleep may feel less stable

### D. Action
What helps right now?

Examples:
- pace tasks
- reduce overstimulation
- hydrate
- take a short break
- use wind-down support

These should not all be blended together into one muddy paragraph if a cleaner structure is possible.

## 12) Patterns: How Codex Should Think About Them

Patterns are the product moat.

The system should not treat patterns as magical truth.
It should treat them as repeated relationships between conditions and user experience that become more or less reliable over time.

Patterns should:
- accumulate
- persist
- fade gradually
- influence current interpretation
- influence outlook

Patterns should not:
- vanish too aggressively
- overclaim
- sound diagnostic

### Pattern tone
Use language like:
- appears to
- tends to
- more often
- has matched your history
- has shown up before

Avoid:
- causes
- proves
- guarantees

### Pattern persistence
Patterns should fade, not disappear suddenly.

Suggested philosophy:
- strong patterns remain clearly visible
- moderate patterns remain useful
- emerging patterns should persist long enough to feel alive
- use recency + confidence + frequency, but do not be too aggressive

## 13) Symptoms: How Codex Should Think About Them

Symptoms are one of the strongest truth signals in Gaia Eyes.

They are not just logs for later analysis.
They are:
1. current-state evidence
2. future pattern evidence
3. feedback loop fuel

### Symptom logging principles
- easy
- fast
- multi-select
- severity-aware
- responsive

### Current policy direction
- symptoms should affect matching gauges same day / near real time
- severity matters
- recency matters
- default severity should be 5, not 3
- quick-log and full log should use the same weighting path
- symptoms should help update health status / body context too

### Future expansion
Do not only track bad symptoms. Consider tracking:
- feeling better
- relief
- clear-headed
- rested
- good energy
- symptom resolved / ongoing / improved / worse

Because the product should eventually understand:
- onset
- duration
- relief
- recurrence

## 14) Follow-Up / Feedback Loop Philosophy

Gaia Eyes should not only collect a symptom and stop.

A future retention / data quality layer should support:
- Still feeling it?
- Did this pass?
- Improved?
- Worse?
- Resolved?

This creates:
- richer duration data
- better pattern validity
- more useful future forecasts

This must be optional and respectful.
It should also be user-controllable in settings.

## 15) Forecast Philosophy

Forecasts are important, but must be built honestly.

Forecasts should be:
- structured
- explainable
- based on actual forecast inputs
- personalized when possible
- staged in rollout

### Current reality
Gaia Eyes already has:
- SWPC 3-day forecast ingested in text form
- local 3-day forecast added
- 7-day local forecast not fully complete yet

### Forecast rollout philosophy
First:
- normalize local 3-day forecast
- parse structured SWPC 3-day forecast
- support credible 24h / 72h outlook

Later:
- 7-day forecast once local + space forecast layers are stable

### Forecast language
Use:
- may
- more likely
- worth watching
- often aligns with

Avoid:
- will
- guaranteed
- certain

## 16) Notifications Philosophy

Notifications are one of the most important engagement systems in Gaia Eyes.

They should:
- be useful
- feel timely
- deep-link correctly
- open the right modal / card
- make immediate sense
- eventually become pattern-aware

They should not:
- feel spammy
- contradict the opened screen
- say one thing while the modal says another
- rely on hidden logic the user cannot understand

### Important
The full chain must feel coherent:

Notification → open app → correct modal/card → explanation → quick log → gauge update → pattern trust

## 17) Current Known UX Refinement Areas

Codex should recognize these as active improvement areas:

### A. Wording / hierarchy
The system has matured faster than the presentation layer.
Needs:
- calmer wording
- better structure
- less robotic phrasing
- clearer leading / supporting / background hierarchy

### B. Driver rendering / state logic
Needs:
- signal truth first
- no false Quiet
- visibility of strong signals
- better separation of objective state vs personal relevance

### C. Notification consistency chain
Needs:
- alert titles consistent with modal titles
- deep-link precision
- post-log state coherence

### D. Symptom UX redesign
Needs:
- multi-select
- grouped categories
- shared severity slider
- suggested symptoms
- post-log refresh

### E. Quick Health Check
Needs:
- stability
- clearer save-state messaging
- partial-success handling
- signal quality guidance

## 18) Onboarding Philosophy

Onboarding should not feel like account setup.
It should feel like:

> Let’s teach Gaia Eyes how to speak to you.

### Suggested onboarding flow
#### Step 1
Choose your experience:
- Scientific
- Mystical

#### Step 2
Choose your guide:
- Cat
- Robot
- Dog

#### Step 3
Choose your tone:
- Straight
- Balanced
- Humorous

#### Step 4
Choose sensitivities / context:
- pressure-sensitive
- sleep-sensitive
- migraine-prone
- allergies / sinus
- chronic pain
- nervous system sensitive
- etc.

#### Step 5
Optional health permissions:
- HealthKit
- menstrual cycle
- notifications
- location

Onboarding should create:
- delight
- immediate relevance
- personalization from day one

## 19) Retention Philosophy

Retention in Gaia Eyes does not come from raw dashboards.
It comes from the system feeling like it understands the user.

Retention drivers include:
- useful notifications
- fast symptom logging
- immediate gauge response
- pattern discovery
- current outlook
- future outlook
- guide personality / tone
- visual delight
- feeling seen

Codex should always ask:
Does this feature help the user feel understood and want to return?

## 20) Facebook / Social Growth Philosophy

Gaia Eyes currently has the most traction on Facebook.

Codex should understand:
- social is not separate from product
- social is the top of the product funnel
- social content should validate lived experience and hint at patterns

### Social content formula that works
1. Call out what people feel
2. Validate that it’s not random
3. Connect it to real conditions
4. Softly point toward Gaia Eyes

The tone can be:
- funny
- relatable
- validating
- curious

It should not become:
- doom-driven
- hard-sell
- overly technical unless in science-targeted posts

## 21) Additional Data Philosophy

Gaia Eyes should continue expanding inputs only when they help explain real daily experience.

Good additions include:
- allergens / pollen / mold
- menstrual cycle context
- respiratory rate
- resting HR
- temperature deviation
- sleep quality / sleep consistency
- ULF context
- hydration / caffeine / stress later if lightweight enough

Do not chase data just because it exists.

Ask:
Will this help explain how people feel or function today?

## 22) ULF Philosophy

ULF is useful, but it should be treated as:
- a backend refinement layer
- a confidence amplifier
- a future pattern engine signal
- not a UI-first requirement

ULF should strengthen:
- signal truth
- pattern confidence
- geomagnetic context

It should not distract from the core loop before the rest of the product is stable.

## 23) Scientific + Mystical Must Share the Same Core

This is critical.

The app can speak in two voices.
It cannot run on two different truths.

So Codex must maintain:
- one signal layer
- one pattern layer
- one forecast layer
- one state system

Only the presentation and wording adapt to the chosen mode.

## 24) What Codex Should Avoid

Avoid designing Gaia Eyes as:
- a feature dump
- a dashboard of equal-weight cards
- an over-technical app with no translation layer
- an ungrounded mystical app disconnected from actual data
- a static tracker with no loop after logging
- a push-spam machine
- a facts-only app that ignores emotional usability

Avoid hiding:
- strong signals
- relevant context
- user-confirmed symptoms

Avoid language that:
- sounds diagnostic
- sounds robotic
- sounds alarmist
- feels internally inconsistent

## 25) What Codex Should Build Next

With current system progress taken into account, Codex should prioritize:

### Product / UX
- onboarding system
- guide selection
- tone system
- science / mystical presentation layer
- symptom UX redesign
- feedback / follow-up loop

### Intelligence
- signal truth rendering
- pattern persistence tuning
- symptom weighting / recency
- structured outlook refinement
- pattern-aware current summaries

### Growth / retention
- free / plus / pro gating design
- better empty states / teaser states
- social-friendly moments
- tester onboarding flow
- useful notifications and follow-up

## 26) Final Product Mindset

Codex should think about Gaia Eyes like this:

> Gaia Eyes is a personalized, creative, trustworthy system that turns environmental complexity into meaningful human guidance.

It should be:
- clever
- beautiful
- validating
- useful
- a little fun
- deeply structured underneath
- emotionally legible on the surface

It is trying to build:
- a data loop
- a trust loop
- a retention loop
- eventually, a prediction loop

## 27) Summary for Codex in One Paragraph

Gaia Eyes is a personalized signal-to-body interpretation engine that combines space weather, Earth weather, environmental signals, HealthKit, and user-reported experience to help users understand current conditions, discover patterns, and anticipate what may matter next. Codex must always prioritize signal truth, clarity, responsiveness, and user trust. The product must support both scientific and mystical presentation modes while sharing one underlying truth layer. The goal is not just to show data, but to make the app feel like a useful guide that responds to the user, learns from them, and keeps them engaged in a meaningful feedback loop.

End.


## 28) Navigation Philosophy

Gaia Eyes should support both:

1. Quick understanding (Mission Control)
2. Deep exploration (Details pages)

Primary → Secondary navigation:

- Mission Control → What Matters Now → All Drivers
- Mission Control → Symptoms → Current Symptoms
- Insights → deep pages

Users should always be able to:
- understand quickly
- explore deeper
- take action

---

## 29) Cross-Platform Consistency

The mobile app and website must remain aligned in:

- data interpretation
- gauge behavior
- modal interactions
- symptom logging
- driver presentation

If a feature evolves on one platform, it must be reviewed for parity on the other.

The web must not lag behind the app in core interaction behavior.

---

## 30) Social Sharing Engine

Gaia Eyes should enable users to generate shareable insights directly from real data.

Goals:
- turn users into distribution channels
- create visually compelling posts
- maintain scientific + accessible messaging

Every share should:
- reflect real data
- be visually clear
- include Gaia Eyes branding
- optionally include suggested caption text

This is a core growth system, not a secondary feature.

---
