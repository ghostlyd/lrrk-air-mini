# USB Credential Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the tightly coupled implementation and verification steps below.

**Goal:** Implement the namespace-scoped persistence backend needed by the approved USB maintenance workflow.

**Architecture:** A synchronous internal backend snapshots and validates a bounded blob, writes only `nvs/lw_pilot/config`, commits, and verifies an exact readback. Its result distinguishes invalid input, failure before writing, uncertain write outcome, and verified readback. It is not called from USB or startup until maintenance exclusion and bounded AP shutdown are implemented.

**Tech Stack:** ESP-IDF 5.3.2 NVS, C11, Python unittest, ASan/UBSan.

**Spec:** `docs/verification/wifi-provisioning-boundary-2026-09-10.md`, approved by the operator on 2026-09-10.

## Global Constraints

- No device access, actual credential creation, erase API, radio activation, reset, or motor output.
- Use only the existing 136-byte LWCF v1 format and dedicated credential namespace/key.
- Caller must exclusively own maintenance, establish Disarmed and retired radio service, and retain ownership through storage. This backend does not claim to enforce those not-yet-integrated lifecycle conditions.
- Input memory must be stable during the initial bounded copy. All subsequent validation and writes use the snapshot. Caller retains responsibility for its input-buffer wipe.
- No logging/readback export, implicit NVS erase, unrelated namespace writes or encryption claims.
- This backend is not complete provisioning; parser, maintenance worker, host private bundles and rotation remain required.

## Task 1: Backend and fault-injection tests

Files: create `target/include/litewing_wifi_store.h`, `target/pios_litewing_wifi_store.c`, `tests/wifi_config_store_test.c`; modify `tests/test_wifi_config.py` and `target/sources.cmake`, all below `ports/ninjapilot-litewing/`.

Interface:

```c
enum lw_wifi_store_result {
    LW_WIFI_STORE_INVALID = -2,
    LW_WIFI_STORE_NOT_WRITTEN = -1,
    LW_WIFI_STORE_UNCERTAIN = 0,
    LW_WIFI_STORE_VERIFIED = 1
};
enum lw_wifi_store_result lw_wifi_config_store(const uint8_t *blob, size_t size);
```

- [ ] Add a compiled C fixture using the real decoder/store and only NVS doubles. Assert exact namespace, key, 136-byte size, set/commit/read ordering, balanced handles, and no erase symbols linked. Cases: invalid/null/short input causes no NVS calls; init/open failure causes no write; set/commit/read failure, short/oversized/mismatched readback all return UNCERTAIN; exact commit/readback returns VERIFIED. Mutate the caller's original buffer inside the set double and verify stored bytes still match the snapshot. Test replaying the same blob after an uncertain write.
- [ ] Run `python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_wifi_config.py -v` and observe the missing backend fail before implementation.
- [ ] Implement bounded snapshot and decoder validation before `nvs_flash_init_partition("nvs")`; open `lw_pilot` read-write, set only `config`, commit, close, reopen read-only and read exactly 136 bytes. Any failure after set is attempted returns UNCERTAIN. Compare all bytes with a fixed-length accumulated difference; success means internal readback verification, not proven power-loss durability. Wipe snapshot, readback and decoded struct on every exit. Close each successfully opened handle once.
- [ ] Add the backend to explicit target sources without introducing a caller. Run fixture with ASan/UBSan and existing decoder/read-only loader tests. Review diff and commit.

## Task 2: Integration evidence

- [ ] Run the pinned target build with the already verified dump-disabled configuration and clean committed source. Record compile/link outcome; an uncalled backend may be discarded and must not be described as runtime reachable.
- [ ] Request independent source review and document all remaining caller-side maintenance conditions. Publish the backend with its tests after review; keep physical provisioning unavailable until the complete worker, parser and host path exist.
