# Pilot-owned telemetry lifecycle — 2026-09-10

Host integration following consumer commit `eee12ca` (merged via PR #67).
This is localhost/source evidence, not a connected-board acceptance record.

## Implemented path

An `OperatorSession` now internally constructs the read-only consumer using
only its derived telemetry key and session identity. It owns the consumer's
lifetime: closing or expiring the operator session also closes the consumer.
No key-export method or new model tool is added.

`OperatorUDP.step` routes the canonical kind-8 header to that consumer. Header
bytes are only a routing hint; authentication, exact layout, session, replay,
clock and object semantics are still checked. Valid telemetry replaces one
pending observation, with no growing queue. It never invokes the physical
input sampler, emits a response or updates the cached pilot challenge/proof.

`take_telemetry()` checks the existing pilot expiry deadline, drains that
one-observation mailbox and returns only a key-free observation. It must run
on the same serialized owner as `step` and `stop`. An expired/closed link
cannot export its pending observation. STOP, timeout and transport failure
clear the mailbox through the existing close path. A previously returned
observation remains historical data, not evidence that the session is active.

The default receipt wall clock is timezone-aware UTC; a keyword-only injected
clock supports deterministic host tests. Local monotonic receipt time remains
separate. Link age stays unknown and data remains partial.

## Evidence

- Test-first run: five new localhost cases failed because the telemetry drain
  and optional wall-clock interfaces did not yet exist.
- Focused pilot suite: 55 passed before the final admission-test extension.
- Full host suite including that extension and the review regression: 293 run,
  284 passed, 9 optional
  OpenAI SDK skips, CPython 3.14.7.
- Real localhost UDP exercises mutually authenticated admission with derived
  keys, telemetry after ACCEPT, a pilot challenge/response, then STOP.
- Other localhost cases cover mailbox replacement, no telemetry-triggered
  sampling/transmission, wrong-key/replay rejection, proof deadline expiry
  despite telemetry, STOP sequence preservation, expiry during observation
  polling and wall-clock failure cleanup.
- Review found invalid wall-clock return values were being swallowed as bad
  network packets, leaving pending telemetry and pilot proof alive. A new
  regression populated both caches and reproduced failure for None and naive
  datetime returns. Validating the local clock outside the packet-rejection
  handler fixes it; all 14 UDP tests now pass. No firmware policy was changed.
- Staged whitespace check passed.
- Scoped re-review confirmed the clock-fault finding addressed, independently
  passed the 14 UDP tests and found no new issues. The full-host result above
  resolves its pending regression condition.

No drone socket, serial device, firmware flash, provisioning operation, real
operator input device or OpenAI endpoint was used. These tests use synthetic
keys and localhost datagrams. The firmware telemetry publisher, actual input
device adapter and radio load/physical checks remain required.
