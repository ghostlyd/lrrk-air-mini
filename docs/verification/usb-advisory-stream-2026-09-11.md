# USB advisory streaming implementation

Current status: one bounded live USB-to-OpenAI session verified on the retained
normal image. A subsequent two-session reopen check succeeded once and then
failed, so reconnect reliability remains unresolved. Not a flight qualification
or indefinite-service claim. Earlier failures below describe the diagnostic-image
investigation.

The collector now offers repeated, complete five-object snapshots on one
reset-neutral transport. Every subsequent delivery requires fresh receipt of
each selected object. Invalid framing, handshake loss, or one second without
a complete aggregate terminates collection. Sessions are bounded to 60 seconds
and the existing private capture byte limit remains enforced. Cancellation
does not initiate a final protocol transaction; transport cleanup still runs.

`USBObservation` preserves the collector snapshot and leaves board serialization
time and sensor sample age unknown. It does not claim authenticated Wi-Fi
provenance. The latest-only inbox supports both explicitly distinct observation
types without copying, accumulating, or manufacturing telemetry fields.

`run_usb_advisory` owns a separate advisory thread and closes its inbox whenever
USB collection exits. Its count is offered snapshots, not completed analyses.
The supplied analysis callback must have its own deadline. Python cannot kill
an arbitrary callback; a one-second unsuccessful join is an error, not successful
shutdown. In-flight results remain historical. This API exposes no motor tools.

Tests exercise repeated acquisition, corruption, cancellation before writes,
silent-link expiry, observation preservation, invalid handoff input, concurrent
acquisition during blocked analysis, and transport cleanup on corruption.

The `litewing-usb-advisory` launcher now connects these components. Supply exact
`--device`, `--usb-location`, and new, separate `--private-capture` and
`--audit-log` paths. It defaults to a 15-second session, three analysis attempts
and a five-second minimum interval. Offline deterministic analysis is default;
`--live-agent` explicitly enables the existing OpenAI provider using the process
environment. Never put an API key on the command line. Results are labeled
historical and include capture time and a session identifier. Audit records keep
provider response hashes, not response text. The provider helper has a 30-second
cooperative deadline and a four-turn limit; session termination signals
cancellation. These are not hard process deadlines or dollar-spend limits.

Provider limits now use a per-run client with zero client and model retries,
a 20-second request timeout, a 1,024-token output limit per model turn, and
disabled tracing. The client closes after each run. Together with the four-turn
limit and session attempt budget these constrain requests, not total dollar
cost or input-token usage. Local SDK configuration/cleanup tests cover these
settings. The bounded fixture provider check below verifies a real invocation,
not live aircraft acquisition.

Remaining work: repeatable live USB/reconnect qualification. The bounded
end-to-end OpenAI session succeeded as recorded below; that success does not
resolve the intermittent failure or qualify firmware for flight.

## Follow-up review fixes

Commit `65b9bd0` addresses three independently reproduced host defects:
inherited HUPCL was retained (allowing hang-up-on-close), successful partial
writes bypassed the write deadline, and disconnect during final-frame completion
could return stream success. Regression tests failed for all three before the
fix and the complete host suite passed afterward: 359 tests. The implementation
clears HUPCL, checks the deadline before each write, and rejects a connected-to-
disconnected transition during completion. Nonblocking syscall duration itself
is not preempted by the deadline.

These offline results do not prove which defect caused the physical reconnect
failure. Follow-up review and a new bounded hardware check remain required.

## First live launcher check

One connected matching USB bridge was enumerated. A five-second offline-only
session was attempted with the normal reset-neutral transport. The launcher
returned failure after capturing 48 bytes, before a complete aggregate. Private
capture analysis found nine initially discarded bytes, then one CRC-valid frame
of 22 bytes plus checksum, followed by invalid synchronization. This reproduces
the intermittent post-synchronization framing failure; its cause is not proven.
No reset, flash, motor command, or OpenAI request was performed.

The check also exposed a missing terminal failure audit event. The launcher now
records `usb_session_failed` with the exception class only, and reports an audit
write failure separately. A regression test verifies corruption produces that
terminal event. This does not repair or bypass the serial framing failure.

## Passive versus active follow-up

A two-second reset-neutral passive read, with no protocol writes, captured
7,171 bytes. Offline CRC scanning found 174 consecutive valid frames after an
initial 34-byte fragment, with zero gaps between those frames. The next active
launcher attempt failed after 21 bytes with invalid synchronization; its audit
now correctly ended with `usb_session_failed` (`UAVTalkLiveError`). No API call
was made. This comparison narrows investigation toward startup buffering or
request/response behavior, but it does not isolate either as the cause.

Source inspection found both the UAVTalk connection lock and the PIOS COM
send-buffer mutex around normal transmission. The ESP32 UART backend calls
`uart_write_bytes` without inspecting its return value; this is an investigation
lead, not proof of byte loss. No decoder relaxation or firmware modification was
made on the basis of these observations.

## Single-connection phase isolation

On one new connection, one second each of passive reception, handshake-only,
and selected-object requests captured 11,017 bytes and 264 consecutive CRC-valid
frames, with no interframe gaps. Phase offsets were 0, 3,544, and 7,079 bytes.
Replay through the production synchronizer at chunk sizes 1, 7, 48, 256, and
4,096 produced the same 264 frames, 53 initial discarded bytes, and the same
partial final frame (36 bytes still needed). Thus this sample does not support
either request traffic alone or input chunk size as the cause.

A separate immediate-handshake-and-requests capture also remained continuous:
7,330 bytes, 178 CRC-valid frames, zero interframe gaps. A subsequent lsof check
found no open owner of the callout device at that instant; it does not exclude
an earlier competing reader. The launcher failure remains intermittent and
unresolved. These diagnostic captures did not bypass the production decoder,
change the firmware, or authorize flight readiness.

## Deadline-boundary correction

A synthetic fragmented-packet regression reproduced a separate shutdown defect:
normal session expiration called decoder finalization with a partial valid frame.
Streaming now uses the existing 250-ms bounded, read-only frame-completion helper
before finalization. Explicit cancellation remains immediate. This fixes normal
deadline truncation, not the startup synchronization failures.

Semantic replay accepted all 264 frames from the phase-isolation capture, but
did not produce a complete post-handshake aggregate. All five selected object
types occurred somewhere in that capture; that is not equivalent to receiving
all five after connection establishment. The complete host suite passed 355
tests after the deadline correction.

## Bounded provider smoke

The CLI processed the checked-in telemetry fixture and made one application-level
OpenAI advisory invocation using the approved existing local key. It exited 0;
the hash-chained audit recorded a completed provider result. The returned answer
correctly identified the fixture as BLOCKED because snapshot and link data were
stale, while distinguishing other nominal fixture fields. The response hash
matched the audit record and the audit file was mode 0600. No secret pattern was
found in the response. Keys and response text were not committed.

This used the new zero-retry scoped client/model configuration, four-turn limit,
1,024 output tokens per turn, disabled tracing and cooperative deadline. One
application invocation is not a claim of exactly one underlying model request.
The complete host suite passed 356 tests. No board access occurred during this
smoke, and live USB-to-OpenAI streaming remains unqualified.

## Collector-only isolation

The production streaming collector, with a simple list sink and no advisory
thread or provider, reproduced invalid synchronization after 35 captured bytes
and zero snapshots. The capture began with a CRC-valid 22-byte object packet
plus checksum (not one of the five selected schemas), followed by 12 bytes that
did not form the next valid frame. AI execution and advisory worker contention
are therefore not necessary triggers.

A separate two-second diagnostic capture using the same synchronizer, but
recording beyond a potential first error, received 7,305 bytes and 178 consecutive
CRC-valid frames without an error. This does not establish a repair: the
production-path failure is still intermittent. No production resynchronization,
firmware change, or motor operation was introduced by these checks.

The initial CRC-valid packets in three failed captures were checked against
the pinned generated headers: `0x8C2D810A` is GyroState, `0xC7009F28` is
AirspeedState, and `0x0BC57454` is GPSVelocitySensor. Their instance IDs were zero.
They are not arbitrary unknown schema IDs; this weakens the hypothesis of
accidentally synchronizing on an embedded payload pattern. The target defines
`PIOS_INCLUDE_FREERTOS`, so the previously inspected conditional COM send mutex
is enabled by source configuration. Neither finding proves runtime lock
correctness or the absence of startup/driver byte loss.

## Normal-image comparison and live USB-to-OpenAI result

After fresh confirmation of propellers removed, a secured clear bench, and
immediately disconnectable power, the retained normal application was flashed
at `0x10000` only. Its SHA-256 is
`bc5af53b2f534a3c17774aae35f3af30d26f574517a85d5f92f14f67bfc7da3f`
and size is 873,440 bytes. Esptool validated its image checksum and reported
successful write hash verification. Before/after private reads of `0x9000`
length `0x7000` (NVS/PHY) and `0x110000` length `0x8000` (settings) were
byte-for-byte identical. No arming settings or credentials were rewritten.
The normal image has UART console disabled; the prior diagnostic image enabled
UART console at 115200. Other image differences mean this is not proof that
console configuration alone caused the framing failures.

The production collector then delivered 25 complete snapshots over five seconds,
capturing 22,233 bytes, all reporting Disarmed. The complete launcher subsequently
ran for 15 seconds, captured 66,421 bytes, and offered 74 snapshots while one
OpenAI advisory invocation completed. Audit replay validated the event chain
through `usb_session_ended`. The response hash matched the output and that output
was explicitly labeled historical. Full capture replay finished at a valid frame
boundary: 74 FlightStatus samples were Disarmed, and 89 actuator samples all
contained four zeros. No motor commands were issued by these tools.

This verifies a bounded working USB-to-Mac-to-OpenAI path on the normal image,
not repeated cold-start reliability, wireless operation, or flight readiness.
The installed application is now the retained normal image, not the temporary
diagnostic image described earlier. Private backups, captures and responses
remain outside Git.
