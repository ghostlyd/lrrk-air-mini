# Bench-only output bound

This diagnostic build is not flight firmware. It investigates the observed
controller saturation without relying on host telemetry to enforce duty.
It does not establish the cause of the saturation or flight readiness.

## Contract

- `CONFIG_LRRK_BENCH_OUTPUT_LIMIT=y` selects the profile; default is disabled.
- Each sanitized motor request is capped at 200/1000, producing no more than
  409/2047 LEDC duty (slightly under 20%). This is a ceiling, not a target.
- The first eligible nonzero frame starts one elapsed one-second interval.
  Zero output, packet refreshes, disarming and rearming do not renew it.
- At expiry, output updates and the existing 20 ms watchdog latch shutdown.
  Reset is required for another interval. Normal arming policy is unchanged.
- Watchdog execution and mutex acquisition are scheduled software operations.
  One second is the deadline, not a measured electrical stopping guarantee.
  Peripheral failure or a stalled CPU cannot be made safe by this code alone.
- IMU, disarm, receiver/failsafe, shutdown and driver-error handling remain.
- PWM observation retains the original requested duty and reports the actual
  successfully submitted capped duty. Expiry reports shutdown suppression.
- Firmware identity is `BEN1` plus the first 16 wrapper commit characters,
  rather than the flight build's `LRRK` prefix. Never bypass a launcher's
  flight-image check to use this image for flight.

## Build and qualification

Use a clean committed checkout, pinned ESP-IDF 5.3.2 and the existing pinned
NinjaPilot/backend sources. Use a separate build directory and a separate
SDKCONFIG file; an existing SDKCONFIG overrides defaults. Supply
`-DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.bench.defaults"` to idf.py
from the ESP-IDF project directory. Verify the resulting SDKCONFIG explicitly
contains `CONFIG_LRRK_BENCH_OUTPUT_LIMIT=y` before accepting the image.

Run the real-driver host tests (`test_brushed_pwm_driver.py`) and identity
tests (`test_firmware_identity.py`), then the full host suite and firmware build.
Host tests fake only hardware/RTOS boundaries; they do not measure board timing.
Application-only deployment must preserve settings and recovery regions and
verify exact readback and the BEN1 marker before any bounded motor test.
Measure actual stop latency and confirm zero output after the interval.

Return to a verified flight-profile build before flight qualification. Removing
the diagnostic ceiling is not itself flight approval: saturation cause,
physical motor mapping/direction, sensor behavior and power qualification still
need evidence. No persisted arming settings are changed by this profile.
