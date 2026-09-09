# LiteWing ESP32-S3 target adapter

This directory contains the repository-owned hardware seams for the selected
NinjaPilot/OpenPilot flight tree. It is intentionally kept outside the pinned
checkout so the upstream source remains clean and reproducible.

`sources.cmake` is included by the future ESP-IDF wrapper after it sets the
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

The ESP-IDF wrapper and hardware build are still open gates: this workstation
does not have `idf.py`, and the adapter has not been flashed or run on a board.
