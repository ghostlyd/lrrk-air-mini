# Session keys and operator admission: source verification

Implementation revision: `af44f77` on `codex/wifi-session-state`.

## Verified scope

- Python and firmware derive three role-separated session keys with the fixed
  root/host-nonce/board-nonce/session transcript from the approved Wi-Fi plan.
- Real pinned mbedTLS HKDF agrees with the Python implementation across input
  variations. Null inputs and injected failure at each of three SDK calls clear
  the entire firmware output. Partial session keys are never published.
- RFC 5869 A.1 passes in the pinned SDK harness. Frozen protocol outputs were
  generated independently with OpenSSL 3.6.4 HKDF, SHA256, root as IKM,
  host||board as salt, and role-label||session as info; Python matches all three.
- The operator-client admission object authenticates board CHALLENGE before
  producing CLAIM, and requires a role-key-authenticated, transcript-bound ACCEPT
  before reporting handshake establishment. It rejects repeated admission,
  wrong roles/keys, malformed proofs, expired attempts, and clock rollback.

The host admission object is an early client integration slice added ahead of
the C admission task. It uses the same fixed transcript, without changing the
approved design. It has no socket, settings, arming, or receiver-write APIs.
Callers must supply a fresh CSPRNG nonce for every new instance. Establishment
records a handshake result only; it is not a live ownership or freshness check.

## Checks at this revision

- Focused port protocol/crypto suite: 9 passed, with pinned mbedTLS supplied.
- Focused Python pilot suite: 20 passed.
- Full assistant suite: 199 run, 190 passed, 9 optional-SDK skips.
- ESP-IDF 5.3.2 ESP32-S3 build: passed; key adapter compiled into `libmain.a`.
  No runtime caller exists yet. Build success does not establish radio operation.
- App size: `0x5dc30`; app partition `0x100000`, 63% free.
- App SHA256: `f8c471295c0305de94e0cb6bd17c62b94c017af8f0f34a42dcf8d5e81b2319b1`.

Full port regression: 332 run, 320 passed, 12 skips (129.400 seconds).
Review found the target HKDF option disabled: the initial unused-adapter build
did not prove it would link with a real caller. A retained-entry-point link check
and enabled target dependency are required before this slice is accepted.
Review also requested ACCEPT-phase expiry/rollback boundary coverage.

## Remaining integration

Firmware admission/challenge state, replay-protected candidate acceptance,
atomic USB/Wi-Fi ownership, AP/socket lifecycle, secure provisioning, operator
input, and live link-loss validation remain unfinished. The C key API requires
fixed-size non-overlapping input/output buffers. Python cannot promise secure
erasure of immutable byte strings. Never expose pilot keys to AI tools.

No hardware access, flashing, credential provisioning, motor output, or flight
was performed for these checks. Prior hardware evidence is not refreshed by
these source-only tests.
