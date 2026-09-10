# USB software-arm and bounded nonzero motor-command proof

## Result

Later state: the temporary RAM-only `Always Armed` proof below has been
superseded by the persisted normal-arming transaction in the
[final flight-configuration record](final-flight-configuration-2026-09-10.md).
That later transaction uses `Yaw Right`, verifies persistence after reset,
reaches Armed with bounded nonzero commands, and closes on a reset-neutral
Disarmed/zero-output snapshot. The record below remains the earlier historical
command-path evidence.

The installed NinjaPilot LiteWing application reached `FlightStatus=Armed`
and emitted six checksum-valid, nonzero `ActuatorCommand` observations while
running from USB-C. The largest observed command was `128/1000`; the peak four
motor channels were `[128, 0, 0, 118]`. The propellers were removed, the board
was contained, and no battery was connected.

The transaction then returned the receiver input to its exact low frame,
observed 11 zero-command samples after the final nonzero sample, stopped
receiver writes, and waited for receiver timeout. The last in-session
telemetry was:

| Object or field | Last observed value |
| --- | --- |
| `FlightModeSettings.Arming` | `Always Armed` |
| `FlightStatus.Armed` | `Armed` |
| `ManualControlCommand.Connected` | `False` |
| `ManualControlCommand.Throttle` / `Thrust` | `-1.0` / `-1.0` |
| `ActuatorCommand` motor channels 1..4 | `[0, 0, 0, 0]` |

The accepted probe result was
`ARMED_NONZERO_MOTOR_PROVEN_LEFT_ARMED_RAM_ONLY`. Per the operator's explicit
instruction, the probe did not restore `Always Disarmed`, did not send an
application reset after arming, and did not write settings persistence. “Left
armed” describes only the final telemetry received before the serial link was
closed. A later investigation corrected the terminal-state interpretation:
closing the link was not observed to disarm the controller, but a conventional
pyserial reopen is not passive on this board. The CH340 DTR/RTS auto-reset
circuit restarted the ESP32-S3; the first `SystemStats.FlightTime` after that
reopen was 402 ms and the persisted `Always Disarmed` value was loaded. A later
POSIX file-descriptor open that did not manipulate modem-control lines observed
uptime continuing from 130,473 ms. Therefore, terminal RAM state must be checked
in the original session or through a reset-neutral open. The earlier blanket
claim that ordinary serial reconnection preserved the state is withdrawn.
“RAM-only” still means the transaction did not persist the setting and does not
establish arming state after a reset or power cycle.

## Reviewed transaction bounds

The one-shot probe enforced all of these conditions before opening the serial
device:

- exact installed application SHA-256
  `d7392031e9e06c39bcb503e0feb834942588b10b99cdfeeaa3248fbedae0ff31`;
- propellers removed, physical containment, and an explicit acknowledgement
  that USB-C can power the motors;
- a byte-exact outbound allowlist limited to named reads, telemetry handshake
  and acknowledgements, one RAM-only `FlightModeSettings.Arming` transition,
  and the two receiver frames below;
- no `ObjectPersistence`, direct `ActuatorCommand`, arbitrary settings, flash,
  erase, eFuse, or reset operation;
- an 800 ms maximum pulse phase and a hard observed-command ceiling of
  `200/1000`.

The exact GCS receiver frames were:

```text
low   = [1000, 1500, 1500, 1500, 1000, 1500, 1500, 1500]
pulse = [1510, 1500, 1500, 1500, 1000, 1500, 1500, 1500]
```

Only channel 1 changed. The decoded `ManualControlCommand` represented the
pulse as throttle/thrust approximately `0.02`, while the other control axes
remained neutral. The flight stack—not the host probe—produced the observed
mixed `ActuatorCommand` values.

## Decoded observations

An independent offline pass scanned checksum-valid frames with byte-verified
NinjaPilot framing and UAVObject XML at pinned revision
`ac77304a58de6c8bd552f94668b46903adb71cb2`. It decoded 857 valid frames,
including 34 `FlightStatus`, 36 `ActuatorCommand`, 30
`FlightModeSettings`, 51 `ManualControlCommand`, and 37 `SystemAlarms`
observations.

Every nonzero actuator observation had `FlightStatus=Armed`,
`Arming=Always Armed`, a connected receiver, and the bounded 0.02
throttle/thrust command:

| Valid-frame ordinal | Motor channels 1..4 |
| ---: | --- |
| 533 | `[71, 0, 0, 64]` |
| 538 | `[74, 0, 0, 66]` |
| 543 | `[80, 0, 0, 70]` |
| 567 | `[113, 0, 0, 103]` |
| 596 | `[127, 0, 0, 114]` |
| 601 | `[128, 0, 0, 118]` |

The 11 following `ActuatorCommand` observations were all zero on channels
1..4 and all remained Armed. The final one was paired with the timed-out,
disconnected receiver state summarized above.

## Evidence handling and reproduction

The private capture is 31,912 bytes with SHA-256
`cce31d2ef701a230827b7b1cf54ca09124a9839ecb669f87a6144c5150b3fcf8`.
It is intentionally not committed because the full UART stream is retained as
private bench evidence. The repository contains a sanitized record with the
six nonzero samples, every post-pulse zero sample, terminal state, bounds, and
provenance hashes:

[`evidence/armed-nonzero-motor-2026-09-09.json`](evidence/armed-nonzero-motor-2026-09-09.json)

Validate that record without hardware access:

```sh
python3 ports/ninjapilot-litewing/diagnostics/arm_motor_evidence.py \
  docs/verification/evidence/armed-nonzero-motor-2026-09-09.json
```

The expected result is `status=PASS`, six nonzero samples, a peak of
`[128, 0, 0, 118]`, 11 post-pulse zero samples, and terminal state
`ARMED_ZERO_RECEIVER_TIMED_OUT`. The private probe's 23 host-only guard and
state-machine tests also passed immediately after the live transaction.

## Claims not established

This evidence clears the narrow **software arming plus nonzero commanded
output** gate. It does not establish electrical PWM duty, electrical cutoff
latency, physical motor rotation during this particular transaction, motor
corner mapping, IMU orientation, battery operation, propeller suitability,
airworthiness, or flight readiness. There is still no flight battery.
