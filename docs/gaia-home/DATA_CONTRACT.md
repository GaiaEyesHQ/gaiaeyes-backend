# Gaia Home Data Contract

Date: 2026-07-30

Status: design contract; no schema or endpoint has been implemented

## Architecture Boundary

Gaia Home uploads to an authenticated FastAPI endpoint. The backend validates
the device and owns writes to Supabase. The device must never hold direct
production database credentials.

```text
Gaia Home -> authenticated FastAPI ingest -> immutable raw measurements
                                             |
                                             +-> versioned hourly/daily features
                                             +-> user pattern analysis
                                             +-> app read surfaces
```

## Device Identity

Each physical unit requires:

- immutable internal device identifier;
- user-visible serial number;
- hardware revision;
- firmware version;
- sensor module identities where available;
- unique revocable device credential;
- claim state and owning Gaia Eyes account;
- last-seen and device-health state.

One shared fleet API key is prohibited.

## Measurement Envelope

```json
{
  "schema_version": "gaia_home_reading_v1",
  "device_id": "GS-HOME-0001",
  "hardware_revision": "A",
  "firmware_version": "0.1.0",
  "sequence": 18422,
  "measured_at_utc": "2026-08-15T03:42:00Z",
  "clock_source": "ntp",
  "clock_quality": "synchronized",
  "metrics": {
    "pm1_ug_m3": 3.2,
    "pm25_ug_m3": 5.8,
    "pm4_ug_m3": 6.4,
    "pm10_ug_m3": 8.1,
    "temperature_c": 23.44,
    "relative_humidity_pct": 46.8,
    "co2_ppm": 1124,
    "voc_index": 134.0,
    "nox_index": 18.0,
    "pressure_hpa": 1007.42,
    "light_lux": 42.0
  },
  "quality": {
    "sensor_warmup": false,
    "sen66_status": "ok",
    "pressure_status": "ok",
    "light_status": "ok",
    "wifi_rssi_dbm": -61,
    "uptime_s": 86420
  }
}
```

The backend adds `received_at_utc`, authenticated owner, request identity, and
ingest-version metadata. Device-provided ownership or room fields are never
trusted as authorization.

## Sampling and Upload

- Hardware should sample at the native useful cadence of each sensor.
- Rev A stores an analysis record at a configurable cadence, initially one
  minute.
- Upload may batch records.
- Device ID plus sequence number forms the idempotency key.
- Network loss must not change measurement timestamps.
- Replayed records retain their original measurement time.
- Unsynchronized measurements are retained with explicit clock-quality flags.
- Missing metrics are null or absent with quality context; never zero-filled.

## Room Assignment

Room assignment is a server-owned effective-dated relation:

```text
assignment_id
home_id
device_id
room_id
effective_from_utc
effective_to_utc nullable
source
created_at
created_by
```

The backend resolves the applicable room interval for a measurement timestamp.
Closing or opening an assignment does not mutate the raw measurement.

Rules:

- intervals for one device may not overlap;
- historical corrections are audited;
- a gap means the room is unknown;
- a room name change does not change the stable room identifier;
- deleted rooms are archived rather than erasing measurement provenance;
- device moves require explicit user confirmation;
- timezone and local-day bucketing remain derived fields.

## Raw Measurement Requirements

The raw layer preserves:

- original device timestamp;
- server receive timestamp;
- sequence number;
- exact reported units;
- raw sensor outputs where available;
- hardware and firmware versions;
- sensor status and warm-up state;
- clock quality;
- source device;
- room assignment resolved separately;
- ingest schema version;
- raw payload or stable payload hash;
- deletion and retention state.

Raw records are append-only except for narrowly controlled privacy deletion or
legal remediation. Corrections create new metadata or corrected derived output;
they do not silently rewrite the original observation.

## Derived Data Requirements

Every derived feature records:

- algorithm name and version;
- calculation timestamp;
- input window;
- source measurement identifiers or reproducible query boundary;
- units;
- parameters and thresholds;
- missing-data rule;
- quality state;
- code commit or release identifier where feasible.

Indoor and outdoor variables retain distinct names. For example:

- `indoor_pressure_hpa`;
- `outdoor_pressure_hpa`;
- `indoor_pm25_ug_m3`;
- `outdoor_aqi`;
- `indoor_relative_humidity_pct`;
- `outdoor_relative_humidity_pct`.

An indoor composite score must never replace its component measurements.

## Personal Pattern Boundary

Gaia Eyes may compare indoor observations with:

- symptoms;
- exposure logs;
- medications;
- sleep;
- HRV;
- resting heart rate;
- respiratory rate;
- other authorized health samples;
- outdoor environmental conditions.

Pattern output must preserve sample counts, lag windows, exposed and unexposed
rates, confidence tier, missing coverage, and source provenance. V1 findings
remain retrospective and observational.

## Retention and Deletion

- Retain raw data while the user account and consent permit it.
- Support account deletion and device-data deletion.
- Removing a device from the account does not silently delete history.
- Factory reset clears device credentials and local buffered records according
  to the documented reset contract.
- Research or aggregate use requires a separate consent and withdrawal model.

