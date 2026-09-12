# Raw-sample bench result

Application c556b20869ef5ac4e0938e355db4f4ab31b11e08, SHA-256
60942410dc91d0e2067f4557a977af142f9c224ca28e046d785980fbabd3d59c,
879568 bytes. Application-only flash and exact readback passed, preserving
bootloader, partition table, NVS, settings and coredump. Startup was Disarmed
with zero commands/PWM and a rolling trace.

The ten-second normal-mixer test completed; positive PWM observations spanned
9.885140 seconds. Automatic cutoff and subsequent zero outputs were observed,
with no PWM write/stop errors. Request-only retrieval later confirmed Disarmed
and zero outputs. All 512 frozen records passed sequence/time validation;
511 have complete provenance and one has four contributors, explicitly truncated
to three retained raw frames. Capture spans 957410 microseconds.

The original 262144-byte download allowance was exceeded by v3 plus background
telemetry. A 524288-byte allowance, with the same 60-second deadline, retrieved
the existing frozen capture. No repeat motor test or reset was needed.

## Findings

Peak published gyro Y: 268.835602 deg/s at record 250. Its raw gyro register
count is 4347, corresponding to pre-bias Y 265.060974 deg/s. Applied Y bias is
3.774628 deg/s. The anomaly exists in the returned register bytes.

Across all complete records, applying the actual body transform (Y, X, -1-Z),
averaging contributors and dividing by 16.4 reproduces all pre-bias axes with
maximum error 0.00000577 deg/s. This checks acquisition-to-estimator arithmetic;
it does not prove that the read bytes represent accurate physical motion.

The event integrates to about 1.4006 degrees of pitch over records 248–262.
Attitude pitch changes from 4.5157 to 5.6838 degrees; this is not independent
confirmation because the estimator consumes the same gyro. Accelerometer data
also changes. Brief movement/vibration in the suspended support remains a
plausible explanation alongside sensor/power/bus interference.

Next discriminating test: repeat the same bounded test with the PCB rigidly
supported on a nonconductive fixture, keeping props removed, motor shafts clear,
USB power and software unchanged. Do not retune PID or suppress sensor values
based on this result. Live-flight readiness remains unverified.

## Nonconductive-fixture comparison: aborted

The next run reused the installed image and output ceiling after a reset and
verified Disarmed/zero-output startup. The user reported the PCB on a
nonconductive fixture. Post-arm settled roll/pitch were -6.4927769/0.2977866
degrees. Four powered receiver writes occurred at host elapsed times
6.309611 through 6.433743 seconds. This was not a ten-second completion.

Reported roll changed from -6.524069 at 6.370028 seconds to -10.563583 at
6.452716 seconds, tripping the runner's absolute ten-degree guard. The sparse
gyro telemetry did not capture the intervening event; it cannot distinguish
actual fixture motion from a sensor/acquisition event.

Failure cleanup wrote neutral once and requested actuator/PWM status once,
then only read for 0.75 seconds. The resulting PWM reply at 6.490726 seconds
was [172, 0, 0, 151] LEDC counts; the actuator reply at 6.498063 was
[84, 0, 0, 74] for the four motor channels. Neither object was requested again.
Receiver telemetry later showed throttle -1 at 6.729266 seconds and Connected
False at 6.980216 seconds. Consequently the final nonzero summary is stale
relative to those receiver observations, but neither receiver observation
proves zero PWM. The runner also silently discards cleanup exceptions and
does not report whether cleanup obtained fresh zero evidence.

A subsequent download refused because the board was still Armed. A hardware
reset followed; startup verification confirmed Disarmed, twelve zero actuator
commands and four zero PWM values. That reset cleared the frozen raw trace,
so no raw-frame conclusion can be drawn from this comparison.

Required runner correction before a powered retry: independently bounded
cleanup with checked neutral writes, paced repeated output-status requests,
fresh zero-output evidence, and explicit cleanup failure reporting. Preserve
the original failure and stop transmitting powered commands immediately.
Do not bypass the tilt guard or retune the controller to hide this event.

The host cleanup correction is implemented in `diagnostics/bench_cleanup.py`
and integrated into the private v3 bench runner. It sends only the supplied
neutral packet and two status requests, using checked writes, 40 ms neutral
cadence, 100 ms status-request cadence, and an independent two-second deadline.
Confirmation requires post-cleanup, at-most-250-ms-old zero actuator/PWM
observations with no reported output errors. Exceptions and timeout are returned
explicitly; the original trial failure remains separate. Six hardware-free
regressions cover delayed request-only replies, stale replies, absent zero,
PWM faults, short writes and parser errors. They do not establish live STOP
latency or validate the whole runner. Live cleanup verification remains pending.

### Live neutral-only cleanup check

A subsequent request-only preflight again confirmed the installed marker,
Disarmed status and zero outputs. A separate disarmed-only serial check then
called the production cleanup helper with the literal neutral receiver packet
and actuator/PWM requests. It obtained fresh zero evidence in 0.041046 seconds
with four checked writes and no cleanup error. No arm or positive-throttle
packet exists in that check. This validates live request/response integration,
not stopping latency from powered operation.

The following normal-mixer attempt failed during initial framing after 65
received bytes (`invalid packet length`), before any receiver input: zero
control packets, no completed phases. It did not exercise motors or powered
cleanup. Preserve strict framing validation; investigate startup stream
synchronization before another retry. The prior disarmed verification is not
a fresh status sample from this failed connection.

Offline examination of the 65-byte failure capture rejects a simple false
initial-sync explanation: offsets 4 and 17 each contain a complete 12-byte
`ReceiverActivity` frame plus valid CRC. At offset 30 the next header begins
with sync/type 0x3c/0x20 but declares length 1, below the ten-byte minimum.
Strict rejection after synchronization is correct. This does not localize
corruption to the MCU, bridge, driver, or host tty configuration.

The inspected PIOS COM path serializes sends with `sendbuffer_sem`; the USART
adapter drains its callback into a local buffer and calls `uart_write_bytes`.
The adapter does not check that function's return value. That is a candidate
for a separate transmit-error diagnostic, not proof it caused these bytes.
No parser tolerance, firmware, PID, or output ceiling was changed during this
investigation. A request-only follow-up can establish current telemetry health
but cannot retroactively repair the rejected capture.
