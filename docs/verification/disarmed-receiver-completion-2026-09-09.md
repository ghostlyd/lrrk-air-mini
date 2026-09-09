# Disarmed receiver-loss probe: bounded-completion follow-up

## Result: PASS for sampled disarmed receiver observations only

One separately reviewed, props-removed, battery-absent USB trial ran with the
diagnostic at `9fa4c6f125098a936b4a040f3a875e072ce50b63`. The CLI exited 0 with
`PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY`. It observed connected neutral input,
disconnected timeout, recovered neutral input, and disconnected timeout again.
The finalized capture passed strict framing validation, including its last CRC.

This supplies the missing disarmed physical observation for
[issue 23](https://github.com/ghostlyd/lrrk-air-mini/issues/23), alongside the
[source/integration checks](gcs-receiver-freshness-2026-09-09.md) and
[verified candidate installation](control-fixes-usb-install-2026-09-09.md).
It does **not** establish exact receiver timeout latency, electrical motor-cut
timing, powered operation, arming readiness or flight readiness. The earlier
[first trial](disarmed-receiver-probe-2026-09-09.md) remains FAIL/inconclusive;
its incomplete capture was not repaired or relabeled.

## Authority and unchanged hardware boundary

The owner had confirmed all propellers removed and the battery absent. Fresh
prelaunch checks matched the selected USB bridge and found no serial owner on
either callout or tty. The diagnostic checkout was clean at the reviewed commit.
The probe used 57600 baud, deasserted DTR/RTS before opening, and closed its
handle. A subsequent `lsof` check found no owner on either serial node.

The installed application attestation remained SHA-256
`3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8`.
The retained image hash was rechecked; this was not a new live flash readback.
This follow-up issued no flash/reset command, settings write, arm request or
motor-output command. It sent only the diagnostic's restricted telemetry
handshake/read requests/ACKs and minimum-throttle neutral receiver packets.
No packets, including ACKs, are sent during final frame completion. No automatic
retry, API-key access or paid AI request occurred. **Always Disarmed remains set.**

## Actual sampled observations

The report recorded 56 neutral-input write attempts, not measured electrical
delivery. Each permitted receiver packet held minimum throttle, neutral axes
and the first mode position. Host timings include preflight and are not
firmware timestamps or electrical latency measurements.

| Phase | Start, host seconds | End, host seconds | Consecutive endpoint matches |
| --- | ---: | ---: | ---: |
| Input 1 | 2.149817333 | 3.355558208 | 9 connected/neutral |
| Silence 1 | 3.355558208 | 4.557131666 | 9 disconnected/timeout |
| Input 2 | 4.557131666 | 5.763440791 | 8 connected/neutral |
| Silence 2 | 5.763440791 | 6.968344750 | 8 disconnected/timeout |

Total reported host time was 6.969542875 seconds. Separate offline decoding
against the verified pinned codec/XML confirmed:

- 34 FlightStatus samples, all Disarmed/Stabilized1.
- 39 ActuatorCommand samples, each with its first four channels zero. Software
  command values alone do not prove voltage, duty cycle or motor-stop latency.
- Six samples each of ManualControlSettings, FlightModeSettings,
  ActuatorSettings and SystemSettings. Every selected settings check passed;
  each object's raw payload was byte-stable. Checks included Always Disarmed,
  enabled sanity checks and QuadX/Throttle SystemSettings.
- 60 ManualControlCommand samples: one initial zero/default, 33
  disconnected/timeout, 18 connected/neutral, four disconnected with neutral
  channels and four connected with timeout channels. Transition samples are
  not fully matching endpoints. All 59 non-initial samples had Throttle and
  Thrust = -1. The final sample was disconnected/timeout and neutral-safe.
- 40 SystemAlarms samples: the first six reported CPUOverload and Actuator
  Critical, followed by 34 with both OK. Receiver alarm runs were Warning 12,
  OK 8, Warning 7, OK 7, Warning 6. BootFault stayed Uninitialised in all 40.
  Names were mapped from pinned XML element names. Preflight waited for fresh
  nominal observations; this does not resolve
  [startup fault reporting, issue 27](https://github.com/ghostlyd/lrrk-air-mini/issues/27).

The replay verifies saved bytes and selected state sequences; it cannot
independently recreate host receive timing from this timestamp-free raw file.
Phase timestamps and cadence acceptance above come from the reviewed runner.

## Capture integrity and bounded final frame

The private capture contains 30,437 bytes with SHA-256
`220e26e2ba586a1975f84c9d3860ecbedcb230b5e5871e31c89fecb91e7f2814`.
Offline size/hash checks matched the finalized report. Initial synchronization
discarded 112 bytes; this is not a lossless-from-open capture.

At the pre-completion cut point, offline decoding found 31 pending bytes of
an instance 0 AttitudeState frame totaling 39 bytes including CRC. The runner
read exactly the remaining eight bytes. Feeding those saved bytes completed
one AttitudeState frame and left zero pending bytes; strict `finish()` passed.
The report records host completion from 6.968356208 to 6.968422875 seconds,
inside the 250 ms completion bound and 21-second total trial bound. This very
short host interval is not a measurement of sensor, UART or safety latency.

The private trial directory is mode 0700 and capture/report files are mode
0600. Raw capture, complete settings and device identifiers are not published.

## Source verification and remaining gates

Independent review accepted the bounded-completion implementation and its
failure-path byte/time reporting. Ten parser tests and 44 focused probe tests
passed; the latter used the intended ESP-IDF Python 3.9 and actual pinned
codec/XML. The full 83 assistant + 155 port tests passed with no skips. GitHub
host, source and SDK checks passed on the exact physical diagnostic commit.
The IDF graph was refreshed with reconfigure only, not a firmware build/flash.

Regressions cover partial headers, bytewise tails, exact frame-boundary reads,
no completion transmissions, corrupt/missing/late tails, changed settings,
Armed/nonzero-output telemetry, contrary final receiver state, and retained
failure metrics. The assistant remains receive-only/advisory; this is not a
general writable drone API.

Arming remains disabled. Full-board storage-fault integration (issue 26),
measured electrical cutoff timing (issue 19), startup fault reporting
(issue 27), physical motor mapping, IMU orientation/calibration, compatible
battery/charging checks, powered tests and flight remain separate unpassed
gates. Closing the receiver-freshness issue does not close any of those gates.
