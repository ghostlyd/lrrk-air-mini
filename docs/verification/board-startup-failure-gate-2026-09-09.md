# Board startup: reported failures now stop module initialization

## Scope

This is the first corrective slice after the
[startup-alarm diagnosis](startup-alarm-diagnosis-2026-09-09.md), not a complete
BootFault-success implementation. Issues [27](https://github.com/ghostlyd/lrrk-air-mini/issues/27),
[26](https://github.com/ghostlyd/lrrk-air-mini/issues/26) and
[19](https://github.com/ghostlyd/lrrk-air-mini/issues/19) remain open.

No serial port was opened, firmware flashed, settings changed, motor command
sent, secret accessed or paid AI call made for this change. The installed
[receiver/thrust candidate](control-fixes-usb-install-2026-09-09.md) and the
[disarmed receiver trial](disarmed-receiver-completion-2026-09-09.md) are
unchanged. The build below is **not installed** or flight-cleared.

## Behavior

The board initializer now stops at its first reported prerequisite failure.
Its one-shot synchronous status stays false after failure; a repeated call
cannot reinitialize resources or clear that condition in the same boot.
The ESP-IDF entry point checks that status before initializing any modules.
Firmware identity reads/writes and required SystemAlarms/GCSReceiver handles
are checked. UART buffer failures stop without leaking untransferred buffers.

Failure handling requests the existing PWM shutdown and only uses initialized
LED/alarm services. PWM shutdown **before** PWM initialization is a no-op;
in that case protection is the tested early return preventing later hardware
and module startup. This does not establish a new pre-init electrical latch.
Early failures can leave telemetry unavailable because its modules never start;
absent telemetry must not be treated as success.

Nominal reported returns still request module startup. They do **not** publish
BootFault OK. The final log now says startup was requested rather than completed,
because System's task runs StartModules asynchronously. PIOS_WDG_Init's return
remains previous-reset flags, not a success/error code.

## Executed tests

`test_board_startup.py` copies the production board initializer and entry point
byte-for-byte into a temporary host build, alongside real generated object
declarations and the real settings-recovery algorithm. Service implementations,
object storage, module boundaries and hardware/RTOS dependencies are controlled
test doubles. This exercises **orchestration**, not service internals or complete
board hardware integration.

- Thirty failure scenarios cover explicit service errors, required object
  handles, settings inspection/load/marker, UART allocations and COM, receiver
  mapping and the target adapter. No later service/module initialization may
  follow failure. Shutdown is requested, invalid LED/alarm use is rejected,
  and a second call after removing the scripted error must not retry startup.
- Nominal and previous-watchdog-reset cases reach module startup; neither
  publishes boot success or duplicates board initialization on a second call.
- The new tests failed against original production source (32 scenario
  failures), then passed after implementation.
- Five disposable-source mutations remove the entry gate, ignore the task
  monitor error, duplicate a free, free a transferred buffer, or corrupt the
  repeated-call status. Each is rejected by its behavioral assertion in CI.
  The latter three controls address review feedback: buffer ownership is now
  tracked individually, and the completion query is checked before/during/after
  initialization and after repetition. These refinements change tests only.
- Full local host gates passed: **83 assistant + 168 port = 251 tests**, no
  skips, with both pinned trees, optional SDK fixture, generated objects,
  real ELF and non-executing build-graph checks supplied. Host-only CI
  intentionally skips external/artifact-dependent tests; the source job
  separately supplies generated objects for the new five-test suite.

## Firmware build provenance

Production source commit: `dc3727fb3153c80cbf513b8af373901856d95dfa` (clean).
ESP-IDF 5.3.2, target ESP32-S3; both external commits remain those in
`SOURCE_MANIFEST.json`. The build reported version `dc3727f` and passed the
real persistence linker gate and application-partition size check.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application bin | 356224 | `2ec7700ef9832f2a0e35d995d282df2bedf905dd6d49abebab724951a04307c0` |
| ELF | 6651176 | `0d8df0ca6a37f5b864bb4c7b6d68f40eac1d214d9ec2643c24c6161c0f4c2ab3` |

The app fits the existing 1 MiB partition. This is build/link evidence, not a
statement that all compiler warnings are resolved: compiling unchanged upstream
sources still reported the sanitycheck thrust-enum pointer warning and
stabilization packed-member/array warnings, among others. No warning was
suppressed by this change. No application, bootloader, partition or NVS bytes
were written to the device.

## Remaining startup gates

Subsequent work: the [event/alarm service correction](startup-service-failures-2026-09-09.md)
closes the specific hidden EventDispatcher/Alarms allocation failures described
below. The following paragraph records the boundary of this original slice.

The synchronous status is not full startup readiness. At the pinned sources,
EventDispatcherInitialize, AlarmsInitialize and COM initialization can hide
internal allocation failures; object registration and debug-log setup lack
complete status. Required module tasks, watchdog subscription and callback
scheduler startup must be checked through their actual asynchronous paths.
Runtime warm-up/missing-sample validity remains separate. BootFault success
must await these checks, not be manufactured by clearing an alarm.

This slice does not execute real NVS corruption through a complete board,
measure electrical cutoff, validate USB-open reset behavior or establish
motor mapping, IMU calibration, battery/charger compatibility or flight readiness.
Always Disarmed remains the installed configuration.

## Reproduce

```sh
LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_board_startup.py -v
```

Generate pinned flight UAVObjects first (`make uavobjects_flight`). Use the
documented wrapper prerequisites for full host and ESP-IDF checks; do not run
the flash commands printed automatically by ESP-IDF merely because a build
completed.
