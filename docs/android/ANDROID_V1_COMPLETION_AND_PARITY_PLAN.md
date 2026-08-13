# Android V1 Completion and iOS Parity Plan

Last reviewed: 2026-08-12

This is the canonical implementation plan for finishing the first Gaia Eyes
Android release and then bringing its user-facing surfaces up to the current
iOS experience. It complements [ANDROID_PARITY_MATRIX.md](ANDROID_PARITY_MATRIX.md)
and does not expand V1 into the next-phase personalization roadmap.

## Executive assessment

Android is a functional beta with the planned Explore, Guide, and notification
code now implemented locally, but it is not yet ready for public submission.

The core account and five-tab experience is working: authentication, resumable
onboarding, location setup, all eight gauges and gauge explanations, Home,
Body, Patterns, Outlook, journal writes, active-symptom editing, Health Connect
import, settings/diagnostics, and hands-free migraine quick logging all have
real implementations. Cache-first reads and persistent write queues also give
the app a solid reliability foundation.

The largest remaining release gaps are:

1. Settings does not yet expose all editable onboarding choices or membership
   management.
2. RevenueCat Subscribe/Restore is configured only at the build-placeholder
   level; the purchase experience and entitlement restoration are not built.
3. Android notifications need production Firebase credentials, the push-token
   migration, and physical-device delivery/permission/deep-link validation.
4. Full Google Play release validation remains unfinished.

## What is already ready

- Supabase magic-link and anonymous-account entry, resumable onboarding, and
  existing-account onboarding bypass.
- Profile location through device location or ZIP code, with later editing.
- Home with all eight shared gauges, expandable layout, gauge explanations,
  possible/current symptoms, Signals to Watch, and journal-entry actions.
- Body with shared account history plus optional Health Connect import for
  sleep, steps, heart rate, resting heart rate, respiratory rate, and SpO2.
- Cache-first Patterns and Outlook using shared backend evidence language.
- Complete Explore hub with All Drivers, Space Weather, Local Conditions,
  Magnetosphere, Schumann Resonance, Earthquakes, and Hazards detail surfaces.
- Guide with Support Right Now, daily check-in and poll, follow-ups, and help.
- Symptom, exposure, and daily-check-in writes with account-scoped persistence,
  foreground delivery, and WorkManager retry.
- Active-symptom status, edit, and delete controls.
- Assistant/deep-link migraine quick logging through the shared symptom queue.
- Initial Settings and redacted diagnostics sharing.
- Android notification preference controls, Android 13+ permission handling,
  FCM token registration/disablement, platform-aware backend delivery, quiet
  hours/sensitivity controls, and notification tap routing.

## V1 completion scope

### P0: required before the public Android release

#### 1. Complete Explore

**Implemented locally.** The remaining requirement is release/device validation
of freshness, partial-data, and responsive-layout states.

Match the current non-personal iOS Explore hub:

1. All Drivers
2. Space Weather
3. Local Conditions
4. Magnetosphere
5. Schumann Resonance
6. More to Explore
   - Earthquakes
   - Hazards

Every card must use shared backend data rather than an Android-only source.
Every live value must show freshness or a clear unavailable/stale state.

#### 2. Add Guide

**Implemented locally.** The current Android sequence follows the post-Home
Guide order and deduplicates support suggestions.

Match the current Guide content order rather than restoring the older Symptoms
and Influences cards that were moved to Home:

1. Support Right Now
2. Optional app notice
3. Daily Check-In
4. Daily Poll
5. Follow-Ups, when present
6. Help and Understanding

Support suggestions must be deduplicated so multiple cards do not repeat the
same grounding, breathing, pacing, or recovery advice.

#### 3. Close Settings and account-management gaps

Users must be able to revisit the setup choices that affect their experience:

- Account and sign out
- Display units, experience mode, and language tone
- Health-context/condition tags already collected during onboarding
- Device location versus ZIP and current local context
- Health Connect permissions, last import, manual refresh, and limited-data
  explanation
- Notifications, alert families, reminders, quiet hours, and permission status
- Membership, Subscribe, and Restore Purchases
- Privacy, terms, support, diagnostics, and account/data deletion routes

Notification controls must remain hidden or clearly unavailable until their
corresponding delivery path is functional. Do not ship switches that imply an
alert can be delivered when only a local placeholder exists.

#### 4. Implement Plus purchase and restore

- Add the approved RevenueCat Android SDK only after explicit dependency
  approval and Google Play products are available.
- Use the same Plus entitlement identity as iOS.
- Support monthly/yearly purchase, restore, pending purchase, cancellation,
  offline entitlement cache, and signed-in account changes.
- Verify the backend entitlement surface after purchase/restore.

#### 5. Implement Android notifications

**Implemented locally; production activation and device QA remain.** The app,
API contract, platform-aware sender, migration, workflow wiring, and focused
tests are present. Before release, apply the migration, configure Firebase
credentials, and exercise the delivery matrix on a physical Android device.

Notifications are part of Android V1, not merely a Settings placeholder.

- Add Firebase Cloud Messaging (FCM) delivery and Android 13+ notification
  permission handling. Request permission only after the user opts in during
  onboarding or Settings, not on first launch.
- Reuse the existing shared preference routes:
  `GET/PUT /v1/profile/notifications`,
  `POST /v1/profile/push-tokens`, and
  `POST /v1/profile/push-tokens/disable`.
- Extend the current iOS-only token contract and APNs sender with an explicit
  Android/FCM provider path. This requires a migration to allow Android tokens,
  API validation for `platform=android`, and sender routing by platform; do not
  overload an APNs token as an FCM token.
- Preserve the existing shared evaluation rules for user preferences,
  sensitivity, quiet hours, cooldowns, stale-source suppression, and bundling.
- Include these V1 families:
  - meaningful Earth and space condition changes
  - meaningful local-condition changes
  - personalized gauge changes
  - symptom follow-up reminders
  - daily check-in reminders
- Register and refresh the FCM token, disable it on sign-out/account change,
  and safely handle invalid or rotated tokens.
- Route taps to the relevant Gaia Eyes surface. Lock-screen copy must be useful
  but avoid exposing symptom or health details by default.
- Keep copy observational and supportive. Notifications may describe a current
  change or suggest checking context, but must not diagnose or claim that a
  symptom is predicted.

#### 6. Finish release hardening

- Production signing and Play release configuration
- Data Safety, Health Connect, privacy, and account-deletion declarations
- User-safe configuration/error screens with no Supabase or internal-service
  wording
- Startup/auth restoration, queue drain, day rollover, stale-cache, and Health
  Connect regression checks
- Physical Samsung validation plus Play-enabled Pixel emulator validation

### P1: V1.1 follow-up

- Social share cards matching the current iOS direction. They are explicitly
  deferred to V1.1 and must be omitted from Android V1 screenshots and launch
  copy. Diagnostics sharing is not a substitute for share cards.
- Deeper pattern drilldowns and polished Plus gating.
- Additional tablet-specific layout polish beyond functional responsive support.

### Explicitly deferred from V1

- True background Health Connect reading; V1 may drain already queued uploads
  in WorkManager, while fresh Health Connect reads remain foreground/resume
  initiated.
- HRV until the RMSSD-versus-SDNN data contract is resolved.
- Wrist/skin temperature and cycle tracking until Android provider quality and
  Play declarations are validated.
- BLE/Polar and camera features.
- Home customization.
- Condition-specific dashboard modes, predictive notices, community features,
  and next-phase migraine/POTS/chronic-illness personalization.

## Screen layout plan

### Explore root

Phone layout is one scrollable column. Larger screens may use a two-column card
grid without creating a separate tablet information architecture.

1. **Header** — Explore title, Settings, shared gauges, refresh/freshness state.
2. **Introduction** — “Explore the signals around you.” with plain-language
   context about local, Earth, and space conditions.
3. **All Drivers** — Visible, Leading, and Supporting counts; opens ranked driver
   detail.
4. **Space Weather** — Kp, geomagnetic state, and solar wind.
5. **Local Conditions** — temperature, AQI, and pressure, with location source.
6. **Magnetosphere** — standoff distance/R0, Bz, and Kp.
7. **Schumann Resonance** — F1, A1, Q1, and station/source freshness.
8. **More to Explore** — Earthquakes and Hazards summary cards.
9. **Evidence boundary** — sources, last updated time, and unavailable/stale
   state. The medical-purpose disclosure remains in onboarding and policy
   surfaces instead of being repeated throughout the app.

Each detail page should contain:

- A short current-state summary
- Key metrics with units
- Recent trend or context where the shared API supports it
- Source and observation time
- A clear stale/unavailable state that preserves the last good cache
- Plain-language help without implying medical causation

Use the existing shared routes, including the current dashboard/space payloads,
`/v1/local/check`, `/v1/space/magnetosphere`,
`/v1/earth/schumann/latest`, `/v1/quakes/latest`, and
`/v1/hazards/gdacs/full`. Add no parallel Android ingestion source.

### Guide

1. **Header** — Guide title and close/back action.
2. **Support Right Now** — no more than three distinct, actionable suggestions
   derived from current body context and shared driver state.
3. **App notice** — optional, only when a current notice exists.
4. **Daily Check-In** — current readiness and CTA into the existing Android
   check-in flow.
5. **Daily Poll** — one quick prompt and simple response choices.
6. **Follow-Ups** — symptom follow-up CTA when active items require an update.
7. **Help and Understanding** — basics, help center, and deeper explanation.

Possible Symptoms and Current Influences remain on Home and are not duplicated
inside Guide. Before implementing Daily Poll, confirm whether its response must
remain device-local like the current iOS behavior or use an existing shared
backend contract.

### Settings

Group settings into predictable sections:

1. Account
2. Your setup
3. Local context
4. Health Connect
5. Notifications
6. Membership
7. Privacy and support
8. Diagnostics

Settings must explain missing permissions or limited device data without
blocking the rest of the app.

## Delivery sequence

### Slice A — Explore data foundation

**Status: implemented locally.**

- Add typed models, repository methods, scoped caches, and contract fixtures for
  the missing Explore sources.
- Reuse the existing authenticated API client and cache envelope.
- Add parser/repository tests for success, partial data, stale data, and errors.

**Acceptance:** every Explore source can load independently, preserve its last
good result, and report observation freshness.

### Slice B — Explore UI and detail navigation

**Status: implemented locally.**

- Build the complete root card sequence.
- Add detail routes for Space Weather, Local Conditions, Magnetosphere,
  Schumann, Earthquakes, and Hazards.
- Add responsive phone/tablet layout checks.

**Acceptance:** the root matches the current iOS information architecture and
no card requires a manual refresh to reveal already cached data.

### Slice C — Guide

**Status: implemented locally.**

- Reuse current symptom, check-in, driver, and profile state.
- Port current iOS content selection and suggestion deduplication behavior.
- Add Daily Poll persistence after its shared/local storage decision is recorded.

**Acceptance:** Guide opens from Home and Settings, shows no duplicate legacy
Home content, and remains useful when one upstream data source is unavailable.

### Slice D — Settings and membership

- Add editable setup/location/Health Connect sections.
- Implement Subscribe and Restore after Play products and RevenueCat are ready.
- Confirm entitlement changes update gated surfaces without reinstalling.

**Acceptance:** a user can correct setup choices, reconnect health/location,
purchase or restore Plus, and find privacy/deletion/support paths.

### Slice E — notifications

**Status: implemented locally; production activation and physical-device
acceptance remain.**

- Add the Android/FCM token lifecycle and platform-aware backend token contract.
- Route the existing shared notification evaluator to APNs or FCM without
  duplicating alert logic.
- Build Settings controls for the supported alert families, reminders, quiet
  hours, sensitivity, and current permission status.
- Add deep links and privacy-safe foreground/background presentation.

**Acceptance:** an opted-in physical Android device receives each supported
notification family once, at the correct time, with quiet hours and cooldowns
honored; an opted-out or signed-out device receives none.

### Slice F — release hardening

- Keep social share cards in the V1.1 backlog and out of V1 store copy.
- Complete production build configuration and Play declarations.
- Run the release matrix below and fix only release-blocking regressions.

## Release verification matrix

Test all of the following before production submission:

- New magic-link account, existing account, and anonymous-account upgrade path
- Fresh onboarding, interrupted onboarding, and completed-account bypass
- Permission allowed, denied, revoked, and no-data Health Connect states
- Device location, ZIP fallback, travel/location change, and location denial
- Online, offline, slow network, expired session, and backend-recovery startup
- Symptom, exposure, and daily check-in queued offline and drained once online
- Day rollover with previous cache retained until the new snapshot arrives
- Hands-free migraine logging on a physical Assistant-enabled device
- Notification permission allowed, denied, revoked, and re-enabled from Settings
- FCM token registration, rotation, invalid-token disablement, sign-out, and
  account-switch isolation
- Each supported alert family, daily reminder, and symptom follow-up deep link
- Quiet hours, cooldown, bundled events, disabled families, stale-source
  suppression, and duplicate-delivery prevention
- Lock-screen copy with sensitive previews disabled
- Purchase, restore, account switch, cancellation, and offline entitlement cache
- Samsung physical phone, Pixel Play-enabled emulator, small phone, and a large
  screen/tablet configuration
- Dark theme, large font, TalkBack focus order, and no white-background/readability
  regressions
- Redacted diagnostics with no PII, tokens, raw health samples, or internal
  configuration values

## Effort and dependency estimate

These are focused engineering estimates, not calendar promises:

- Complete Explore: 5–8 engineering days
- Guide: 4–6 engineering days
- Settings and membership: 4–7 engineering days after Play/RevenueCat products
- Notifications: 5–8 engineering days after Firebase/FCM credentials are ready
- Release hardening and QA: 4–7 engineering days plus external review time

The largest engineering dependency is now RevenueCat purchase/restore plus
release hardening. Google Play account approval, product approval, Health
Connect review, Firebase configuration, migration deployment, and tester
availability can extend calendar time independently.

## V1 exit criteria

Android V1 is ready to submit when:

- Every P0 surface above is implemented or explicitly removed from store copy.
- Explore and Guide match the current iOS information architecture.
- New users can complete onboarding without assistance.
- Core reads remain usable through transient failures and writes retry safely.
- Health Connect remains optional and never blocks Home or journaling.
- Opted-in Android notifications deliver through FCM with preferences, quiet
  hours, cooldowns, deep links, and account isolation working end to end.
- Purchase/restore and account deletion/privacy paths pass release testing.
- No known P0/P1 crash, data-isolation, secret-exposure, or unreadable-UI issue
  remains.

## Website parity note

This plan changes no public surface. When the Google Play listing is live, add a
Google Play badge and Android language to the website/member hub. If any P0
feature is intentionally omitted from Android V1, ensure shared website copy
does not imply that feature is already available on both platforms.
