# Flux.ai Handoff: Gaia Home Rev A

Date: 2026-07-30

Status: staged engineering brief

## Operating Rule

Flux is an engineering copilot, not the approving engineer. It may create or
modify the schematic only after requirements are attached and reviewed.
Manufacturer datasheets control when this document and a source disagree.

Attach:

- `REV_A_HARDWARE_SPEC.md`;
- current SEN6x datasheet;
- current SEN6x mechanical and handling guidance;
- current BMP390L datasheet and handling guidance;
- current OPT3001 datasheet;
- current ESP32-S3-WROOM-1 datasheet;
- proposed regulator datasheet;
- USB-C connector drawing;
- selected assembler capabilities and design rules.

## Gate 1: Requirements Matrix

Prompt:

```text
Read every attached requirement and datasheet. Do not edit the schematic.
Produce a requirements matrix covering each supply voltage, typical and peak
current, interface, bus address, required passive, connector pin, absolute
maximum, startup state, mechanical keep-out, thermal concern, airflow
constraint, test requirement, and unresolved decision. Cite document and page
for each electrical or mechanical requirement. Flag conflicts instead of
guessing.
```

Approval requires:

- complete source list with revision dates;
- no guessed pinout;
- no unresolved voltage-domain conflict;
- explicit current and thermal requirements;
- explicit mechanical keep-outs.

## Gate 2: Architecture and Power Budget

Prompt:

```text
Propose the block architecture and calculate typical and worst-case power for
Gaia Home Rev A. Include ESP32 Wi-Fi transients and SEN66 peak load. Recommend
three suitable 3.3 V regulators with exact manufacturer part numbers,
availability, transient response, dropout, thermal margin, package risk, and
required external components. Do not add components to the project yet.
```

Approval requires:

- reviewed regulator selection;
- thermal calculation;
- headroom at USB minimum input;
- protection strategy;
- component sourcing check.

## Gate 3: Schematic

Prompt:

```text
Create the schematic in named functional blocks:
1. USB-C input and protection
2. 3.3 V regulation
3. ESP32-S3-WROOM-1 and native USB
4. SEN66 connector
5. BMP390L
6. OPT3001
7. RGB LED and button
8. expansion connector
9. programming and test points

Use only datasheet-backed connections. After each block, list the source-backed
requirements satisfied and every unresolved issue. Do not silently select an
alternate footprint or part.
```

## Gate 4: Schematic Audit

Prompt:

```text
Audit the completed schematic as if five boards will be assembled without
manual electrical rework. Check power sequencing, rail capacity, decoupling,
USB-C configuration, USB and external-connector ESD protection, I2C addresses
and pull-ups, reset and boot behavior, connector orientation, unused pins,
test access, exact part-number-to-footprint matching, and recovery paths.
List findings by severity. Do not change the schematic until each finding is
reviewed.
```

Approval requires a human sign-off from the designated hardware reviewer.

## Gate 5: Placement Constraints

Prompt:

```text
Before placement, generate explicit layout constraints for:
- ESP32 antenna clearance
- SEN66 intake, exhaust, retainer, and no-recirculation zones
- thermal separation between sensors and heat sources
- BMP390L ambient venting
- OPT3001 optical window and LED isolation
- USB and regulator current paths
- ground-plane continuity
- mounting holes and enclosure interfaces
- factory-test access

Identify every constraint Flux cannot reliably verify.
```

## Gate 6: PCB Layout Review

The reviewer must check:

- mechanical fit using current 3D models;
- antenna keep-out;
- continuous ground return;
- power trace and via capacity;
- regulator thermal behavior;
- sensor heat separation;
- airflow path;
- pressure vent;
- light contamination;
- connector access;
- mounting and tolerances;
- test-pad accessibility.

## Gate 7: Manufacturing Audit

Prompt:

```text
Perform a final DFM audit against the selected assembler's current rules.
Verify every BOM manufacturer part number against its symbol, footprint,
orientation, lifecycle, and sourcing status. List all DRC exceptions,
unverified footprints, unavailable parts, manual operations, mechanical
uncertainties, and substitutions. Do not describe the design as ready until
the human reviewer resolves every high- or medium-severity item.
```

## Order Release Checklist

- [ ] Schematic approved.
- [ ] Typical and worst-case power budget approved.
- [ ] Every footprint checked against manufacturer drawings.
- [ ] Connector orientation checked physically and in 3D.
- [ ] PCB and enclosure reviewed together.
- [ ] SEN66 airflow guidance satisfied.
- [ ] ESP32 antenna keep-out satisfied.
- [ ] DRC clean or every exception documented.
- [ ] BOM contains exact orderable parts.
- [ ] Assembly capabilities confirmed.
- [ ] Factory test procedure ready.
- [ ] Firmware can flash and recover through accessible pads.
- [ ] Two complete units ordered; spare bare boards acceptable.

