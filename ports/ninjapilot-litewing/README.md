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
5. build with the recorded ESP-IDF toolchain; and
6. complete separate prop-off bench and human-orientation checks.

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

## Target adapter status

The repository-owned adapter under [`target/`](target/) now supplies the two
hardware seams the pinned OpenPilotESP32 reference does not: an MPU6050 I2C
driver that probes `WHO_AM_I`, publishes the existing PIOS sensor queue record,
and fails the output gate on stale data; and a four-channel LEDC backend that
maps `0..1000` to 20 kHz duty, stages frames, and zeroes on disarm, sensor
fault, failsafe, shutdown, or a 100 ms controller-update timeout.

The `target/sources.cmake` fragment is consumed by the eventual ESP-IDF
wrapper. It must be linked with the pinned reference ESP32 PiOS support while
excluding the reference servo-pulse and ICM-20602 sources. This workstation
does not have `idf.py`, so the ESP-IDF compile and all hardware behavior remain
unverified; no firmware is flashed by these sources.
