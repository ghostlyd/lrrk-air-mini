# Checked module startup and ManualControl resources

This follows the [System lifecycle correction](system-task-lifecycle-2026-09-09.md).
It is source/build work, **not installed firmware or arming clearance**.
[Issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27) remains unfinished.
No device/serial opening, reset, flash, settings, arming, motor, credentials or
paid API action occurred. Installed Always Disarmed firmware is unchanged.

## Failure path corrected

The explicit module table discarded all initialization/start results and used
unsigned declarations for signed upstream functions. Its checked target-only
entry points now retain the order Attitude, Stabilization, Actuator, Receiver,
ManualControl, Telemetry and return the first nonzero result without calling
later modules. Initialization and start each permit one attempt; start requires
successful initialization. A premature start is rejected without consuming
the still-available initialization attempt. These are boot-caller APIs, not
concurrent lifecycle APIs or automatic retry machinery.

The actual ESP-IDF entry point consumes initialization errors with PWM shutdown
and BootFault Critical, before creating System. The actual generated System
consumes start errors through its existing owned queue/monitor cleanup before
starting the callback scheduler or making its normal queue connections.
Already-started module tasks are **not** transactionally rolled back or deleted;
their resources remain owned, and the output shutdown latch is asserted.
This is not evidence that every task has started successfully or that all
actuator outputs remained electrically zero during partial startup.

All selected upstream module functions originally returned success even when
some internal operations failed. Checking their return values alone would not
repair that. This change also checks the real ManualControl initializer's six
required objects and scheduler callback registration. Existing object handles
are preserved without duplicate initialization (which normally returns -2).
A missing object must initialize successfully and return a usable handle.
Objects already registered globally are not deleted after a later failure.
The real scheduler retains its existing ownership/cleanup behavior when new
worker, callback-info or semaphore allocation fails.

ManualControl's runtime handlers, start-time connections and dispatch behavior
are unchanged. Advanced-feature configurations are not validated here; the
selected target defines PIOS_EXCLUDE_ADVANCED_FEATURES. No BootFault OK is added.

## Evidence and limits

- The original table failed 12 injected module-error cases. Tests now cover
  all six initialization/start failures with both early and deferred System
  task execution, plus nominal startup and forbidden ordering/repeats.
- Complete ManualControl, actual table/entry, and the real scheduler are linked
  together. Its initial 15 resource-failure cases failed before the fix; the
  permanent original-source control now rejects 16 cases including a shared
  scheduler worker. Existing-object and fresh-object nominal paths pass.
- Six deliberate mutations catch discarded table errors, ignored errors in
  either consumer, repeated initialization/start and start before initialization.
  Existing System/scheduler negative controls remain. Compiler failures alone
  cannot satisfy the controls.
- The focused scheduler/System suite passes 28 tests with no skips, including
  the real firmware graph. The full local host run passes 83 assistant + 211
  port = 294 tests with no skips. AI tests are offline. Final revision checks
  and independent review are recorded in the PR, not inferred from this report.
- Objects, other module entry points, RTOS and hardware are controlled host
  boundaries. ManualControl handlers are expected not to execute in these
  initializer tests. This is not a complete board boot, flight-controller test,
  physical cutoff measurement or real FreeRTOS scheduling proof.

The hash-checked generator verifies the complete ManualControl input SHA-256
`9526b9c0058b3727b8e268791cb0049dd7b830ec7d967ee6703fab67b80dc31f`
alongside its existing scheduler/System pins. External trees and GPL notices
are preserved. Drift and file/directory/symlink/hardlink protection tests cover
all three sources. CMake selects/watches the adapted ManualControl copy;
selection and dependency tests failed before integration, then passed against
the regenerated real firmware graph. Existing source CI discovers these tests;
CI without an SDK graph skips that graph check and is not a target build.

## Retained private build — NOT INSTALLED

Production/test commit: `56fb64f509c89c51d53b597c53d4c83c3c6effea`.
ESP-IDF 5.3.2 ESP32-S3 incremental build reports version `56fb64f` and passes
persistence linkage and sizing within the existing 1 MiB application partition.
This is not a clean-from-scratch build. Existing upstream warnings and the
CMake deprecation warning remain; no production warning suppression was added.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 357280 | `460e775a9756d6dea533707d44572f300d0a236a8ae06d433ffdebac543a74e7` |
| ELF | 6659196 | `d75b32ec2f67064c456b63c448f6d5ef27a1e6087f4bc1f79688688702b603d9` |

Generated ManualControl SHA-256:
`e6e0ab2d597ee23659aa718e928f61fc84742567eaf3806c9869be0d21f478b1`.
Generated System SHA-256:
`d59bd5ec7b2b0d7f53d100db4fb0938274919a282204a1db41a5b83a0f019c62`.
Later documentation changes do not alter these retained bytes.

## Remaining work

Required module internals still need checked object/queue/task/connection and
watchdog results, particularly Actuator, Attitude, Receiver, Stabilization and
Telemetry. ManualControl's start-time connections and dispatch remain unchecked.
Board COM/registration/debug-log/watchdog internals, existing System reset and
later connection/read branches, and runtime sample validity remain open.

Physical cutoff, motor order, IMU orientation/calibration, USB-reset behavior
and a verified battery/charger/connector combination are separate gates. No
battery is assumed available. Obtain fresh props-off/power confirmation before
any new hardware I/O; source/build success must not clear these gates.
