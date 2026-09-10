# LiteWing port and dependency inventory

Status: ESP32-S3 wrapper build verified on 2026-09-09. This document records what is evidenced in
this repository and on the connected development host. The approved
NinjaPilot/OpenPilot LiteWing target is pinned, and the ESP32-S3
image builds successfully. A separately authorized [USB-only session](verification/usb-bringup-2026-09-09.md)
verified an 8 MB recovery backup, flashed the candidate, and observed disarmed
telemetry plus changing IMU/attitude values at 57600 baud. A subsequent
[USB software-arm proof](verification/armed-nonzero-motor-proof-2026-09-09.md)
observed six bounded nonzero motor-command samples while Armed, followed by 11
zero-command samples and receiver timeout while still Armed. The full bench and
flight gates remain incomplete; no flight has been performed.

## Scope and target boundary

The checked-in baseline is the [upstream LiteWing](https://github.com/jobitjoseph/LiteWing) ESP-Drone/Crazyflie-compatible
ESP-IDF firmware and its host-side Python examples. The selected port target
is NinjaPilot/OpenPilot's LiteWing-compatible path:

| Candidate | Fit with the existing LiteWing board | Current decision |
| --- | --- | --- |
| [NinjaPilot/OpenPilot LiteWing target](https://github.com/MAVProxyUser/OpenPilotESP32-WROOM-32E) | ESP32-S3 and the existing MPU6050/brushed-MOSFET architecture are plausible, but it is a different flight-tree/build boundary. | **Selected and pinned:** NinjaPilot `litewing` at `ac77304a58de6c8bd552f94668b46903adb71cb2`; reference ESP32 HAL at `7233c97f844c0377930bcdf22998e289638b64c6`. |
| [OpenDrone-hw/OpenFC-Lite](https://github.com/OpenDrone-hw/OpenFC-Lite) | Targets a different RP2354B flight controller, external ESC architecture, and higher-voltage battery system. | Not a firmware-only LiteWing port. |
| OpenDroneID/Remote ID | A telemetry/broadcast feature rather than a replacement flight stack. | Optional later feature. |

The target adapter and source manifest are now being built in
`ports/ninjapilot-litewing/`. Changes must remain additive and reversible, and
the existing ESP-Drone image remains the recovery baseline until the new path
passes source, build, simulation, bench, and human-orientation gates.

The OpenPilotESP32 WROOM patch set is pinned for provenance but is not applied
to the selected NinjaPilot `litewing` commit: the shared patch fails closed on
that newer branch, and the separate sensor patch targets ICM20602 rather than
LiteWing's MPU6050. The repository-owned bootstrap applies the reviewed
LiteWing contract and native simulator loopback patches.

## LiteWing hardware baseline

Owner inventory update (2026-09-09): no battery is currently available.
Battery-powered checks and flight verification therefore remain pending. USB-C
nevertheless powers the motor path: the bounded software-arm transaction has
now produced nonzero flight-stack motor commands without a battery. That result
does not establish electrical duty or physical rotation in the recorded trial.
Source work, host simulation, and AI development can continue. A battery is a
required outstanding purchase; verify cell count, voltage, current capability,
mass, fit, and the physical connector/polarity before selecting a SKU. The
BOM's connector designation alone is not proof of the assembled board's wiring.

The primary hardware evidence is the KiCad design and production BOM in
`hardware/LieWingV2.6.C/` (the directory name preserves the upstream `LieWing`
spelling). Owner photos show a **V1.2** board marking. The PCB source in that
V2.6.C directory itself prints `V 1.2`, with a closely matching visual layout;
the directory name and silkscreen are not interchangeable revision labels.
See [photo identification](verification/board-photo-identification-2026-09-09.md).
This remains the candidate design for port planning, not proof of net-by-net
or fitted-part equivalence.

### Board-level components evidenced by the V2.6 BOM

Purchase decisions must also use [parts selection and purchase gates](PARTS_SELECTION.md).
In particular, the published battery guide's 2.0 mm connector conflicts with
the 2.50 mm J2 specified by this revision's BOM; neither identifies the fitted
connector until the physical board is checked.

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
available to the bounded live AI telemetry adapter when its exact topology
location also matches. USB enumeration does not identify the aircraft and no
firmware flash is implied by its presence.

The local ESP-IDF 5.3.2 installation now builds the wrapper through compile,
link, image generation, and partition sizing. Homebrew CMake, Ninja, and Qt 5
provide host tools; `qmake` is under `/opt/homebrew/opt/qt@5/bin` and ESP-IDF
activation is documented in the port README. This build does not establish
physical hardware behavior. The native simulator also compiles and packages
with Homebrew binutils 2.47 installed; its startup probe and remaining physics
dependencies are recorded in [simulator verification](verification/simulator-build-2026-09-09.md).

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

The OpenAI credential is a host secret and is not present in this repository.
Live mode requires `OPENAI_API_KEY` to be supplied at runtime from an approved
host secret store; the service remains offline/dry-run by default and never
places the credential on the flight controller.

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

## Selected target implementation

The source/provenance record, reproducible bootstrap, and no-flash ESP-IDF
wrapper are maintained in
[`ports/ninjapilot-litewing/`](../ports/ninjapilot-litewing/). The upstream
`litewing` branch currently contains a POSIX/Gazebo twin rather than a
flashable LiteWing ESP32-S3 board target. The repository-owned target adapter
and ESP-IDF board glue now contain the MPU6050 I2C and brushed-duty HAL seams;
the toolchain build has passed and physical gates remain open.

The adapter depends on the pinned reference ESP32 PiOS support for the
architecture header, IDF I2C transaction backend, and common ESP32 services.
It explicitly excludes the reference ICM-20602 SPI driver and servo-pulse
backend. See [`ports/ninjapilot-litewing/target/README.md`](../ports/ninjapilot-litewing/target/README.md)
and `target/sources.cmake` for the source boundary.

The implemented host AI layer is documented in
[`docs/AI_ASSISTANT.md`](AI_ASSISTANT.md). It is advisory, offline-capable,
and cannot write flight-control outputs.

## Required software dependencies

The selected wrapper needs these dependencies before its build gate can pass:

- ESP-IDF 5.3.2 with the ESP32-S3 toolchain and `idf.py` in the environment.
- Python 3 for manifest/source checks and NinjaPilot's version-info script.
- Git, with clean checkouts at the exact commits in `SOURCE_MANIFEST.json`.
- NinjaPilot's generated flight UAVObjects (`make uavobjects_flight`), which
  in turn requires the upstream Qt/qmake generator toolchain.
- GNU `objcopy` (Homebrew `binutils`) for native simulator packaging on macOS.
- Gazebo and its matching Python transport/message bindings for external
  physics simulation; these are not flight-controller firmware dependencies.
- No OpenAI package or API key on the flight controller. The optional OpenAI
  Agents SDK is host-only and remains behind the advisory/approval boundary.
- Python `pyserial>=3.5,<4` for the optional exclusive 57600-baud live UAVTalk
  adapter. The unused `cflib` client remains a separate host-only `crazyflie`
  extra and is not pulled into this serial path.

The board-level parts evidenced by the V2.6.C production BOM are the ESP32-S3-
WROOM-1 (U8), MPU-6050 (U7), CH340K (U5), TP4056 (IC1), SPX3819M5-L-3-3/TR
(U2), AO3401A (U1), four IRLML6344TRPBF motor MOSFETs (T1-T4), 2N27002DW
(U6), SS34/1N4148W protection diodes, USB-C (J1), and JST XH 2P battery
connector (J2). The fitted motor, propeller, guard, and battery SKUs are not
established by the BOM and must be recorded before any powered test.
