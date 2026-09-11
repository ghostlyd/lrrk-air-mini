# Configuration-aware USB telemetry

## Purpose and authorization

Implement the user-approved host-only design: assess the observed stabilization
configuration instead of treating a `stabilized1` label as proof of behavior.
This contributes to the OpenPilot/LiteWing and OpenAI-assistance project; it
does not establish flight readiness by itself. Firmware, arming, motor commands,
settings writes, and existing safety thresholds are outside this change.

## Source contract

Use NinjaPilot revision `ac77304a58de6c8bd552f94668b46903adb71cb2`.
Its generated headers define FlightModeSettings (`0x4D896486`, 59-byte payload)
and SystemSettings (`0xD9D093B8`, 46-byte payload). Verify complete layouts and
enumerations against generated headers and pinned XML in tests; never infer
offsets from a photograph or a previous observation.

`flight/modules/ManualControl/stabilizedhandler.c` selects one of six
StabilizationNSettings arrays from FlightStatus.FlightMode. Each array has
Roll, Pitch, Yaw, and Thrust. FlightModePosition is a selector mapping, not the
source of the active stabilization tuple once FlightStatus is observed.

## Host representation

Extend normalized snapshots to schema version 3, retaining readers for versions
1 and 2. Absent configuration is unknown. Add a frozen configuration observation
containing the six four-axis tuples, airframe type, system thrust-control mode,
and each settings object's age at snapshot capture. Retain symbolic enumeration
values; malformed wire enums are protocol errors, not default values.

Do not retain SystemSettings aircraft-name bytes in normalized data or public
evidence. New configuration fields participate in canonical snapshot hashing.
Advance the analyzer version because its interpretation changes. Existing
approval bindings must reject changed snapshots or analyzer policy identities.
Old recordings remain readable but cannot manufacture configuration evidence.

## Collection and freshness

Keep the five existing mandatory telemetry objects and their 200 ms request
cadence unchanged. Request the two settings objects at session start and no
more than once per second thereafter, with no catch-up bursts. These are
optional observations: their absence does not stop the ordinary telemetry feed.

Only narrowly allowlisted requests and acknowledgements are added. Canonical
NACK for either settings object clears that object's cached observation;
malformed NACKs retain the existing strict failure behavior. Settings responses
must have the pinned ID, exact length, supported type, and instance zero.

Use receipt monotonic times for age accounting. At assessment time, add elapsed
time since capture to both settings ages. Configuration is usable only when
both ages are below 2000 ms; the exact boundary is stale. This is a new settings
observation contract, not a relaxation of link, IMU, or battery thresholds.
Clear configuration on connection-state invalidation, termination, and a new
session. Never reuse it across devices. A mode change selects the corresponding
tuple, never the previously active slot's tuple.

The two objects are not an atomic firmware transaction. Report this as sampled
configuration with bounded age, not proof that settings cannot change between
responses. Unmatched or missing components remain unknown. Configuration must
not freshen older attitude, actuator, IMU, or link observations merely by
arriving later.

## Mode assessment

For stabilized slots 1 through 6, require fresh complete configuration. For the
LiteWing QuadX with Throttle thrust control, classify an observed roll/pitch/yaw
tuple using Rate or Attitude and Manual thrust as requiring no positioning
hardware. This finding concerns mode dependencies only; other preflight
findings still apply independently.

All other combinations remain explicitly unknown until their exact dependencies
are supported by source-backed policy. In particular, AltitudeHold,
AltitudeVario, CruiseControl, relay tuning, unsupported airframes, unknown
system thrust modes, and invalid axis combinations must not inherit a PASS
from the slot label or from a generic declared positioning capability. Include
the selected four-axis tuple and the reason in the finding. Do not reinterpret
unrelated named modes or remove existing alarm findings in this change.

## Verification and acceptance

Automated tests must cover all six slot selections, thrust changes, changed
airframe/thrust-control mode, absent and stale components, the 2000 ms boundary,
elapsed-time aging, nonzero instances, malformed lengths and enums, NACK cache
revocation, reconnection/session clearing, bounded request cadence, and ordinary
telemetry continuing without configuration. Verify schema 1/2 reads, schema 3
round trips, changed configuration hashes, and approval invalidation.

Use synthetic settings packets checked against the pinned generator. Test the
actual collection-to-normalization-to-preflight flow, not only helper functions.
Run the full host suite and relevant existing serial/approval regression tests.

Perform a bounded USB request-only comparison of the existing and extended
collector on the same installed image. Record receive/transmit byte counts,
complete aggregate rate, CRC/parser errors, mandatory-object timeouts, and IMU
sample-age distribution. The expected added receive load at one poll per second
is 127 bytes/s, plus 22 bytes/s of outbound requests before acknowledgements.
Treat UART transmit and receive directions separately.

Acceptance requires no mandatory-object timeout, no malformed frames, bounded
polling, and no greater than 10 percent reduction in aggregate delivery rate
over comparable 15-second runs. Report IMU freshness separately; do not conceal
the existing analyzer-age issue or claim this feature solves it. If bandwidth
acceptance fails, diagnose the measured failure before proposing the alternative
compact firmware object. Do not silently change architectures or flash firmware.

Publish only sanitized results and source/test identities. Keep raw captures,
hardware identifiers, credentials, and provider prompts/responses private.
No OpenAI call is necessary for the deterministic integration tests.
