# LiteWing ESP32-S3 target adapter

This directory contains the repository-owned hardware seams for the selected
NinjaPilot/OpenPilot flight tree. It is intentionally kept outside the pinned
checkout so the upstream source remains clean and reproducible.

`sources.cmake` is included by the ESP-IDF wrapper after it sets the
following inputs:

- the selected NinjaPilot checkout from `SOURCE_MANIFEST.json`;
- the pinned OpenPilotESP32 reference backend;
- the generated UAVObject sources required by the flight tree.

The wrapper must use the reference `pios_esp32.h`, `pios_esp32_priv.h`, and
I2C backend, but must replace the reference `pios_servo.c` and
`pios_icm20602.c` entries with the sources listed in this directory. The
compatibility header named `pios_icm20602.h` exists only because the shared
Attitude module uses that compile-time selector; the implementation is an
MPU6050 driver over I2C0.

Board initialization is deliberately a narrow call from the wrapper's board
file:

```c
if (PIOS_LiteWing_Board_Init() != 0) {
    /* keep the board in boot fault; the PWM backend is already at zero */
}
```

The adapter uses the selected tree's existing sensor queue record and actuator
entry points. It does not expose an AI or host-control path to the motor
backend. The host AI layer remains advisory and outside the flight controller.

The PWM backend uses 20 kHz at 11-bit LEDC resolution, mapping the shared
`0..1000` range to `0..2047`. Twelve bits at 20 kHz would require 81.92 MHz,
above the ESP32-S3 LEDC clock sources' 80 MHz maximum; see the pinned
[ESP-IDF LEDC clock and resolution documentation](https://docs.espressif.com/projects/esp-idf/en/v5.3.2/esp32s3/api-reference/peripherals/ledc.html).

Every duty-stage and duty-update result is checked. A failure latches output
unavailable until reboot and attempts to stop all four channels at idle-low,
even if one stop fails. Fresh telemetry, IMU recovery or another initialization
call cannot clear that latch. An initial zero-frame failure or missing watchdog
task is not successful initialization. A permanent peripheral failure can also
prevent stopping a pin: this software policy is not an independent electrical
kill switch or proof of measured zero output.

Host driver tests compile the actual backend and run it with fake hardware,
RTOS and UAVObject interfaces. They cover duty staging/clamping, disarm, IMU
fault, failsafe, shutdown, watchdog timing boundaries and injected LEDC errors.
They do not model electrical timing, task preemption or cross-channel atomicity.
The watchdog uses a greater-than-100-ms age threshold checked every 20 ms;
scheduling and mutex contention can delay its response further. A hard
motor-cut deadline remains a separate validation/design gate, not a passing
claim from these host tests.

The ESP-IDF 5.3.2 wrapper build passed compile, link, image generation, and
partition sizing on 2026-09-09. The adapter has not been flashed or run on a
board; runtime and physical verification remain open.
