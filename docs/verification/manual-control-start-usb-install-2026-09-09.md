# Checked ManualControl start: USB installation and runtime checks

## Result and scope

The application built from exact merged source
`b10009e6c6f0a4d070c38f531a0a9f30a99e5951` is installed on the
USB-connected LiteWing. The application passed write-time verification, a
separate four-region flash comparison and a full byte-for-byte readback.
Bootloader, partition table and persisted settings remained unchanged. A
bounded 30-second telemetry observation then found the board running,
Disarmed, configured Always Disarmed and producing changing finite IMU and
attitude values.

The user confirmed before device access that all four propellers were removed
and the battery was absent. The diagnostic sent no receiver values, settings
writes, arming requests or motor commands. This is USB bench evidence, **not
commanded motor-output, arming or flight clearance**.

## USB power-model correction

Battery absence does not make this hardware a logic-only or motor-de-energized
test article. A user-supplied copy of the
[LiteWing USB-C recording](https://x.com/d0tslash/status/2095720911743725618)
visibly shows the USB-C cable connected, the white battery connector empty and
the propellers rotating through successive positions. That behavioral evidence
invalidates the earlier schematic-only assumption that USB could not energize
the motor path.

Accordingly, this installation and observation are classified as an energized,
motor-capable bench session. Its controls were physical propeller removal,
containment, an observed Disarmed state, `Always Disarmed` configuration and
zero values on motor channels 1..4. Battery absence is recorded only as the
actual configuration; it is not used as a safety interlock.

## Exact merged candidate

ESP-IDF 5.3.2 and CMake/Ninja completed a clean 1,180-step ESP32-S3 build. The
application version was `b10009e`, and the application used `0x57c40` bytes of
the 1 MiB application partition, leaving `0xa83c0` bytes (66%) free. Strong
persistence symbols were present at `UAVObjSave=0x4200ca08`,
`UAVObjLoad=0x4200ca8c` and `UAVObjDelete=0x4200a874`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 359488 | `d7392031e9e06c39bcb503e0feb834942588b10b99cdfeeaa3248fbedae0ff31` |
| ELF | 6674868 | `65ec8c7f60cb3bccd6dfbe51f75f4ce6578b0b3db1ac7190cf8046f051e9f6b0` |
| Generated `manualcontrol.c` | 25741 | `cafa0f76f2b23d458c7db62256336ea1f77cc1b54d9bd379bebfabbf3472c00c` |

The generated ManualControl hash reproduces the reviewed
[start-lifecycle source](manual-control-start-lifecycle-2026-09-09.md). The
build used pinned NinjaPilot revision
`ac77304a58de6c8bd552f94668b46903adb71cb2` and ESP32 reference revision
`7233c97f844c0377930bcdf22998e289638b64c6`. The clean build's 22,944-byte
bootloader had SHA-256
`bf3aada74a811c739a12f60c24d4951397ba1ab581971fbdd050a6780eff4a7c`;
it differed from the installed bootloader and was not written. The generated
3,072-byte partition table matched the installed table at SHA-256
`a84ab9b6709ab8803191f08586451681c906dc441870525b44da907f9c142b51`,
but it was also excluded from the write.

The exact merged build passed all 275 port tests without skips and 83 offline
assistant tests with nine explicit optional OpenAI SDK/live-service skips. The
separate OpenAI SDK CI job had already passed as a required merge gate; no live
API or paid provider action was part of this firmware build or installation.

## Pre-write preservation gate

Immediately before writing, macOS exposed the expected WCH callout device and
no process owned it. Esptool 4.12.0 identified the ESP32-S3 revision v0.2. Fresh
private readbacks matched the prior installed baseline:

| Live region | Offset | Bytes | Pre-write SHA-256 |
| --- | ---: | ---: | --- |
| Bootloader | `0x0` | 22944 | `3d2d5b1543a2a27371bbd5521a9b1d9cbb3a4404ce0387cb77f8fa8d3156a11f` |
| Partition table | `0x8000` | 3072 | `a84ab9b6709ab8803191f08586451681c906dc441870525b44da907f9c142b51` |
| Previous application | `0x10000` | 359424 | `e0dab3285561113470eb4d3e19489bb4d56a785b8be617ba856e59951e94df9f` |
| Settings | `0x110000` | 32768 | `c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a` |

The board's unique hardware identifier and all raw recovery bytes remain
private.

## Application-only installation

At 115200 baud, only the reviewed application at offset `0x10000` was written.
Esptool preserved the flash mode, frequency and size, erased application
sectors `0x10000..0x67fff`, wrote all 359,488 bytes, verified the transfer hash
and hard-reset the board. No whole-chip erase, force option, eFuse change,
security override, bootloader write, partition-table write or settings write
occurred.

A separate `verify_flash` invocation then matched all four expected regions:

- the unchanged bootloader at `0x0`;
- the unchanged partition table at `0x8000`;
- the new application at `0x10000`; and
- the unchanged 32 KiB settings region at `0x110000`.

A fresh full application readback was byte-for-byte identical to the reviewed
candidate and reproduced SHA-256
`d7392031e9e06c39bcb503e0feb834942588b10b99cdfeeaa3248fbedae0ff31`.
Settings readbacks after installation and after the runtime observation were
both byte-for-byte identical to the pre-write copy and reproduced SHA-256
`c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a`.

## Guarded runtime observation

The private USB diagnostic's five outbound-allowlist tests passed immediately
before use: named object reads, telemetry handshake/status and protocol
acknowledgements were accepted; control/settings writes, non-allowlisted reads
and malformed frames were rejected before an OS write. An initial invocation
with the macOS system Python stopped before opening the device because its
optional serial module was absent; it captured zero bytes and transmitted
nothing. The allowlist tests then passed again under the dependency-complete,
pinned ESP-IDF Python environment before the one live observation.

At 57600 baud, the bounded probe transmitted 119 allowed telemetry
status/handshake frames and 364 named object requests. It sent no control or
settings packet, reported no runtime guard failure and released the serial
port. The private capture contains 120,601 bytes at SHA-256
`237f7b9dd90dafc4879a5570c7c8f4a04a72ca5a4ac0cc9e7d4389c1535eb763`.

Offline decoding used byte-verified source and XML from the pinned NinjaPilot
revision. It counted 2,673 complete checksum-valid object frames and produced
these sampled observations:

| Observation | Result |
| --- | --- |
| `FlightStatus` | 29 samples; every `Armed` value was `Disarmed` |
| `ActuatorCommand` | 58 samples; channels 1..4 were zero in every sample |
| `FlightModeSettings.Arming` | 28 samples; every value was `Always Disarmed` |
| `ManualControlCommand` | 148 samples; final state was disconnected with timeout channel values and throttle/thrust `-1` |
| `AttitudeState` | 749 finite samples; all 749 roll/pitch/yaw/quaternion vectors differed |
| `GyroState` | 30 finite, changing three-axis samples |
| `AccelState` | 30 finite, changing three-axis samples |

The first `SystemAlarms` sample reported CPUOverload and Actuator Critical; the
following 57 samples reported both OK. ManualControl and Stabilization remained
OK in all 58 samples. Receiver remained Warning and BootFault remained
Uninitialised in all 58 samples. This records decoded host receipt order, not
electrical startup timing or complete asynchronous readiness. The offline
parser can resynchronize past malformed bytes, so the result describes valid
sampled frames rather than a lossless UART recording.

The sampled ManualControl activity is consistent with the module running, but
it cannot exercise or prove its injected startup-failure branches on the live
board. Those paths remain source/host-test evidence; a successful boot is not a
substitute for fault injection.

## Remaining gates

This installation advances
[issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27), but does not
close it. BootFault remains Uninitialised, the first sampled CPUOverload and
Actuator alarms were Critical, and Receiver remains Warning with no receiver
input. Issues [19](https://github.com/ghostlyd/lrrk-air-mini/issues/19) and
[26](https://github.com/ghostlyd/lrrk-air-mini/issues/26) also remain open.

There is still no battery. Motor-corner mapping, IMU orientation/calibration,
battery/charger/connector acceptance, powered cutoff timing, receiver hardware
behavior and flight acceptance remain separate unpassed gates. Authorization
to arm or drive outputs does not establish any of them. USB-C is treated as a
live motor-power source throughout those gates. Arming therefore
remains `Always Disarmed`, and no motor-output or flight action was attempted.
