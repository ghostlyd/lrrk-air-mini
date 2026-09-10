# Firmware telemetry publisher — source and host evidence

The command task now produces kind-8 telemetry for its established pilot peer.
It selects AttitudeState, FlightStatus, FlightBatteryState, SystemAlarms and
ActuatorCommand in rotation, with at most one attempt per 100 ms. It uses the
session's independently derived telemetry key and a separate nonwrapping sequence.
No telemetry receipt or send renews a pilot challenge or receiver-input lifetime.

Four cached objects use the generated zero-wait object-manager guard and report
unknown measurement age. Battery voltage bytes and age come from one coherent
acquisition record; stale/future/absent samples remain NaN with unknown age.
Unmeasured current and other battery floats remain NaN rather than synthetic zero.
Target compilation asserts all five generated IDs and byte sizes.

The task owns one fixed local frame; no queue or stale backlog persists. Busy
reads consume their scheduled turn. It checks the elapsed 2 ms budget and pilot
expiry after the read and after authentication. EAGAIN/EWOULDBLOCK/EINTR drop the
datagram without a retry or sequence reuse. Fatal/short sends follow existing
transport retirement. Scratch key, frame, record and datagram are wiped before
return. Timing checks are cooperative, not a measured execution-time guarantee.

## Tests

- Battery suites: 19 passed, including real coherent store/export serialization
  under ASan/UBSan, sample replacement at the clock boundary, exact 500 ms expiry,
  future/negative clock, NULL/capacity rejection and buffer canaries.
- Target read adapter: sanitizer test passed for five selections, failure-zeroed
  records and clock/missing-handle behavior. Synthetic headers isolate this unit
  test; only the target build checks actual generated headers.
- Real task/controller/receiver plus pinned mbedTLS: existing fault cases and
  thirteen telemetry cases passed. Read-time and MAC-time stop/expiry/budget
  failures suppress send; backpressure and EINTR consume sequences; control/root
  keys fail telemetry authentication.
- Real C task/session/HMAC over localhost UDP into production Python admission,
  demultiplexer and semantic consumer: five distinct types observed, followed by
  STOP or link loss. Five additional omission runs each show exactly the other
  four types and reject the all-five assertion. Distinct roll, voltage and actuator
  values are checked; defaults cannot satisfy missing observations. This fixes
  the independent review's P2 test-coverage finding.
- Full port suite with pinned flight source: 382 run, 361 passed, 21 optional
  environment skips. The separately run pinned-crypto task suite executes its
  otherwise optional integration cases. After test-only refinements, that full
  task suite passed again, including all omission and MAC-time cases.
- Full assistant suite: 293 run, 284 passed, 9 optional environment skips.

No board access, radio association, credentials, OpenAI requests, flash, arming
or motor commands occurred. Localhost fixture data are synthetic. Remaining
physical qualification includes task timing/stack usage under radio load, board
identity, provisioning/association, USB recovery, and observed motor-stop behavior.
No flight-readiness claim follows from these host results. Target-build evidence
will be recorded separately against the committed source revision.
