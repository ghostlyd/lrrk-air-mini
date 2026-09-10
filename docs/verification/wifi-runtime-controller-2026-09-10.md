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

## Authenticated admission samples

The host admission peer can now encode an explicit tuple of eight bounded integer
samples as a 16-byte network-order CLAIM payload. Its legacy no-samples form
remains handshake-only. The session core validates either legacy empty or bounded
16-byte forms; the runtime controller independently requires the authenticated
16-byte form and calibrated neutral predicate before entering the core CLAIM
transition. Session/sequence/challenge freshness checks remain in that transition.
Malformed/non-neutral traffic still runs expiry processing and cannot obtain an
ACCEPT or receiver reservation. Controller initialization now accepts the mapping
snapshot; a missing mapping leaves admission unable to pass neutral validation.

Seven host admission tests and 39 firmware pilot test methods pass, including
16 real controller scenarios. Added fixtures verify encoded sample bytes, strict
host types/bounds, empty-CLAIM rejection and signed off-neutral rejection.
The earlier missing-sample API/struct test failures preceded implementation.
Source review, final build and full regression for this change remain pending.
Actual persisted-settings snapshot capture, group validation and settings-drift
exclusion remain required in the platform adapter; this change does not pretend
the test-supplied mapping is a live settings observation.

## Settings observation adapter

At `25c1285`, scoped admission review found no Critical/Important issues. Target
build passed and the full port regression completed: 368 run, 356 passed,
12 skipped (132.726 seconds). The assistant suite ran 201 with 9 skips.

`PIOS_LiteWing_PilotReadAdmissionMapping` now reads current ManualControlSettings
through its real generated getter and validates primary GCS groups, disabled
collective/accessory groups, calibration, bounds and unique mappings. It checks
FlightStatus Disarmed before and after the settings read. Every failure clears
the output; it never rewrites settings or assumes persisted defaults. Eleven
standalone cases using the pinned checkout's real generated UAVObject headers
pass fatal ASan/UBSan, including failures at each getter and arming during reads.

This getter alone is not an atomic admission transaction. The pending runtime
must exclude settings writers across capture/initialization/admission, recheck
flight state at CLAIM, and invalidate on settings changes. Observed RAM settings
are not proof that the corresponding values have been saved to flash. No live
runtime caller or hardware operation is introduced. Adapter review/build pending.

## Admission UART write guard

The adapter at `dccb28e` passed the target build and scoped source review, with
no Critical/Important findings. The new receiver BeginAdmission/EndAdmission
guard provides a temporary UART-write exclusion transaction without granting
pilot ownership. Begin refuses fresh USB input, active ownership, another guard,
or any admitted storage transaction in flight. A monotonically issued token
prevents stale cleanup from ending a newer guard. Begin/end timestamp fences
reject delayed pre-transaction USB packets. Ending after successful ownership
claim preserves wireless write exclusion. It does not exclude local setters.

Thirty GCS regressions pass, including guard/storage non-entry, fresh-input and
in-flight refusal, stale-token rejection, delayed packet fencing and claim/end
coexistence. The new fixture failed for missing APIs before implementation.
Runtime integration must authenticate before acquiring the guard, use it only
around synchronous snapshot/CLAIM work (never wait for packets while holding it),
end on every path, and handle clock/cleanup failure explicitly. Mapping must be
captured or checked inside this transaction, not trusted from a prior HELLO.
The actual orchestrating task and local-settings-writer lifecycle remain pending.

## Guarded observed receive transaction

The guard at `4f20c6c` passed scoped source review. The observed controller entry
now authenticates admission framing before invoking its platform mapping reader,
checks Disarmed/mapping through that reader before acquiring the UART guard,
then re-reads inside the guard before neutral/session validation and reservation.
It releases the guard before returning a reply. A failed read retires admission
and cleans up. If clock rollback prevents cleanup, the controller retains the
token, refuses a new observed transaction, and retries cleanup through tick or
fault handling. It never discards the token while the guard remains held.

Forty pilot test methods pass with the pinned source and mbedTLS supplied.
Twenty real controller scenarios include successful guarded capture from an
initially absent mapping, failed guarded read with restored USB writes,
rollback/token retry, and bad MAC causing zero mapping reads. The mapping reader
fixture checks actual UART storage exclusion during capture; real generated
UAVObject getter tests remain separate. No final real-flight task timing claim
follows from these tests. Source review and target build for this entry pending.

The runtime must pass PIOS_LiteWing_PilotReadAdmissionMapping as the reader and
call only from a single owning task, after boot-time local settings work ends.
Concurrent local settings setters are not excluded by the UART guard and remain
a runtime lifecycle constraint. No AP/socket task or live caller is enabled yet.
