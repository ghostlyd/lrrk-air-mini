# Brushed PWM driver verification — 2026-09-09

## Corrections

Executing the actual target driver against host-side ESP-IDF seams exposed an
infeasible timer configuration and unhandled write-error paths that the earlier
pure contract tests/source-marker checks did not cover.

The previous 12-bit, 20 kHz configuration requires 81.92 MHz at divider 1.
The ESP32-S3 LEDC clock sources top out at 80 MHz. In the pinned IDF divisor
calculation, the encoded divider is 250, below the valid minimum 256. Eleven
bits gives divider 500 and preserves 20 kHz with `0..1000` actuator values
mapped into `0..2047` hardware duty. This conclusion is based on the pinned
driver and [Espressif's clock/resolution documentation](https://docs.espressif.com/projects/esp-idf/en/v5.3.2/esp32s3/api-reference/peripherals/ledc.html),
not an observation from the physical board.

The driver now checks each duty-stage and duty-update return value. On failure
it latches hardware unavailable and attempts `ledc_stop(..., idle_level=0)` on
every channel, continuing after an individual stop error. Later updates cannot
re-enable stopped channels. The latch requires reboot; another init call or
healthy input cannot clear it. Initial zero-write failures and missing watchdog
task creation cannot be hidden by a later successful-looking init return.

Stopping is best effort when the peripheral itself fails. A software error
return is not proof that a gate pin is electrically low.

## Host verification

The test compiles the production `pios_litewing_brushed_pwm.c` and
`litewing_contract.c` as C11 with `-Wall -Wextra -Werror`. Only hardware,
FreeRTOS and FlightStatus boundaries are substituted. Each scenario runs in a
separate process; no test-only reset API was added to production code.

Twelve test methods run 27 process scenarios:

- feasible timer, staged/clamped duty and invalid output index;
- disarm, IMU fault, failsafe and shutdown;
- the watchdog's current 100 ms age predicate;
- stage, update and stop errors at each of the four channels;
- initial zero-stage and zero-update errors at every channel;
- watchdog-task creation failure followed by another init and a
  healthy/armed/full-duty update attempt.

Before the timer correction, ordinary init scenarios failed. Correcting only
the resolution made the six ordinary scenarios pass but left 17 injected
fault scenarios failing. Checking errors/latching the fault made those pass.
Independent review prompted the four additional initial-update scenarios and
the post-watchdog-failure command attempt.

The final local host gate passes **60 assistant tests and 49 port tests** with
the optional AI SDK installed. The IDF environment separately ran the
standard-library assistant path, explicitly skipping optional SDK tests.

## ESP32-S3 compile and image evidence

The corrected driver also passed the real ESP-IDF 5.3.2 compile, link, binary
generation and partition-size checks; the host stubs were not used there.

| Input or result | Value |
| --- | --- |
| NinjaPilot source | `ac77304a58de6c8bd552f94668b46903adb71cb2` |
| ESP32 reference source | `7233c97f844c0377930bcdf22998e289638b64c6` |
| Candidate base | `9c291fb621b61e07c2da3a5dec72b2c3e0bc8780` plus this driver correction |
| Driver SHA-256 | `8d53f0847f7adb88afa20f79d0bb8579c187e0e76992daa7b9027a6001aa180f` |
| Toolchain | ESP-IDF 5.3.2; Xtensa GCC 13.2.0; installed IDF Python 3.9.6 environment |
| Application size | `0x56a10` bytes in a `0x100000` partition, 66% free |
| Application SHA-256 | `27694eae6e58cee9a554aece8965363824873557d5a3abcd28fcbc11d93a83c3` |
| Build result | `ESP_IDF_BUILD=PASS target=esp32s3` |

The digest identifies the locally built candidate, not a released or flashed
image or a promise of bit-for-bit reproducible build metadata. Generated files
and full build logs remain in the ignored ESP-IDF build directory. The full
build still reports warnings in upstream/reference code; it is not presented
as warning-free.

An initial build invocation selected the unrelated Python 3.14 AI environment
and stopped before compilation because that IDF environment did not exist.
Explicitly activating the already installed IDF Python 3.9 environment resolved
the selection error without installing or replacing a toolchain.

## Review and remaining gates

Independent source review found no blocking defect in the corrected driver,
confirmed the clock arithmetic and verified the real-driver host tests. It
identified the pre-existing timing limitation tracked in
[issue #19](https://github.com/ghostlyd/lrrk-air-mini/issues/19): age greater
than 100 ms is checked by a 20 ms polling task, with additional scheduling and
mutex delay. This is not a proven hard motor-cut deadline.

Host stubs do not prove electrical timing, task preemption, simultaneous
cross-channel updates, motor corner mapping or physical shutdown behavior.
No serial port, physical motor, firmware flashing or API credential was used.
Battery compatibility, physical driver validation and human flight gates
remain open; this source correction is not flight clearance.
