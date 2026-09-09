# Disarmed receiver-loss probe: first physical trial

## Result: FAIL / acceptance remains inconclusive

One props-removed, battery-absent USB trial ran with the reviewed diagnostic
at `1ec2973d3feea409bb05997c1aac6d2fae1e1cd2`. All four expected sampled
receiver phases were observed, but final strict framing validation rejected
an incomplete trailing frame. The CLI exited2 and published a FAIL report.
**This is not receiver-loss acceptance, arming enablement or flight readiness.**

The source instrument correctly refused to turn a valid capture prefix into
a complete PASS. It did not retry. [Issue23](https://github.com/ghostlyd/lrrk-air-mini/issues/23)
remains open. The next capture-boundary improvement must be separately tested
and reviewed; do not drop the trailing bytes, relax CRC checks or relabel this
run as passing.

## Authority and unchanged hardware boundary

This one bounded USB trial stayed within the owner's hardware-test authority.
The owner confirmed all four propellers removed with the battery absent. The
trial deliberately kept **Always Disarmed**. Before opening, the exact USB bridge VID/PID, callout and
location matched the selected device; `lsof` found no owner on either callout
or tty. The diagnostic checkout was clean at the accepted commit.

The installed application attestation remained SHA-256
`3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8`, from the
[previous verified installation](control-fixes-usb-install-2026-09-09.md).
The retained local image still matched that hash. That local check was not a
new live flash readback. This session issued no flash/reset command, settings
write, arm request or motor-output command. The probe used57600 baud with
DTR/RTS deasserted before open and closed its handle at the end. A subsequent
`lsof` check again found no owner. No API key or paid AI request was used.

## Actual sampled observations

The report recorded55 neutral-input write attempts. The only permitted receiver
packet held minimum throttle, neutral axes and the first mode position.
Host timings include read-only preflight; they are not electrical timing.

| Phase | Start, host seconds | End, host seconds | Consecutive endpoint matches |
| --- | ---: | ---: | ---: |
| Input1 | 2.148737 | 3.354765 | 9 connected/neutral |
| Silence1 | 3.354765 | 4.555332 | 9 disconnected/timeout |
| Input2 | 4.555332 | 5.756478 | 8 connected/neutral |
| Silence2 | 5.756478 | 6.959330 | 8 disconnected/timeout |

Total reported trial time was6.961160459s. Offline decoding of the preserved
capture independently confirmed:

- 34 FlightStatus samples, all Disarmed/Stabilized1.
- 39 ActuatorCommand samples, each with the first four channels zero. These
  software values do not prove measured electrical output.
- Six samples each of ManualControlSettings, FlightModeSettings,
  ActuatorSettings and SystemSettings, each byte-stable for its object. All
  selected settings passed the exact diagnostic checks, including
  Always Disarmed and QuadX/Throttle SystemSettings.
- 60 ManualControlCommand samples: one initial zero/default sample;33
  disconnected/timeout;18 connected/neutral; four disconnected with neutral
  channel values and four connected with timeout channel values. The latter
  transition samples are not counted as fully matching endpoints. All59
  non-initial samples had Throttle and Thrust=-1.
- 40 SystemAlarms samples: the first six reported CPUOverload/Actuator Critical,
  then34 reported both OK. Receiver alarm runs were Warning12, OK8, Warning7,
  OK7, Warning6. BootFault remained Uninitialised in all40. Preflight delayed
  the first input until nominal fresh observations. These findings do not
  resolve [startup fault reporting, issue27](https://github.com/ghostlyd/lrrk-air-mini/issues/27).

Alarm names above were mapped from the pinned SystemAlarms XML element names,
not guessed from numeric indices.

## Capture integrity and exact failure

The private raw capture contains30,421 bytes with SHA-256
`97f78974dd7e68fd8f35633248bcc6955c779bfced77e4cdc123a1c89d667bd6`.
Its finalized bytes and digest match the report. Initial synchronization
discarded110 bytes; this is not a lossless-from-open capture.

Offline strict decoding reproduced25 pending bytes from an instance0
AttitudeState frame whose declared length is38 bytes before CRC (39 including
CRC). `finish()` raised `UAVTalkError: truncated frame at end of capture`.
The incomplete frame was not accepted as telemetry. Its termination explains
the capture-validation failure; it does not alone establish a firmware fault.

Raw captures, complete settings and device identifiers remain private. The
directory is0700 and capture/report files are0600. Only these selected findings
and hashes are published.

## Source verification and remaining work

The independent review accepted exactly one bounded physical trial after eight
findings were corrected with failing-first host regressions: delayed-I/O
freshness/deadlines, verified-byte codec/XML loading, consecutive phase endpoint
matches, final framing validation, capture/report publication ordering, raw
settings-byte immutability, transmission-boundary cadence and post-close
freshness. Host checks passed37 focused tests in the intended ESP-IDF Python3.9,
plus the full82 assistant +148 port tests with no skips. GitHub host, source
and SDK checks passed at the tested commit. The IDF graph was refreshed by
reconfigure only; no additional firmware was built or flashed.

This source PR adds a restricted diagnostic, not a generally writable drone
API. The AI assistant remains receive-only/advisory. The four-phase sampled
observations are useful evidence, but incomplete framing keeps issue23 open.
A bounded, reviewed frame-completion procedure is the next diagnostic task;
there is no automatic physical retry.

Arming stays disabled. Full-board storage-fault integration (issue26), measured
electrical cutoff timing (issue19), startup fault reporting (issue27), physical
motor mapping, IMU orientation/calibration, compatible battery/charging checks,
powered operation and flight remain separate unpassed gates.
