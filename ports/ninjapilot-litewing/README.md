# NinjaPilot LiteWing port

This directory owns the reproducible adapter boundary between the LiteWing
V2.6.C hardware and the selected NinjaPilot/OpenPilot flight tree. The source
inputs are pinned in [`SOURCE_MANIFEST.json`](SOURCE_MANIFEST.json).

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
device. The bootstrap verifies and applies only the repository-owned LiteWing
contract patch, then writes a marker outside the checkout. A matching marker
makes a repeat invocation a no-op. A source mismatch, dirty checkout, patch
mismatch, or ambiguous marker fails closed.

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
calls `flash`, `monitor`, `esptool`, or any motor-output test. The local
ESP-IDF 5.3.2 / ESP32-S3 toolchain is installed and verified. When the exact
external checkouts and generated flight UAVObjects are supplied, the wrapper
gate verifies compilation, linking, image generation, and partition sizing.

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
fault, failsafe, shutdown, or a 100 ms controller-update timeout.

The `target/sources.cmake` fragment is consumed by the ESP-IDF wrapper and is
linked with the pinned reference ESP32 PiOS support while excluding the
reference servo-pulse and ICM-20602 sources. The local no-flash gate has been
verified through compilation, linking, image generation, and partition-size
checking for ESP32-S3. Hardware behavior remains unverified; no firmware is
flashed by these sources.
