# Gaia Home Rev A Hardware Specification

Date: 2026-07-30

Status: engineering input; requires schematic and layout approval before order

## Objective

Rev A is a USB-C-powered indoor environmental data-validation node. It is not
a battery product, portable product, regulatory monitor, medical device, or
finished retail design.

## Reference Architecture

```text
USB-C 5 V input
      |
Protection and 3.3 V regulation
      |
ESP32-S3-WROOM-1
      |
      +-- Sensirion SEN66
      +-- Bosch BMP390L
      +-- Texas Instruments OPT3001
      +-- RGB status LED
      +-- multifunction button
      +-- protected expansion/test interface
```

## Selected Components

| Function | Baseline component | Notes |
|---|---|---|
| PM, CO2, temperature, RH, VOC Index, NOx Index | Sensirion SEN66 | Removable complete module |
| Pressure | Bosch BMP390L | Ambient vent path required |
| Visible light | Texas Instruments OPT3001 | Optically isolated from status LED |
| Controller | ESP32-S3-WROOM-1 | Integrated antenna module |
| Input | USB-C 5 V | No USB Power Delivery required |
| Status | One RGB LED | No large light ring |
| Control | One pushbutton | Provisioning/reset behavior |

Component substitutions require an explicit change record covering electrical,
mechanical, firmware, accuracy, sourcing, and data-contract effects.

## Excluded from Rev A

- display;
- battery and charge controller;
- microphone;
- GPS;
- magnetometer or EMF sensing;
- radon;
- carbon-monoxide life-safety sensing;
- formaldehyde-specific claims;
- leak probe;
- touch controls;
- custom RF design;
- bare ESP32-S3 implementation.

## Power Requirements

- USB-C sink at 5 V.
- Correct Type-C configuration-channel resistors.
- USB ESD protection.
- Input overcurrent protection.
- Reverse-current protection where applicable.
- Regulated 3.3 V rail.
- Regulator rated for at least 1 A continuous output with verified transient and
  thermal margin.
- Power budget must include ESP32 Wi-Fi peaks and the SEN66 peak load.
- Bulk capacitance near the SEN66 connector and ESP32 module.
- Datasheet-required local decoupling at each IC.
- Test points for 5 V, 3.3 V, ground, SDA, SCL, reset, and boot.

The engineer must produce a typical and worst-case power budget before
schematic approval.

## Interfaces

- SEN66 over its documented I2C interface and manufacturer-specified connector.
- BMP390L over I2C.
- OPT3001 over I2C.
- Native ESP32-S3 USB for firmware flashing and diagnostic serial operation.
- Bluetooth Low Energy for provisioning.
- 2.4 GHz Wi-Fi for synchronization.
- Protected expansion connector with 3.3 V, ground, SDA, SCL, and two GPIOs.

The design must verify bus addresses, voltage compatibility, required pull-ups,
connector orientation, cable availability, and any bus-capacitance constraint
from current manufacturer documentation.

## PCB Requirements

- Four-layer FR-4 preferred.
- 1.6 mm nominal thickness unless mechanical work requires another value.
- 1 oz copper.
- Solid ground plane.
- No blind or buried vias.
- Components on one side where practical.
- Conservative fabrication rules compatible with the selected assembler.
- PCB antenna at a board edge with Espressif keep-out rules enforced.
- No copper, component, fastener, or enclosure metal inside the antenna
  keep-out.
- Clear polarity, pin-1, connector, revision, and test markings.
- Factory-programming and pogo-test access.
- Mounting holes coordinated with the enclosure.
- Unique hardware-revision marking and serial-label area.

## Mechanical and Environmental Requirements

- Follow the current SEN6x mechanical design, handling, airflow, retainer, and
  temperature-compensation guidance.
- Treat SEN66 intake and exhaust as separate controlled paths.
- Prevent recirculation of warm internal exhaust into the intake.
- Keep regulator, ESP32, USB connector, and other heat sources away from the
  environmental sensing zone.
- Mount the BMP390L away from heat and provide a protected ambient-pressure
  vent.
- Protect the pressure port from adhesive, coating, direct drafts, and
  enclosure pressure pulses.
- Place OPT3001 behind a suitable light opening.
- Prevent RGB LED and internal reflections from contaminating light readings.
- Enclosure openings must resist ordinary accidental blockage while allowing
  required airflow.
- The finished unit must stand securely in the intended orientation.

The enclosure and PCB are one measurement system and must be reviewed together.

## Firmware Requirements Affecting Hardware

- Unique device identity.
- Secure boot and signed firmware considered before pilot.
- BLE onboarding and Wi-Fi provisioning.
- NTP time synchronization with explicit unsynchronized state.
- Monotonic sequence number per device.
- Flash-backed offline queue.
- Idempotent replay.
- Watchdog recovery.
- Sensor initialization, warm-up, and health reporting.
- OTA update and recovery path.
- Factory-test firmware.
- Long-press provisioning reset.

## Factory Test

Each assembled board must support verification of:

- 5 V input;
- 3.3 V rail and load stability;
- ESP32 USB programming;
- BLE and Wi-Fi operation;
- SEN66 communication and serial identity;
- BMP390L communication;
- OPT3001 communication;
- RGB channels;
- pushbutton;
- offline buffering;
- reset and recovery behavior.

## Required Manufacturing Package

- native Flux project export;
- schematic review artifact;
- Gerber files;
- NC drill files;
- BOM with exact manufacturer part numbers;
- pick-and-place file;
- assembly drawing;
- fabrication notes;
- assembly notes;
- PCB STEP model;
- SEN66 mounting and airflow drawing;
- test-point map;
- DRC report;
- footprint and orientation verification record;
- unresolved-issue list.

No order is placed with unexplained DRC violations, unverified footprints, or
unresolved connector orientation.

## Authoritative Sources

Current manufacturer documentation is authoritative over this summary:

- Sensirion SEN66 product page and SEN6x datasheet:
  https://sensirion.com/products/catalog/SEN66
- Sensirion SEN6x mechanical, handling, testing, and temperature-compensation
  documents linked from the product page.
- Bosch BMP390/BMP390L documentation:
  https://www.bosch-sensortec.com/products/environmental-sensors/pressure-sensors/bmp390/
- Texas Instruments OPT3001 documentation:
  https://www.ti.com/product/OPT3001
- Espressif ESP32-S3-WROOM-1 documentation:
  https://www.espressif.com/en/module/esp32-s3-wroom-1-en

The exact revisions used for design review must be recorded in the project.

