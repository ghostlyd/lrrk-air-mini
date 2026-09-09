# Startup alarm investigation: source reproductions, not a firmware fix

## Status and scope

[Issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27) remains open.
This change adds executable host reproductions and documents the missing boot
success contract. It does not change firmware, clear alarms, weaken preflight,
open a serial device or enable arming. No firmware build, flash/reset command,
paid AI request or credential access is part of this investigation.

The installed candidate and previous physical acceptance boundaries remain in
the [installation](control-fixes-usb-install-2026-09-09.md) and
[disarmed receiver follow-up](disarmed-receiver-completion-2026-09-09.md) reports.

## Evidence chain

| Symptom | Executed or inspected cause | What is not proved |
| --- | --- | --- |
| Early CPUOverload Critical, later OK | The actual pinned runtime shim returns zero on its first idle-task observation; the actual task monitor publishes that zero as idle percentage. System code computes load as `100 - idle` and compares against the target's 95% Critical threshold. | A true first-interval workload measurement, or exact physical time of that first update. |
| Early Actuator Critical, later OK | The complete adapted Actuator task calls `setFailsafe()` before its first queue receive. With the real alarm library, valid subsequent updates eventually clear it; absent/lost updates keep or reassert Critical and zero commands in the disarmed fixture. | Electrical duty, stop latency, real scheduler behavior or flight readiness. |
| Critical remains briefly after a healthy update | The real alarm library permits a severity decrease only after **more than** 1000 ms since the last change; increases are immediate. | That every physical transient has this cause, or that the safety hold can be removed. |
| BootFault remains Uninitialised | Generated defaults are Uninitialised; the board publishes only failures, not success. Module and System startup also have unchecked failure paths, so simply reaching the final log message is insufficient. | A successfully completed whole-board initialization or an accepted BootFault fix. |

### CPU runtime/monitor reproduction

`test_startup_runtime.py` compiles the runtime shim and task monitor from Git
objects at their exact pins, with controlled RTOS snapshots and clock values.
It does not replace the counter-delta or percentage implementation with a model.
The first sample has 50,000 microseconds of accumulated idle time available,
but returns **0% idle** because the shim establishes its baseline at that call.
Later controlled intervals return 20%, 50% and 80% idle as supplied. Matching
counter wrap also returns 50%. A missing task snapshot returns zero too: the
current interface cannot distinguish missing/warm-up data from real zero idle.

This is a narrow characterization of the **current limitation**, not an
acceptance test for a correct readiness interface. Replace it with explicit
validity and consumer tests when correcting the runtime contract. The System
module's load conversion and alarm threshold are source-inspected here, not
executed as a complete System task. No CPU alarm is cleared by this test.

The reference task-creation shim pins flight tasks, including System, to core
1. The installed IDF 5.3.2 `xTaskGetIdleTaskHandle()` implementation returns the
calling core's idle task. The reported value is therefore an application-core
estimate under that configuration, not a verified aggregate of both S3 cores.

### Real actuator and alarm-library reproduction

The `ActuatorStartup` test executable links the complete adapted Actuator task,
real generated UAVObjects and actual pinned `alarms.c`. Only object storage,
RTOS/queue inputs, logging and hardware outputs are replaced by host boundaries.
The new startup scenarios use simulated **Disarmed** state and minimum throttle;
no physical control API is reachable.

- Before the first supplied event, the task has already published Critical and
  zero values for the first four actuator channels.
- With no events, it keeps Critical and zero outputs.
- After five missing events followed by valid updates, the real alarm grace
  expires and Actuator becomes OK while outputs remain zero.
- Losing updates again reasserts Critical, still with zero outputs.
- A separate alarm-library boundary case sets Critical at tick 2000: a clear
  at tick 3000 is refused, a clear at 3001 succeeds, and a same-tick new Critical
  is accepted immediately. These are scripted host ticks, not electrical or
  measured RTOS scheduling times.

Negative controls demonstrate sensitivity: omitting the initial `setFailsafe`
from a disposable adapted source fails the startup assertions; compiling the
alarm library with zero grace fails the 1000-ms boundary assertion. A runtime
mutation that discards the later delta also fails. Upstream checkouts and all
production firmware files remain unchanged.

### Additional offline observations from the physical captures

The first and follow-up receiver captures both contain seven SystemStats
samples. Both first samples report FlightTime **402 ms** and CPULoad **54%**;
later sampled loads are 54–55%, with final reported times 6222 ms and 6221 ms
respectively. Thus the sampled Critical alarm does not itself prove that the
CPU was overloaded at those later sample times; alarm hold behavior is a
reproduced source explanation consistent with the observations.

These uptime values are also important: despite the probe issuing no reset
command and deasserting DTR/RTS before opening, the captures begin with low
reported uptime. This does **not** prove what caused a restart, nor establish
that opening this bridge is reset-free. Serial-open/reset behavior needs
separate observation before relying on a live connection during powered use.
No new device opening was performed to investigate it here.

Capture hashes and the first trial's historical FAIL status remain as recorded
in their original reports. Offline replay of its valid prefix does not repair
that incomplete first capture or turn it into a passing trial.

## Why BootFault cannot be marked successful yet

Source inspection of the actual target identifies these unclosed boundaries:

- `pios_board.c` latches detected failures and inhibits outputs, but some
  prerequisite returns are unchecked (including callback scheduler, object
  infrastructure and alarm initialization). Its LED-initialization early
  return also needs to be covered by the eventual boot contract.
- `InitMods.c` discards every initializer and starter return value.
- Several actual module functions return zero even if queue/task creation
  fails; checking only their return values would still give false success.
- The reference `xTaskCreate` wrapper increments a failure counter, but the
  current startup path does not use it as a success gate. System startup itself
  also ignores task-creation results, and the callback scheduler starts later.
- The existing board-fault latch must not be cleared by later nominal telemetry,
  successful sensor initialization or a generic `AlarmsClear(BootFault)`.

Corrective work must define checked prerequisites across board services,
objects/storage, module initialization, required task handles and callback
scheduler startup. Failure must remain latched and outputs inhibited; success
must be published only after all required stages actually complete. Test
failure injection, clean boot and reset behavior through the integrated startup
path before the separately reviewed props-off/battery-absent physical check.
This overlaps the full-board storage/output-inhibit coverage in issue 26, but
does not close it. Do not suppress CPU or Actuator alarms to manufacture a pass.

## Reproduction and source provenance

```sh
LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot \
LRRK_TEST_REFERENCE_ROOT=/path/to/pinned/OpenPilotESP32-WROOM-32E \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_startup_runtime.py -v
LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_thrust_control.py -v
```

The control test requires generated flight UAVObjects. GitHub's source job
fetches both exact pins, runs the runtime characterization and generates the
objects before running the complete control tests. The two focused suites pass
4 and 20 tests respectively, including the existing thrust regressions.

Primary sources inspected:

- [Runtime shim, ESP32 reference pin](https://github.com/MAVProxyUser/OpenPilotESP32-WROOM-32E/blob/7233c97f844c0377930bcdf22998e289638b64c6/pios/esp32/pios_task_runtime.c)
- [Task monitor, NinjaPilot pin](https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja/blob/ac77304a58de6c8bd552f94668b46903adb71cb2/flight/pios/common/pios_task_monitor.c)
- [System module](https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja/blob/ac77304a58de6c8bd552f94668b46903adb71cb2/flight/modules/System/systemmod.c)
- [Actuator task](https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja/blob/ac77304a58de6c8bd552f94668b46903adb71cb2/flight/modules/Actuator/actuator.c) and [alarm library](https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja/blob/ac77304a58de6c8bd552f94668b46903adb71cb2/flight/libraries/alarms.c)
- [Target board initialization](../../ports/ninjapilot-litewing/target/firmware/pios_board.c), [module table](../../ports/ninjapilot-litewing/target/firmware/InitMods.c) and [entry point](../../ports/ninjapilot-litewing/target/firmware/litewing.c)

Arming, powered tests, electrical cutoff, physical motor mapping, IMU
orientation/calibration, battery/charging validation and flight remain unpassed.
