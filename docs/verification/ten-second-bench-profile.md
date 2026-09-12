# Ten-second bench profile

The PWM driver now supports a build-time one-shot interval of 1–10 seconds.
The original bench profile still defaults to one second. The explicit
`sdkconfig.bench-ten-second.defaults` profile selects ten seconds with the
unchanged 200/1000 per-motor ceiling and BEN1 diagnostic identity.

The interval starts at the first eligible nonzero frame. Zero commands,
disarm/rearm and fresh receiver packets do not renew it. Output updates and
the watchdog enforce expiry; actual scheduling latency is not a guaranteed
electrical cutoff. IMU health, failsafe, stale updates and driver errors can
stop outputs earlier. This is not flight firmware.

Use a fresh SDKCONFIG when selecting the profile: defaults do not override
an existing generated configuration. Verify the resolved duration before build.

## Evidence boundary

Native tests execute the production driver with hardware/RTOS seams replaced.
They exercise fresh 40 ms updates through ten seconds, expiry on both update
and watchdog paths, the unchanged duty ceiling, and nonrenewal after rearming.
These tests are not electrical or motor-rotation evidence.

The ten-second image below was subsequently flashed application-only and
readback-verified, preserving bootloader and settings. The observed gyro
transient remains unresolved; a longer deadline does not establish flight readiness.

## Prepared candidate (2026-09-11)

The private candidate was built from source commit
`e8d2c1e852c77e64df30900e93df13906d26ad71`. Its resolved configuration differs
from the previously deployed diagnostic build only in the output duration:
1000 to 10000 ms. Attitude tracing and the output ceiling remain unchanged.

- Application size: 878944 bytes.
- SHA-256: `b6fa863b4dd97db4d83a36ddbd3fe53e49bd764152ad6e7357c7ed57beadee2a`.
- Embedded identity: `BEN1e8d2c1e852c77e64`.
- Offline image inspection: checksum and validation hash valid.

The private one-shot runner has been adapted to a 30-second host transaction
deadline and a maximum 10.35-second powered observation phase. It retains the
same receiver throttle, pose guard, telemetry freshness checks, PWM ceiling,
and failure cleanup. There is no automatic powered retry. Its three targeted
hardware-free tests reject a one-second cutoff as ten-second success, exercise
the longer observation and shutdown sequence, and retain cap/pose rejection.
These targeted tests do not qualify the complete serial transaction.

Acceptance requires positive PWM receipts spanning at least nine seconds,
followed by a fresh shutdown/zero receipt. This is sampled software evidence,
not proof of continuous electrical output or motor rotation. The runner requires
the candidate identity; exact application readback must precede its use.
The first trial aborted on the 0.5-degree settled-pose deviation check. That
check was then removed from the private props-off runner at the operator's
request; the separate absolute tilt and finite-telemetry checks remain.
The next trial transmitted receiver inputs spanning 10.305 seconds, with
nonzero PWM receipts spanning 9.788 seconds and peak submitted duty 375/2047.
The cutoff receipt missed the powered observation window; cleanup reported
shutdown and zero submitted PWM. The operator did not see sustained rotation.
The runner now has a separately bounded one-second request-only cutoff wait,
without extending powered inputs; seven targeted host tests pass. This change
has not yet been exercised live. Do not use this BEN1 candidate for flight.

## Single-motor isolation profile

`CONFIG_LRRK_BENCH_SINGLE_MOTOR` is opt-in and requires the bench output limit.
Any nonzero sanitized demand selects channel 1 at fixed 200/1000 duty while
channels 2–4 remain zero. Zero demand and fault suppression still zero output.
This removes mixer variation from applied output, not from the recorded sensor
data. The deadline is unchanged and does not renew on rearming. Twenty-eight
driver tests pass, including fixed output, deadline, IMU/failsafe/disarm,
stale-update and peripheral-error stops. Hardware behavior is not yet verified.
