# Callback scheduler: checked startup and owned-resource cleanup

## Disposition

Source-tested and built, **not installed**. This is a bounded continuation of
the [startup services correction](startup-service-failures-2026-09-09.md), under
[issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27). It does not close
the complete boot-readiness gate or authorize a change to Always Disarmed.
No serial/device access, reset, flash, settings, arming, motor command,
credential access or paid AI request occurred during this work.

## Corrected behavior

- Failed scheduler registration releases its unpublished callback, task and
  binary semaphore allocations. Existing published callbacks remain owned by
  the scheduler and are not freed out from under callers.
- Scheduler startup checks each worker creation and task-monitor registration.
  On failure, it unregisters its successfully registered worker monitor slots
  and deletes all workers from that batch before releasing the scheduler mutex.
  It returns an error and cannot retry in the same initialization lifetime.
  Later callback registration is rejected after failed startup.
- New workers cannot invoke a callback while startup holds the recursive
  scheduler mutex. Previously queued callbacks remain pending for successful
  startup; the failed batch does not execute them.
- A callback registered before startup may increase its shared worker's stack.
  Once that worker runs, a request exceeding its fixed stack is rejected.
  Successful smaller late registration and new-worker registration still run;
  failed late registration preserves existing workers and callbacks.
- The real System task consumes a scheduler-start error: it calls the target
  PWM shutdown latch, sets BootFault Critical and deletes itself before normal
  persistence/settings callback connection and monitoring-loop work. It does
  not clear BootFault, retry startup or automatically reset the board.

Original task priorities, callback loop/dispatch/scheduling algorithms and the
ESP32 task shim's stack-word-to-byte conversion are unchanged. Worker monitor
registration retains upstream's first-four-worker slot convention; this does
not add monitoring capacity or validate all required tasks.

## Source and build boundary

`prepare_scheduler.py` checks both complete source hashes before applying
exact replacements to build-directory copies. Upstream GPL notices remain.
It rejects output within/above the input tree, escaping resolved input paths,
and aliased output files before writes; unchanged outputs keep their mtimes.
These are trusted-workspace checks, not atomic writes against a concurrent
filesystem adversary. The external pinned trees are not modified.

NinjaPilot commit: `ac77304a58de6c8bd552f94668b46903adb71cb2`.
ESP32 reference commit: `7233c97f844c0377930bcdf22998e289638b64c6`.

| Input relative to NinjaPilot `flight/` | SHA-256 |
| --- | --- |
| `pios/common/pios_callbackscheduler.c` | `db96ab58cee5988f405980570de631da5626cd8df71654fb4aabc754cb87c01b` |
| `modules/System/systemmod.c` | `9ec818dcdf55e33d99e005ca618b07abdd365e9e5bcb280cabbeb45f16d2a150` |

CMake selects only the two adapted sources and registers both generators,
both original C inputs and both replacement fragments as reconfiguration
dependencies. The actual generated firmware graph is tested for those edges
and exact source selections. Its regression test failed for both old source
selections and five absent dependencies before integration, then passed.

## Executed evidence and limits

The 15 focused test methods cover preparation, scheduler lifecycle and the
System consumer. Host compilation uses complete real C implementations, with
generated object declarations, rather than copied-out startup functions.

- Scheduler faults: mutex, task allocation, binary signal, callback allocation,
  first/second worker creation and first/second monitor registration. Resource
  ownership checks reject invalid frees/deletes, invalid monitor handles,
  leftover workers or registrations, held locks and premature callbacks.
- Nominal cases: pending callback delivery and redispatch, larger pre-start
  stack, smaller late callback sharing an existing worker, and a new late
  worker. Late allocation/task/monitor failure leaves the original worker usable.
- The RTOS boundary immediately invokes newly created workers until they block.
  This exercises the real scheduler mutex gate and callback loop, but is a
  deterministic single-thread fixture, not actual FreeRTOS timing or multicore
  execution. Host stack-watermark writes are disabled with `USE_SIM_POSIX`;
  the production stack instrumentation is unchanged and not proven by this test.
- System tests link the complete adapted scheduler and actual System module.
  Other modules, object storage, alarm writes, PWM shutdown and RTOS remain
  controlled boundaries. Failure requires shutdown before the Critical alarm,
  no later boot connections, and no remaining scheduler workers. Nominal
  startup reaches the first monitoring-loop entry and delivers pending work;
  this does not exercise the entire monitoring loop or whole-board boot.
- Permanent negative controls compile the original scheduler (ten behavioral
  scenario failures) and the original System caller with the corrected scheduler
  (two failures). Compiler failures alone cannot satisfy these controls.
- Full local host gates: **83 assistant + 198 port = 281 tests, no skips**,
  with both pinned trees, generated UAVObjects, optional AI SDK, real firmware
  ELF and build graph supplied. AI tests use offline fixtures, not live API calls.

The first target build exposed the original System file's relative header
include. The adapter now uses the pinned public header via the existing include
path. The adapted host test uses that same header path without a staged header
copy. The original-source negative control alone retains its relative layout.

CI runs the focused source tests after pinned object generation. The real
build-graph check intentionally skips there without an SDK graph; default host
jobs also skip external-source fixtures. CI host checks are not an ESP32 build.

## Artifact provenance

Clean production/test commit: `e42b5325eb88f0e8e9b55434724811c994f2585c`.
ESP-IDF 5.3.2 / ESP32-S3 incremental build reported version `e42b532` and passed
the real persistence linker and application partition gates. Earlier builds
compiled both new C copies. This is not a clean-from-scratch build. The existing
ISR wake-pointer type warning and CMake deprecation warning remain; no new
production warning suppression was added.

| Retained private artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application bin | 356624 | `ba4a6c1ddf65367752f0bc8813331fa33228378cba84d34d80a16c93fdaba67e` |
| ELF | 6653748 | `62524159ebc943cb0032ad2c44bc01f75b91d770b3c0cbfc1b54dcbe4eb59292` |

The application fits the existing 1 MiB partition. These artifacts are **not
installed**; no application, bootloader, partition, NVS or eFuse bytes changed
on the device. Later documentation-only commits do not rebuild these artifacts.

## Review and integration

Independent review of `830e7c1` through `e42b532`, plus documentation `228f224`,
found no Critical or Important findings and independently passed all 15 focused
tests, including the generated graph check. The full-suite/build/artifact
observations above are parent-executed, not independently repeated by that review.
GitHub checks are recorded on [PR 37](https://github.com/ghostlyd/lrrk-air-mini/pull/37);
merge requires their acceptance and does not establish physical readiness.

One nonblocking Minor finding remains within issue 27: the new System failure
path deletes its task without retiring System's own monitor slot. The selected
configuration has no surviving consumer enumerating that slot after System
stops, but its handle becomes stale. The System fixture does not model that
slot's lifetime. Correcting this must coordinate task creation, registration
and self-deletion: System may run before its creator registers it, so merely
adding an unregister call is insufficient. This is explicitly deferred to the
System/module startup lifecycle slice, not counted as completed validation.

The [subsequent System lifecycle correction](system-task-lifecycle-2026-09-09.md)
addresses that specific finding with self-registration and owned retirement.
Its source/build evidence remains separate from installation and full startup.

## Remaining readiness gates

System-task creation itself, required module initializer/start returns, their
internal object/queue/task failures, COM allocations, task-monitor initialization,
debug-log setup and complete watchdog subscription still need validation.
This slice does not make all allocation failures safe or report BootFault OK.
Runtime warm-up/missing-sample validity, electrical cutoff, physical motor order,
IMU orientation/calibration, reset-free USB opening, and verified battery/charger
connector polarity remain separate. No battery is assumed available. Fresh
physical confirmation is required before further device I/O.
