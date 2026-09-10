# USB credential persistence backend

Implementation checkpoint: `29d111f`. This is an internal, currently unwired
storage backend for the approved maintenance workflow, not a working USB
provisioning command.

`lw_wifi_config_store` snapshots exactly 136 bytes, validates the existing LWCF
format, and writes only `nvs/lw_pilot/config`. It commits, closes the writer,
reopens read-only, and compares all readback bytes with the snapshot. It never
erases a key or partition, starts Wi-Fi, resets, or prints credentials.

Results distinguish invalid input, no credential write attempted, uncertain
outcome after a set attempt, and commit plus verified internal readback. A set
error is conservatively uncertain. Host integration must preserve the pending
credential bundle across an uncertain result; it must not assume old credentials
remain or generate a replacement automatically.

## Evidence

- The new test failed against the missing backend before implementation.
- Three ASan/UBSan-backed test methods pass: existing decoder, read-only loader,
  and new store. The store fixture exercises success, init/open/set/commit/
  reopen/read errors, short/oversized/mismatched readback, invalid input,
  caller-buffer mutation during write, and retrying identical credentials.
- The fixture checks exact namespace/key, operation ordering and balanced
  handles. No erase or radio implementation is linked into the fixture.
- ESP-IDF 5.3.2 compiles the backend and the wrapper build passes at `29d111f`,
  with persistence-link validation and a `0xd3e20`-byte image (17% app space
  free). The backend is uncalled and may be linker-discarded: this does not
  establish runtime reachability or physical storage behavior.
- Independent source review accepted the backend with no Critical/Important
  findings. Sanitizers do not prove secret erasure or power-loss durability.

## Required integration

The caller must establish and hold exclusive maintenance ownership, verify
Disarmed, and complete bounded cooperative radio shutdown before calling this
backend. These are explicit API preconditions, not checks already enforced by
the backend. No UART or startup caller has been added.

The caller must wipe its original input buffer; the backend wipes its snapshot,
readback, and decoded local struct. This does not promise wiping SDK, compiler,
host or historical flash copies. Board NVS remains unencrypted. Live write,
power interruption, recovery, host-bundle and rotation tests remain outstanding.
No board access or actual credentials were used in this work.
