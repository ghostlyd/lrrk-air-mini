# USB advisory streaming implementation

Status: host-library implementation; not a flight qualification or continuous
OpenAI service claim.

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

Remaining work: review SDK retry/token limits, live USB qualification, and a
bounded end-to-end OpenAI streaming session. These host tests do not
resolve the previously observed intermittent framing failure or qualify the
temporary diagnostic firmware for flight.

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
