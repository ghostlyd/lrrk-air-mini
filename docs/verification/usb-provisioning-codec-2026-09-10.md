# Host USB provisioning codec

Implementation revision: `1f996b1` in draft PR #65.

`ai_assistant/src/lrrk_litewing_ai/usb_provisioning_wire.py` implements the pure
codec from the approved USB wire contract. It constructs LWCF credential blobs,
163-byte submission frames, and 11-byte status requests. Incoming complete
status/receipt frames require exact length, type, object ID, instance, CRC and
schema. Status additionally requires the caller's nonzero pending transaction
ID. Errors deliberately omit input values.

An ACK reports only queue acceptance; its frame carries no transaction ID.
`persisted_and_finished` becomes true only for FINISHED plus VERIFIED status,
not during blocked cleanup. Neither condition proves power-loss durability,
active radio credentials, or flight readiness.

## Checks

- Seven Python unit tests passed: literal header/payload layout, CRC, text/key
  bounds, credential padding, no input echo, wrong/stale transaction rejection,
  repaired-CRC semantic corruption, extra/truncated bytes and status/result
  distinctions.
- The actual C LWCF decoder agreed with host acceptance for 1,092 cases: two
  valid boundary blobs, two length errors and every single-bit mutation of a
  136-byte valid blob. C rejection also cleared its output structure.
- Full AI host suite under Python 3.14.7: 227 tests executed, 218 passed and nine
  skipped. Printed stale-telemetry/preflight rejections came from synthetic test
  fixtures, not current-board observations.

## Remaining integration

This module performs no I/O, generates no credentials, and is not registered as
an AI tool or command-line entry point. It does not save private bundles, open
serial, assemble fragments or retransmit. The operator transport must save its
private pending bundle before sending bytes and resolve lost ACKs by correlated
status polling. Python's immutable buffers are not reliably erasable.

Firmware parser interception, reserved-ID collision checks, rejection-buffer
wiping, fragmented/corrupt-frame tests, host private-bundle lifecycle and worker
startup remain unimplemented. No board access, radio activation, real credential
creation, flashing, arming, or motor commands occurred for this codec work.

Independent review of `59b0723..1f996b1` found no blocking correctness/security
issue. Follow-up test improvements add fixed request/ACK/NACK vectors whose CRCs
were calculated by separate GF(2) polynomial long division, a fixed submission
CRC, malformed-receipt cases, and decoded C-field equality for every accepted
interop blob. The codec suite now has eight tests. Actual C frame-parser parity
remains part of the firmware parser integration, not this blob-parity check.
