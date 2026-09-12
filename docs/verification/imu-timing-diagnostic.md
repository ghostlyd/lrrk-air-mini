# IMU timing diagnostic

Purpose: distinguish data-ready notification timeouts from I2C read failures
after the fixture trace showed all-ones frames followed by a 50 ms delivery gap.
This does not fix or suppress that fault, change PID settings, or alter the
output ceiling/health decisions.

`LiteWingIMUTiming` is a separate single-instance, request-only object:
data ID `0x5AF673A8`, metadata ID `0x5AF673A9`, version 1, 21-byte payload.
Both inbound data and metadata writes are denied by the target unpack boundary.
The existing nine-byte `LiteWingIMUHealth` remains unchanged.

| Offset | Field | Meaning |
| --- | --- | --- |
| 0 | NotificationTimeouts | Saturating count of waits returning no notification |
| 4 | ReadFailures | Saturating count of attempted I2C reads returning failure |
| 8 | LastWaitUs | Latest notification-wait wall time |
| 12 | LastReadUs | Latest attempted-read wall time; zero if no notification |
| 16 | MaxReadUs | Maximum attempted-read wall time in this observation epoch |
| 20 | Version | One byte, value 1 |

First five fields are little-endian uint32. Durations saturate; backward clock
observations use UINT32_MAX. I2C duration includes lock wait and scheduling,
not just wire time. A read returning success with bad bytes does not increment
ReadFailures. Counter resets follow driver observation invalidation; compare
samples only within a known uninterrupted boot/observation epoch.

Packing takes a coherent driver snapshot on request, not a cached object.
No extra periodic publisher or motor commands are introduced. Zero counters
alone do not prove a healthy sensor; read the existing health object and raw
trace alongside these diagnostics.

Native tests simulate a 50 ms read failure, later success, and a 20 ms missing
notification; they check distinct counters, retained maximum, and literal wire
bytes. These are software tests, not live reproduction. Firmware build,
application-only flash/readback, and live timing retrieval remain pending.

## Installed diagnostic and first complete trial

Source `98625a370ffeb67616b0a663577bd32de1999096` built successfully:
880096-byte application, SHA-256
`ebd5026c2059525dc5cbf57fe639cb07a0de83a66f78c6af238c8fcb625dfe19`.
Application-only flash and exact readback passed. Bootloader, partition table,
NVS, settings and coredump matched the pre-flash backup. Startup confirmed
marker `BEN198625a370ffeb676`, Disarmed, zero outputs and live timing v1.

Immediately before the next test, both failure counters were zero and maximum
read duration was 3151 us. The secured, props-off normal-mixer transaction
completed with unchanged limits. Positive PWM receipts spanned 9.838803 s;
firmware shutdown and subsequent twelve zero actuator commands/four zero PWM
values were observed. No output write/stop errors were reported. The final
runner sample remained Armed with shutdown latched; this is not flight
readiness or physical rotation proof. User observation and post-trial raw
trace/timing analysis remain separate evidence.

The user observed only three motors rotating. In 31 baseline PWM snapshots,
channel 4 was zero in 28; its maximum LEDC value was 47. Thus this run is not
an all-four physical motor pass and does not establish a defective fourth motor.
The physical corner corresponding to the user's observation is still pending.

The board subsequently disarmed; all 512 frozen records were retrieved without
reset. At download start NotificationTimeouts was 0, ReadFailures was 5 and
MaxReadUs was 3158. These are cumulative counts across the test and wait before
download, not timestamps of individual failures. This trial did not reproduce
the prior 50 ms read/delivery gap (largest estimator-record gap: 4516 us).

It did reproduce suspect successful reads. Record 76 contains fourteen 0xfe
bytes (all seven signed registers decode as -258). Record 77 contains frames
with twelve and thirteen 0xff bytes. Record 80 then reports gyro
[267.091064, -101.240501, -227.669586] deg/s and PWM [0,409,0,135]. The earlier
record 75 PWM was [0,6,6,0]. This ordering supports sensor-data corruption
preceding the large differential command, but does not identify the electrical
cause or prove all subsequent gyro readings are false.

Next investigation is bus/sensor integrity under motor load, not PID tuning or
raising throttle to make all channels turn. Existing I2C adapter configuration
uses a glitch filter and internal pullups; that source setting is not proof of
actual signal integrity or adequate external pullups. Do not claim live-flight
readiness from a transaction that completed despite corrupted sensor data.
