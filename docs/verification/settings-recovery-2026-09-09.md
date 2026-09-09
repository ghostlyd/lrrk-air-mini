# LiteWing settings recovery — 2026-09-09

## Scope

This change addresses [issue #22](https://github.com/ghostlyd/lrrk-air-mini/issues/22)
and the [confirmed persistence-linking diagnosis](settings-persistence-2026-09-09.md).
The baseline is `441aec6225ac11264cabd0e62940c3d2ce48d2b3`. Upstream flight,
reference and ESP-IDF pins are unchanged. No new flight mode, receiver protocol,
AI command sink or arming permission is introduced.

## Linkage and build gate

The existing target linker script now explicitly references
`uavobject_persistence_linked`, forcing the real persistence object out of the
archive. `verify_persistence_link.py` inspects the actual ELF using the target
`nm`: Save, Load and Delete must be distinct, nonzero, strong text symbols,
not aliases of the weak success stub; the real implementation anchor must be
present. Missing/duplicate symbols, failed inspection and non-ELF input fail.
The gate runs in default and direct application builds, including no-op
rebuilds; application generation and normal flash targets depend on it.
It proves the expected linkage, not complete storage correctness.

Before the linker fix, this gate rejected the actual previously flashed
artifact: all three functions resolved to the weak stub at `0x42032b14`.
After the fix, a real ESP32-S3 build using ESP-IDF 5.3.2 passed with separate
strong implementations. Host-only tests do not replace that artifact check.

Review also identified an inherited `UAVObjDelete` that ignored backend
erase/commit failure. The target renames only that unchecked upstream definition
at compile time and supplies an anchored, checked `UAVObjDelete` adapter.
External checkout contents are unchanged. Tests through the actual adapter and
NVS backend reproduce and correct false-success deletion, including already
absent success. The corrected ELF binds callers to the target adapter.

## Non-destructive storage and recovery

The target uses a GPL-3.0-or-later adaptation of the pinned reference NVS
backend, with attribution retained in the source and license inventory.
Automatic partition erasure on incompatible/full NVS and automatic key
deletion on object-size mismatch are removed. Explicit format/delete APIs
remain distinct operations; this boot path does not call them.

Object inspection distinguishes **confirmed absent**, **present with matching
layout**, and **error/incompatible**. Any object-load I/O or layout failure
latches storage unhealthy for the boot, including failures during automatic
UAVObject registration. A failed/partial blob read is staged and never copied
into live object memory. Missing objects alone do not set this fault.

The startup coordinator covers MixerSettings, ActuatorSettings and
ManualControlSettings:

1. Inspect all three before any writes; stop on errors or incompatible data.
2. Reload all existing objects before writing anything; preserve their values.
3. Apply the existing LiteWing defaults only to confirmed absent objects.
4. Check each save, confirm the object now exists with the expected layout,
   and reload it successfully. A no-op save returning success cannot pass.
5. Check the provisioning marker write/commit only after all objects are usable.

The marker is no longer the authority to skip object checks. This permits a
board with the old marker but missing blobs to recover without overwriting
other stored settings. Partial progress across an interrupted sequence is
allowed: the next boot preserves completed objects and retries absent ones.
This is **not an atomic transaction across three objects**, and it does not
claim power-cut durability from host tests. Invalid existing objects are not
silently replaced; explicit migration/recovery is required.

Storage/recovery failure sets BootFault Critical. After adapter initialization,
any latched board boot fault shuts down the brushed-output backend, whose
shutdown state requires reboot. Successful storage checks do not clear unrelated
alarms or enable GCS control. BootFault success reporting and the separate
[GCS input-age defect](https://github.com/ghostlyd/lrrk-air-mini/issues/23) remain
outside this correction.

## Verification boundaries

Regression tests reproduced the weak-link failure in the old real artifact and
the destructive storage behaviors in the pinned reference C backend before
correction. Native C tests exercise the adapted production backend with only
ESP-IDF NVS replaced, plus the actual recovery coordinator with controlled
storage callbacks. They cover absent/partial/existing objects, preserved values
across simulated volatile-state reset, each inspect/load/save/read-back failure,
no-op saves, commit failures, malformed storage, short/partial reads and
allocation failure. All eight presence combinations and retries following each
interrupted stage are exercised. Direct application/flash graph regressions
failed before dependency correction; flash graph inspection is dry-run only.

The host suite is also run with the real ELF and generated build graph
explicitly supplied to the artifact regressions. ESP-IDF's Python environment
lacks the optional AI SDK, so its build-wrapper run skips nine SDK tests; these
were exercised separately in the SDK environment. The ESP32-S3 build and
linkage gate passed. The authorized on-device recovery and reset round trip
for the exact corrected candidate are recorded below.

The final reviewed host run passed **82 assistant and 70 port tests**, with no
skipped tests in the SDK-equipped environment and real-artifact/graph checks
enabled. Independent focused re-review approved the restricted bench candidate
with no remaining critical or important findings. Full-board fault injection
using corrupt metadata or a nonessential settings object remains a follow-up;
source tracing is not a substitute for that end-to-end fault test.

## Authorized application flash and reset round trip

The user confirmed all four propellers removed and the battery absent before
bootloader access. The clean source revision
`aefaa95c12a43e221691079c5b8665aed0bbb40e` was rebuilt and checked after review.
The final host run again passed all 152 tests, without skips, with the committed
candidate's actual ELF and build graph supplied. GitHub host, SDK and source
checks passed before flashing.

- Application: 355,408 bytes, SHA-256
  `de7933ad67f970e015b95fb385f1a423302040b9ba808ab110bd8bcf738417c5`.
- ELF: SHA-256
  `7df25ae62a2fee69bd1d79c91db70076c99622390793caab096a3df3febc37c3`.
- Strong Save/Load/Delete addresses: `0x4200c5d4`, `0x4200c658`,
  `0x4200a68c`; the persistence-link gate passed.

The bootloader and partition table were byte-identical to the previously
verified candidate. Only the application at `0x10000` was written, at 115200
baud, preserving image flash parameters. The affected application sectors were
`0x10000..0x66fff`; no whole-chip or explicit settings-partition erase was
performed. Esptool verified the write, and a separate `verify_flash` command
matched the staged application's digest before another hardware reset.

The 32 KiB settings partition at `0x110000` was backed up privately and
separately verified before flashing. Following recovery, another readback was
separately verified against the device. A further hardware reset, telemetry
capture and second readback showed the recovered partition remained
byte-identical. The pre-recovery snapshot differs from both recovered copies:

| Private snapshot | SHA-256 |
| --- | --- |
| Before correction | `6872fa0af27fcb99090cf726c9b506aa5f7d0e3b5b77556545cb6bc5f69adda9` |
| After recovery | `c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a` |
| After subsequent reset | `c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a` |

Two 30-second captures at the application's 57600 baud were independently
decoded using the pinned upstream object definitions. Each contained 28
checksum-valid samples of each essential settings object and FlightModeSettings.
Every payload for each of these four objects was identical within and between
the two captures; this is a decoded-sample claim, not lossless-stream proof.

| Capture | Bytes | Disarmed samples | Samples with four zero motor commands | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| After recovery | 119,734 | 29 | 57 | `b2ffcae06b58f2054d0a8e50a43c8fabc1db05792e21579a1f4049846600ddaa` |
| After subsequent reset | 120,516 | 29 | 58 | `af1b11b36b68ff40638242af1590068339ff0b14693766195e6b7aa8056e152b` |

Observed settings now contain four Motor mixers with the target quad-X vectors
and a `[0, 0.25, 0.5, 0.75, 1]` throttle curve; the other mixers are Disabled.
The first four actuator minima/neutrals are zero and maxima 1000, with
MotorsSpinWhileArmed FALSE. The first five receiver groups are GCS with channel
numbers 1..5. FlightModeSettings remains **Always Disarmed**, with sanity checks
enabled. No receiver input was sent: configured channels read timeout `65535`
and Connected remains False. Command fields for unmapped channels 5..12 remain
1000; only the first four correspond to this board's brushed-output adapter.

Each capture has 58 SystemAlarms samples. The first reports CPUOverload and
Actuator Critical; the following 57 report both OK. Receiver remains Warning
and BootFault remains Uninitialised throughout. The early Critical samples
are not suppressed or presented as an all-clear boot. The root cause of those
early transitions and correct BootFault success reporting remain follow-ups.

The guarded diagnostic transmitted only telemetry handshake/status frames and
allowlisted read requests, with no failures. It sent no settings writes,
receiver values, arming requests or motor commands. Firmware boot recovery itself
performed the reviewed persistent writes. The serial port was closed after
each operation and the final readback ended with a hardware reset to the
application. These results establish this board's essential-settings recovery
and hardware-reset persistence, not power-removal durability, arbitrary stored
configuration preservation on real hardware, or physical fault-injection proof.

Retain the verified private full-flash backup; do not upload raw NVS, captures
or device identifiers. Subsequent flashes still require an exact reviewed
candidate and the props-off, battery-absent bench state.
Flight, physical motor mapping, sensor calibration, battery compatibility and
electrical shutdown timing remain separate unpassed gates.
