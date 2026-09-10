# Wireless protocol core verification

This is source/library evidence, not an enabled wireless pilot link.

## Implemented boundary

- Python codec: canonical LWPL v1 framing and HMAC-SHA-256 verification.
- C codec: allocation-free framing, capacity validation, output clearing on
  decode failure, and explicit authentication callback.
- IDF adapter: mbedTLS SHA-256 HMAC with caller-supplied 32-byte key, no secret
  discovery or provisioning, and cleared output on SDK failure.

Session identity and sequence are opaque fields here. Session admission, replay
and challenge-age enforcement, UART ownership, AP/UDP integration, and operator
input delivery are still required before accepting a wireless flight command.

## Verification observed

Python codec independently reviewed at `3980e4f`. C source review found no
correctness issues at `13184a4`. Follow-up test review approved `0dd446a`,
including fatal sanitizer mode and C-produced payload tampering.

The focused C/adapter/vector suite runs eight methods with the real mbedTLS
source supplied. The full assistant suite runs 190 methods: 181 passed and nine
optional-SDK methods skipped. Native sanitizer coverage uses ASan and UBSan with
`-fno-sanitize-recover=all`; it spans payload sizes 0–512 and exact allocated
truncation boundaries. Its stub MAC is only a memory-test boundary.

The separate cryptographic test builds the real clean mbedTLS checkout at
`98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8` from ESP-IDF 5.3.2 on the host.
It passes [RFC 4231 section 4.2](https://www.rfc-editor.org/rfc/rfc4231#section-4.2)
and the frozen full-frame synthetic vector in `pilot_crypto_vector_test.c`.
The Python test independently checks that same frozen packet. The RFC primitive
test uses its published 20-byte key; production adapter tests retain the required
32-byte key. No test key is a deployed credential.

Host mbedTLS uses a minimal SHA-256/MD configuration, not ESP32 hardware crypto.
The test skips when `LRRK_TEST_MBEDTLS_ROOT` is absent; a skipped run is not
cryptographic verification. A supplied wrong revision or dirty tracked source
fails. Reproduce from the repository root:

```sh
LRRK_TEST_MBEDTLS_ROOT=/path/to/esp-idf/components/mbedtls/mbedtls \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p 'test_pilot*.py'
```

## Target compilation

ESP-IDF 5.3.2 build passed at `ded1950`, application size `0x5dc30`, with
63% partition space free. Application SHA-256:
`6d1ff027a30d6b87fb9b1200d488f4c59ac290e01bcba05d843f2c15019796e8`.
`lw_wire_encode`, `lw_wire_decode`, and `lw_pilot_mac` are present in the main
static archive but absent from the final ELF because no ingress calls them yet.
Thus compilation is proven, runtime linkage and execution are not.

The initial sandboxed component-manager invocation failed while inspecting
parent processes. The approved build retry outside the sandbox succeeded.
No flashing, credential access, radio activation, settings writes, or motor
commands occurred. Independent whole-slice review approved `03e4933` with no
Important findings, including the adapter and pinned real-crypto tests.

CI now has a dedicated `pilot-crypto-gate` that obtains the exact mbedTLS revision
and supplies it to the focused suite. Its live result must be checked separately;
adding the workflow does not itself prove the hosted test passed.
