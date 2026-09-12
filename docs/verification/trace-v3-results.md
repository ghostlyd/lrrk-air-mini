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
