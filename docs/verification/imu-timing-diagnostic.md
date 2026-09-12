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
bytes. These are software tests, not live reproduction. The subsequent build,
application-only flash/readback, and live timing retrieval are recorded below.

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

## Repeat attempt and bus-design inspection

The requested repeat reused the installed image and unchanged runner. Following
one reset, request-only startup verification reported Disarmed, twelve zero
actuator commands, four zero PWM values, no read failures or notification
timeouts, and MaxReadUs 3087. The runner then stopped during inspection:
reported roll -14.353 degrees and pitch -4.817 degrees exceeded its absolute
10-degree roll/pitch bound. It transmitted zero receiver-input packets and
ended Disarmed with zero outputs. This was not a motor test or evidence about
which physical corner failed to rotate. Fixture leveling remains pending;
the reported attitude is not an independent measurement of physical pose.

Repository design inspection confirms that the V2.6.C production netlist
connects R16 between /SCL and +3V3 and R14 between /SDA and +3V3; its BOM lists
both as 10k. The target currently configures the IMU bus at 400000 Hz. This
establishes the repository design, not the fitted values on the photographed
v1.2 board, nor actual rise time, capacitance or supply stability under load.
Do not infer a proven pullup defect or change hardware from this comparison
alone. Preserve the corrupt-frame trace as the baseline for a controlled
bus-integrity comparison; no PID, bus-speed or output-limit change was made.

## Repeat after fixture adjustment

The unchanged runner completed after the owner reported the fixture ready.
Settled reported roll/pitch were -3.816/-0.654 degrees. Positive PWM receipts
spanned 9.885504 seconds, followed by shutdown and verified zero commands/PWM.
The 32 baseline snapshots had nonzero channel counts [29,28,2,28] and maximum
LEDC values [313,295,33,217]. The owner initially identified channel 1 as not
turning, then explicitly withdrew confidence in that identification. Physical
corner/rotation remains unconfirmed; channel 3 was commanded zero in 30 of
32 snapshots. Do not infer measured rotation from these command snapshots.

A first trace request stopped because the board was still Armed. A later
request confirmed Disarmed and zero outputs and retrieved all 512 records
without reset. Timing counters were NotificationTimeouts=0, ReadFailures=6,
MaxReadUs=3221; counts span the boot, not exclusively the motor interval.
Records 221 and 223 contain frames with twelve and thirteen 0xff bytes.
Record 225 reports gyro [-153.682,-148.705,-373.178] deg/s and submitted PWM
[0,409,0,409]; record 226 reports [409,409,0,409]. This reproduces suspect
sensor bytes preceding a large gyro excursion and differential output. It
does not establish whether subsequent excursions are physical or erroneous,
or identify the electrical cause. A channel-isolation retry is deferred in
favor of investigating this repeated sensor-integrity evidence.

## Controlled I2C-rate comparison

Commit `c128a38` made the IMU I2C clock an explicit Kconfig value, bounded to
100000--400000 Hz, with the existing 400000 Hz default. Focused contract tests
and both ESP-IDF builds passed. Matched ten-second bench configurations used
the same output ceiling, duration and attitude trace:

| image | I2C clock | application SHA-256 | deployment result |
| --- | ---: | --- | --- |
| control | 400 kHz | `e36002babf89deaa89f83ba95fcdd8e5c9da72a138f8edda71abb1db14bdba5e` | application-only restore, exact readback |
| comparison | 100 kHz | `4745b054bcd3bdd6c58738869b1e33f9d52ed8ad15cb5628b5b30e65cb574869` | exact readback, rejected before motor test |

The 100 kHz image booted but produced a repeatable UART CRC mismatch in the
request-only startup stream after four valid frames, so it was not used for
actuation. The 400 kHz image was restored and passed request-only startup with
Disarmed, twelve zero actuator commands, four zero PWM values and no startup
alarm. Its matched motor transaction then stopped at the existing Attitude and
Stabilization `Error` alarms as baseline input began; cleanup confirmed zero
PWM. This does not identify whether the sensor corruption is electrical,
timing-related, or an estimator/firmware interaction.

The board is currently running the restored 400 kHz image, reset-verified
Disarmed with zero actuator/PWM output. Do not treat either the 100 kHz UART
failure or the 400 kHz alarm stop as flight evidence. Further work requires
isolating the raw MPU6050/I2C fault before a live-flight image can be claimed.
