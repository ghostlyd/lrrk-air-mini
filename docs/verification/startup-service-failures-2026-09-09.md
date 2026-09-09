# Startup services: propagate allocation failures into the board gate

## Scope and disposition

This is a bounded follow-up to the [board startup gate](board-startup-failure-gate-2026-09-09.md)
under [issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27). The gate
could only reject errors reported by its prerequisites. The pinned event and
alarm implementations hid several internal allocation failures.

The changes below are tested and built, **not installed**. No serial device
was opened, reset or flashed; no settings, arming or motor command was sent;
no secret or paid AI endpoint was accessed. The installed
[receiver/thrust firmware](control-fixes-usb-install-2026-09-09.md) and
[bounded disarmed receiver evidence](disarmed-receiver-completion-2026-09-09.md)
are unchanged. Always Disarmed remains the installed configuration.

## Corrected behavior

- Event queue allocation failure returns `-1` and deletes its owned mutex.
- Callback registration failure returns `-1`, deletes the owned queue and
  mutex, and does not dispatch a null callback handle.
- Alarm initialization preserves an existing SystemAlarms object. If no object
  exists, registration failure returns `-1`; successful registration retains
  its normal defaults. A missing recursive mutex also returns `-1`.
- Periodic-event allocation failure releases the recursive mutex before
  returning `-1`, allowing subsequent event operations to proceed.

The existing board and entry-point gate now sees the event/alarm initializer
errors and stops before module initialization. The alarm service is not used
to report a fault if its mutex failed to initialize. Depending on where boot
stops, telemetry is unavailable; absence of telemetry is not readiness.

Normal dispatch semantics are preserved: callback dispatch marks work pending
even when the scheduler's binary signal is already full. Its zero return must
not be interpreted as missing callback registration. Alarm decreases still
require strictly more than 1000 ms; escalation remains immediate. This change
does not publish BootFault OK or bypass another preflight condition.

## Source boundary

`prepare_startup.py` validates both complete inputs and exact replacement
anchors before writing build-directory copies. It preserves upstream GPL
notices and leaves both external source trees unchanged. CMake watches the
generator and inputs and selects only the generated service copies.

Pinned NinjaPilot commit: `ac77304a58de6c8bd552f94668b46903adb71cb2`.
Reference backend commit: `7233c97f844c0377930bcdf22998e289638b64c6`.
Paths below are relative to NinjaPilot's `flight/` directory.

| Input | SHA-256 |
| --- | --- |
| `libraries/alarms.c` | `85a4828d601673db7964dbf13600ee93687821a0818c5bd4a479f4ed42560fdd` |
| `uavobjects/eventdispatcher.c` | `5778e5de80793601bc53ccdecd80865eaaa38d806eb032de297576a9c6e84ddb` |

The generator rejects output within or above the source directory, and
symlink/hardlink output files, before modifying either output. Repeat generation
preserves unchanged output modification times. These are trusted-build-workspace
checks, not an atomic filesystem transaction or a concurrent-adversary sandbox.

## Executed evidence

The eight-test `test_startup_services.py` suite compiles the complete real
EventDispatcher and Alarms implementations alongside the actual board
initializer, ESP-IDF entry function and settings-recovery algorithm. It uses
generated object declarations. Lower-level RTOS resources, callback registration,
object storage, other board services and module entry points remain controlled
test boundaries. This is not execution of the entire callback scheduler,
asynchronous module startup, NVS, or physical hardware.

- Three event-resource faults and the alarm-mutex fault traverse the actual
  board/entry gate: no module starts, no later hardware initialization and no
  invalid alarm/queue/mutex use. Owned event resources are checked for cleanup.
- Direct alarm tests cover failed object registration, existing Critical alarm
  preservation, and defaults on first registration. The object-registration
  implementation itself is a controlled boundary in this suite.
- Periodic allocation failure must leave its mutex unheld. Nominal queued
  callback delivery and real alarm grace/escalation remain usable.
- Before the fix, original service code produced six failing scenario
  assertions. A permanent negative control recompiles original services and
  requires their specific queue, callback, board-status and lock assertions;
  a compiler error alone cannot satisfy that control.
- Four preparation tests reject drift/unsafe outputs and verify unchanged
  source bytes and no-op output timestamps. A fifth test reads the actual
  generated firmware compile graph and requires exactly one adapted source
  for each service. That graph test failed against both old source selections
  before reconfiguration and passed against the new graph.
- The existing 20 thrust-control tests now link the adapted alarm source for
  their startup/alarm regressions. Full local host gates passed with both pinned
  checkouts, generated objects, the optional SDK, real ELF and build graph:
  **83 assistant + 181 port = 264 tests, no skips**.

CI's source job supplies pinned generated objects for the service/preparation
tests. Its compile-graph test intentionally skips without an SDK build graph;
the default host job also skips external-input-dependent fixtures. These CI
jobs must not be represented as the full local ESP32 build.

## Build provenance

Production/test commit: `67e5681ec5f41c465e6ab77682760fd0c9a37759`, clean.
ESP-IDF 5.3.2 / ESP32-S3 incremental build reported version `67e5681` and passed
the real persistence linker and application-partition size gates. The preceding
build compiled both newly selected service copies. This is not a clean-from-scratch
rebuild or a warning-free claim: unchanged upstream compiler warnings recorded
in the previous report remain unresolved; the CMake deprecation warning remains.
No new warning suppression was added to production compilation.

| Retained artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application bin | 356288 | `ace9cad07ea3a0582a1a59e5f056982745d119a3498ac379b0b2cdd10076c696` |
| ELF | 6651720 | `5e3838353d08d11c4000bc353a5f5fc478580819ea5717d30ef45a191597dd2b` |

The application fits the existing 1 MiB partition. Both artifacts are retained
privately and are **not installed**. Documentation-only follow-ups do not change
these artifact bytes. No bootloader, partition, NVS or application device bytes
were changed.

## Remaining readiness gates

This does not finish issue 27. Callback scheduler internals and task creation,
required module startup, COM internal allocations, object registration and
debug-log setup still need complete failure propagation. Runtime warm-up and
missing-sample validity also remain separate. BootFault success must wait for
the full required startup path; it must not be manufactured by clearing alarms.

Physical storage-fault inhibition (issue 26), electrical cutoff (issue 19),
motor order, IMU orientation/calibration, USB-open reset behavior and verified
battery/charger/connector compatibility remain unpassed. Arming approval is
authority to progress, not evidence that these gates passed. Fresh physical
safety confirmation is required before another device session.

## Reproduce without hardware

```sh
LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_startup_services.py -v
LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot \
LRRK_IDF_BUILD_DIR=/path/to/this/checkout/ports/ninjapilot-litewing/esp-idf/build \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_startup_preparation.py -v
```

Generate the pinned flight objects first (`make uavobjects_flight`), and follow
the wrapper README for the SDK/build prerequisites. Do not execute the flash
commands ESP-IDF prints automatically after a successful build.
