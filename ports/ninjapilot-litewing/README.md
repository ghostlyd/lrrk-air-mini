# NinjaPilot LiteWing port

This directory owns the reproducible adapter boundary between the LiteWing
V2.6.C hardware and the selected NinjaPilot/OpenPilot flight tree. The source
inputs are pinned in [`SOURCE_MANIFEST.json`](SOURCE_MANIFEST.json).

The [settings-recovery report](../../docs/verification/settings-recovery-2026-09-09.md)
records the real persistence linker gate and non-destructive NVS recovery
contract. Successful compilation or linkage is not physical flight clearance.

The [thrust-control correction](../../docs/verification/thrust-control-width-2026-09-09.md)
records the checked byte-to-enum read and complete control-task regressions.
Invalid, unreadable, or `None` thrust modes select fault handling on this target.

The [subsequent USB installation report](../../docs/verification/control-fixes-usb-install-2026-09-09.md)
identifies the exact installed receiver/thrust candidate and settings-preserving
reset observations. Always Disarmed remains set; receiver-loss, electrical and
flight acceptance are not established by installing that candidate.

A [subsequent bounded disarmed receiver trial](../../docs/verification/disarmed-receiver-completion-2026-09-09.md)
observed loss/recovery/loss with a complete validated capture. This narrow
physical receiver-observation pass does not establish electrical cutoff timing,
powered tests or flight readiness, and does not enable arming.

The [startup-alarm investigation](../../docs/verification/startup-alarm-diagnosis-2026-09-09.md)
adds real-code host reproductions of counter warm-up, initial actuator failsafe
and alarm grace behavior. Boot-success failure propagation remains incomplete;
this investigation does not clear alarms or change installed firmware.

The [board startup failure gate](../../docs/verification/board-startup-failure-gate-2026-09-09.md)
now stops module initialization after reported synchronous board errors and
prevents same-boot reinitialization. It is tested and built, not installed;
complete BootFault success and asynchronous startup validation remain open.

The [event/alarm service correction](../../docs/verification/startup-service-failures-2026-09-09.md)
extends that gate into the real service implementations: allocation failures
now return errors, existing alarms are preserved, and a failed periodic-event
allocation releases its mutex. These changes are source-tested and built only;
the installed firmware and Always Disarmed setting are unchanged.

The [callback scheduler correction](../../docs/verification/callback-scheduler-startup-2026-09-09.md)
adds checked worker startup, owned-resource cleanup and a System-task stop path
after scheduler failure. Real-code host regressions and an ESP32-S3 build pass;
the candidate is not installed and complete startup/arming readiness remains open.

The [System lifecycle correction](../../docs/verification/system-task-lifecycle-2026-09-09.md)
checks System-owned initialization resources, removes its creator/monitor race,
and propagates synchronous System errors to the actual entry point. Required
module internals and the complete boot/physical gates still need validation.

The selected upstream `litewing` branch currently includes a POSIX/Gazebo
LiteWing twin, not a flashable ESP32-S3 target. The repository-owned target
work therefore proceeds in gates:

1. verify source revisions and patch hashes;
2. preserve the POSIX simulation path;
3. add the LiteWing board contract;
4. implement and review the MPU6050 I2C and brushed-duty HAL pieces;
5. compose the no-flash ESP-IDF wrapper against exact external commits;
6. build with the recorded ESP-IDF toolchain; and
7. complete separate prop-off bench and human-orientation checks.

The existing ESP-Drone firmware is the recovery baseline. No script in this
directory flashes a device, starts a motor, or changes the physical board.

## Source workflow

From a workspace directory that contains or will contain a clean NinjaPilot
checkout:

```sh
ports/ninjapilot-litewing/bootstrap.sh /path/to/workspace /path/to/workspace/NinjaPilot
LRRK_ALLOW_DIRTY=1 ports/ninjapilot-litewing/verify_source.sh /path/to/workspace/NinjaPilot /path/to/workspace/.lrrk-litewing-patches
ports/ninjapilot-litewing/simulate.sh /path/to/workspace/NinjaPilot
ports/ninjapilot-litewing/revert.sh /path/to/workspace /path/to/workspace/NinjaPilot
```

The manifest records the two OpenPilotESP32 WROOM patches as checksum-pinned
reference material, but marks them `apply: false`: the selected NinjaPilot
`litewing` commit has diverged and the MPU patch targets a different ICM20602
device. The bootstrap verifies and applies the repository-owned LiteWing
contract and native simulator loopback patches, then writes a marker outside
the checkout. A matching marker
makes a repeat invocation a no-op. A source mismatch, dirty checkout, patch
mismatch, or ambiguous marker fails closed.

## Simulator build and runtime

`simulate.sh` verifies the source and builds/packages the native `fw_simlitewing`
target. It reports `SIMULATION_BUILD=PASS` separately from
`SIMULATION_RUNTIME=NOT_RUN`; compilation does not establish flight behavior.
On Apple Silicon the pinned build uses Qt 5 and GNU `objcopy`:

```sh
brew install qt@5 binutils
export PATH="/opt/homebrew/opt/qt@5/bin:/opt/homebrew/opt/binutils/bin:/opt/homebrew/bin:$PATH"
ports/ninjapilot-litewing/simulate.sh /path/to/NinjaPilot
```

The pinned upstream Makefile also discovers Homebrew's keg-only `objcopy`
directly. `fw_simlitewing_elf` builds just the native executable; the default
target additionally packages `.bin` and `.opfw` files. These are simulator
artifacts, not ESP32-S3 flash images.

See [the recorded simulator check](../../docs/verification/simulator-build-2026-09-09.md)
for observed startup and remaining physics requirements.

Gazebo Harmonic, the native `simposix` target, and the isolated Python bridge
environment are covered in [dependency setup and verification](../../docs/verification/gazebo-dependencies-2026-09-09.md).
These checks do not establish a working LiteWing physics/control loop.

The [disarmed integration probe](simulation/README.md) now verifies live
Gazebo IMU ingestion by the native firmware, disarmed/zero motor telemetry,
freshness rejection, and loopback socket ownership. It remains separate from
armed closed-loop dynamics and physical ESP32 driver validation.

## Hardware contract

The first image targets the ESP32-S3-WROOM-1, MPU6050 on I2C0 (SDA 11, SCL
10, data-ready 12), and four brushed outputs on GPIO5/6/3/4. The output range
is `0..1000` at 20 kHz duty. Zero is the safe output. Motor corner order and
IMU orientation are provisional until a human verifies the physical board with
props removed.

Optional VL53L1X and PMW3901 modules are not enabled by this first target.

## ESP-IDF wrapper

The checked-in project under [`esp-idf/`](esp-idf/) targets ESP32-S3 and
requires ESP-IDF 5.3.2, the pinned NinjaPilot checkout, the pinned
OpenPilotESP32 backend checkout, and generated flight UAVObjects:

```sh
# Host dependencies used by the pinned NinjaPilot UAVObject generator.
brew install cmake ninja qt@5
export PATH="/opt/homebrew/opt/qt@5/bin:/opt/homebrew/bin:$PATH"

# From the repository root; only needed for a fresh local toolchain.
mkdir -p .toolchains
git clone --depth 1 --recursive --branch v5.3.2 \
  https://github.com/espressif/esp-idf.git \
  .toolchains/esp-idf-v5.3.2
export IDF_TOOLS_PATH="$PWD/.toolchains/espressif"
.toolchains/esp-idf-v5.3.2/install.sh esp32s3

(cd /path/to/NinjaPilot && make uavobjects_flight)
# The installed local toolchain can be activated from the repository root.
export IDF_TOOLS_PATH="$PWD/.toolchains/espressif"
export PATH="/opt/homebrew/bin:$PATH"
. "$PWD/.toolchains/esp-idf-v5.3.2/export.sh"
ports/ninjapilot-litewing/build.sh \
  --flight-checkout /path/to/NinjaPilot \
  --reference-checkout /path/to/OpenPilotESP32-WROOM-32E
```

When `IDF_PATH` is not already set, `build.sh` also discovers this local
installation automatically. The command is intentionally build-only. It never
opens a serial device, invokes flashing/monitoring, or runs a motor-output test.
ESP-IDF uses `esptool` offline to generate the binary image. The local
ESP-IDF 5.3.2 / ESP32-S3 toolchain is installed and verified. When the exact
external checkouts and generated flight UAVObjects are supplied, the wrapper
gate verifies compilation, linking, image generation, and partition sizing.

Keep the SDK and ESP-IDF Python environments separate. This workstation's
installed IDF environment is `idf5.3_py3.9_env`; selecting a different Python
minor version can make `export.sh` look for a nonexistent environment. For
this existing installation, activate it before invoking `build.sh` (from the
checkout that contains the installed `.toolchains` directory):

```sh
export IDF_TOOLS_PATH="$PWD/.toolchains/espressif"
export PATH="$IDF_TOOLS_PATH/python_env/idf5.3_py3.9_env/bin:/opt/homebrew/opt/qt@5/bin:/opt/homebrew/bin:$PATH"
. "$PWD/.toolchains/esp-idf-v5.3.2/export.sh"
```

The environment name describes the verified workstation, not a portable
requirement; other installations must select their own installed IDF Python
environment. Do not install another toolchain merely because an unrelated
virtual environment is active.

The wrapper consumes the reference architecture, UART, I2C, watchdog, NVS,
and task-runtime sources, but excludes the reference ICM-20602 and servo-pulse
drivers. LiteWing supplies those two seams through its MPU6050 I2C queue driver
and fixed 20 kHz brushed LEDC backend.

The host generator uses Qt 5 (`qt@5` is currently deprecated upstream but is
still required by this pinned NinjaPilot tree). ESP-IDF source and tools are
kept under the ignored `.toolchains/` directory; the generated `sdkconfig` and
ESP-IDF `build/` tree are also local artifacts.

## Target adapter status

The repository-owned adapter under [`target/`](target/) now supplies the two
hardware seams the pinned OpenPilotESP32 reference does not: an MPU6050 I2C
driver that probes `WHO_AM_I`, publishes the existing PIOS sensor queue record,
and fails the output gate on stale data; and a four-channel LEDC backend that
maps `0..1000` to 20 kHz duty, stages frames, and zeroes on disarm, sensor
fault, failsafe, shutdown, or stale controller updates. The output watchdog
tests for age greater than 100 ms on a 20 ms polling task; polling phase,
scheduling and mutex contention add delay. This is not a proven 100 ms
electrical motor-cut deadline.

The `target/sources.cmake` fragment is consumed by the ESP-IDF wrapper and is
linked with the pinned reference ESP32 PiOS support while excluding the
reference servo-pulse and ICM-20602 sources. The local no-flash gate has been
verified through compilation, linking, image generation, and partition-size
checking for ESP32-S3. A separately authorized [USB-only bench session](../../docs/verification/usb-bringup-2026-09-09.md)
now records verified backup/flashing and disarmed telemetry from the physical
board. Electrical output timing, calibrated orientation and flight remain
unverified. No firmware is flashed by the build scripts themselves.
