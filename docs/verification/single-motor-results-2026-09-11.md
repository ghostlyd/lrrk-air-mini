# Props-off single-motor observations

These are USB-C bench results, not flight qualification. The operator reports
the board secured, propellers removed, and power switch ON. No flight-battery
qualification is established by these tests.

Each diagnostic selects one motor at fixed 200/1000 duty (409/2047 submitted
LEDC steps), keeps other channels zero, and latches output off ten seconds
after the first eligible nonzero frame. Normal arming and fault stops remain.
No PID values or sensor samples were changed for these tests.

| Channel | Positive PWM receipt span | Operator observation | Peak absolute gyro in captured approximately first second |
| --- | --- | --- | --- |
| 1 | 9.892 s | Continuous, smooth rotation confirmed | 10.86 degrees/s |
| 2 | 9.820 s | Continuous, smooth rotation confirmed | 1.31 degrees/s |
| 3 | 9.772 s initially; 9.871 s on successful retry | Continuous, smooth rotation confirmed on retry | 5.83 degrees/s (initial capture) |
| 4 | 9.924 s | Continuous, smooth rotation confirmed | 6.14 degrees/s |

Receipt spans are sampled host telemetry, not electrical timing measurements.
All four channels reported the selected channel only, followed by shutdown and
zero PWM. The motor-2 host transaction aborted after cutoff because one PWM
snapshot was unavailable; subsequent cleanup reported zero commands and zero
PWM with no driver errors. An unavailable snapshot can result from the driver's
zero-wait observation lock; the exact cause was not instrumented. Motor-1 and
motor-3 and motor-4 successful transactions completed their cutoff and withdrawal checks.

All four frozen 512-record traces were retrieved only after Disarmed and zero
output were confirmed. These traces cover about one second, not the full run.
The earlier mixed-output run reached approximately 245 degrees/s. That large
transient did not recur in these single-channel captures. This comparison does
not yet distinguish multi-motor electrical interference, fixture motion,
vibration, or controller/output interaction.

## Application identity

Application-only flashing was followed by exact readback. Bootloader, partition
table, NVS, settings, and coredump regions were preserved. Raw captures and
flash backups remain private and are not committed.

| Channel | Source commit | Application SHA-256 |
| --- | --- | --- |
| 1 | `ba43bacf8b27865995874baf3f9ef1c9ccfe5b18` | `3924fad26f55687d515fb743029a244b960371459861f9b053cdd4c4294b47fb` |
| 2 | `44b52a281ba790a493f457a22db157914aae4c26` | `50c0a4434083e9ad95dbe5c6aa07a2748dae5d343e45bc03a6301a6a4ca8254d` |
| 3 | `44b52a281ba790a493f457a22db157914aae4c26` | `1c0e26c21f4ed9e116ac3c12f2e7798fc0a8e1218e3dc182bf9897d7bcc74a8c` |
| 4 | `2e3cbfb5cb7afd6234ad719e3173dbbf6c6d4fe8` | `b9abb7363e53495bb752f8bbb44713719e2d9352e3658a20a729362ee877e63d` |

Channels 2 and 3 share a source identity but differ in resolved build-time
channel selection. The source marker alone cannot distinguish their images;
use exact binary readback and applied-channel telemetry.

All four individual physical observations are now confirmed by the operator.
Next: qualify the bounded simultaneous fixed-duty diagnostic before running it
to compare combined load with the earlier mixed-output transient.
Motor direction/corner mapping, the mixed-output transient, flight-battery
qualification, and a normal non-diagnostic flight image remain outstanding.
