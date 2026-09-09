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
linkage gate passed. This report does not yet establish an on-device recovery
or physical reboot round trip for the corrected image.

The final reviewed host run passed **82 assistant and 70 port tests**, with no
skipped tests in the SDK-equipped environment and real-artifact/graph checks
enabled. Independent focused re-review approved the restricted bench candidate
with no remaining critical or important findings. Full-board fault injection
using corrupt metadata or a nonessential settings object remains a follow-up;
source tracing is not a substitute for that end-to-end fault test.

Retain the verified private full-flash backup; do not upload raw NVS, captures
or device identifiers. Before a further authorized USB-only flash, review the
exact candidate and keep the battery absent and all propellers removed.
Flight, physical motor mapping, sensor calibration, battery compatibility and
electrical shutdown timing remain separate unpassed gates.
