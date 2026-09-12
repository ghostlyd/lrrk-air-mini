# USB-only bench cutoff trial

## Scope and installed image

The owner confirmed USB-C-only power. The previously confirmed props-off,
secured bench setup remained the scope; this was not a flight attempt.
One trial was executed, without reset/retry or settings changes during it.

Bench source: `53e764731b0d92a6afa2992dd5dbc3aac7a404b5`, merged by PR #86.
Live marker: `BEN153e764731b0d92a6`.
Application SHA256:
`d8b232144e4e47609e92706c6f065db4cfb95858b1ddee624cb4d10b70b9befb`.
Application-only flash and exact readback preceded the trial; bootloader,
partition/NVS, settings and coredump regions were unchanged. The private
8 MiB recovery backup and raw telemetry were not uploaded.

## Observations

Normal yaw-right arming was observed. At zero throttle after arming, settled
attitude was approximately roll -4.551 degrees, pitch -0.363 degrees. The
existing pinned receiver mapping selected pose-aligned inputs; no PID,
orientation, arming-policy or receiver-timeout settings were changed.

Relative times below are host receipt/write times, not device or electrical
timestamps. The finite host transaction completed in 7.93 seconds.

| Event | Time (seconds) | Evidence |
| --- | ---: | --- |
| First low-throttle powered receiver write | 5.0506 | 8% requested throttle; no roll/pitch/yaw excursion phase |
| Nonzero PWM sample | 5.5487 | Requested `[79,79,78,80]`; successfully submitted `[162,162,160,164]` out of 2047 |
| Last powered receiver write | 6.0876 | 26 powered writes total, approximately 40 ms cadence |
| Firmware shutdown sample | 6.1180 | Requested `[81,78,79,78]` but submitted `[0,0,0,0]`; `shutdown` suppression |
| Neutral-command zero proof | 7.0681 | Connected low-throttle observations and all twelve actuator commands zero |
| Receiver withdrawal proof | 7.9241 | Receiver disconnected, actuator commands zero, FlightStatus still Armed |

The shutdown report arrived 1.0674 seconds after the first powered host write.
This is **not** a measurement of motor stop latency or precise electrical
on-time: UART transport, request scheduling, and sparse PWM snapshots intervene.
The report does show the output gate holding zero despite remaining nonzero
controller demand. Final available PWM observation had four known zero outputs,
zero write/stop errors and shutdown suppression. The normal arming timeout
remained enabled; the end-of-trial Armed state is not an indefinite state claim.

During the powered phase, sampled roll stayed within -4.5682 to -4.5610 degrees
and pitch within -0.4152 to -0.3538 degrees. The previous large transient was
not reproduced in these samples. Sparse telemetry cannot exclude unobserved
short transients. This trial did not exercise the 20% ceiling: its observed
applied duty was approximately 8%, below that ceiling.

## Verification boundary

The private test used normal GCSReceiver inputs plus bounded telemetry requests,
handshakes and acknowledgements. No settings, metadata or direct actuator writes.
Four local cutoff-validator tests and nine existing pose/pacing/zero-evidence
tests passed before execution. Physical rotation confirmation is still pending
from the owner; PWM API success is not shaft-speed measurement.

Prior fitted corner/direction evidence is already recorded in
[the final configuration record](final-flight-configuration-2026-09-10.md).
This trial neither repeats that direction measurement nor invalidates it;
assembly changes would require revalidation. Remaining: physical feedback on
this trial, actual stopping behavior, saturation-cause investigation,
power/battery qualification, and restoration/qualification of a flight-profile
image before active flight.
The BEN1 bench image deliberately latches outputs off after its first interval
until reset, and must not be used for flight.
