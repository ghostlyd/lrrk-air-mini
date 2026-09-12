# Normal-mixer trace v2 bench result

Application source: `2a4e434`; application SHA-256:
`c40c160d34918e296f5a5da4a01901493373d5c7a45aac558dabf6d19f88fbb4`.
Application-only readback matched; bootloader, partition table, NVS, settings
and coredump regions were preserved. Startup was Disarmed with zero outputs.

The bounded trial completed with positive PWM observations spanning 9.884 s,
automatic cutoff and subsequent zero actuator commands/PWM. No PWM write or
stop errors were reported. The board subsequently reported Disarmed during
request-only retrieval of all 512 frozen trace records (1.009592 s).

The first attempt aborted on a CRC error before any receiver input. A separate
five-second status check passed before the successful retry. CRC checking was
not relaxed. Intermittent startup framing corruption remains unresolved.

## Gyro result

At trace index 70, pre-bias Z was 285.792694 deg/s; effective applied Z bias
was 0.110352 deg/s; published gyro Z was 285.903046 deg/s. The spike therefore
predates adaptive bias application. Across all records, reconstruction error
for Gyro minus PreBias minus AppliedBias was at most 1.20e-7 deg/s.

The first large pre-bias Z sample (76.707 deg/s) occurs 1,182 us after the
first nonzero PWM snapshot, while submitted PWM is [2,4,0,0]. At the peak
(4,442 us after trigger), PWM is [409,0,409,0]. Eight records exceed 20 deg/s.
These are independently timed software snapshots, not electrical timing or
proof of causality. Accelerometer values also change around the event.

The 14-byte decoder uses explicit big-endian signed conversion; the driver
orients and copies samples into a queue, which Attitude averages and scales.
No conversion defect is established by this inspection. PreBias is downstream
of acquisition, averaging, scaling, temperature compensation and board rotation;
it cannot distinguish sensor motion/noise from bus or intermediate corruption.

Next discriminating measurement: correlate raw acquisition bytes and sample
sequence with the estimator input, without changing PID/filter settings or
discarding the anomalous samples. The operator clarified the physical result
as "continuous steady rotation, I think." This is a tentative positive
observation, not a definitive speed-consistency measurement.
This result does not establish live-flight readiness.
