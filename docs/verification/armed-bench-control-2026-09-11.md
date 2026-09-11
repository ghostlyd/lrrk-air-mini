# Normal-armed bench control observations

## Scope

The operator authorized active normal-armed motor testing on the secured bench.
These are live flight-stack command observations, not RPM, electrical duty-cycle
measurements, battery qualification, hover, or free-flight evidence. The board
was not flashed, reset, calibrated, or reconfigured during these transactions.
Live FirmwareIAPObj description matched `LRRK4fb49389076b4379`; this marker check
does not replace the earlier byte-equal application readback.

## Completed transaction

The finite transaction used the pinned UAVTalk codec and literal GCSReceiver
packets, with fresh configuration/status validation, normal yaw-right arming,
and a 40 ms input schedule. FlightModeSettings remained Yaw Right, 1000 ms arming
sequence, 30000 ms armed timeout, sanity checks enabled. QuadX/Throttle and the
Stabilized1 Attitude/Attitude/Rate/Manual tuple were observed live.

The current receiver profile has three mode positions: raw channel 5 at 1000
selects Stabilized1; 1500 would select Stabilized2. The test explicitly selected
the first position rather than assuming the neutral switch value selects it.

After three connected low-throttle observations, normal arming reached Armed.
Fresh Armed/zero-command observations preceded the powered phase. The secured
pose was approximately roll -4.5 degrees, pitch -8.6 degrees. For this static
fixture, the pilot input requested that pose instead of asking the immobilized
board to become level: raw roll/pitch 1449/1412 map to -4.51/-8.58 degrees with
the observed 55-degree limits, zero expo, and 0.02 subtractive deadband. The pose
match was checked before and during the pulse. This is not a saved trim or a
calibration adjustment.

Raw throttle 1510 produced observed normalized throttle 0.02. It is **not** a
claim of 2 percent physical motor duty. The 0.6-second host transmission window
was bounded separately from board input expiry and physical response.

- Transaction duration: 4.031 seconds; 64 receiver input packets.
- Received bytes: 18,748; initial synchronization discard: 40 bytes.
- All four channels produced nonzero commands; per-channel peaks: **2, 18, 42, 23**.
- After deliberate receiver-stream withdrawal, telemetry reported receiver
  disconnected and all twelve actuator slots zero, while FlightStatus remained
  **Armed** at the final observation.
- No settings, metadata, persistence, FlightStatus, or direct ActuatorCommand
  writes were sent. Normal automatic-disarm behavior was not disabled.

The final Armed observation is historical; it is not a promise that the board
remains armed after the session and configured timeout.

## Failed attempts retained

1. A level-target test reached Armed and accepted throttle 0.02. Reported motor
   commands rose through `[152,45,0,0]`, `[180,55,0,0]`, then `[215,63,0,0]`.
   The last sample exceeded the test's reactive 200-command ceiling. The test
   aborted, attempted neutral, and closed. Seven follow-up actuator samples
   independently showed all twelve slots zero; no Critical/Error alarms were
   reported. A secured nonlevel pose versus a level target is consistent with
   increased corrective demand; the later pose-matched result supports that
   interpretation without proving it was the only contributor.
2. The first pose-matched attempt ended before arming because a fixed 0.4-second
   wait had not established receiver connection. It sent ten neutral packets
   and observed zero outputs. The harness was changed to wait for three actual
   connected low-throttle samples within a two-second deadline, consistent with
   the receiver's valid-input hysteresis and asynchronous telemetry publication.
3. The next attempt stopped during initial framing before any receiver input.
   Its 93-byte capture contained overlapping CRC-valid candidate frames. The
   existing strict parser was not weakened; a later fresh session succeeded.
   Initial synchronization ambiguity remains a distinct diagnostic finding,
   not something the completed motor transaction proves fixed.

The ceiling detects reported commands after the fact; it is not a firmware or
electrical hard cap. Raw captures, hardware identity, and operational scripts
remain private outside Git. Controlled flight still requires its own physical
power, propeller, pilot-link and flight-envelope qualification.
