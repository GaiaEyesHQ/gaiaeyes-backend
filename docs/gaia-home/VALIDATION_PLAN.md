# Gaia Home Rev A Validation Plan

Date: 2026-07-30

Status: pre-build test plan

## Purpose

Testing does not need to establish the broad premise that indoor environmental
conditions can matter. Rev A testing establishes that Gaia Home produces
reliable, usable, correctly attributed data and that the combined Gaia Eyes
experience adds value beyond existing outdoor context.

## Phase 1: Bench Bring-Up

For each unit:

- inspect assembly and connector orientation;
- verify shorts before installing expensive modules where practical;
- validate 5 V and 3.3 V rails;
- test regulator stability under Wi-Fi and sensor load;
- flash factory firmware;
- verify every sensor identity and output;
- test button, RGB LED, reset, and recovery;
- verify BLE provisioning and Wi-Fi reconnection;
- verify OTA and failed-update recovery;
- confirm no unexpected thermal hotspot.

## Phase 2: Side-by-Side Consistency

Operate the two Rev A units together for at least seven days.

Compare:

- CO2 baseline and response;
- PM channels;
- temperature;
- humidity;
- VOC Index;
- NOx Index;
- pressure;
- light;
- missing samples;
- clock and sequence continuity.

The test must distinguish expected sensor-to-sensor tolerance from:

- enclosure bias;
- component heating;
- airflow obstruction;
- firmware conversion error;
- wrong units;
- clock drift;
- network data loss.

## Phase 3: Controlled Events

Document start and end times for:

- occupancy in a closed room;
- opening a window or door;
- cooking;
- cleaning-product use;
- shower or humidity event;
- humidifier or dehumidifier operation if available;
- HVAC cycle;
- air purifier operation;
- transition from dark to daylight.

The test evaluates response shape and recovery, not medical effect.

## Phase 4: Room-Move Workflow

Suggested sequence:

1. Bedroom for seven nights.
2. Office for five working days.
3. Living room or kitchen for three to five days.
4. One intentional correction of an incorrectly entered move time.

Verify:

- assignment intervals never overlap;
- data before and after a move resolves to the correct room;
- corrections are audited;
- unknown gaps remain unknown;
- room renaming preserves identity;
- app summaries state actual monitored coverage.

## Phase 5: Gaia Eyes Integration

Verify:

- authenticated ingest;
- idempotent batch replay;
- offline buffering;
- server receipt timestamps;
- raw-versus-derived separation;
- indoor-versus-outdoor naming;
- timezone and local-day derivation;
- symptom and wearable timeline alignment;
- pattern calculations preserve lag and sample counts;
- user-facing copy remains observational.

Phone voice-assistant entry is validated separately from Gaia Home hardware:

- the authenticated phone selects the correct Gaia Eyes user;
- the command writes the same canonical event as manual app entry;
- the user receives an unambiguous confirmation;
- correction and undo are available;
- a failed or ambiguous command does not create a silent health event;
- environmental measurements are aligned by timestamp rather than duplicated
  into the event;
- no audio or voiceprint enters the Gaia Home data stream.

## Optional Display Validation

If Rev A includes a display, verify:

- it remains readable in expected bedroom and office lighting;
- it can be dimmed or turned off for sleep;
- it does not contaminate OPT3001 readings;
- its heat does not materially bias temperature or humidity;
- it does not obstruct SEN66 airflow or ESP32 antenna performance;
- it communicates room, freshness, and device status without becoming a
  duplicate app interface;
- Gaia Home continues collecting and synchronizing normally if the display
  fails.

## Acceptance Targets

Targets must be finalized with the hardware reviewer before testing. At minimum:

- 30 continuous days without unrecoverable lockup;
- recovery after power and Wi-Fi interruption;
- no silent duplicate or reordered records;
- explicit handling of unsynchronized time;
- complete provenance for every stored measurement;
- stable room attribution;
- bounded and documented temperature self-heating;
- pressure trends suitable for delta calculation;
- useful event response from CO2, PM, VOC Index, and NOx Index;
- no status-light contamination of light readings;
- no unacceptable fan noise for bedroom placement.

## Competitive Benchmark Policy

An external commercial monitor may be purchased after Gaia Home requirements
are frozen and used as a black-box benchmark.

Allowed observations:

- published specifications and documentation;
- overall dimensions and placement requirements;
- external intake and exhaust arrangement;
- display and interaction behavior;
- fan noise;
- response and recovery under shared room conditions;
- packaging, setup, and support experience.

Not permitted in this project without separate approval:

- copying proprietary enclosure geometry;
- reverse engineering firmware or undocumented protocols;
- copying PCB layout;
- presenting a competitor's telemetry as reference-grade;
- allowing competitor behavior to overwrite independently recorded Gaia Home
  requirements.

Benchmark observations must be recorded with date, model, firmware version,
placement, and test conditions.

## Rev B Decision

Proceed only when the validation report identifies:

- retained components;
- required electrical corrections;
- required mechanical or airflow corrections;
- firmware and data-contract changes;
- manufacturing lessons;
- realistic unit economics;
- remaining certification and privacy work;
- evidence that the single-device room-profile experience is understandable
  and useful.
