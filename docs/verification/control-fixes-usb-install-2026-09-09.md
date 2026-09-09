# LiteWing control fixes: USB installation and reset checks

## Result and scope

The reviewed PR29 receiver-freshness and PR30 thrust-control fixes are now
installed on the USB-connected LiteWing. The application passed a separate
flash digest comparison and two subsequent 30-second disarmed telemetry checks.
The existing settings were preserved. **Arming was not enabled.**

The user authorized flashing and separately authorized enabling arming, and
confirmed all four propellers removed with the battery absent. That authority
does not establish readiness. This session sent no receiver values, settings
writes, arming requests or motor commands. It does not accept receiver-loss
behavior, electrical output timing, powered operation or flight.

## Exact candidate and flash boundary

Source `d7b2d454aafced55d219f32deddd070822464e20` is the clean reviewed PR30
candidate, incorporating PR29. PR30 merged as
`6b0779d92f2525c1cc326437e268eee66c7117cd`. Pinned upstream source revisions and
ESP-IDF 5.3.2 are unchanged; the source/build evidence remains in the
[receiver-freshness](gcs-receiver-freshness-2026-09-09.md) and
[thrust-control](thrust-control-width-2026-09-09.md) reports.

- Application: 355,904 bytes, SHA-256
  `3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8`.
- ELF: SHA-256
  `a36fc6e6e65ef8ae4472c90a131f5fb2f5adf90ff7b1fb1cacb7a9339f778781`.
- Only application offset `0x10000` was written; erased application sectors
  were `0x10000..0x66fff`. Esptool 4.12.0 used 115200 baud and kept the image's
  flash mode, frequency and size parameters.
- Write-time verification passed. A separate `verify_flash` invocation then
  matched the exact staged application before reset to the application.

Before writing, the expected USB bridge identity/location and absence of
another serial owner were checked. Separate device comparisons matched the
previous PR25 application, bootloader and partition table. A fresh private
32 KiB settings backup at `0x110000` was read and separately verified.
After the application write, the unchanged bootloader, partition table and
pre-flash settings also passed separate comparisons.

A post-boot settings readback was separately verified and compared byte-for-byte
with the pre-flash copy and the prior PR25 post-reset snapshot. All have SHA-256
`c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a`.
No whole-chip erase, settings format, bootloader/partition rewrite, security
override or eFuse change occurred. The original private 8 MiB recovery backup
and previous application remain available; full recovery has not been tested.

## Observed telemetry

The existing private guarded diagnostic used 57600 baud. Its five outbound
allowlist tests passed before use. Each post-install run transmitted only
118 telemetry status/handshake frames and 364 allowed read requests, returned
zero with no guard failures, and closed the serial port. The second run reset
to the application after the post-boot settings readback.

The captures were decoded again offline against the pinned upstream XML
definitions, requiring exact payload sizes for decoded known data objects.
The parser can resynchronize/drop malformed data: these are checksum-valid
sample observations, **not lossless UART capture or continuous safety proof**.

| Capture | Bytes | Disarmed status samples | Samples with first four motor commands zero |
| --- | ---: | ---: | ---: |
| Before update | 120,534 | 29 | 58 |
| First boot after update | 119,663 | 29 | 57 |
| Subsequent hardware reset | 119,826 | 29 | 57 |

Capture SHA-256 values, respectively:

- `42d1533f1f07f458a48f662c116865f51a83b0cb36e407ae278ba0d873dccb83`
- `7065d64a5ddf3a61f0197d8bf577c195fe36f2707dc07766e0aaecccbcc07639`
- `24f4d68f2d57420691268ea0375c53e585de9acdeb7e4506f82e718bfed5a5dc`

Each capture contains 28 samples each of ManualControlSettings,
ActuatorSettings, MixerSettings, FlightModeSettings and HwSettings. Each object
has one unique payload within its capture, identical across all three captures.
All observed arming settings remain **Always Disarmed**. The first four actuator
minima/neutrals remain zero, maxima 1000 and MotorsSpinWhileArmed FALSE. Channels
5..12 in ActuatorCommand remain 1000; they are outside this board's four-motor
output mapping and must not be reported as actual motor duty.

ManualControlCommand remains Connected=False. Each capture includes one initial
zero-valued command sample (including Throttle/Thrust zero), followed by timeout
values for the five configured channels, unmapped values for the remaining
channels, and Throttle/Thrust -1. The two post-install captures each contain
147 samples: one initial, then 146 timeout/failsafe samples. It would be wrong
to claim every command sample already contained timeout values. No fresh
receiver input was sent, so no connected-to-disconnected transition was tested.
SystemSettings was not requested or received; these captures do not independently
establish its ThrustControl setting.

All three captures contain 58 SystemAlarms samples. The first reports
CPUOverload and Actuator Critical; subsequent 57 report both OK. Receiver
remains Warning and BootFault Uninitialised. This records the first observed
sample order, not precise firmware startup timing or an explanation of the
transitions. Those findings remain [issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27),
not an all-clear boot.

## Local verification and remaining gates

The current source tree's full host run passed **82 assistant + 111 port tests**,
with no skips, using the installed candidate's ELF, actual generated build graph
and pinned source inputs. The first run after switching to this documentation
branch failed two graph assertions because Ninja's dry run only printed
`Re-running CMake...`. Explicit ESP-IDF reconfiguration refreshed the graph;
the unchanged tests then passed. No test was relaxed, and no further image was
built or flashed by that refresh. Graph inspection of `flash` used `ninja -n`.

Next is a separately guarded, neutral-input receiver-loss bench test while
Always Disarmed. [Issue 23](https://github.com/ghostlyd/lrrk-air-mini/issues/23)
remains open: installing the freshness correction is not its physical acceptance.
Startup fault reporting (27), full-board storage-fault injection (26), measured
electrical shutdown latency (19), physical motor mapping, IMU orientation and
calibration, and a compatible battery/powered test remain separate unpassed
gates. No API key was accessed and no paid AI request was made in this session.

Raw captures, NVS, flash backups and private device identifiers remain local;
this report publishes only selected findings and content hashes.
