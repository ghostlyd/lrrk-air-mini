# Gazebo and simposix dependencies — 2026-09-09

Host: macOS 26.5.2, Apple Silicon. NinjaPilot source:
`ac77304a58de6c8bd552f94668b46903adb71cb2`.

## Installation

Following [Gazebo's official macOS instructions](https://gazebosim.org/docs/harmonic/install_osx/):

```sh
brew tap osrf/simulation
brew trust osrf/simulation
brew install gz-harmonic
```

Installed: Gazebo Harmonic formula `1.0.0_5`, Sim `8.15.0_4`, Transport
`13.6.0_4`, Messages `10.4.0_4`, Qt `5.15.19`, and GNU binutils `2.47`.
`gz sim --versions` reports `8.15.0`. The native simulator uses the pinned
source tree, not a separate Homebrew simposix package:

```sh
export PATH="/opt/homebrew/opt/qt@5/bin:/opt/homebrew/opt/binutils/bin:/opt/homebrew/bin:$PATH"
make -C /path/to/NinjaPilot fw_simposix_elf
```

The native build exited successfully. A three-second process probe survived
until deliberately terminated with SIGTERM. This establishes startup only,
not a physics connection or flight behavior.

## Python bridge environment

Homebrew's Gazebo bindings are exposed through Python 3.14 site-packages.
Their generated protobuf code requires runtime 7.36.1 or compatible newer
7.x; the runtime was missing from the original Homebrew installation.
Use an ignored environment from the repository root, leaving Homebrew's
externally managed Python untouched:

```sh
/opt/homebrew/bin/python3.14 -m venv --system-site-packages .toolchains/gazebo-python
.toolchains/gazebo-python/bin/python -m pip install 'protobuf==7.36.1' 'matplotlib==3.11.1'
source .toolchains/gazebo-python/bin/activate
```

This environment intentionally shares Homebrew's native Gazebo bindings and
NumPy; it is not a portable or fully locked environment. Recheck imports after
Homebrew upgrades. Do not reuse the ESP-IDF Python environment for Gazebo.

Verified imports: `gz.transport13`, `Pose_V`, `Actuators`, `IMU`, `NavSat`,
`Magnetometer`, and `FluidPressure` from `gz.msgs10`, NumPy 2.5.3,
Matplotlib 3.11.1, and protobuf 7.36.1. A `Pose_V` serialization roundtrip
passed, and `python -m pip check` reported no broken requirements.
The full upstream bridge was not launched by this dependency check.

## Headless runtime check

```sh
GZ_IP=127.0.0.1 GZ_PARTITION=lrrk-litewing-install-check \
  /opt/homebrew/bin/gz sim -s -r --iterations 10 -v 3 \
  /opt/homebrew/opt/gz-sim8/share/gz/gz-sim8/worlds/empty.sdf
```

Exit status: 0. Gazebo initialized the bundled empty world with a 1 ms physics
profile, ran the finite test, and exited. No GUI was exercised.

## Remaining gates

- Review a LiteWing-specific world and bridge configuration before sustained use.
- Verify sensor ingestion, motor mixing, telemetry, and failsafes in that loop.
- Restrict the native simulator's all-interface UDP bindings before sustained use.
- Audit legacy/deprecated dependency warnings separately; installation is not a security audit.
- No serial access, flashing, physical motor test, or flight was performed.
  The owner has no battery; powered hardware validation remains pending.
