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
