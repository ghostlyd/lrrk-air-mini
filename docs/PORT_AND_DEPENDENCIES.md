# LiteWing port and dependency inventory

Latest hardware checkpoint (2026-09-11): the retained normal application was
restored with an application-only flash; NVS/PHY and settings bytes were
unchanged. A 15-second USB advisory session delivered 74 snapshots and completed
one OpenAI analysis, with captured status Disarmed and all motor outputs zero.
See the [normal-image comparison](verification/usb-advisory-stream-2026-09-11.md#normal-image-comparison-and-live-usb-to-openai-result).
This supersedes older statements below that the diagnostic image is installed,
but does not establish repeated-start reliability or flight qualification.

USB-first update (2026-09-11): the draft branch adds `litewing-usb-advisory`,
combining reset-neutral USB acquisition, a separate latest-only advisory worker,
bounded provider attempts and cooperative deadlines. Mac internet stays on its
normal connection; no drone USB network stack or additional network hardware is
required for this path. The latest local suite passed 355 tests, but live startup
framing is intermittent and unresolved. See the [streaming record](verification/usb-advisory-stream-2026-09-11.md).
This draft source is not a merged release or installed firmware claim.

Current checkpoint: the keyboard launcher and local advisory worker are merged
through PR #74. Credential storage was verified. A complete USB power cycle
recovered live USB telemetry and changing attitude samples with disarmed/zero
motor outputs; the earlier MPU6050 probe failure is not yet explained or proven
fixed across resets. A temporary console
diagnostic image remains installed, not flight-qualified. Historical bench
successes below do not supersede this [live diagnostic](verification/wifi-activation-diagnostic-2026-09-10.md).

Status: ESP32-S3 wrapper build and final USB configuration verified through
2026-09-10. This document records what is evidenced in this repository and on
the connected development host. The approved
NinjaPilot/OpenPilot LiteWing target is pinned, and the ESP32-S3
image builds successfully. A separately authorized [USB-only session](verification/usb-bringup-2026-09-09.md)
verified an 8 MB recovery backup, flashed the candidate, and observed disarmed
telemetry plus changing IMU/attitude values at 57600 baud. A subsequent
[USB software-arm proof](verification/armed-nonzero-motor-proof-2026-09-09.md)
observed six bounded nonzero motor-command samples while Armed, followed by 11
zero-command samples and receiver timeout while still Armed. The full bench and
flight gates remain incomplete; no flight has been performed. The later
[final configuration record](verification/final-flight-configuration-2026-09-10.md)
puts the installed image in merged `main` history, persists normal `Yaw Right`
arming through reset, proves normal arming with bounded nonzero commands,
confirms all four fitted motor directions, accepts the stationary IMU for an
initial attitude/rate flight, and closes Disarmed at zero output.

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
does not establish electrical duty in the recorded trial. A separate
user-supplied four-corner recording now confirms physical fitted rotations and
continuity; it is not represented as synchronized with the UART transaction.
Source work, host simulation, and AI development can continue. A battery is a
required outstanding purchase; verify cell count, voltage, current capability,
mass, fit, and the physical connector/polarity before selecting a SKU. The BOM's
connector designation alone is not proof of the assembled board's wiring.

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

### Selected OpenPilot wrapper (distinct from the stock baseline)

Use `ports/ninjapilot-litewing/esp-idf`, not the root ESP-Drone project, for
the selected port. The wrapper requires the manifest-pinned NinjaPilot and
reference HAL trees, generated UAVObjects, and ESP-IDF **5.3.2** with its
ESP32-S3 toolchain. The stock `cflib`/CRTP client below is not an OpenPilot
UAVTalk controller and should not be assumed compatible with this image.

The battery telemetry implementation adds the IDF-provided `esp_adc` component
(continuous ADC1 and curve-fitting calibration); it does not require a separate
ADC breakout or additional Python hardware library. It targets GPIO2 using the
candidate board's nominal resistor-divider ratio, which still needs fitted-board
electrical validation. Initialization and sampling run on one pinned worker;
missing calibration produces unavailable voltage, not a guessed conversion.
See the [battery integration/build record](verification/battery-telemetry-bringup-2026-09-10.md).

The host AI package declares CPython **3.11 through 3.14**. Keep its environment
separate from the ESP-IDF-managed Python environment. UART telemetry uses the
pinned UAVTalk decoder; optional serial and OpenAI SDK dependencies are declared
in [`ai_assistant/pyproject.toml`](../ai_assistant/pyproject.toml). OpenAI runs on
the host, with no API credential or model on the board. The selected wrapper's
authenticated Wi-Fi command runtime and USB provisioning workflow are now
source-integrated. Authenticated wireless telemetry now reaches the advisory
runtime in localhost integration tests. One-shot physical credential storage
was verified. The Mac keyboard adapter and launcher are implemented and tested;
live AP activation, board-side wireless telemetry and operator/radio
qualification remain unfinished.
The stock firmware's Wi-Fi features below do not establish
support in this port.

### Authenticated Wi-Fi dependency checkpoint — 2026-09-10

Initial source checkpoint: PR #62, merged as `62333acf7a4d65c0961d0c63837c182d14e63abb`.
Telemetry and advisory rows below are updated through PR #69
(`7b30469702d38958c0d65ba3dbb1a209602d53ee`) and PR #70
(`40cf494286fb2911b59e27b91a78c0d7515ea506`).
The dependency declarations below were checked against the wrapper's
[`main/CMakeLists.txt`](../ports/ninjapilot-litewing/esp-idf/main/CMakeLists.txt),
[`sources.cmake`](../ports/ninjapilot-litewing/target/sources.cmake),
[`sdkconfig.defaults`](../ports/ninjapilot-litewing/esp-idf/sdkconfig.defaults),
and the host package metadata. This is source dependency verification, not a
fresh installation or live radio test.

| Boundary | Required dependency | Implementation / remaining work |
| --- | --- | --- |
| Drone AP | ESP-IDF 5.3.2 `esp_wifi`, `esp_netif`, `esp_event` and SDK networking | AP lifecycle and bounded UDP command task are linked through System startup; no extra radio module |
| Command authentication | IDF `mbedtls`, HKDF enabled by `CONFIG_MBEDTLS_HKDF_C` | Direction-separated keys, authenticated session and replay/freshness enforcement |
| Credential loading/storage | IDF `nvs_flash` | Dedicated `lw_pilot/config`; integrated bounded USB worker, scoped writer and verified readback; private host rotation preserves old/pending copies |
| Timing/randomness | IDF `esp_timer`, `esp_hw_support` | Monotonic challenge age and platform RNG; radio-load timing still needs measurement |
| Host pilot protocol | CPython 3.11–3.14 standard-library networking, HMAC and randomness; Tk for the GUI | Mac keyboard adapter and explicit demo/live launcher merged in PR #74; local Tk and installed-package tests passed; live pilot qualification remains outstanding |
| USB telemetry | Optional `uavtalk` extra: `pyserial>=3.5,<4` | Existing UAVTalk path retained; stock CRTP clients cannot operate LWPL |
| Authenticated telemetry | Pinned NinjaPilot UAVObject manager, battery acquisition boundary and IDF `mbedtls`; CPython standard library on the host | Five rotating schemas, independent telemetry key/sequence, coherent battery bytes/age; real C-to-Python localhost integration verified, not board radio qualification |
| Host advisory AI | Optional `openai` extra: `openai-agents==0.22.1`; standard-library handoff requires no extra package | Read-only worker integrated with launcher; no pilot key shared with AI tools; launcher runs local preflight analysis without API calls; live wireless-to-OpenAI validation remains outstanding |
| Concurrent host networking | Wi-Fi to the drone AP plus an independent internet route for cloud AI | The drone AP does not supply internet. On the observed Mac, the default route is Wi-Fi (`en1`) and Ethernet (`en0`) is inactive; alternate-uplink qualification remains outstanding. Local/offline assistance does not require internet |
| Windows private audit files | `oschmod==0.3.12`, `pywin32==312` | Declared Windows-only dependencies; not yet a credential-bundle storage implementation |

Provisioning update: the [operator commands](../ai_assistant/README.md#operator-provisioning)
use the existing `uavtalk` extra for USB and standard-library UDP/HMAC/randomness
for key reachability. macOS storage also checks descriptor ACLs through system
libc; Linux rejects POSIX ACL attributes. No additional pip dependency is added.
Windows provisioning and Linux serial opening are not implemented. The current
provisioning source candidate was rebuilt at `daeb3bf` with ESP-IDF 5.3.2 and dump-disabled
configuration; physical activation is not inferred from that build.

The later publisher build at `e86d872` uses the same ESP-IDF 5.3.2 dependency
boundary and disabled core dumps. Its linked image is `0xd53e0` bytes, with 17%
free in the unchanged application partition. See the
[publisher build and integration evidence](verification/wifi-telemetry-publisher-2026-09-10.md).
The [advisory handoff evidence](verification/wifi-advisory-handoff-2026-09-10.md)
separately records 300 assistant tests (9 optional skips) and the real
C/UDP/Python/runtime path. That host-only change adds no third-party dependency
and performs no OpenAI request or board operation. A slow consumer can miss
object types: the slot holds a latest partial observation, not a complete or
synchronized aircraft state. The selected Mac keyboard adapter, user-facing
launcher and advisory-worker scheduling are implemented; the complete live
wireless operator workflow still requires qualification. Tk is required for the
GUI (locally installed as Homebrew `python-tk@3.14`), not for headless advisory
use. See [keyboard operation and limits](../ai_assistant/README.md#mac-keyboard-pilot).

No additional onboard AI computer, GPS, optical-flow sensor or range sensor is
required by this attitude/rate pilot-link design. These exclusions do not imply
position hold, autonomous navigation, or flight qualification. See the
[integrated runtime record](verification/wifi-runtime-2026-09-10.md) for the
build/test scope, and the [provisioning audit](verification/wifi-provisioning-boundary-2026-09-10.md)
for the remaining credential lifecycle.

#### Crash-dump and storage confidentiality prerequisite

At the PR #62 baseline, wrapper defaults enabled ELF core dumps to flash. The
then-inspected generated build configuration also had NVS encryption and flash
encryption disabled. `pios_litewing_wifi_command.c` keeps its root and controller state in
the owning task's stack frame. ESP-IDF 5.3.2's local core-dump documentation
states that dumps include task stacks. Therefore crash dumps may contain
credential/session material, even though routine logs do not print it and
normal cleanup wipes buffers. Disabling optional DRAM capture does not exclude
task stacks.

Before provisioning real credentials, resolve the crash-dump policy explicitly
and test the resulting build configuration. Treat any existing dump, full-flash
backup or raw provisioning capture as potentially secret-bearing; do not commit
or upload it. This audit has not read device storage, changed eFuses, erased
dumps, or established encrypted storage. Disabling future dumps alone would
not remove an old dump or encrypt the credential NVS record.

Source update `6120324` now disables future core dumps and rejects unsafe
effective configurations. A fresh pinned IDF build passed and a separate
dump-enabled configuration was rejected by the real build. See the
[credential-retention verification](verification/pilot-credential-retention-2026-09-10.md).
This change is not an installed-image claim; historical dumps and plaintext
NVS retain the limitations above.

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
and ESP-IDF board glue now contain the MPU6050 I2C and brushed-duty HAL seams.
The toolchain build, merged-image identity, startup, normal arming, motor mapping
and initial-flight IMU configuration gates have passed; battery-system,
propeller and actual hover gates remain open.

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
