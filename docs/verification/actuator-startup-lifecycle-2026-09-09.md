# Checked Actuator startup lifecycle

This extends the [checked module table](checked-module-startup-2026-09-09.md)
into Actuator's actual initializer and worker. It is source/build work only:
installed Always Disarmed firmware is unchanged. No serial/device opening,
reset, flashing, settings, arming, motors, credentials or paid API calls occurred.
[Issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27) remains unfinished.

## Corrected behavior

- Seven required objects in the selected target configuration must exist or
  initialize successfully with usable handles: ActuatorSettings, MixerSettings,
  ActuatorDesired, AccessoryDesired, ActuatorCommand, VtolPathFollowerSettings,
  SystemSettings. Existing handles/defaults are not reinitialized.
- All four initialization callbacks are checked. They reference static code
  and global objects, so successful subscriptions remain valid after a later
  failure; they are not transactionally disconnected.
- The input queue is allocated and published last. Allocation failure never
  attempts a null-queue subscription. Failed subscription frees only the
  unpublished queue. The pinned object manager allocates before linking a new
  subscription, so its error does not leave a published reference.
- Start requires successful initialization and permits only one attempt.
  Initialization also permits one attempt; premature start consumes neither.
  These are boot-caller-only APIs, not concurrent/restart APIs.
- Watchdog flag registration is checked in the serialized startup caller
  **before** task creation. A duplicate flag or failed task creation returns
  an error through the real module table and stops later module starts.
  There is no watchdog flag rollback/retry after task creation fails.
- The task registers its own current handle before its initial settings
  callbacks and output setup. Failed monitor registration latches PWM shutdown,
  raises BootFault Critical, and deletes only the unregistered current task.
  The creator never republishes a retired worker's handle. Connected queues
  stay allocated until reboot, including when task/monitor startup fails.

Successful `ActuatorStart` means task creation was accepted, **not that the
worker ran or is ready**. Monitor failure can occur before or after that call
returns; its asynchronous fault does not roll back other module tasks or turn
an already accepted start result into an error. No BootFault OK is added.

The existing callback system, later settings reads, runtime outputs and
watchdog supervisor internals are not comprehensively repaired here. In
particular, subscribed settings callbacks can be dispatched by other tasks;
the worker's monitor-before-setup check is not a global callback barrier.
This change is not proof of electrical zero during partial startup or measured
watchdog cutoff latency.

## Verification

The host fixture compiles the entire adapted Actuator and the actual target
module table with real generated UAVObject code. Other module entry points,
object storage/event subscriptions, RTOS calls, monitor/watchdog and hardware
boundaries are controlled. Early/deferred execution is deterministic, not a
FreeRTOS concurrency simulation. Tests reach the first queue wait on the
nominal path; the earlier full runtime thrust/failsafe tests remain separate.

The first test run compiled successfully and failed 22 behavioral cases before
the production change. Permanent original-source controls reject the same
22 cases. Nine deliberate mutations catch ignored task/watchdog/monitor
results, missing queue cleanup or fault shutdown/alarm, repeated initialization
or start, and start before initialization. Compile errors cannot satisfy a
negative control. Resource failure coverage includes each of seven object
registrations, four callback subscriptions, queue allocation/connection,
watchdog/task creation and early/deferred monitor registration.

The actual ESP32-S3 compiler's preprocessor output confirms watchdog support
and advanced-feature paths are enabled, while DIAG_MIXERSTATUS is not. A test
checks parity with the lifecycle fixture, and another checks actual generated
Actuator selection plus the startup fragment's CMake dependency. The optional
diagnostic MixerStatus branch is checked in source but is not exercised by this
selected-configuration fixture. Advanced navigation readiness is not implied.

Local full verification passes **83 assistant + 226 port = 309 tests**, no
skips, with pinned sources and the SDK build graph provided. Assistant tests
are offline. The source CI's existing `test_thrust_*.py` discovery includes the
new lifecycle suite; CI without an SDK graph skips the two SDK-specific checks
and is not evidence of an ESP32-S3 build.

The generator retains the upstream source SHA-256 check
`4c5d155937f4f61e482cad7e7121d417574aba8d3f360994d763f061e497b9e7`
and the prior thrust/failsafe adaptations. External source checkouts and GPL
notices remain unchanged. ESP-IDF 5.3.2 incremental build, persistence linkage
and partition sizing passed; this is not a clean-from-scratch build.

## Retained private build — NOT INSTALLED

Production/test commit: `aad9403e503dae760eef211f002ed8430d8bbad2`.
The incremental build reports version `aad9403`. Persistence linkage passes
with UAVObjSave at `0x4200c9d0`, UAVObjLoad at `0x4200ca54`, and UAVObjDelete
at `0x4200a83c`. The application fits the existing 1 MiB partition with 66%
free. Existing upstream and CMake deprecation warnings remain; no production
warning suppression was added.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 357664 | `6fa18e51ae430b511cab58da7dea0879cf66df348cddc34d05cf78bf495ba146` |
| ELF | 6661504 | `5d667bf402fd92b45e8e9109178276bf81c26b526df1e098cefdaf33243e346a` |

Generated Actuator SHA-256:
`ee153e215b6441827fd70e3e31399e155001ab4c8a3cb3e844d4cc3edf2c2520`.
Later report changes do not alter these retained bytes. Independent review
and exact final-revision CI results are recorded in the PR.

## Remaining gates

Attitude, Stabilization, Receiver and Telemetry internals, ManualControl's
start-time connections, board startup services and runtime sample validity
still need work. Issues [19](https://github.com/ghostlyd/lrrk-air-mini/issues/19),
[26](https://github.com/ghostlyd/lrrk-air-mini/issues/26) and
[27](https://github.com/ghostlyd/lrrk-air-mini/issues/27) remain open.
Physical motor-cut timing, motor order, IMU orientation/calibration, USB reset
behavior and a verified battery/charger/connector combination are separate
gates. No battery is assumed available. Obtain fresh props-off/power
confirmation before new hardware I/O; source/build success is not arming
clearance.
