# Current LiteWing image and flight-readiness evidence — 2026-09-09

## Outcome

The ESP32-S3 is running the app built from wrapper commit
`37f2476c6984f15dfe2b9ecd2861321652497804`. The app partition was read back
byte-for-byte after flashing, whole-boot readiness reports success, the motor
corner/direction contract and IMU body transform are implemented in one tested
source contract, and a bounded USB-powered transaction reached Armed with
nonzero flight-stack-generated motor commands before returning all four motor
commands to zero.

| Readiness item | Result | Evidence boundary |
| --- | --- | --- |
| Current-image identity | PASS | Firmware telemetry contains `LRRK37f2476c6984f15d`; app readback equals the built image; wrapper commit `37f2476` is in merged `main` history. |
| Startup alarms | PASS | `BootFault=OK`; settled and post-reset snapshots have no Critical/Error alarm. Receiver is Warning with none attached; unused optional sensors remain Uninitialised. |
| Motor corner/direction mapping | PASS | PCB nets/coordinates, owner photos, A/B labels, wire colors and the user-supplied four-corner spin recording agree with the tested mixer contract. |
| IMU orientation | PASS | Source/package orientation and live negative body-Z gravity agree with `body=(sensor Y, sensor X, -sensor Z)`. |
| IMU calibration | PASS for initial attitude/rate flight | Runtime gyro-bias estimation is active; stationary gravity-derived and live roll/pitch agree within 0.033°/0.006°. Factory accelerometer scale remains explicit; no six-face precision calibration is claimed. |

This is not a claim of battery-powered flight readiness. No flight battery is
available, and no battery/charger/connector or propeller flight check occurred.
The later complete configuration transaction is recorded in
[final-flight-configuration-2026-09-10.md](final-flight-configuration-2026-09-10.md).

## Exact build and flash

- ESP-IDF: 5.3.2, target ESP32-S3.
- Application source version: `37f2476`.
- Built and read-back app SHA-256:
  `98214708fcf511b3ccfb3a5511784791dda4166d87cd809102393e395d37f013`.
- App size: 359,776 bytes (`0x57d60`), written only at factory offset `0x10000`.
- The bootloader, partition table and settings regions compared equal before
  and after the app-only flash.
- Firmware telemetry retained canonical NinjaPilot board identity (type 19,
  revision 2 and upstream source `ac77304a`) and added the exact wrapper marker
  in the reserved description tail.
- PR #51 placed the installed wrapper source in merged `main` history at merge
  commit `dc3345dab633557de72e901627e31b7ffaea78b0`.

The generated identity step rejects dirty/nested inputs and produces the marker
from the exact clean wrapper commit. The board startup path does not manufacture
success from the marker: it separately requires initialized board services, a
healthy MPU-6050 sample, six required tasks and a clear/read-back of BootFault.
Failure latches output shutdown and Critical BootFault.

## Settled boot and reset diagnosis

The private 30-second settled capture is 130,847 bytes with SHA-256
`e0c75569d38b59fb0b02666a31b5eb1d486e697aad2aa35d11849d78438e0caf`.
Its terminal state was Disarmed, four zero motor commands, 54% reported CPU,
`BootFault=OK`, and no Critical/Error alarms. Receiver remained Warning because
no receiver was attached; unused optional sensors remained Uninitialised.

A conventional CH340 pyserial reopen reset the controller even though the probe
did not send a reset command. A fresh capture began at `FlightTime=402 ms` and
ended at 29,501 ms. The repository schematic explains the mechanism: CH340
`DTR/RTS` feed the board's Auto Reset Circuit and ESP32-S3 `EN/IO0`.

A separate POSIX file-descriptor open configured 57,600 baud without changing
modem-control lines. Its first/last observed uptimes were 130,473/138,321 ms,
proving that method did not restart the running image. That private 32,492-byte
capture has SHA-256
`4662232d51c508b1b87f18e66ab8c5e7a070db35bd0d9ba99b483cb8e048ef94`.
Ordinary serial reopen is therefore a reset operation on this board, not an
independent read-only observation of RAM state.

The reviewed diagnostic implementation was then exercised against the same
board without transmitting any bytes. It discarded 28 bounded pre-frame bytes,
decoded zero motor commands and the settled alarm state, and observed uptime
continuing from 576,322 to 579,360 ms. Its 13,122-byte private capture has
SHA-256 `3d96d648725a84c48a6e7b154681eecb607abf97a669855302c91610a443972c`.

## Motor and IMU contracts

The production and tested motor contract is:

| Channel | GPIO | Corner | Fitted class/wires | Intended direction | Mixer yaw |
| ---: | ---: | --- | --- | --- | ---: |
| 1 | 5 | front-right | B, black/white | CCW | -127 |
| 2 | 6 | rear-right | A, red/blue | CW | +127 |
| 3 | 3 | rear-left | B, black/white | CCW | -127 |
| 4 | 4 | front-left | A, red/blue | CW | +127 |

The MPU-6050 production transform is `body X=chip Y`, `body Y=chip X`, and
`body Z=-chip Z`. The final stationary sample mean was approximately
`(0.018, 0.655, -9.430) m/s²`; gyro output was small and finite. Gravity-derived
roll/pitch agreed with live attitude within 0.033°/0.006°. The transform also
has explicit signed-16-bit endpoint coverage.

Detailed sources and claim boundaries are in
[motor-imu-mapping-2026-09-09.md](motor-imu-mapping-2026-09-09.md).

## Current-image normal arming/nonzero proof

The final configuration persists normal `Yaw Right` arming and verifies it
after a deliberate reset. The subsequent bounded transaction used that normal
policy, observed three connected low-input samples, held 21 connected arming
samples, reached `FlightStatus=Armed`, and produced four nonzero
`ActuatorCommand` samples. Peak channels were `[59, 0, 0, 62]` on the
`0..1000` command scale. It then observed 12 zero samples and ended Armed with
all four channels zero and the receiver disconnected. No persistent write was
sent in the arm transaction. The 47,198-byte capture has SHA-256
`369484118eba2569f7aea04ed3e2f6535a0b2f4fdd15fe3a535b441aae14e885`.

After the configured 30-second timeout, a request-only reset-neutral snapshot
observed Disarmed, all four channels zero, `Yaw Right` still loaded,
`BootFault=OK`, and no Critical/Error alarm. This is consistent with the
configured automatic-disarm path; the separate capture is not a continuous
electrical trace. That closing 81,566-byte capture has SHA-256
`586da78dbd3a9aa2983b8d3821544f25d60b49b499a825557adeb4c6f885ea12`.

## Verification

The flashed firmware source passed the pre-flash gate with 107 assistant tests
and 137 port tests. After adding the final evidence validator, the complete
branch gate passed 107 assistant tests and 146 port tests (45 total skips for
platform/hardware-specific cases); its focused receiver-probe suite has 47
passing tests. The real ESP-IDF build passed, and esptool verified the written
app hash. Private raw UART streams and flash readbacks remain outside Git; only
hashes and selected decoded results are published.

The remaining physical preflight work is a compatible battery/power-system
check, correct propeller fitting, and a controlled open-area hover test. A
six-face accelerometer procedure remains an unperformed precision-calibration
improvement rather than a result inferred from one stationary pose.
