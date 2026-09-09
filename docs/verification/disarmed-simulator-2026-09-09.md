# Native disarmed integration — 2026-09-09

Host: macOS arm64, Gazebo Sim 8.15.0, Python 3.14 Gazebo environment.
Flight source: `ac77304a58de6c8bd552f94668b46903adb71cb2`, plus the
manifest-pinned contract and simlitewing loopback patches.

The [repository-owned probe](../../ports/ninjapilot-litewing/simulation/README.md)
was built and run against actual Gazebo and the native firmware, not mocked
sensor/telemetry APIs. It never opened a serial device or launched the upstream
arming/gain-changing bridge.

## Positive result

Final positive run: `lrrk-disarmed-72k19e80`, process exit 0.

| Check | Observed evidence |
| --- | --- |
| Gazebo IMU | 8,887 finite received samples |
| Native FlightStatus | 387 observed messages, all Disarmed |
| Native ActuatorCommand | 404 observed messages, first four channels always zero |
| Native AttitudeState | 805 finite observations; final roll/pitch/yaw approximately zero on the resting world |
| End-of-run freshness | All four required streams within 500 ms |
| Native processing | 15 diagnostic windows with at least 10 successful sensor reads, following a startup window with none |
| Socket ownership | Native process bound `127.0.0.1:9000` and `127.0.0.1:9001`; no non-loopback socket observed by the PID-scoped check |
| Cleanup | Native exited on SIGTERM (-15); Gazebo exited 0 after requested shutdown |

Native executable SHA-256:
`cc9ccc0cd4c567ad6685d59e3c6595ab0d96d1a2aff4a286a016cbdb590c4c4e`.
The script rebuilds the target before running; generated logs, native settings
and raw incoming UAVTalk remain in its separate evidence directory.

An earlier positive run received 5,275 IMU, 385 status, 402 actuator and 801
attitude messages. Sample counts vary with server startup and scheduling and
are not a benchmark or hard-real-time performance claim.

## Negative result

Run `lrrk-disarmed-f1o684n0` used `--sensor-dropout`, stopping IMU forwarding
after 12 seconds while polling telemetry continued. It exited 1 with
`{"status": "FAIL", "reason": "stale imu stream"}`. The native diagnostic
returned to `attitude: ok=0 err=100`. Both processes were stopped, and a later
check found no listeners on the three native simulator ports.

This proves the probe does not accept historical good samples after a sensor
dropout. The controller was disarmed throughout; this is **not** an armed
failsafe or motor-cut latency test.

## Coverage and remaining gates

The local suite passes 52 AI tests and 37 port tests, including 12 new probe
tests for incomplete/stale evidence, arming/armed telemetry, nonzero/short
actuator data, nonfinite data, latched failures, write allowlisting, socket
scope and targeted cleanup. Source/process paths were self-reviewed; no
independent reviewer was available for this run.

The approved disarmed sensor path now has live evidence. A stationary attitude
report and sensor-read counters do not establish dynamic axis/sign accuracy,
closed-loop stability, mixer corner correctness or any physical ESP32 HAL
behavior. The [earlier fidelity differences](litewing-world-fidelity-2026-09-09.md)
still apply. Dynamic orientation, armed physics scenarios, real driver bench
tests, battery/connector compatibility and human flight gates remain open.
