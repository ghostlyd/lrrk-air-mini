# lrrk-air-mini / LiteWing

Open source hardware and software for the LiteWing compact Wi-Fi drone, with a
host-side control and AI-assistance layer under active development.

![LiteWing](Documents/Images/LiteWing.png)

LiteWing is an ESP32-S3-based quadcopter platform. The board combines the
flight controller, brushed-motor drivers, battery charging, USB serial, and
Wi-Fi control on one small PCB. The firmware in this repository is the
ESP-Drone/Crazyflie-compatible flight stack supplied by the upstream LiteWing
project; the host tools use its CRTP-over-UDP interface.

## Repository status

This repository is the maintained `lrrk-air-mini` source tree. The original
LiteWing repository is retained as the `upstream` Git remote for provenance and
source comparison. AI assistance is being added as a host-side, advisory layer:
it may inspect telemetry and propose bounded actions, but it cannot directly
write motor outputs and flight actions require an explicit human approval gate.

The port boundary and dependency inventory are documented in
[`docs/PORT_AND_DEPENDENCIES.md`](docs/PORT_AND_DEPENDENCIES.md). The first
authorized [USB-only flash and telemetry check](docs/verification/usb-bringup-2026-09-09.md)
has completed with propellers removed and no battery. The original full flash
is backed up locally. The candidate remains configured `Always Disarmed`;
powered motor tests, calibration, physical safety validation and flight remain
pending.

The NinjaPilot target's [settings-persistence correction and USB reset
verification](docs/verification/settings-recovery-2026-09-09.md) are also complete
for the documented bench candidate. This is not flight clearance; receiver-loss
supervision and physical output validation remain outstanding.

The [GCS receiver freshness work](docs/verification/gcs-receiver-freshness-2026-09-09.md)
records source, protocol-integration and remaining physical receiver-loss gates.

## Firmware build

The firmware is an ESP-IDF project. Install a compatible ESP-IDF toolchain,
select the ESP32-S3 target, then build from the repository root:

```sh
idf.py set-target esp32s3
idf.py build
```

Do not run `idf.py flash` while a battery is connected or propellers are
installed. The default LiteWing firmware exposes a Wi-Fi network and accepts
CRTP/UDP control from a host on the same network.

## Host tools

The existing examples are under [`Python-Scripts/`](Python-Scripts/). The
maintained AI-assistance host service will live separately from the flight
controller and will default to dry-run/advisory mode.

## Upstream

The original LiteWing source and hardware are from
[`jobitjoseph/LiteWing`](https://github.com/jobitjoseph/LiteWing). Changes in
this repository should retain upstream attribution and keep hardware revisions
traceable to the KiCad files and production BOMs.
