# Checked Attitude and Receiver startup

This extends the [checked module table](checked-module-startup-2026-09-09.md)
and [Actuator lifecycle work](actuator-startup-lifecycle-2026-09-09.md) into the
two selected input workers. It is source/build work only. No device/serial
opening, reset, flash, settings, arming, motor, credential or paid API action
is part of this change. The last recorded installed firmware remains Always
Disarmed; it has not been re-observed during this source-only work.

## Contract

Both initializers require usable existing objects or successful initialization
with usable handles. Attitude checks five selected objects; Receiver checks
seven. Each checks its two initialization subscriptions. Existing objects and
defaults are not reinitialized. Initialization and start are boot-caller-only,
one-shot APIs, not concurrent restart APIs. Premature start consumes neither
initialization nor startup. A failed attempt cannot be retried in the same boot.

Watchdog registration is checked in the serialized caller before task creation.
Creation failure returns through the real module table and stops later starts.
No watchdog flag rollback or retry is attempted. Workers register their own
current task handles before worker setup reads; the creator does not retain or
republish a handle that a worker may already have retired.

Worker startup failure latches PWM shutdown and raises BootFault Critical.
A worker that never registered deletes only itself. A registered worker first
unregisters; if that fails it parks without further input processing, preserving
a live task for the still-published monitor handle. It never deletes a task
while leaving that handle published. The fixture verifies these source-level
effects; it does not measure electrical PWM or watchdog cutoff.

`Start == 0` means task creation was accepted, **not worker readiness**. Worker
failure may happen before or after that return. It neither changes an already
accepted return into a module-table error nor rolls back other started tasks.
This change adds no BootFault OK and no global asynchronous-ready barrier.

### Attitude

- Checks the initial quaternion read and write.
- Allocates its sample buffer during initialization, before any task creation,
  and rejects null allocation. The module retains this static buffer until
  reboot, including after later startup failure.
- Checks the selected IMU driver test and queue before entering the sample loop.
  The target's `PIOS_INCLUDE_ICM20602` compatibility interface actually selects
  the repository's MPU6050 I2C driver, not a physical ICM20602.

The fixture selects board revision `0x02`, matching the target's board-info
structure, and reaches the first real sample receive boundary. This does not
establish valid samples, calibration, orientation, or runtime estimator health.

### Receiver

- Requires three AccessoryDesired instances before task creation. Existing
  instances are retained; only missing instances are allocated.
- Checks both returned instance ID and actual count growth. Source inspection
  of pinned `uavobjectmanager.c` shows that `UAVObjCreateInstance` can return the
  intended nonzero ID even when allocation fails. A nonzero result alone is
  insufficient. The consumer fixture models this behavior; it does not link
  the entire object manager or claim an allocator-level reproduction.
- Moves the explicit initial settings callback into the monitored worker and
  checks its initial ManualControlCommand and FlightStatus reads before the
  first periodic wait. A failed read stops this worker; no uninitialized local
  command/state enters its loop.

Successfully registered static callbacks, global objects, partial instance
allocations and the Attitude buffer are retained after later failure. They are
not transactionally rolled back. Other tasks can dispatch subscribed settings
callbacks, so monitor-before-worker-setup is **not a global callback barrier**.
Later settings reads and periodic input/estimator operations are not all checked
by this change.

## Verification boundary

The fixture compiles each entire adapted module with the actual target module
table, real generated UAVObjects, and (for Attitude) real coordinate-conversion
and delta-time code. The object store, subscriptions, RTOS, monitor, watchdog and
driver are controlled boundaries. Early/deferred worker execution is
deterministic, not a FreeRTOS scheduling or physical concurrency simulation.

The initial pre-adaptation fixture compiled and rejected 57 behavioral cases.
Permanent original-source controls reject 33 cases and 39 deliberate
gate-removal mutations retain the regression evidence; compile errors do not count as negative-control
success. The original Receiver's pre-existing enum/byte warning remains visible
but is not fatal only in the original-source compilation. Adapted test builds
retain `-Werror`; production warning policy is unchanged.

The focused suite passes 13 tests with 58 behavioral cases and both SDK checks,
without skips. Coverage includes each selected object and subscription failure, Attitude's
initial read/write/buffer, Receiver's instance allocation/count mismatch,
watchdog/task creation, monitor registration, initial sensor/read failures,
monitor cleanup failure, existing resources, ordering and repeat rejection.
Worker cleanup is checked with both early and deferred execution. Tests check
the exact subscription object/callback/mask tuples and require worker reads to
occur after monitor registration. Previous full runtime thrust/failsafe tests
are retained separately; they do not cover the new initializers.

Independent review found three fixture gaps in the initial candidate. Removing
either initial settings callback, replacing indefinite parking with one delay,
or hardcoding the smaller upstream fallback task depths escaped the tests. All
six escaped mutations and both SDK/fixture stack mismatches were independently
reproduced before correction. These were test gaps; the production calls,
parking loop and board stack constants were already present and unchanged.

The fixture now seeds distinguishable scale/90-degree-yaw settings and checks
their applied values and rotation at Attitude's first sample receive. Receiver's
controlled frame classifier returns Custom; a seeded TreatCustomCraftAs setting
must resolve to Ground before the first wait. This is synthetic settings-effect
coverage, not physical orientation or navigation evidence. A simulated parking
delay now returns once; a second safe wait is required while the task remains
live and monitored. A single-delay mutant reaches the forbidden deletion and
fails. Six permanent mutations cover these review findings.

The real ESP32-S3 compiler macro check confirms watchdog, quaternion and selected
IMU support, with advanced-feature exclusion disabled. RAW_SENSORS, ADXL345,
ADC, input LPF and USB RCTX branches are not selected by this target fixture.
Those optional paths and advanced navigation readiness are not established.
The input fixture consumes the real board header for stack/watchdog constants,
and compares numeric stack bytes with the actual SDK preprocessor: Attitude
4096 and Receiver 3072 bytes, or 1024/768 words at the module's task-create
boundary before the ESP32 shim converts back to bytes. This checks argument
parity, not runtime stack sufficiency. The original fixture incorrectly used
the 540/1152-byte upstream fallbacks; that mismatch is corrected.

The generated-build selection test first failed against the old graph because
it selected the unadapted Attitude source. CMake now selects both adapted inputs
and watches their upstream files, adapter helpers and startup fragment. Source
drift tests cover all three control modules and preserve all three existing
output files on input mismatch. This does not add general output-path alias or
filesystem transaction hardening to the generator.

The source CI explicitly runs the new suite after generating real objects. Its
two SDK-specific tests skip when no SDK graph is supplied; source-only CI must
not be treated as an ESP32-S3 build. Assistant tests remain offline.

### Pinned inputs

External checkouts and upstream license notices remain unchanged. The new
target-only adapter consumes complete SHA-256-checked source files:

| Module | SHA-256 |
| --- | --- |
| Attitude | `73386b3c3e73e1f3296937fd1bed6dbf0e91bf778dc86b67e0455ac0e166bd1f` |
| Receiver | `0a9395a6335524700ec7ded9993fb256e1058471b62ef71246a50b98dcee82f9` |

Receiver's prior thrust/failsafe adaptations and the existing Actuator adapter
are preserved. The full local suite passes **83 assistant + 239 port = 322
tests**, without skips, with pinned sources and SDK graph supplied. The
ESP-IDF 5.3.2 incremental build also passes.

## Retained private build — NOT INSTALLED

Production/test commit: `d0c15008aa7bd01274f0838035d42c24c692a26b`.
The clean-worktree incremental build reports version `d0c1500`; this is not
a clean-from-scratch build. Persistence linkage passes with UAVObjSave at
`0x4200c9e0`, UAVObjLoad at `0x4200ca64`, and UAVObjDelete at `0x4200a84c`.
The application fits the existing 1 MiB partition with 66% free. Existing
upstream unused-variable and CMake deprecation warnings remain; no production
warning suppression was added.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 358384 | `3c31fc39b529303063f3e40ca865f91bfde55224f7ec53070cbe99e1e7119d71` |
| ELF | 6666936 | `b3cff9671a9dd5de189d5a3c49f41144073d487f845185ab2fd91d75805baae9` |

Generated Attitude SHA-256:
`52fe8228107c53b509914d530dc6c723fe65dd38c89d546e7e5c26b2db733f97`.
Generated Receiver SHA-256:
`f76bcc891a4ea4963d7d4021175c8af6eb9b3a565e2af36c82e0164d715f79b6`.
Later report and test-only changes do not alter these retained bytes. Independent review
and exact final-revision CI results are recorded in the PR.

## Remaining gates

Stabilization/Telemetry internals, ManualControl's start-time subscriptions and
dispatch, full board/startup failure propagation, asynchronous readiness and
runtime sample validity remain unfinished. Issues
[19](https://github.com/ghostlyd/lrrk-air-mini/issues/19),
[26](https://github.com/ghostlyd/lrrk-air-mini/issues/26) and
[27](https://github.com/ghostlyd/lrrk-air-mini/issues/27) remain open.
No arming setting is changed. Physical cutoff timing, motor order, IMU
orientation/calibration, USB reset behavior and battery/charger/connector
verification remain separate. No battery is assumed available; fresh physical
props-off/power confirmation is required before further hardware I/O.
