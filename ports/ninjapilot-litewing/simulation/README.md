# Disarmed native integration probe

This macOS-only diagnostic drives the **native simlitewing executable**, not
the ESP32 firmware image or physical drone. It creates its own Gazebo world
and firmware processes and leaves logs in a new evidence directory. There is
no serial transport or remote-host parameter. No arming, receiver stick,
gain, actuator or model motor command is sent.

## Prepare

Use the [Gazebo dependency environment](../../../docs/verification/gazebo-dependencies-2026-09-09.md)
and manifest-pinned NinjaPilot checkout. Current `bootstrap.sh` applies the
contract patch and `simlitewing-loopback.patch` to a fresh source checkout.
For a previously bootstrapped checkout carrying only the contract patch,
review `git status` and apply the additional patch explicitly:

```sh
git -C /path/to/NinjaPilot apply --check "$PWD/ports/ninjapilot-litewing/patches/simlitewing-loopback.patch"
git -C /path/to/NinjaPilot apply "$PWD/ports/ninjapilot-litewing/patches/simlitewing-loopback.patch"
```

If already applied, do not reapply it. The existing bootstrap/revert commands
check the current patch set; an older marker alone cannot bypass missing
loopback changes. The patch changes only the native board's three UDP bind
addresses. It does not change physical board pin mappings or control gains.

## Run from the repository root

```sh
export PATH="$PWD/.toolchains/gazebo-python/bin:/opt/homebrew/opt/qt@5/bin:/opt/homebrew/opt/binutils/bin:/opt/homebrew/bin:$PATH"
python ports/ninjapilot-litewing/simulation/disarmed_probe.py \
  --checkout /path/to/NinjaPilot
```

`--output /new/evidence/directory` optionally chooses an unused directory.
The probe verifies source identity and exact loopback edits, rejects unrelated
tracked/untracked source changes, rebuilds the native target (300-second build
timeout), checks ports are free, and starts a fresh firmware settings directory.
Existing simulator processes are never killed to make room.

During its 20-second sensor window it subscribes to Gazebo IMU and converts
FLU sensor axes to OpenPilot FRD, forwards only GyroSensor/AccelSensor and GCS
handshake data, and requests FlightStatus, ActuatorCommand and AttitudeState.
It requires at least 100 finite IMU samples, 10 replies per required object,
all streams younger than 500 ms at completion, disarmed status on every
observed status, and all four motor channels zero on every observed command.
The native log must show at least three windows with ten successful sensor
reads. Native network sockets are checked by owned PID before sensor traffic
and again at completion; a non-loopback socket fails the run.

No new motor command publisher is created in Gazebo. Processes are stopped
in cleanup, including failure/interruption paths; startup, socket checks and
shutdown waits are bounded. Logs and raw received UAVTalk stay in the evidence
directory. A zero exit means only this **disarmed native sensor check** passed.
Telemetry sampling does not prove there were no unobserved output transients.
Loopback limits network exposure but is not authentication against other local
processes. This is a trusted-development-host diagnostic, not a sandbox.

## Negative check

Repeat with `--sensor-dropout`. After 12 seconds the probe stops forwarding
and counting IMU samples. Expected outcome: **exit 1**, `status: FAIL`, reason
`stale imu stream` (or insufficient samples if startup itself was too slow).
It must never pass merely because telemetry still contains old good values.
This verifies probe rejection; it does not test an armed vehicle's failsafe.

Host unit tests require no Gazebo installation and cover missing/stale data,
arming/armed states, nonzero/short motor data, nonfinite sensor/attitude data,
latched failures, write allowlisting, socket ownership and cleanup targeting.
See [observed integration evidence](../../../docs/verification/disarmed-simulator-2026-09-09.md).
