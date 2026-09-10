# Wireless Session State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Authenticate a single pilot session and reject replayed or expired controls before producing a receiver-input candidate.

**Architecture:** Build on the reviewed LWPL codec with pure session state, injected clocks/randomness, and explicit outcomes. The controller owns serialization of access; only a subsequent ownership adapter may commit accepted candidates to receiver storage. No network task directly sets PWM.

**Tech Stack:** C11, ESP-IDF 5.3.2 mbedTLS HKDF/HMAC, CPython 3.11–3.14 standard-library HMAC, unittest/ctypes.

**Spec:** `docs/superpowers/specs/2026-09-10-wifi-pilot-link-design.md` (approved).

## Global Constraints

- The OpenAI assistant remains host-side and advisory.
- Use constant-time tag comparison. Never implement a new cryptographic primitive.
- Session creation is allowed only while disarmed with no active pilot owner.
- Reboot, stop, expiry, or rotation retires the session.
- Wireless ingress is not passed to general `UAVObjUnpack`.
- No firmware flash, radio activation, credential provisioning, or motor operation is performed by source/build tests.
- No accepted codec frame alone grants authority to act.

## Fixed transcript and limits

All frames use the existing LWPL version-1 envelope. All byte strings below
are ASCII without a terminating NUL. Nonces are cryptographically generated:
32-byte host nonce, 32-byte board nonce, 16-byte session identity, and 16-byte
challenge identity. Failure to obtain randomness leaves the session closed.

1. HELLO: direction 0/kind 1; zero session, sequence 0, zero challenge;
   payload is the 32-byte host nonce; authenticate with the provisioned root key.
2. Initial CHALLENGE: direction 1/kind 2; random session, sequence 0, random
   challenge; payload is host nonce followed by board nonce (64 bytes);
   authenticate with the root key. Host must match its outstanding host nonce.
3. Derive three independent 32-byte session keys using RFC 5869 HKDF-SHA-256.
   IKM is the root key; salt is host nonce concatenated with board nonce.
   Info is respectively `LWPL/v1/c2b/`, `LWPL/v1/b2c/`, or
   `LWPL/v1/telemetry/`, concatenated with the 16-byte session identity.
4. CLAIM: direction 0/kind 3; session, sequence 1, current challenge;
   empty payload; authenticate using c2b. Verify disarmed/no-owner again.
5. ACCEPT: direction 1/kind 4; session, sequence 1, accepted challenge;
   empty payload; authenticate using b2c. This grants a pilot session, not arming.
6. Active CHALLENGE: direction 1/kind 2, session, increasing board-control
   sequence, fresh challenge, empty payload; authenticate using b2c.
   Active TELEMETRY uses only the telemetry key and its own sequence space.

The read-only AI telemetry consumer can receive only the telemetry key, never
the root/c2b/b2c keys. Key export and actual secret provisioning are separate
interfaces; no automatic file/env lookup is introduced by the pure core.

Initial admission expires after 1000 ms; its rolling challenges expire at
75 ms. An authenticated HELLO cannot replace pending or active state. Lost
ACCEPT causes host timeout, not automatic flight resumption: retry admission
only after the prior state expires and the aircraft is disarmed. Do not add an
idempotent CLAIM path that silently renews receiver freshness.

One challenge is issued every 20 ms. Retain four issuance records. A valid
command references a retained challenge with age in [0, 75000] microseconds.
Clock rollback retires the session. A timestamp previously observed is never
replaced with a newer socket-read timestamp to rescue an expired frame.

Pilot payload: eight network-order uint16 channels, exactly 16 bytes, each
within 1000–2000. The ownership adapter will validate target-specific neutral
and channel mapping against persisted settings; this core does not guess them.
PILOT is kind 5; STOP is kind 6 with empty payload. Both use c2b and strictly
increasing sequence values after CLAIM. Sequence exhaustion retires the session.
STOP invalidates the session and all candidates. No arbitrary UAVObjects are
accepted. Malformed, unauthenticated, stale, or replayed packets do not renew
timestamps or change ownership.

For an accepted PILOT, candidate age originates at challenge issuance. Origins
must not regress; increasing sequences may share an origin without renewing it.
At 100 ms since the latest accepted origin, session input is invalid. Active
session without a first PILOT expires 100 ms after CLAIM's challenge origin.
The existing receiver timeout remains authoritative at consumption time; no
claim about physical motor-stop latency follows solely from these limits.

## Task 1: Cross-language key derivation

**Files:** create `ai_assistant/src/lrrk_litewing_ai/pilot_keys.py`,
`ai_assistant/tests/test_pilot_keys.py`,
`ports/ninjapilot-litewing/target/include/pios_litewing_pilot_keys.h`,
`ports/ninjapilot-litewing/target/pios_litewing_pilot_keys.c`, and
`ports/ninjapilot-litewing/tests/test_pilot_keys.py`.

**Interfaces:** Python `derive_keys(root: bytes, host_nonce: bytes, board_nonce: bytes, session: bytes) -> SessionKeys` returns frozen `SessionKeys(c2b: bytes, b2c: bytes, telemetry: bytes)`; invalid exact lengths/types raise ValueError. C `int lw_pilot_derive_keys(const uint8_t root[32], const uint8_t host[32], const uint8_t board[32], const uint8_t session[16], struct lw_session_keys *out)` returns 0/-1; all output bytes clear on failure. `struct lw_session_keys` owns three 32-byte arrays with those names.

- [ ] Write failing length/domain-separation tests:

```python
keys = derive_keys(b"r"*32, b"h"*32, b"b"*32, b"s"*16)
self.assertEqual(len({keys.c2b, keys.b2c, keys.telemetry}), 3)
self.assertNotEqual(keys.c2b, derive_keys(b"r"*32,b"h"*32,b"b"*32,b"t"*16).c2b)
```

- [ ] Run `PYTHONPATH=ai_assistant/src python3 -m unittest discover -s ai_assistant/tests -p test_pilot_keys.py`; observe missing implementation failure.
- [ ] Implement RFC5869 extract via HMAC(salt, root); for 32-byte output, expand via HMAC(PRK, info + byte 1). C calls `mbedtls_hkdf` with the same buffers and labels. Reject null pointers and clear C output after any SDK error. Do not log keys.
- [ ] Add published RFC5869 primitive vectors, frozen full-transcript vectors, every input-length boundary, and injected SDK failure at each of three derivations. Compile real pinned mbedTLS `hkdf.c` with the existing host crypto fixture.
- [ ] Run focused tests and full assistant suite; commit only after pass. Review exact labels and transcript before session consumption.

## Task 2: Admission state and challenge ownership

Execution status (2026-09-10): initial admission is implemented in `6269e3d`,
failure retirement coverage in `0c9133c`, and rolling challenges in `50670dc`.
The header now specifies the encoded receive and timed challenge-issuance APIs.
The host admission peer and role-key derivation landed in PR #57. Twenty-five
session tests pass with real pinned mbedTLS, including fatal ASan/UBSan admission
buffer checks, active controls, pending ring rollover, and session-level KDF/MAC
failure injection (`7c5799b`). Independent review approved that failure fixture
and closed the prior SDK-failure coverage gap. Independent review approved the
initial, rolling-challenge, and acceptance-core slices;
additional tests cover its collision/capacity/sequence-exhaustion coverage note.
Task 3's encoded prepare/commit and STOP core is implemented in `9cc3a49`, with
active-control sanitizer coverage and mixed-channel decoding in `a7048a3`.
Actual atomic receiver publication is not implemented or proven. Commit requires
the future adapter to hold its ownership/receiver lock through publication,
recheck owner identity, and retire on publication failure. No runtime caller,
AP, provisioning, or hardware operation is introduced by this source slice.

**Files:** create `ports/ninjapilot-litewing/target/include/litewing_pilot_session.h`,
`ports/ninjapilot-litewing/target/litewing_pilot_session.c`, and
`ports/ninjapilot-litewing/tests/test_pilot_session.py`.

**Interfaces:** define `enum lw_session_phase { LW_CLOSED, LW_PENDING, LW_ACTIVE }`;
`struct lw_pilot_session` owns phase, key material, nonces, four challenge slots,
monotonic clock high-water, sequence counters, and expiry origins.
`lw_session_init(state)` zeroes closed state. `lw_session_retire(state)` securely
clears keys and closes it. `lw_session_tick(state, now_us)` returns -1 after
rollback/expiry, otherwise 0. All public operations are caller-serialized.
Admission consumes authenticated HELLO/CLAIM frames through a single receive
entry point, never by exposing an unauthenticated parsed-frame accept method.

- [ ] Write failing tests for initial HELLO/CHALLENGE/CLAIM/ACCEPT transcript,
  with a deterministic synthetic RNG and exact monotonically advanced clock.
  Assert CLAIM does not emit a receiver candidate or change arming state.
- [ ] Implement bounded admission with the fixed transcript above. Check root
  MAC before allocating pending state; check c2b MAC and repeated disarmed/no-owner
  inputs before activation. RNG/KDF/encoding failure retires partial state.
- [ ] Add rejection cases: wrong host nonce, wrong session/key, reflected frame,
  pending replacement, duplicate CLAIM, failed recheck, expired challenge,
  expired pending state, RNG failure, and clock rollback. Assert state and
  freshness remain unchanged on invalid traffic except expiry/retirement.
- [ ] Run the real C state under ASan/UBSan fatal mode and commit. No UART,
  socket, settings, or receiver writes are permitted in this task.

## Task 3: Replay and control candidate enforcement

**Files:** extend the session header/source and `test_pilot_session.py`.

**Interfaces:** `struct lw_pilot_candidate { uint16_t channels[8]; int64_t origin_us; uint64_t sequence; };` owns immutable-by-contract output bytes.
Receive outcomes are REJECT, HANDSHAKE_REPLY, PILOT_CANDIDATE, and RETIRED.
The outer ownership adapter must atomically commit candidate and session state;
until that adapter exists no candidate reaches live receiver storage.

- [ ] Write failing tests showing a repeated sequence, old session, or challenge
  age 75001 us cannot produce a candidate or extend validity; 75000 us is accepted.
- [ ] Implement exact payload lengths, channel bounds, monotonic sequence and
  nonregressing challenge origin. Validate MAC and all fields before committing
  sequence/origin. A failed consumer commit must retire the session rather than
  leave an accepted-but-unpublished command eligible for replay.
- [ ] Test same-origin increasing sequences, uint64 exhaustion, lost/expired
  first PILOT, STOP, clock extremes, and 100 ms expiry without incoming traffic.
  Inject pauses before commit and revalidate against current time. Zero candidate
  outputs on every non-candidate result.
- [ ] Exercise all these paths through authenticated encoded bytes using the
  real codec/KDF/MAC test harness, not only direct state assignments. Run full
  host regression, independent review, and the pinned target build; commit.

## Coverage boundary

This plan covers session cryptography and a testable acceptance state machine.
It does not enable a radio or send receiver input. Successor work must integrate
atomic UART/Wi-Fi ownership, bounded AP/UDP lifecycle and provisioning, an
operator-input client, telemetry-only AI consumption, and the approved physical
bench/flight gates. All remain required for the full goal.
