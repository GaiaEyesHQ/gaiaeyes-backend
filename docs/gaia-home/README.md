# Gaia Home Documentation

Date: 2026-07-30

Status: product definition and Rev A engineering handoff

Gaia Home is a stationary indoor environmental context sensor for Gaia Eyes.
It measures the conditions around a person so Gaia Eyes can compare actual
indoor exposure with symptoms, wearable physiology, sleep, logged exposures,
medications, and outdoor environmental conditions.

The product is not positioned as a generic air-quality display or a medical
device. Its value comes from the synchronized history Gaia Eyes builds across:

- body and wearable observations;
- user-reported symptoms and exposures;
- indoor environmental measurements;
- outdoor environmental context;
- room assignment and time;
- cautious, explainable personal pattern analysis.

## Current Product Decision

Proceed toward an independently owned Gaia Home hardware and data system.

The first hardware revision is a USB-C-powered, stationary validation unit.
It uses one full environmental sensor node and can be moved between rooms.
The Gaia Eyes app records each move as a new effective-dated room assignment,
allowing one device to build a room-by-room home profile.

Future products remain optional:

- **Gaia Mini**: lower-cost stationary room extension;
- **Gaia Go**: portable personal environmental context sensor.

Neither product is part of Rev A.

## Documentation Map

- [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md)
  defines the user problem, product boundaries, room model, claims, and success
  criteria.
- [REV_A_HARDWARE_SPEC.md](REV_A_HARDWARE_SPEC.md)
  defines the Rev A sensor stack, electrical requirements, mechanical
  constraints, testability, and manufacturing outputs.
- [DATA_CONTRACT.md](DATA_CONTRACT.md)
  defines device identity, upload behavior, raw measurement storage, room
  assignment, provenance, and derived-data boundaries.
- [FLUX_HANDOFF.md](FLUX_HANDOFF.md)
  provides the staged Flux.ai brief and review gates for schematic, layout,
  and manufacturing preparation.
- [VALIDATION_PLAN.md](VALIDATION_PLAN.md)
  defines the engineering and product validation required before Rev B or a
  pilot build.

## Non-Negotiable Principles

1. Gaia Eyes remains the product intelligence layer.
2. The backend owns production writes to Supabase.
3. Raw measurements are preserved and never replaced by derived scores.
4. Indoor and outdoor measurements remain distinct sources.
5. Missing data is unknown, not zero and not a negative finding.
6. Room moves never rewrite earlier room history.
7. Personal associations are not presented as causation.
8. Rev A is a validation instrument, not a retail-ready medical device.
9. Product requirements are independently developed from Gaia Eyes needs.
10. External devices may be used only as black-box benchmarks, not copied as
    design templates.

## Immediate Milestone

Build two functioning Rev A units that:

- collect the complete V1 signal set;
- maintain reliable UTC timestamps and sequence ordering;
- buffer through network interruptions;
- upload authenticated measurements to Gaia Eyes;
- support effective-dated room moves;
- run continuously for at least 30 days;
- produce analysis-grade data for indoor-versus-outdoor and
  environment-versus-health comparisons.

