# LiteWing motor and IMU mapping evidence — 2026-09-09

This note resolves the software mapping used by the LiteWing target. It keeps
source, owner-photo observations, and live telemetry distinct. Propellers were
reported removed and no battery was present during the live capture.

## Motor channel contract

The repository PCB routes J7/J8/J9/J10 to `MOT_1`/`MOT_2`/`MOT_3`/`MOT_4`,
which route to ESP32-S3 GPIO 5/6/3/4. With the antenna at the front and USB-C
at the rear, connector coordinates establish this order:

| Actuator channel | GPIO | PCB corner | PCB class | Visible wire pair | Required rotation | Mixer yaw |
| --- | ---: | --- | --- | --- | --- | ---: |
| 1 | 5 | front-right | B | black/white | CCW | -127 |
| 2 | 6 | rear-right | A | red/blue | CW | +127 |
| 3 | 3 | rear-left | B | black/white | CCW | -127 |
| 4 | 4 | front-left | A | red/blue | CW | +127 |

The owner photos visibly show alternating A/B markings and the corresponding
wire colors. CircuitDigest's LiteWing assembly guide identifies A propellers
as clockwise and B propellers as counter-clockwise. Racerstar's 8520 listing
identifies red/blue motors as clockwise and black/white motors as
counter-clockwise. The production GPIO constants and mixer yaw terms now use
one tested repository contract so they cannot silently drift apart.

Sources:

- repository PCB: `hardware/LieWingV2.6.C/LieWingV2.6.C.kicad_pcb`
- [CircuitDigest LiteWing assembly guide](https://circuitdigest.com/articles/assembling-litewing-drone)
- [Racerstar 8520 motor listing](https://www.racerstar.com/racerstar-8520-8_5x20mm-53500rpm-coreless-motor-red-for-eachine-qx80-diy-micro-fpv-quadcopter-p-240.html)

This establishes net, corner, fitted motor class, and intended rotation. A
bounded sequential low-duty run is still the final assembled-continuity check;
it must end with every command and output at zero.

## IMU body transform

The fitted MPU-6050 is U7 on the top side of the repository PCB at 180 degrees.
The package pin-one location and TDK package-axis diagram agree with the
NinjaPilot MPU6000 `TOP_0DEG` convention. The production transform is therefore:

| OpenPilot body axis | MPU-6050 sensor axis |
| --- | --- |
| +X | +Y |
| +Y | +X |
| +Z | -Z |

The transform is now a pure tested contract used by the production driver.
It preserves defined behavior for every signed 16-bit sample, including the
negative endpoint.

Primary source: [TDK InvenSense MPU-6000/MPU-6050 datasheet](https://www.invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Datasheet.pdf).
The pinned comparison source is NinjaPilot commit
`ac77304a58de6c8bd552f94668b46903adb71cb2`, file
`flight/pios/common/pios_mpu6000.c`.

## Live stationary evidence and calibration boundary

A 15-second read-only UAVTalk capture produced 131 accelerometer, 128 gyro,
and 329 attitude samples. Capture SHA-256:
`791ceb0667463ba794a31c346adb21ff9d7aa948147e49da3f58585d69f84663`.

Stationary means were approximately `(0.022, 0.641, -9.434) m/s²`; gravity is
on negative body Z as required and the small body-Y component is consistent
with a slightly tilted resting board. Stored board rotation and level trim are
zero. Stored accelerometer/gyro biases are zero and scale terms are one. The
Attitude module is configured to estimate gyro bias during startup and again
during arming.

No guessed persistent accelerometer correction was written from this single
pose. One stationary orientation cannot separate per-axis offset from scale;
a true six-face calibration requires physically repositioning the board. The
current live data establishes correct orientation, stable sampling, and usable
factory-scale behavior, but it is not represented as a six-face calibration.
