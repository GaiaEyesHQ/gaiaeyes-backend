# Future Exposure System Backlog

This is a reminder/backlog doc so the broader exposure work does not fall off after the first implementation pass.

## Implemented In V1

- event-based exposure storage
- gauge integration for:
  - `overexertion`
  - `allergen_exposure`
- sensitivity extension:
  - `exertion_recovery_sensitive`

## Still Planned

Future exposure keys to evaluate after V1 is stable:

- `poor_sleep`
- `stress`
- `alcohol`
- `travel`
- `illness`

These were intentionally deferred because they overlap more strongly with:

- wearables
- symptom logging
- existing health context
- current recovery logic

## Guide / Check-In Follow-Ups

Potential capture surfaces after the backend model is stable:

- Guide Hub daily poll slot
- Guide Hub open card slot
- Daily check-in follow-up section
- symptom follow-up flow when a likely confounder is obvious

Guide should stay a capture surface, not the source of truth.

## UX Reminder

Before making Daily Check-In a primary exposure capture surface, verify and fix the stale check-in bug noted during review:

- check-in prompt says it is time to check in
- opening the screen can still show an older completed day instead of the current target day

That bug should be resolved before exposure capture is routed primarily through Daily Check-In.

## Implementation Reminder

Do not add the deferred exposure keys by copying the same weights blindly.

For each new exposure key, define:

- which gauges it can influence
- how long it should decay
- where it overlaps with symptoms or wearables
- what personalization tags should scale it
- whether it belongs in Guide explanations, gauge explanations, or both
