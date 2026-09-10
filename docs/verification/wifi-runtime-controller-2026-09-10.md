# Wireless runtime controller integration (in progress)

Based on merged PR #59 (`658052b`). The new controller connects encoded session
admission/control to the real receiver ownership and publication APIs. ACCEPT is
suppressed and cleared if reservation fails. Loss of the trusted disarmed or
neutral observation during admission retires pending state. Authenticated pilot
input is committed through the atomic receiver adapter; STOP, periodic expiry,
and transport fault invalidate input while retaining the reservation. Explicit
release requires both disarmed and neutral observations.

The controller requires external serialization and trusted current observations;
these are not wire fields. Seven real crypto/session/receiver scenarios run with
fatal ASan/UBSan: publication, STOP, timeout, fault, non-neutral admission, armed
admission, and fresh USB ownership conflict. The initial missing-controller test
failed; the first implementation failed the two admission-retirement assertions;
the correction passes all 36 pilot test methods with pinned mbedTLS supplied.

This is not the complete runtime: flight/settings observation validation, the
single-owner task or mutex, periodic challenge scheduling, AP/socket lifecycle,
credential provisioning, host operator client and telemetry delivery still need
integration. No runtime caller is activated by this change.

## Follow-up verification

The target build exposed missing PIOS/FreeRTOS header prerequisites, fixed in
`43a9ba0`. Review found receive-completion timestamps could look like clock
rollback after queued publication or a periodic tick. `4242cf8` uses the current
processing clock for session checks while retaining challenge issuance as the
input-age origin. Queued-control and tick-before-receive tests failed before the
fix and pass afterward. Re-review accepted the correction with no new
Critical/Important findings. The ESP-IDF build and persistence link check passed
at `4242cf8`. The earlier full suite ran 365 tests with 12 skips; it started before
the timing correction and is not final-revision regression evidence.

The controller now exposes periodic challenge issuance using the platform clock.
Tests verify the 20ms boundary, b2c-authenticated proof, non-renewal of input age,
and immediate receiver invalidation on challenge output-capacity failure. All 36
pilot methods pass, including 14 controller scenarios with fatal ASan/UBSan.
Challenge-adapter review and final-revision build/regression are pending.
No hardware access or secret provisioning occurred.

## Admission integration gap

At `5bb8fd6`, challenge-adapter source review accepted the change with no
Critical/Important findings; the ESP-IDF target build completed successfully.

The current empty CLAIM payload cannot prove the requesting operator's controls
are neutral. Do not substitute stale ManualControlCommand values, disconnected
failsafe defaults, or a constant true observation. Before radio activation,
extend the authenticated admission transcript with fresh channel samples and
validate them against persisted settings, then update both C and Python peers
and their transcript vectors. Empty legacy CLAIM must not gain live ownership
through the runtime adapter. This is a correction needed to fulfill the approved
neutral-admission requirement, not an optional enhancement.

`litewing_pilot_neutral` provides the calibrated predicate for that integration:
five unique one-based primary mappings, protocol-range calibration and samples,
throttle at calibrated minimum (including reversal), axes and flight-mode at
calibrated neutral. It deliberately uses exact neutral rather than guessing a
deadband. Endpoint neutral calibration is supported, consistent with the pinned
Receiver scaleChannel implementation's zero-denominator handling. The eventual
platform adapter must additionally validate channel groups, unsupported inputs,
current FlightStatus, and settings snapshot consistency. This predicate alone
does not read settings, authenticate samples, reserve input, or activate radio.
