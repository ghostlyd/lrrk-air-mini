# LiteWing port and dependency inventory

Status: discovery baseline. This document records what is evidenced in this
repository and on the connected development host. It does not claim that an
OpenDrone flight stack has been ported or that a flight has been performed.

## Scope and target boundary

The checked-in baseline is the [upstream LiteWing](https://github.com/jobitjoseph/LiteWing) ESP-Drone/Crazyflie-compatible
ESP-IDF firmware and its host-side Python examples. The requested OpenDrone
port is still target-selectable:

| Candidate | Fit with the existing LiteWing board | Current decision |
| --- | --- | --- |
| [NinjaPilot/OpenPilot LiteWing target](https://github.com/MAVProxyUser/OpenPilotESP32-WROOM-32E) | ESP32-S3 and the existing MPU6050/brushed-MOSFET architecture are plausible, but it is a different flight-tree/build boundary. | Recommended candidate; not yet pinned or ported. |
| [OpenDrone-hw/OpenFC-Lite](https://github.com/OpenDrone-hw/OpenFC-Lite) | Targets a different RP2354B flight controller, external ESC architecture, and higher-voltage battery system. | Not a firmware-only LiteWing port. |
| OpenDroneID/Remote ID | A telemetry/broadcast feature rather than a replacement flight stack. | Optional later feature. |

Until the target is selected, changes must remain flight-stack-neutral and the
existing ESP-Drone image remains the recovery baseline.

## LiteWing hardware baseline

The primary hardware evidence is the KiCad design and production BOM in
`hardware/LieWingV2.6.C/` (the directory name preserves the upstream `LieWing`
spelling). V2.6 is the revision to use for port planning unless the physical
board is identified otherwise.

### Board-level components evidenced by the V2.6 BOM

| Function | Part or assembly evidence | Designator / source |
| --- | --- | --- |
| MCU and Wi-Fi | ESP32-S3-WROOM-1 | U8 in `production/bom.csv` |
| IMU | MPU-6050 | U7 in `production/bom.csv` |
| USB serial | CH340K | U5 in `production/bom.csv` |
| Battery charger | TP4056 | IC1 in `production/bom.csv` |
| 3.3 V regulator | SPX3819M5-L-3-3/TR | U2 in `production/bom.csv` |
| Power switching | AO3401A, SS34, 1N4148W | U1, D1, D2-D5 |
| Brushed-motor switching | Four IRLML6344TRPBF MOSFETs and 2N27002DW gate/driver part | T1-T4, U6 |
| Physical connections | USB-C receptacle and JST XH 2-pin battery connector | J1, J2 |
| Indicators and controls | Red/blue/green LEDs, power switch, two tactile switches, buzzer | LED1-LED6, SW1-SW3 |

The production BOM does not establish the exact motor, propeller, guard, or
battery SKU. Those airframe items must be inspected and recorded separately
before a powered test. The firmware selects a brushed 720 motor profile for
the ESP32-S3/S2 target; that is not proof of the fitted motor's exact model.

### Optional expansion hardware

The V2.6 schematic/PCB contains footprints and repository support for a VL53L1X
time-of-flight sensor and a PMW3901 optical-flow sensor. These are add-ons, not
assumed to be populated on the base board. Position-hold behavior must remain
disabled or fail closed when the relevant sensors are absent or unverified.

## Existing firmware and host dependencies

### Firmware baseline

- Root project: ESP-IDF (`CMakeLists.txt`, `main/`, `components/`).
- Target default for ESP32-S3: `TARGET_ESP32_S2_DRONE_V1_2`, the upstream
  compatibility label used for the ESP32-S2/S3 board family.
- `sdkconfig.defaults.esp32s3` selects dual-core operation and 240 MHz CPU.
- Default V2.x pin evidence is in `main/Kconfig.projbuild`: MPU interrupt GPIO12;
  I2C0 GPIO11/10; SPI GPIO37/35/36 with CS GPIO42; and motors GPIO5/6/3/4.
- The firmware uses Wi-Fi and the CRTP/Crazyflie-compatible host protocol.
  Existing examples use `cflib` and UDP URIs; the checked-in packet log records
  the drone-side destination port as 2390. Port and address assumptions must be
  discovered from the live connection before any control automation.
- Component manifests require ESP-IDF `>=4.1.0` and declare Espressif
  `esp-now`; the exact build should use the upstream-compatible ESP-IDF release
  selected during the port work, then record that version in the repository.

The source currently contains a configurable default Wi-Fi network. A deployed
airframe must use a unique password, and credentials must not be committed.

### Host-side current client

`Python-Scripts/crazyflie-clients-python/pyproject.toml` declares Python
`>=3.10` and dependencies including `cflib`, `pyserial`, `numpy`, PyQt6,
PyQtGraph, VisPy, PyOpenGL, PyYAML, PyZMQ, and SDL support on macOS/Windows.
The existing scripts are exploratory examples, not a flight-safety API.

The connected macOS host currently exposes the WCH serial device as:

```text
/dev/cu.wchusbserial410
```

The observed bridge identity is USB vendor/product `1A86:7522`. The device is
available for later bench diagnostics; no firmware flash is implied by its
presence.

## OpenAI assistance dependency boundary

The AI layer belongs on the host, never in the flight-controller motor loop and
never with an API key on the drone. The first implementation should provide,
using the [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents)
only on the host:

1. A read-only telemetry adapter for the active firmware protocol.
2. Deterministic preflight, link-health, battery, sensor, and configuration
   checks that do not require a model.
3. An advisory OpenAI agent whose tools can inspect state, explain faults, and
   propose bounded actions.
4. An explicit human approval gate for any action that could change flight
   state, followed by a deterministic executor with an independent kill switch.
5. Dry-run and simulation tests that prove the agent cannot emit raw motor
   outputs or bypass the approval state machine.

The OpenAI credential is a host secret. It is not present in this repository,
and no credential was written during the initial setup. The service must run in
offline/dry-run mode until a local secret destination is explicitly approved.

## Required verification gates

The port is not complete until each gate has independent evidence:

- **Source gate:** selected upstream revision, license/provenance record, and a
  reproducible build configuration are committed.
- **Build gate:** firmware builds for ESP32-S3 with the selected toolchain.
- **Simulation gate:** sensor, mixer, failsafe, telemetry, and AI safety tests
  pass without a connected battery or motors.
- **Bench gate:** serial, IMU identity, motor-output disable behavior, Wi-Fi,
  and telemetry are checked with propellers removed and battery disconnected
  except for an explicitly controlled electrical test.
- **Human-control gate:** the ordinary controller remains authoritative and the
  AI layer can be disconnected without changing flight behavior.
- **Flight gate:** only after the preceding gates, with a documented airframe,
  battery, propeller, open-area, and emergency-disarm checklist.

No gate is inferred from a successful USB connection, a local source checkout,
or a passing host-only test.

## Next implementation decision

Select and pin the exact OpenDrone/OpenPilot repository and branch. The
recommended path is the LiteWing-compatible NinjaPilot/OpenPilot target while
retaining the current ESP-Drone firmware as a recovery image. Once confirmed,
the next change should add the selected target's source/provenance record and a
reproducible build harness before adding any AI or flight-control behavior.
