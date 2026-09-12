# Fixed-all props-off diagnostic

The USB-C secured-bench transaction completed with the diagnostic application
from source `22586d1b230cd73f59b950ece28fe314656be010`.
Application SHA-256:
`498017285d0f09eb64d5dc12d52f2504f94b3bfd7bc34d48acbee69c61226ff0`.
Exact readback verified the application and preservation of bootloader,
partition table, NVS, settings, and coredump regions.

Resolved configuration: fixed-all enabled, single-motor disabled, 200/1000
per-motor duty, ten-second nonrenewing cutoff, attitude trace enabled.
The 35 native PWM tests include fresh-demand suppression and watchdog expiry
with the last update only one microsecond old. Review identified those coverage
gaps; they were addressed in test-only commit `28bcb7b` without rebuilding the
unchanged application.

## Observations

- Positive PWM receipts spanned 9.832 seconds; the ten-second firmware cutoff
  was observed, followed by zero commands and zero submitted PWM.
- The transaction completed normally with zero write/stop errors. Its final
  state was Armed with shutdown latched and zero output. Later request-only
  retrieval confirmed Disarmed and zero output before downloading the trace.
- The operator confirmed that all four motors ran smoothly and continuously
  together during this trial. This is physical observation, not measured RPM.
  Command telemetry alone is not rotation evidence.

The frozen trace contains 512 records over 1.029717 seconds, including 64
pretrigger records. Peak absolute gyro was 1.2964 degrees/s, with no sample above
20 degrees/s. The earlier mixed-output capture peaked at 245.1437 degrees/s.
All captured accelerometer, gyro, and attitude values were finite.

Of the 448 posttrigger records, 437 showed `[409,409,409,409]` submitted LEDC
counts and 11 showed known, unsuppressed zero output. Thus this is not evidence
of uninterrupted electrical output: sanitized zero demand still stops all
channels. Roll ranged from -0.128 to -0.082 degrees and pitch from 4.505 to
4.546 degrees within this short capture.

## Interpretation and next step

The prior large transient was not reproduced by this fixed-all trial. This
weakens, but does not eliminate, combined-load interference as an explanation.
Different fixture conditions and limited capture duration prevent a causal
conclusion. Do not change PID gains or suppress readings on this evidence.

Next compare the normal mixer path under the same fixture conditions, retaining
the bounded bench ceiling and cutoff. This remains a diagnostic image,
not a flight-qualified controller. Battery qualification, physical corner and
direction mapping, IMU qualification, and normal-image flight validation remain.
Raw captures and backups remain private outside Git.
