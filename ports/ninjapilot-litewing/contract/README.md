# LiteWing target contract seam

`litewing_contract.c` is a platform-neutral test seam for the eventual
NinjaPilot ESP32-S3 HAL. It encodes only the safety-critical board contract:
board identity, brushed duty bounds, MPU6050 identity, arming prerequisites,
and all-channel safe output. It performs no GPIO, I2C, PWM, Wi-Fi, or UAVTalk
access.

The eventual ESP-IDF implementation must call equivalent logic before touching
hardware. This seam is not a flashable firmware target and is not evidence of
hardware execution.
