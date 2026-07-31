# Gaia Home Product Requirements

Date: 2026-07-30

Status: Rev A baseline

## Product Statement

Gaia Home measures the indoor environment a person actually occupies and adds
that context to Gaia Eyes' existing body, symptom, wearable, and environmental
history.

The central user question is:

> What was happening around me when my body changed?

Gaia Home does not need to prove that indoor conditions affect every person.
It must help each user determine which measured conditions repeatedly overlap
with changes in their own health and daily experience.

## Primary Users

Initial health contexts include:

- migraine and headache;
- POTS and dysautonomia;
- fibromyalgia and chronic pain;
- chronic fatigue and variable energy;
- arthritis and joint sensitivity;
- sleep disruption;
- asthma, allergy, and irritation context without diagnostic claims.

Gaia Home remains one shared product. Health-context profiles affect relevance,
copy, charts, and candidate patterns, not the underlying measurements.

## V1 User Experience

### Setup

1. User claims the device in Gaia Eyes.
2. User provisions Wi-Fi through Bluetooth.
3. Gaia Eyes assigns the device to a home.
4. User names the initial room.
5. Gaia Eyes creates the first room-assignment interval.

### Move Device

The app provides a `Move Device` action:

1. User chooses an existing room or creates a room.
2. User confirms when the device moved.
3. The current room interval closes at that timestamp.
4. A new room interval begins.
5. Historical measurements retain their original assignment.

The app must never imply that an unmonitored room was measured continuously.

### Home Profile

The app may summarize:

- monitored hours per room;
- date range and coverage per room;
- typical and extreme conditions;
- recurring ventilation or air-quality events;
- indoor-versus-outdoor differences;
- symptom, sleep, and wearable overlaps;
- missing or uncertain coverage.

## Required Measurements

- carbon dioxide in ppm;
- PM1.0, PM2.5, PM4.0, and PM10 mass concentration;
- ambient temperature;
- relative humidity;
- VOC Index;
- NOx Index;
- barometric pressure;
- visible-light illuminance.

## Required Derived Context

Derived fields are computed outside the immutable raw record and remain
versioned:

- pressure deltas and rate of change;
- temperature and humidity change;
- dew point;
- absolute humidity where useful;
- condensation-condition risk;
- dampness and mold-growth-condition risk;
- CO2 exposure duration bands;
- PM event duration and recovery;
- VOC and NOx anomaly events;
- indoor-versus-outdoor differences;
- room coverage;
- personal lagged associations.

V1 must not claim mold presence, identify chemical compounds, or convert an
association into a causal conclusion.

## Claims Boundary

Allowed:

- "Bedroom CO2 remained elevated for 3.2 hours."
- "This VOC Index increase overlapped with 6 of 9 headache logs."
- "Your room was drier than nearby outdoor conditions overnight."
- "Conditions associated with mold growth persisted for 18 hours."
- "This is an association in your history, not proof of cause."

Not allowed:

- "Mold detected."
- "VOC caused your migraine."
- "A migraine is coming."
- "This room is medically unsafe."
- "NO2 concentration" when the source is only NOx Index.
- "TVOC concentration" without a validated and explicitly labeled conversion.
- "EPA indoor AQI."

## Privacy Requirements

- No microphone or camera in Rev A.
- No audio recording or inference.
- Device credentials are unique and revocable.
- Wi-Fi credentials never leave the device except as required by the
  provisioning process.
- Sensitive health interpretation occurs in Gaia Eyes, not in the room device.
- Household members receive reasonable notice that environmental monitoring is
  active.
- Room labels and device identity are user-controlled.

## Commercial Requirements

The target retail product should:

- provide meaningful value with one full device;
- avoid requiring a screen;
- use the existing Gaia Eyes app as its primary interface;
- avoid a battery in the first stationary product;
- support over-the-air firmware updates;
- allow a future lower-cost Mini without changing the core data model;
- remain useful when temporarily offline;
- avoid proprietary dependence on a competing monitor or cloud service.

The Rev A target is two complete units. Fabricating additional unpopulated
carrier boards is acceptable when required by the board house.

## Product Success Criteria

Rev A supports moving toward Rev B when:

- measurements are complete, timestamped, ordered, and recoverable;
- room moves preserve accurate history;
- indoor conditions show material differences from existing outdoor context;
- enclosure and electronics do not create unacceptable measurement distortion;
- users can understand the readings without a device screen;
- Gaia Eyes can generate useful retrospective context without overstating
  evidence;
- the likely retail cost supports a viable margin and support reserve.

