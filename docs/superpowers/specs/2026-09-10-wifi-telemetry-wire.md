# Authenticated Wi-Fi telemetry wire refinement

Status: implementation refinement of the approved wireless workflow; not a
hardware acceptance record. Base: merge `8812ed4430622ef58f0a3ae59ef0b5c7ed40b408`.

## Scope

Extend the approved [pilot-link design](2026-09-10-wifi-pilot-link-design.md)
with a bounded telemetry record. First deliverable is a side-effect-free C and
Python codec with shared vectors. Publisher, session consumer, local pilot
handoff and AI integration remain separate implementation steps. A codec alone
does not establish replay protection, freshness, source identity or flight readiness.

## Canonical record

Reuse the LWPL version 1 envelope with direction 1, new kind 8 and zero flags.
The session must be nonzero. Telemetry sequence starts at 1 and never wraps;
it is independent of the pilot/control reply sequence. The challenge field is
all zero: this record does not claim a round-trip freshness proof.
Use only the existing `LWPL/v1/telemetry/` HKDF-derived 32-byte key, never the
root, c2b or b2c key. The complete canonical envelope and payload remain MACed.
Allowing kind 8 in the envelope codec must not authorize it in any controller.

Payload has exactly this layout; integer metadata is network byte order:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 1 | Telemetry schema version, exactly 1 |
| 1 | 1 | Reserved, exactly zero |
| 2 | 2 | Object payload length |
| 4 | 4 | Pinned UAVObject ID |
| 8 | 8 | Board monotonic serialization timestamp in microseconds |
| 16 | 8 | Sample age in microseconds, or UINT64_MAX for unknown |
| 24 | variable | Exact pinned little-endian object payload, no UAVTalk header/CRC |

Timestamps must be at most INT64_MAX, matching the platform monotonic clock.
Known sample age must be at most the serialization timestamp. Only a
producer-owned measurement timestamp may establish sample age; object read,
serialization and unchanged-value observation do not establish it.
The timestamp must be captured coherently with the same sample that produced
the payload. A later, separate timestamp lookup must not attach newer timing
to older bytes. Until the producer exports that coherent pair, use UINT64_MAX;
this includes the current byte-only battery packing interface.

The allowlist and exact sizes are AttitudeState `0xD7E0D964`/28,
FlightStatus `0xEF69B6BC`/8, FlightBatteryState `0x26962352`/30,
SystemAlarms `0x6B7639EC`/25 and ActuatorCommand `0xB8229FE4`/29.
Names/IDs/layouts are taken from the pinned schemas already consumed by
`ai_assistant/src/lrrk_litewing_ai/uavobjects.py`; verify against generated
headers during target integration. Single instance zero is implicit.
Maximum payload is 54 bytes and maximum complete datagram is 136 bytes.
Reject other IDs, lengths, versions, reserved bits, trailing bytes and invalid
metadata. Numeric/enum validation remains required at the snapshot boundary.

## Consumer lifecycle and truthful time

A future session consumer takes only a session ID and telemetry key via a
local trusted pilot-owned handoff, never discovers provisioning bundles and
never derives keys itself. It authenticates before accepting data, rejects
wrong session and non-increasing sequence, and rejects regressing board or
local monotonic clocks. Invalid input cannot advance its accepted state.
Session closure invalidates the consumer; reconnection needs a new handoff.
Shared-key HMAC proves possession, not an independently attested board: a
telemetry-key holder can forge telemetry. Keep the key out of model input,
logs and public artifacts.

Record board serialization time, sample age, local monotonic receipt time and
local UTC receipt time separately. Neither one-way arrival nor a first packet
establishes clock offset or transit age. Until a reviewed freshness exchange
exists, `link_age_ms` stays null and reports explicitly say transport age is
unknown. Rejecting duplicates does not make a delayed unseen packet fresh.
Do not use these observations to clear flight readiness or combine partial
objects into an apparently simultaneous snapshot. The public snapshot may use
UTC receipt as `captured_at` only with explicit receipt-time provenance.

## Runtime integration constraints

One bounded stream to the established pilot peer; no subscription server,
new command type, raw object writes or telemetry-owned keepalive. A trusted
host demultiplexer forwards only kind 8 datagrams to the telemetry consumer.
The consumer has no send socket or command methods. Telemetry receipt never
refreshes pilot input, ownership or challenge age. STOP, loss, rotation and
maintenance retire the stream with the pilot session.

Use one fixed scratch frame separate from pilot ingress, at most one telemetry
attempt per 100 ms, rotating the five selected objects. No queued sample survives
an attempt; contention consumes its turn without a retry or backlog. Publisher
work remains in the low-priority command task, outside stabilization/PWM callbacks.
The implementation refinement replaces the proposed producer/mailbox with the
reviewed zero-wait object-manager guard: a busy mutex skips the read, and the
pinned serializer's nested recursive acquisition is by its existing owner.
Battery uses a short acquisition-record critical section and one coherent local
copy for bytes and age. This removes object-manager lock waiting; it does not
establish measured worst-case execution time. Check the existing 2 ms elapsed
budget after read and authentication and recheck pilot expiry before send.
On telemetry EAGAIN drop that datagram without reusing its sequence; fatal
socket errors follow existing transport fault behavior. Challenge/control
responses retain their current failure policy. Battery bytes must go through
the existing battery sample-age serialization boundary.

## Acceptance boundaries

Codec acceptance: shared Python/C byte vectors, both directions rejected when
wrong, key separation, tag corruption, all truncations, extra bytes, exact
object lengths and metadata boundaries. Test actual C codec, not a substitute.

Integration acceptance additionally requires real session retirement/replay
tests, stale/unknown-time analyzer behavior, localhost loss/delay/reordering,
proof that telemetry cannot renew control, pinned ESP-IDF build and existing
USB/provisioning regressions. Board association, radio load/latency and physical
motor-stop behavior remain unverified until separately performed.
