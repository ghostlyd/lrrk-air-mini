# NinjaPilot LiteWing Port Design

## Status

Approved target: the NinjaPilot/OpenPilot LiteWing-compatible path.

The selected flight-tree source is
[`MAVProxyUser/NinjaPilot-15.02.ninja`](https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja),
branch `litewing`, pinned for this work at
`ac77304a58de6c8bd552f94668b46903adb71cb2`. The ESP32 reference HAL is
[`MAVProxyUser/OpenPilotESP32-WROOM-32E`](https://github.com/MAVProxyUser/OpenPilotESP32-WROOM-32E),
pinned at `7233c97f844c0377930bcdf22998e289638b64c6`.

The upstream LiteWing branch currently provides a POSIX `simlitewing` board and
Gazebo bridge, but not a flashable LiteWing ESP32-S3 target. The reference ESP32
port provides the architecture/HAL pattern and identifies the remaining LiteWing
work: board pin map, brushed output, MPU6050-over-I²C, and valid console/telemetry
integration. This repository will own the LiteWing target adapter and its
reproducible patch workflow; it will not silently modify an unrelated upstream
checkout.

## Goal

Produce a reproducible NinjaPilot flight target for the LiteWing V2.6.C
ESP32-S3 board, with a validated POSIX/Gazebo path and an ESP-IDF ESP32-S3
firmware build. Preserve the existing ESP-Drone firmware as the recovery
baseline until the new target passes every source, build, simulation, and bench
gate.

## Hardware contract

The target is defined by the checked-in KiCad/BOM evidence in
`hardware/LieWingV2.6.C/`:

| Function | Contract |
| --- | --- |
| MCU | ESP32-S3-WROOM-1, dual core, 240 MHz configuration |
| IMU | MPU6050 on I2C0, SDA GPIO11, SCL GPIO10, data-ready GPIO12 |
| Motor outputs | Four brushed 720 motors through low-side MOSFETs, GPIO5/6/3/4 |
| Motor waveform | 20 kHz duty output; `0..1000` means `0..100.0%` duty |
| Motor safety | Neutral/minimum `0`, `MotorsSpinWhileArmed=false`; a disarmed or failsafe state writes zero duty |
| Battery sense | ADC GPIO2 |
| USB serial | CH340K bridge on UART0; current macOS device is observed as `/dev/cu.wchusbserial410` |
| Board identity | `board_type=0x13`, `board_rev=0x02` for the LiteWing target; keep sensor-path revision semantics explicit |
| Base sensors | MPU6050 only; barometer, magnetometer, ToF, and optical flow are add-ons |
| Telemetry | UAVTalk over the ESP32 Wi-Fi transport, with the host-side port/configuration recorded in the target manifest |

The motor corner order is not proven by the schematic alone. The target must
carry the Quad-X order as a provisional configuration and require a human
orientation/motor-order bench check before permitting a powered test.

## Port architecture

```text
NinjaPilot flight tree (pinned external source)
        |
        +-- shared compatibility patch (pinned, checksum verified)
        |
        +-- LiteWing target patch owned by this repository
                |
                +-- PiOS ESP32-S3 HAL
                |     +-- I2C0 MPU6050 transport
                |     +-- 20 kHz brushed duty backend
                |     +-- UART0/Wi-Fi telemetry
                |     +-- task/core/watchdog integration
                |
                +-- target board definition and ESP-IDF project
                |
                +-- simlitewing/Gazebo regression path
```

The target-specific code must remain additive and guarded. Existing
CopterControl, POSIX, and reference ESP32 targets must continue to build from
their original source paths. The bootstrap script must reject the wrong source
revision before applying a patch.

### Sensor path

Reuse the flight-tree MPU/ICM register and sensor-queue abstractions only where
the device contract is proven. Add a dedicated ESP32 I²C transport for the
MPU6050 at its actual 7-bit address, probe `WHO_AM_I`, configure the sample
rate/filter/ranges, and publish the same gyro/accelerometer queue records used by
the attitude estimator. A missing or invalid sensor must raise a boot/attitude
fault and must not allow arming.

Do not enable optional barometer, magnetometer, ToF, or optical-flow modules in
the first hardware image. Their footprints and drivers are separate work and
must not be inferred from a connector footprint.

### Motor path

Keep the existing actuator/mixer interface above the HAL. The LiteWing backend
maps the first four actuator channels to ESP32-S3 PWM duty, not 1000–2000 µs
servo pulses. The backend must:

- configure a deterministic 20 kHz carrier;
- clamp every channel to `0..1000` before writing hardware;
- write all four channels to zero on init, disarm, failsafe, sensor fault, and
  transport loss;
- update channels as one control-frame operation where the ESP-IDF API allows;
- expose no ESC-calibration path, because this is a brushed-MOSFET board;
- keep the status/UI layer below flight-control task priorities.

The first hardware image is attitude/rate control only. No AI request, planner,
trajectory, or host disconnect may directly write an actuator channel.

### Build and source boundary

The repository will contain a manifest with the selected upstream URLs, commits,
patch SHA-256 values, apply policy, and expected target files. The two WROOM
patches are retained as reference-only evidence because they do not apply to
the selected `litewing` branch without a reviewed refresh. A bootstrap command
will:

1. obtain or validate the pinned NinjaPilot checkout;
2. verify the reference patch metadata without applying incompatible changes;
3. apply the LiteWing target contract patch after `git apply --check` succeeds;
4. generate UAVObjects;
5. build the POSIX twin; and
6. build the ESP32-S3 image with the recorded ESP-IDF version.

The patch workflow must be reversible and must never flash a device. Flashing is
a separate, human-reviewed operation after bench gates pass.

## Verification gates

1. **Patch integrity:** wrong source commit, missing patch, or checksum mismatch
   fails closed.
2. **Host compile:** `fw_simlitewing` builds and starts; the simulator consumes
   IMU data and produces `ActuatorCommand` output.
3. **Control regression:** level, pitch, and roll stimuli produce the expected
   Quad-X correction signs; zero-throttle output is all zeros; saturation is
   bounded to `0..1000`.
4. **ESP-IDF compile:** the LiteWing target builds for ESP32-S3 with the exact
   recorded toolchain; no claim of hardware execution is made by this gate.
5. **Bench electrical gate:** props removed, battery disconnected except for an
   explicitly controlled power test; USB identity, IMU `WHO_AM_I`, watchdog,
   zero-output, and disarm/failsafe behavior are recorded.
6. **Human orientation gate:** physical motor corner mapping and IMU frame are
   verified by a human before any motor spin.
7. **Flight gate:** only after all preceding evidence exists, in an open area
   with a documented emergency-disarm procedure.

## Non-goals

- Replacing the LiteWing board with OpenDrone-hw hardware.
- Flashing firmware during source/build development.
- Adding GPS, navigation, optical flow, altitude hold, or Remote ID to the
  first flight image.
- Letting a language model run the stabilization loop or emit raw motor values.
