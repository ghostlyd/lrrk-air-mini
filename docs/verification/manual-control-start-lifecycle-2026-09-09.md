# ManualControl start lifecycle

This follows the
[checked module startup correction](checked-module-startup-2026-09-09.md) and
addresses a bounded part of
[issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27). It is
source/build evidence at the time of review, **not BootFault-success
publication, arming clearance or flight clearance**. The application installed
by PR #44 and its verified Always Disarmed setting were not changed or accessed
during that source slice. After merge, the exact merged application was
separately [installed and observed over USB](manual-control-start-usb-install-2026-09-09.md)
under the props-removed, battery-absent gate. Battery absence records the test
configuration; it is not a claim that USB left the motor path de-energized.

## Corrected startup contract

The selected complete ManualControl source previously returned success from
`ManualControlStart` after discarding the reported result of its configuration check,
three start-time subscriptions and ManualControl alarm clear. It also allowed
start before successful initialization and repeated start calls. The checked
module table consumed only the reported result, so those discarded failures
could not reach its existing System failure gate.

The hash-checked target copy now implements a boot-caller-only lifecycle:

- initialization permits one attempt and publishes readiness only after all
  eight required objects, two initialization subscriptions and the scheduler
  callback allocation have succeeded;
- start requires that readiness and permits one attempt;
- a reported nonzero configuration-check result, any of the three exact start
  subscription failures, or a failed ManualControl alarm clear is returned;
- failure reaches the real module table and System task, which stop before
  Telemetry start, callback-scheduler start and normal System connections,
  then latch brushed-output shutdown and BootFault Critical; and
- a successful start applies the existing frame/arming/takeoff initialization
  and marks the ManualControl callback pending for later scheduler execution.

The start subscriptions retain their upstream order and identities:
`SystemSettings` and `ManualControlSettings` use `configurationUpdatedCb`, and
`ManualControlCommand` uses `commandUpdatedCb`. Successful static subscriptions
are not disconnected if a later step fails. The boot path is not retryable and
does not attempt transactional rollback of shared object or scheduler state.

## Initially-full dispatch is not an error

The real callback scheduler creates each worker with an initially-full binary
signal. Before scheduler start, `PIOS_CALLBACKSCHEDULER_Dispatch` still marks
the callback waiting, but its signal give returns zero because the signal is
already full. Treating that zero as failure would reject the correct startup
path. The target code deliberately ignores this return after checking the
non-null callback allocation, while the integrated real-scheduler fixture
proves that the exact ManualControl callback subsequently executes once after
scheduler start.

The fixture also observes the initial arm-handler call, frame-setting callback and
takeoff initializer before scheduler start, then observes one dispatched
ManualControl task pass, one runtime arm-handler call with `init=false`, one
takeoff-handler call, one Manual handler call and its initial FlightStatus
publication. The arm handler itself is a counter stub: it does not read arming
settings or prove a disarmed state. These are controlled host boundaries, not
physical output or asynchronous board readiness evidence.

## Verification

Seven focused scenarios were red against the original selected source and pass
after the correction: premature start, nominal plus repeated start,
one injected nonzero configuration-interface result, alarm-clear failure and
each of the three subscription failures. The failure cases prove that no later module or scheduler worker
starts and that the existing System failure path requests output shutdown and
BootFault Critical. Exact callback objects, callback-function relationships and
execution order are asserted.

The pinned `configuration_check` implementation currently always returns zero
and itself ignores the results of publishing or clearing its configuration
alarm. The injected nonzero case is therefore a future-interface propagation
guard, not evidence that current configuration-alarm write failures reach this
gate. That real internal path remains open.

Ten deliberate mutations are rejected without accepting setup errors as
behavioral failures: missing readiness or repeat guards,
discarded configuration/alarm results, each discarded subscription result,
miswired SystemSettings callback, omitted initial dispatch, and the incorrect
requirement that the initially-full dispatch return `pdTRUE`. A permanent
original-source control reproduces all seven focused failures. Generator drift,
source/output alias protection, selected-source preprocessing and CMake watch
dependencies remain covered.

The final build-backed host run passes 83 offline assistant tests (nine optional
OpenAI SDK/live-service skips) and 275 port tests with no port skips. The latter
uses the actual compile commands and Ninja graph plus an explicitly supplied
ELF/tool persistence check. No live API call is part of the firmware gate.

## Retained source-review build — not the installed artifact

Production source commit: `acc585c536be49df368a6309f755e6bf0b876993`.
The clean build uses ESP-IDF 5.3.2 for ESP32-S3, NinjaPilot
`ac77304a58de6c8bd552f94668b46903adb71cb2` and the ESP32 reference tree
`7233c97f844c0377930bcdf22998e289638b64c6`. Persistence linkage passes at
`UAVObjSave=0x4200ca08`, `UAVObjLoad=0x4200ca8c` and
`UAVObjDelete=0x4200a874`. The application occupies `0x57c40` bytes of the
1 MiB partition, leaving `0xa83c0` bytes (66%).

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Application | 359488 | `5217d74837c673b0d761672929497d284a50a8b12b7a1ac5369405bbb158d6f8` |
| ELF | 6674844 | `614320d2eec8bb8522116a0ebf35d790c6450d62c393ef01359ba50dba97fa41` |
| Generated ManualControl | 25741 | `cafa0f76f2b23d458c7db62256336ea1f77cc1b54d9bd379bebfabbf3472c00c` |

These source-review artifacts and their build graph remain private with
owner-only modes; those exact bytes were not installed. The later clean build
from the merged commit has different version metadata and is identified by the
separate USB installation report. Its application-only write passed the
pre-write/readback/recovery-reviewed gate. Neither build's generated bootloader
was an installation candidate.

## Remaining boundaries

This change does not make the void `SettingsUpdatedCb`, `armHandler` or
`takeOffLocationHandlerInit` internals report failure. Runtime ManualControl
object reads/writes and callback re-dispatch, Telemetry internals, remaining
board/System branches, whole-board asynchronous validity and truthful
BootFault-success publication remain open. The first sampled CPUOverload and
Actuator alarm transitions observed after PR #44 are not explained or removed
by this source slice.

There is still no battery. Motor corner order, IMU orientation/calibration,
receiver authority, measured electrical cutoff latency, battery/charger/
connector compatibility and powered flight behavior remain separate gates.
USB-C must be treated as motor-capable power even with that battery connector
empty.
No serial opening, reset, settings write, arming request or motor command
occurred during the source slice documented here. The later USB report records
the separately authorized installation and read-only runtime observation.
