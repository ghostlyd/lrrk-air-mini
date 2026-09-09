# LiteWing world sensor check and fidelity review — 2026-09-09

Source: NinjaPilot `ac77304a58de6c8bd552f94668b46903adb71cb2`.
Runtime: Gazebo Sim 8.15.0, macOS arm64, isolated Gazebo Python environment.
Reviewed source files (relative to that pinned external checkout):

- `ground/gazebo_bridge/worlds/litewing.sdf`
- `ground/gazebo_bridge/tools/litewing_bridge.py`
- `flight/targets/boards/simlitewing/firmware/Makefile`

## Observed sensor evidence

The LiteWing-specific world, not merely Gazebo's empty example, completed
2,000 headless iterations with exit 0. A separate 5,000-iteration run with
a Python subscriber on `/litewing/imu` completed with exit 0 and delivered
2,500 messages. All six acceleration/angular-velocity components were finite.
The final 100 samples averaged approximately `(0, 0, 9.80665000006821)` m/s²
and `(0, 0, 0)` rad/s. The acceptance check required at least 100 messages,
vertical acceleration within 0.5 m/s² of gravity, and the other five mean
components within 0.5 of zero in their respective units.

The subscriber was created before launching the server, using
`gz.transport13.Node.subscribe` with `gz.msgs10.imu_pb2.IMU`. The server command:

```sh
GZ_IP=127.0.0.1 GZ_PARTITION=lrrk-litewing-imu-check \
  gz sim -s -r --iterations 5000 -v 2 \
  /path/to/NinjaPilot/ground/gazebo_bridge/worlds/litewing.sdf
```

The subscriber must use the same IP/partition environment. The harness bounded
the process to 45 seconds, with termination/collection in a finally block if
still running; the normal run completed without forced termination.
No motor command publisher, firmware process, bridge, or serial device was
started by this check. It proves world loading, physics progression, and
resting IMU delivery, not firmware sensor ingestion or closed-loop control.

## Fidelity differences that must remain explicit

| Boundary | Pinned simulator / bridge | Current ESP-IDF wrapper |
| --- | --- | --- |
| Module set | Adds Logging, Flip, RemoteID, AltFilter | These four modules are not in `NINJA_MODULE_SRCS` |
| Sensor input | Gazebo IMU transformed to OpenPilot axes; bridge injects noisy truth-derived barometer | MPU6050 hardware driver; no barometer driver in first target |
| Collective control | Bridge uses world-truth altitude/velocity with its own controller | No equivalent truth input exists on physical hardware |
| Gains | Bridge overwrites roll/pitch rate and attitude gains unless `LITEWING_STOCK_GAINS=1` | A bridge-modified simulation is not validation of hardware defaults |
| Physical parameters | Assumed geometry, inertia, thrust, battery contribution, and provisional corner mapping | Actual battery, mass, motor order, and IMU orientation still need verification |

The SDF comment claims 55 g total, but its inertial entries sum to **57 g**:
55 g base plus four 0.5 g rotors. At the configured maximum speed, four motors
produce `4 * 2.4e-8 * 3000² = 0.864 N`, implying ideal thrust/weight about
1.546 and ideal hover fraction about 0.647, not the bridge's 0.624. These are
calculations from model inputs, not measured motor performance. Do not retune
hardware or purchase parts based on them. Resolve the intended total mass and
measure the physical configuration before treating the model as calibrated.

The bridge also caches actuator values without a freshness cutoff and prints
"touchdown" after its descent loop even if that loop expired at its time limit.
Neither printed touchdown nor process exit alone is an acceptance condition.
Future closed-loop tests need explicit fresh-sensor/actuator, attitude, altitude,
touchdown, disarm, and process-cleanup assertions, including negative cases.

## Next integration gate

Use a repository-owned, bounded harness against a explicitly declared module
configuration; restrict native UDP to loopback, prove IMU ingestion and safe
disarmed outputs first, then exercise the full control loop and fault cases.
Keep the upstream bridge's experimental gain changes and auxiliary sensors
separate from evidence for the shipped ESP-IDF target. No hardware flight
readiness is established; the owner still has no battery.
