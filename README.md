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
is backed up locally. A later [propeller-off USB transaction](docs/verification/armed-nonzero-motor-proof-2026-09-09.md)
proved `FlightStatus=Armed` together with six nonzero motor-command samples,
then 11 zero-command samples and receiver timeout while still Armed. It made no
persistent settings write and, by operator request, did not restore
`Always Disarmed`; the last observed `Always Armed` state was RAM-only and is
not evidence of persistence across a verified reset or power cycle. Later live
diagnosis established that a conventional pyserial reopen is not passive: the
CH340 DTR/RTS auto-reset path restarted the ESP32-S3 and the first observed
uptime was 402 ms. A reset-neutral POSIX open preserved continuing uptime.
Terminal RAM state must therefore be checked in the original session or through
that reset-neutral path. At that checkpoint, direct electrical measurement,
six-face precision calibration, battery operation, physical flight safety and
flight remained pending.

The later [final flight-configuration record](docs/verification/final-flight-configuration-2026-09-10.md)
verifies that the installed source is in merged `main` history, persists normal
`Yaw Right` arming across a deliberate reboot, reaches Armed with bounded
flight-stack motor commands, and closes on a reset-neutral Disarmed/zero-output
snapshot. A user-supplied four-corner recording confirms the fitted motor
directions, while stationary IMU data and live attitude agree closely enough
for initial controlled attitude/rate flight. Battery-system validation,
propeller fitting and an open-area hover remain separate physical gates.

The NinjaPilot target's [settings-persistence correction and USB reset
verification](docs/verification/settings-recovery-2026-09-09.md) are also complete
for the documented bench candidate. This is not flight clearance; physical
output validation remains outstanding.

The [GCS receiver freshness work](docs/verification/gcs-receiver-freshness-2026-09-09.md)
records the source and protocol-integration checks.

The reviewed receiver/thrust fixes are now [installed and checked over USB](docs/verification/control-fixes-usb-install-2026-09-09.md),
with preserved settings and disarmed telemetry across a reset. Arming is still
disabled at that recorded checkpoint. A [separate bounded USB trial](docs/verification/disarmed-receiver-completion-2026-09-09.md)
now passes the sampled disarmed receiver-loss/recovery checks with a complete
capture. Exact timeout latency, electrical output, powered operation and flight
remain unverified; this does not enable arming.

The checked Stabilization startup build is now [installed and observed over
USB](docs/verification/stabilization-startup-usb-install-2026-09-09.md). The
application, bootloader, partition table and settings passed separate live
comparisons; sampled runtime state remained disarmed with zero commands on the
four motor channels. Initial startup alarms and BootFault still prevent flight
clearance, and arming remained `Always Disarmed` at that checkpoint.

The checked ManualControl start build is likewise [installed and observed over
USB](docs/verification/manual-control-start-usb-install-2026-09-09.md). Its
application and preserved regions passed independent comparisons and complete
readbacks. Sampled ManualControl state ended disconnected, FlightStatus
remained Disarmed, and motor channels 1..4 remained zero. This does not clear
the persistent BootFault, startup-alarm or flight gates. The later bounded
arm/motor proof clears only the software-arming and commanded-output evidence
gate.

**USB-C is a motor-capable power source on this hardware.** Battery absence is
not a motor de-energization gate: a user-supplied
[LiteWing recording](https://x.com/d0tslash/status/2095720911743725618)
shows the battery connector empty while USB-C powers rotating propellers. USB
bench work must therefore use propeller removal, containment, explicit state
observation, bounded commands, and a verified return to zero as controls for
any energized motor test.

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
