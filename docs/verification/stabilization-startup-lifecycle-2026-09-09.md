# Checked Stabilization startup lifecycle — 2026-09-09

This source/build-only change extends the
[four-axis storage correction](stabilization-storage-2026-09-09.md) through the
selected Stabilization module's synchronous initialization and start paths. It
does not install firmware, change settings, enable arming, drive a motor or
claim asynchronous readiness. The last recorded installed firmware remains
Always Disarmed and was not re-observed during this work.

Subsequent status: after this source report merged, the exact merge application
was [installed and observed over USB](stabilization-startup-usb-install-2026-09-09.md).
The statements below retain the boundary at the time this source-only evidence
was collected.

## Synchronous contract

`StabilizationInitialize` is now a one-shot operation. It accepts usable
existing objects without reinitializing them and otherwise requires successful
registration plus a usable handle for eleven objects. It also checks the sine
lookup initialization and propagates failures from both checked control loops.
The resources-ready state is published only after all of those steps complete.

The outer loop checks six objects, its callback-scheduler allocation and its
Attitude subscription. The inner loop checks seven unique objects, its
scheduler allocation, its Gyro subscription and its first failsafe schedule.
The scheduler API reports `1` when a fresh callback acquires that schedule;
`0` and `2` describe an existing schedule and are rejected during first
initialization. The duplicate upstream `ActuatorDesiredInitialize` call is
removed from the generated inner loop.

`StabilizationStart` rejects premature and repeated calls. In order it:

1. consumes its one-shot start attempt;
2. checks watchdog registration;
3. checks eight exact object/callback subscriptions; and
4. applies settings, desired modes, the selected bank and flight-mode state.

Subscriptions are installed before initial application so a concurrent update
cannot be lost between the initial read and connection. Initial application
checks complete-object reads and writes for Stabilization settings, desired
state, status, manual control, bank settings and the active bank. This replaces
void-return field getters only where failure propagation is required. A
callback notes an application failure only while the serialized initial apply
is in progress; later runtime callback behavior is not turned into a false
synchronous start result.

A failed initialization or start is not retried during the same boot. Objects,
subscriptions, scheduler records and watchdog state that were established
before a later failure are retained; there is no unsupported transactional
rollback. The existing checked module table stops later initialization or
start on a nonzero result, and the System caller retains its output-shutdown and
BootFault Critical path. This is fail-closed source behavior, not measured
electrical output evidence.

`Start == 0` establishes only that these synchronous resources and initial
reads completed. It does not establish callback-worker health, estimator
validity, calibrated sensors, safe gains, BootFault success, electrical cutoff
timing or flight readiness.

## Source and build boundary

The external NinjaPilot checkout remains read-only. The generator validates all
three complete inputs before writing any output:

| Source | Pinned SHA-256 |
| --- | --- |
| `stabilization.c` | `0bf808ebe597aa76abefbe026e1d40ade38ec2fe5645400aac7ea6cd2b347918` |
| `outerloop.c` | `a89228f3c6a3700cccb41b35bcf886672e901c6b18c6c851f11fcbeeaa9bb314` |
| `innerloop.c` | `9de7fe11cba25a25e226414471d10001824c07e5345cfcfe763960a2eae0d1b9` |

Input symlink escapes, changed or missing inputs, source/output ancestry and
each symlink, hardlink or nonregular output are rejected before any file is
written. Re-running against the same inputs is byte-idempotent. CMake now
selects all three generated sources and watches the generator, startup helper
and three upstream files for graph regeneration.

The generated source retains the target's existing four-axis bounds and packed
quaternion corrections. It still rejects simulator and Revolution feature
selection so the direct-thrust target semantics cannot silently change.

## Verification

The red phase established that the old generator failed twelve multi-input and
output-transaction cases plus one setup case, that the outer and inner checked
entry points did not exist, and that the unadapted top-level source failed all
checked lifecycle scenarios. Permanent original-source controls reject all 33
top-level lifecycle cases. Twenty-six deliberate startup-check removals cover
object, scheduler, initial schedule, watchdog, subscription, initial-state,
resource-ready, ordering and one-shot behavior. Compile failures do not count
as negative-control success.

The focused suites cover:

- every selected object registration failure and existing-object path;
- both loop scheduler allocations and exact subscriptions;
- the fresh inner-loop schedule result;
- all eight top-level subscriptions and watchdog ordering;
- every initial state read/write failure used by startup;
- premature, failed, successful and repeated lifecycle calls;
- generator drift, alias, no-partial-write and idempotence properties; and
- the retained four-axis sanitizer and packed-member checks.

With the pinned external trees and the real ESP-IDF graph supplied, all 30
focused tests pass without skips. The complete local gate passes **83 assistant
+ 269 port = 352 tests**, without skips. The source CI explicitly runs the new
inner-loop and top-level suites after generating real UAVObjects. CI without an
ESP-IDF graph still reports the SDK-only checks as skipped and is not firmware
build evidence.

An ESP-IDF 5.3.2 incremental build of implementation commit
`65a7106676b668d7d37d2dd37c041f35649efb83` passes after graph regeneration.
The compiler builds all three generated sources. Persistence linkage passes at
`UAVObjSave=0x4200c9fc`, `UAVObjLoad=0x4200ca80` and
`UAVObjDelete=0x4200a868`. The application occupies `0x57c00` bytes and leaves
`0xa8400` bytes (66%) free in the 1 MiB app partition.

## Retained private build — NOT INSTALLED

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 359424 | `e0ea5b4d988dc40439f1e114cda87227a68c92bdbf2b364289f7232523fa66f0` |
| ELF | 6674800 | `eb22e80ee761218acaf5bdec04036605946744164c597ec5e103e6e807393c13` |
| Generated `stabilization.c` | 21459 | `326ba723066c0904585a42c24a8f51468cfd0da1f85853ff547a03ff1fe6eb97` |
| Generated `outerloop.c` | 19195 | `49ad62540b32c808f71bfb0be056b40a15b6e7ef0116791977a70126049fd3d7` |
| Generated `innerloop.c` | 25211 | `984ff82497e23df51a153ffd1c3cd7b5375cb46da893a918e32b5613759ff66a` |

The build printed flashing commands as normal ESP-IDF guidance; none was run.

## Read-only device baseline

After explicit authorization, macOS observed `/dev/cu.wchusbserial410` and
`/dev/tty.wchusbserial410` with read/write permissions. IORegistry still
reported decimal vendor/product `6790:29986` (`1A86:7522`), and no other process
owned the callout device.

Esptool 4.12.0 then opened the port at 115200 baud for read-only baseline work.
The live ESP32-S3 revision v0.2 bootloader, partition table and installed
application each passed a separate digest comparison against the prior approved
candidate. A fresh 32 KiB settings image was read from `0x110000`, separately
verified against flash, stored privately with mode 0600 and byte-matched the
previous snapshot at SHA-256
`c886cec93e0b5c383e6382ef478570487dde31e6d95f02c34698a6eeca9a6f7a`.
Private files and unique identifiers remain local.

Those three operations each hard-reset the USB-powered board after completion.
No erase, flash write, settings write, monitor, telemetry request, motor or
arming command was issued. The new application above remains **not installed**.

## Remaining gates

The user's authorization makes future bounded device work permissible; it is
not evidence that a gate passed. There is still no battery. Issues
[19](https://github.com/ghostlyd/lrrk-air-mini/issues/19),
[26](https://github.com/ghostlyd/lrrk-air-mini/issues/26) and
[27](https://github.com/ghostlyd/lrrk-air-mini/issues/27) remain open for the
physical cutoff, storage/output inhibit and complete startup/BootFault work.
Telemetry startup internals, integrated asynchronous readiness, motor-corner
order, IMU orientation/calibration, battery/charger/connector selection and
physical flight acceptance remain separate. A fresh props-off, battery/power
and exact-artifact confirmation is required before future hardware I/O.
