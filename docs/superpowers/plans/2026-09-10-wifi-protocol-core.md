# Wi-Fi Protocol Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a byte-exact authenticated C/Python envelope codec as the first dependency of the approved wireless pilot link.

**Architecture:** The codec owns framing and authentication only. Session admission, replay state, challenge expiry, transport ownership, and radio lifecycle are separate consumers and must reject frames before any receiver mutation. A valid codec result alone is never authority to act.

**Tech Stack:** C11, ESP-IDF 5.3.2 mbedTLS, CPython 3.11–3.14 standard library, unittest/ctypes.

**Spec:** `docs/superpowers/specs/2026-09-10-wifi-pilot-link-design.md` (operator-approved).

## Global Constraints

- The OpenAI assistant remains host-side and advisory.
- No firmware flash, radio activation, credential provisioning, or motor operation is performed by source/build tests.
- Use constant-time tag comparison. Never implement a new cryptographic primitive.
- Missing or invalid configuration leaves Wi-Fi disabled without disabling USB recovery.
- No built-in key or checked-in credential; published test keys are explicitly synthetic.
- Preserve CPython 3.11–3.14 and ESP-IDF 5.3.2 support.

## Full-goal dependency map

This plan delivers only the codec. It is not wireless control acceptance.
The next execution plans must cover, in order:

1. Authenticated session admission and HKDF direction keys; challenge ring,
   monotonic sequence, 75 ms challenge limit, and 100 ms receiver-origin expiry.
2. Atomic UART/Wi-Fi ownership with pre-storage rejection, stop/session retirement,
   and actual control-task failsafe integration.
3. AP provisioning and bounded UDP lifecycle alongside USB; operator input client,
   telemetry-only adapter, and simulator loss/delay/flood tests.
4. Pinned firmware build, failure injection, load/scheduling measurements,
   separately authorized props-off deployment, USB recovery, and physical flight
   qualification with a verified battery/propeller assembly.

Each successor consumes the reviewed codec; no codec API is exposed to AI tools.
The implementation plan for session admission must fix exact HKDF labels and
nonce transcript before that task's code is written. No session keys are derived
or used by this codec-only stage.

## Canonical envelope

Network byte order; no padding. Header is 50 bytes, tag 32 bytes, payload at
most 512 bytes; complete datagram at most 594 bytes.

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 4 | ASCII `LWPL` |
| 4 | 1 | Version 1 |
| 5 | 1 | Direction: 0 host-to-board, 1 board-to-host |
| 6 | 1 | Kind: HELLO=1, CHALLENGE=2, CLAIM=3, ACCEPT=4, PILOT=5, STOP=6, TELEMETRY=7 |
| 7 | 1 | Flags, exactly zero |
| 8 | 16 | Session identity |
| 24 | 8 | Unsigned sequence |
| 32 | 16 | Challenge identity |
| 48 | 2 | Payload length |
| 50 | variable | Payload |
| 50 + payload length | 32 | HMAC-SHA-256 over header and payload |

Host-to-board kinds are 1, 3, 5, 6; board-to-host kinds are 2, 4, 7.
Reject inconsistent kind/direction, unknown kind, nonzero flags, wrong version,
truncation, extra bytes, and overlength input. Fixed session/challenge fields
are opaque here; the state machine assigns and validates their meaning.
Zero/nonzero sequence legality is likewise a state-machine decision, but the
codec must reject values outside uint64. Keys must be exactly 32 bytes.

## Task 1: Python reference codec and literal framing tests

**Files:**
- Create `ai_assistant/src/lrrk_litewing_ai/pilot_wire.py`.
- Create `ai_assistant/tests/test_pilot_wire.py`.

**Interfaces:**
`Envelope(direction: int, kind: int, session: bytes, sequence: int, challenge: bytes, payload: bytes)` is frozen.
`encode(envelope: Envelope, key: bytes) -> bytes` and
`decode(datagram: bytes, key: bytes, expected_direction: int) -> Envelope`
raise `ValueError` for invalid framing/authentication; decode returns no partial result.
No sockets, file reads, secret discovery, receiver writes, or AI registration.

- [ ] Write the first behavior test; derive expected header independently:

```python
def test_header_is_canonical(self):
    packet = encode(Envelope(0, 5, b"s" * 16, 9, b"c" * 16, b"\x01\x02"), b"k" * 32)
    self.assertEqual(packet[:8], b"LWPL\x01\x00\x05\x00")
    self.assertEqual(packet[24:32], b"\0\0\0\0\0\0\0\x09")
    self.assertEqual(packet[48:52], b"\x00\x02\x01\x02")
    self.assertEqual(len(packet), 84)
```

- [ ] Run `PYTHONPATH=ai_assistant/src python3 -m unittest discover -s ai_assistant/tests -p test_pilot_wire.py`; observe missing codec failure.
- [ ] Implement with `struct.Struct("!4sBBBB16sQ16sH")`, `hmac.digest(key, unsigned_packet, "sha256")`, and `hmac.compare_digest`. Validate field types/lengths before packing, excluding bool where integer fields are required.
- [ ] Add one failing test at a time for each malformed field, altered tag/payload/header, wrong key/direction, empty and 512-byte payloads, 513-byte rejection, all truncation boundaries, uint64 limits, and trailing bytes. Repeat red/green.
- [ ] Exercise tag failure with an independently constructed valid-length frame, not just a frame that fails preliminary shape validation:

```python
def test_payload_tamper_is_rejected(self):
    packet = bytearray(encode(Envelope(0, 5, b"s"*16, 9, b"c"*16, b"ab"), b"k"*32))
    packet[50] ^= 1
    with self.assertRaises(ValueError):
        decode(bytes(packet), b"k"*32, 0)
```

- [ ] Run focused and full assistant unittest discovery without an API key, then commit the codec and its tests.

## Task 2: Allocation-free C codec and cross-language tests

**Files:**
- Create `ports/ninjapilot-litewing/target/include/litewing_pilot_wire.h`.
- Create `ports/ninjapilot-litewing/target/litewing_pilot_wire.c`.
- Create `ports/ninjapilot-litewing/tests/test_pilot_wire.py`.

**Interfaces:**
Define `struct lw_wire_frame` with uint8 direction/kind, 16-byte session/challenge,
uint64 sequence, uint16 payload_len, and owned 512-byte payload storage.
Define `lw_wire_mac_fn` as `int (*)(void *ctx, const uint8_t *message, size_t length, uint8_t tag[32])`.
`lw_wire_decode(const uint8_t *wire, size_t length, uint8_t expected_direction, lw_wire_mac_fn mac, void *ctx, struct lw_wire_frame *out)` returns 0 on success, -1 on any failure; clears non-null `out` on failure.
`lw_wire_encode(const struct lw_wire_frame *frame, lw_wire_mac_fn mac, void *ctx, uint8_t *wire, size_t capacity, size_t *written)` returns 0/-1 and sets `*written=0` before work. Only success permits transmission.

- [ ] Compile the real C source into a shared library with `cc -std=c11 -Wall -Wextra -Werror -shared -fPIC`; first test must fail before source exists.
- [ ] Test C decoding Python packets and Python decoding C packets, comparing every field against literal inputs. The ctypes MAC callback uses standard-library HMAC and is a test boundary, not production crypto.
- [ ] Implement field-by-field byte reads/writes without unaligned casts or native struct serialization. Check capacities before writes. Validate size/type combinations before invoking MAC; compare all 32 tag bytes without early exit. No heap or state mutation.
- [ ] Include a failing MAC callback and prefilled output sentinel; assert error and cleared output. Guard encoded output with canaries and test every too-small capacity.
- [ ] Port corruption and boundary cases from Task 1 as literal test cases, including a C-produced valid frame whose payload is then mutated. Run host ASan/UBSan over the same corpus where supported.
- [ ] Run `python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_pilot_wire.py` and full assistant tests, then commit.

## Task 3: IDF MAC adapter and independent vectors

**Files:**
- Create `ports/ninjapilot-litewing/target/include/pios_litewing_pilot_mac.h`.
- Create `ports/ninjapilot-litewing/target/pios_litewing_pilot_mac.c`.
- Create `ports/ninjapilot-litewing/tests/test_pilot_mac.py` and SDK-boundary C fixture.
- Modify `ports/ninjapilot-litewing/target/sources.cmake` and the IDF component dependency list only as required for compiling these modules.

**Interfaces:**
`struct lw_pilot_mac_key { uint8_t bytes[32]; };`
`int lw_pilot_mac(void *ctx, const uint8_t *message, size_t length, uint8_t tag[32]);`
The caller supplies an already selected direction key; the adapter neither provisions nor derives it.

- [ ] Write failing tests for null pointers, SDK algorithm lookup failure, and SDK HMAC failure; assert a zeroed tag and -1. Never expose a partially written tag after failure.
- [ ] Implement `mbedtls_md_info_from_type(MBEDTLS_MD_SHA256)` and `mbedtls_md_hmac(info, key->bytes, 32, message, length, tag)`. Propagate failures; do not use an insecure fallback.
- [ ] Check the cryptographic primitive with a published HMAC-SHA-256 known-answer test using the pinned mbedTLS implementation, not the fake adapter. Keep that primitive test separate from the fixed-32-byte production key contract.
- [ ] Freeze one full synthetic protocol packet as a literal cross-language vector and verify both implementations against it. Document synthetic key, unsigned bytes, and tag; no live credentials enter tests.
- [ ] Build on a clean committed tree using the repository's pinned ESP-IDF activation. No `flash` argument is allowed. Record which symbols are retained or discarded; codec compilation alone is not radio integration.
- [ ] Request independent review of exact commit, wire bytes, failure behavior, and tests. Commit evidence and open a PR without claiming session authentication, replay enforcement, or flight readiness is implemented.

## Self-review and execution handoff

Spec coverage: this plan implements the framing/authentication dependency only.
Every remaining subsystem and physical gate is explicitly retained in the full-goal
dependency map. The codec has no path to authorize commands; state and ownership
gates must exist before linking it into ingress. No changes to the approved
arming policy, startup alarms, or battery requirements are part of this plan.

Execution choice: inline, using executing-plans, under the operator's existing
autonomous-work authorization. Review at each independently testable boundary;
do not request another design approval merely to execute this approved direction.
