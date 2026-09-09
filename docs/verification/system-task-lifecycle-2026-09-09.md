# System task: checked resources and owned monitor lifetime

## Scope

This source-only follow-up to [PR 37's scheduler correction](callback-scheduler-startup-2026-09-09.md)
addresses System's task-creation result and the review finding about its stale
monitor handle. It also connects synchronous System initialization errors to
the actual ESP-IDF entry point. It is tested and built, **not installed**.

No serial/device opening, reset, flash, settings, arming, motor, credential or
paid API action occurred. Installed firmware and Always Disarmed remain unchanged.
[Issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27) remains open for
the wider boot contract, not merely this task's lifecycle.

## Ownership and error behavior

- System initialization is a single boot-caller attempt. Missing required
  SystemSettings, SystemStats, FlightStatus and ObjectPersistence objects must
  initialize successfully and return usable handles. Existing handles are
  preserved without reinitializing objects. Objects already registered globally
  are not freed when a later prerequisite fails.
- Queue allocation is checked. Task creation is checked. If task creation
  fails, the creator deletes its unpublished persistence queue and returns an
  error. The entry point now consumes that error, latches PWM shutdown, reports
  BootFault Critical and returns without claiming startup was requested.
- On successful task creation, System owns the queue. It registers its own
  current handle before starting other modules. There is no creator-side
  handle registration or write-back, so a task that stops before creation
  returns cannot be re-registered afterward as a dangling handle.
- Failed self-registration stops before module start. Failed scheduler start
  stops before System connects its queue or callbacks. Both paths latch PWM
  shutdown and report BootFault Critical, then release the unpublished queue.
  An owned monitor slot is retired before System deletes itself.
- If the monitor refuses retirement, System remains alive and parked with
  outputs latched off. It must not delete a still-published handle or resume
  startup after a delay/wakeup. The selected real monitor normally accepts
  retirement after successful registration; the refusal case is fault injection.
- Repeated System initialize/start calls cannot allocate another set of
  resources, reset a live task's error flags or retry a failed initialization.
  These are **boot-caller-only entry points**, not concurrent start APIs.

A zero initializer result means task creation was accepted, not that the task
has completed asynchronous startup. It may not have run yet—or may already
have reported an asynchronous fault. No BootFault OK publication is added.
The original priorities and stack-word-to-byte shim are unchanged.

## Source boundary

The existing hash-checked generator still verifies both complete pinned
scheduler/System inputs before writing target-only copies; upstream GPL
notices and the external source trees remain unchanged. The source pins and
path-alias protections are those in the [scheduler report](callback-scheduler-startup-2026-09-09.md#source-and-build-boundary).
The new `system_start.inc` fragment is a CMake configure dependency. Its graph
assertion failed before integration and passed after the real build regenerated.
The scheduler's production implementation is otherwise unchanged from PR 37.

## Executed tests

The System suite now has nine test methods. It compiles the complete real
System module, adapted scheduler and actual target entry point. Object storage
and registration, task-monitor storage, other module starts, PWM/alarm effects,
board state and RTOS operations are controlled boundaries. This is not an
entire board boot, physical cutoff measurement or actual FreeRTOS scheduling.

Initial regressions produced 23 failing lifecycle scenarios: required object
initialization and missing handles, queue/task errors, early/deferred execution,
monitor ownership and repeated entry. The entry-point integration then exposed
four ignored-error cases. Each was observed failing before its production fix.
Nominal paths include existing and newly registered objects, immediate and
deferred task execution, the first monitoring-loop entry and a real queued
scheduler callback. The fixture checks resource ownership, registration of
only live handles, no delete with an owned monitor slot, and queue cleanup.

Seven permanent mutations must fail behavioral assertions: creator-side late
registration, omitted monitor retirement, leaked queue after failed task
creation, ignored entry-point error, repeated initialization, ignored monitor
registration failure and falling through after only one parked delay. Compiler
errors alone cannot satisfy these controls. The single-delay mutation initially
escaped the fixture; allowing two simulated delay returns before stopping on
the third made that faulty variant fail while the real parking loop passed.
The original System/scheduler negative controls from PR 37 remain in place.

Full local host gates passed with both pinned trees, generated objects, optional
AI SDK, actual ELF and firmware graph: **83 assistant + 204 port = 287 tests,
no skips**. AI tests were offline. The existing CI source job automatically
includes the expanded System suite; its graph test skips without an SDK graph,
and default CI host jobs skip external-input-dependent fixtures. CI host tests
are not a target build.

## Retained build

Clean production/test commit: `43134492c9f29313d987f9f6a8b35bd9e2df072d`.
ESP-IDF 5.3.2 / ESP32-S3 incremental build reported `4313449`, passed the real
persistence linker check and fit the existing 1 MiB application partition.
This was not a clean-from-scratch build. Existing upstream compiler warnings
and the CMake deprecation warning are not resolved; no new production warning
suppression was introduced.

| Private, uninstalled artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 356944 | `55d23dc3eb9b18fe48537d765260bff38442cf54a75773d034b3d5472781fe1e` |
| ELF | 6656220 | `3e469f42ca6e5bfe6618ecae2be46273f15355e1631f7a5f33da948c24911bd7` |

Generated System source SHA-256:
`d361628d5f1f8c34f6b57cbfc8f62ac043b1abe3fc6d4bb5a94f39350cbd2e27`.
Later documentation commits do not change these retained artifact bytes.
Independent review and remote CI are pending at this report's first revision.

## Remaining gates

Subsequent work checks the table and ManualControl initialization path in the
[module startup report](checked-module-startup-2026-09-09.md). The following is
the remaining-gate snapshot at this report's original revision.

The void InitMods table still ignores required module initializer/start returns.
Those modules' internal object/queue/task failures, COM allocations, task-monitor
initialization, debug-log setup and watchdog subscription need validation.
The existing System `mallocFailed` reset branch, later connection/read failures,
optional diagnostic configurations and full monitoring loop are outside these
tests. Runtime warm-up/missing-sample validity also remains unresolved.

Electrical cutoff, motor order, IMU orientation/calibration, USB-reset behavior,
and a verified battery/charger/connector-polarity combination remain separate
physical gates. A battery is not assumed available. Fresh props-off and power
confirmation is required before new hardware I/O. Neither build success nor
these source regressions enable arming or establish flight readiness.
