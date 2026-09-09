# Disarmed receiver-loss bench probe

This is a scoped extension of the approved LiteWing bench-validation design,
under the owner's standing autonomous repository and hardware-test authority.
It does not enable arming. Implement the tightly coupled safety controller and
serial harness locally with test-first development; obtain independent review
before physical use. Existing firmware and the receive-only AI API are unchanged.

## Contract

- Separate diagnostics command, not a general GCS or an AI tool. No settings,
  metadata, FlightStatus, actuator or persistence writes. Only telemetry status,
  selected read requests, ACKs and one exact GCSReceiver packet are permitted.
- Verify the pinned upstream Python codec/XML tree before import. Use the
  repository's strict receive-only frame decoder; bound initial frame sync,
  reject corruption after synchronization. CRC is not authentication.
  Execute/parse the verified bytes themselves, never cached bytecode or a
  second filesystem read. Unresolved framing at completion prevents PASS.
- Exact eight-channel packet: `[1000,1500,1500,1500,1000,1500,1500,1500]`.
  Throttle minimum, neutral axes and first mode position; never arbitrary CLI
  channel values. Verify actual settings map the first five channels to GCS
  throttle/roll/pitch/yaw/mode with min1000/neutral1500/max2000.
- Before input: fresh Always Disarmed, sanity checks enabled, Disarmed flight
  status, Stabilized1/manual thrust, zero first-four motor commands, motor
  minima/neutral0/max1000, MotorsSpinWhileArmed FALSE, QuadX/Throttle SystemSettings,
  and disconnected timeout receiver evidence. Read SystemSettings explicitly.
- Freshness limits: fast status/actuator/manual/alarms <=0.75s; settings <=2.5s.
  Full raw settings payload bytes must not change once captured. Critical/Error alarms
  reject input. BootFault Uninitialised and unused sensors are explicitly only
  tolerated for this unarmed USB/no-battery test, not treated as flight ready.
- Input1 (1.2s), silence1 (1.2s), input2 (1.2s), silence2 (1.2s), preceded by
  at most15s of read-only preflight. Input cadence40ms; do not catch up bursts
  after a missed deadline. Missed input interval >=80ms aborts transmission.
- Require >=3 consecutive connected neutral-command observations ending each input phase
  and >=3 consecutive disconnected timeout/failsafe observations ending each silence phase.
  Phase evidence must be received after phase entry; preflight cannot count.
- After the four phases, finish only an already-pending frame within250ms and
  the unchanged21s total trial deadline. Read no farther than its boundary;
  complete partial length headers before requesting the remaining bytes.
  No packets at all may be transmitted during completion, including ACKs.
  Preserve all CRC/schema/settings/safety/freshness checks and require final
  disconnected timeout receiver state. Late, absent, malformed or unsafe tail
  data fail. Report additional bytes and host-relative completion times. Do not
  claim coverage of subsequent unread telemetry or repair an earlier FAIL.
- Every failure latches, ends input, and prevents PASS. Continue no control
  writes in cleanup; close only the owned serial handle. No automatic retry.
- Exact USB VID1a86/PID7522, explicit callout and location supplied by operator;
  fixed57600 baud, DTR/RTS false before opening. Probe never resets/flashes.
- Operator confirms props removed, battery absent, exact installed reviewed
  firmware (PR31 installation evidence). Local firmware digest verification
  alone is not a device identity or installed-firmware attestation.
- Private new capture/report paths, exclusive creation, mode0600, maximum1MiB
  capture and21s trial deadline checked around I/O and after port close. This
  is not an OS-call preemption guarantee. Batch age starts before serial read;
  disk/decoder delays cannot refresh observations. Final disk publication is
  outside the trial timer and requires successful capture/report flush/fsync/close.
  Publish report.json without overwrite; report.pending is never a final result.
  Report phases, observation counts and
  host-relative timings; do not claim firmware/electrical 100ms stop latency.

## Acceptance

Behavioral host tests cover wrong settings, stale/armed/nonzero data, latch,
missing transitions, neutral-only transmission, short writes, corruption,
clock regression, missed cadence, resource bounds and port cleanup. Pinned
schema integration runs in source CI. Mocked serial tests prove host behavior,
not firmware or electrical behavior. Physical acceptance requires the reviewed
probe's real input/silence/recovery/silence report on the installed candidate.
