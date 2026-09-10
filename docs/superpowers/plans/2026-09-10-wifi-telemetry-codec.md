# Wi-Fi Telemetry Codec Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver interoperable bounded C/Python telemetry codecs without enabling a radio or claiming runtime freshness.

**Architecture:** Reuse LWPL authentication and add a strict telemetry-specific wrapper. Keep payload parsing independent of networking, key discovery, receiver ownership and snapshot interpretation. This plan implements the codec subproject only; runtime integration remains required by the parent design.

**Tech Stack:** C11, Python 3.11–3.14 standard library, existing unittest/ctypes C harness, ASan/UBSan.

**Spec:** `docs/superpowers/specs/2026-09-10-wifi-telemetry-wire.md`

## Global Constraints

- Use only the existing `LWPL/v1/telemetry/` HKDF-derived 32-byte key, never the root, c2b or b2c key.
- Maximum payload is 54 bytes and maximum complete datagram is 136 bytes.
- A codec alone does not establish replay protection, freshness, source identity or flight readiness.
- No real credentials, network association, flash, serial access or motor operation in this subproject.

---

### Task 1: Canonical envelope and payload codecs

**Files:**
- Create `ai_assistant/src/lrrk_litewing_ai/telemetry_wire.py`.
- Create `ports/ninjapilot-litewing/target/include/litewing_telemetry_wire.h`.
- Create `ports/ninjapilot-litewing/target/litewing_telemetry_wire.c`.
- Modify `ai_assistant/src/lrrk_litewing_ai/pilot_wire.py` and `ports/ninjapilot-litewing/target/litewing_pilot_wire.c` only to admit kind 8 for direction 1.
- Create `ai_assistant/tests/test_telemetry_wire.py` and `ports/ninjapilot-litewing/tests/test_telemetry_wire.py`.
- Extend existing `test_pilot_wire.py` in both test directories with kind 8 direction 1 vectors; retain direction 0 rejection.

**Interfaces:**
- Python frozen `TelemetryRecord(object_id: int, serialized_us: int, sample_age_us: int | None, data: bytes)`.
- Python `encode_record(record: TelemetryRecord) -> bytes`, `decode_record(payload: bytes) -> TelemetryRecord`.
- Python `encode_telemetry(record, session: bytes, sequence: int, key: bytes) -> bytes` and `decode_telemetry(datagram: bytes, key: bytes) -> tuple[Envelope, TelemetryRecord]`; wrappers enforce kind/direction/nonzero session/positive sequence/zero challenge.
- C `struct lw_telemetry_record { uint32_t object_id; uint64_t serialized_us, sample_age_us; uint16_t data_len; uint8_t data[30]; };` uses UINT64_MAX for unknown age.
- C `int lw_telemetry_payload_encode(const struct lw_telemetry_record *, uint8_t *, size_t, size_t *)` and `int lw_telemetry_payload_decode(const uint8_t *, size_t, struct lw_telemetry_record *)`.
- C `int lw_telemetry_frame_validate(const struct lw_wire_frame *, struct lw_telemetry_record *)` validates a previously authenticated envelope; it never authenticates or authorizes on its own. All decoders zero output on error, all encoders zero written on error. Caller buffers/structures must not overlap.

- [ ] Write the independent byte-layout test before creating implementation modules:

```python
def test_frozen_payload(self):
    record = TelemetryRecord(0xEF69B6BC, 1000, None, bytes(8))
    expected = bytes.fromhex(
        "01000008ef69b6bc00000000000003e8ffffffffffffffff"
        "0000000000000000")
    self.assertEqual(encode_record(record), expected)
    self.assertEqual(decode_record(expected), record)
```

- [ ] Run `/opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p test_telemetry_wire.py -v` with `PYTHONPATH=ai_assistant/src`; require failure due to missing module before implementation.
- [ ] Implement payload helpers around `struct.Struct('!BBHIQQ')`, exact allowlist `{0xD7E0D964:28, 0xEF69B6BC:8, 0x26962352:30, 0x6B7639EC:25, 0xB8229FE4:29}` and explicit integer/type bounds. Reject bool integers and mutable/non-byte payloads. Use UINT64_MAX only as unknown, not a timestamp.
- [ ] Implement the same field layout with explicit shifts in C, bounded copies after all validation, and no packed-struct casts or allocation. Encode/decode data bytes unchanged; leave numeric/enum interpretation to existing object snapshot parsing.
- [ ] Compile actual C sources using the existing ctypes harness pattern (`cc -std=c11 -Wall -Wextra -Werror -shared -fPIC`). Bind the record struct and functions with exact ctypes argument types. For each allowlisted object and ages `0`, serialization timestamp and unknown, compare C encoded bytes with Python and decode each side's bytes on the other side.
- [ ] Exercise every truncated length, one trailing byte, wrong schema/reserved field, all wrong object lengths, unknown IDs, sample age greater than serialization time, timestamp INT64_MAX+1, NULL output/input and every undersized C output capacity. Assert unchanged buffer canaries and zero error outputs.
- [ ] Wrap the frozen payload in direction 1/kind 8, sequence 1, nonzero synthetic session and zero challenge. Check every-byte tampering, wrong keys/direction, zero session/sequence and nonzero challenge. Use existing `pilot_keys.py` derived keys to prove a telemetry tag rejects under c2b/b2c/root; test keys are synthetic and public.
- [ ] Add a standalone C sanitizer harness for payload boundaries and NULL contracts following `pilot_wire_memory_test.c`; run ASan/UBSan with `-fno-sanitize-recover=all`.
- [ ] Run both full host suites with Homebrew Python on PATH. Require existing pilot controller/session tests still reject non-command traffic and preserve freshness. Do not weaken tests to accommodate kind 8 outside the framing layer.
- [ ] Record exact tests, failures fixed, limitations and source revision in `docs/verification/wifi-telemetry-codec-2026-09-10.md`; obtain code review before merge.
- [ ] Commit only the enumerated files and verification record with `git commit -m "feat: add bounded authenticated telemetry wire codecs"`; no target activation in this commit.

## Next integration deliverables (not completed by this plan)

The parent design still requires the session/replay consumer, trusted local
key handoff, firmware producer with battery sample-age boundary, nonblocking
mailbox scheduling, host demultiplexer and advisory analyzer integration.
Write their implementation plans against inspected runtime interfaces after
the codec contract is tested. Do not label this codec milestone a working
wireless telemetry link or use it as flight acceptance.
