# Next diagnostic: exact acquisition provenance

Purpose: distinguish values present in returned MPU6050 register bytes from
changes introduced between publication and the pre-bias estimator sample.
This is instrumentation, not a PID, filter or motor-output change.

## Bounded representation

The host UAVTalk decoder currently limits payloads to 217 bytes. Extend the
120-byte trace by 90 bytes, targeting 210 bytes, rather than enlarging that
protocol limit. Retain three contributors per estimator record:

- Each contributor: successful-read sequence (uint32), read-start and
  read-completion timestamp lows (two uint32), exact 14 register bytes.
- Aggregate: first/last consumed sequence (two uint32), consumed count
  (uint16, saturating with overflow flag), retained count and flags (uint8).

Three entries use 78 bytes; aggregate fields use 12. Regenerate and verify
actual wire layout, object ID and metadata protection before deployment.
Queue depth does not bound a draining consumer: mark incomplete provenance
when more than three samples contribute, without truncating the flight drain.

## Association

Populate a diagnostic trailer before queue publication. Change producer,
queue item size, discard buffer and consumer allocation together. Preserve
the existing sensor payload prefix and queue replacement policy. Sequence
every successful read and preserve its sequence on enqueue retry.

Accumulate trailers at each successful consumer dequeue, before the existing
arithmetic. Clear at sensor-update entry; consume once with the estimator
record. Never use an independently sampled latest-value snapshot as provenance.
Timestamp lows need bounded-age reconstruction against the record's 64-bit
time; ambiguous ages are invalid, not guessed.

## Verification before another hardware run

Exercise actual producer/consumer seams with distinct frames, multiple samples,
queue eviction, producer refill, overflow, sequence/time wrap, and early returns.
Compare flight results with tracing enabled and disabled. Verify frozen
retention, wire round-trip, malformed-field rejection and inbound data/metadata
write rejection. Confirm memory use and application build before flash.

Raw bytes prove what the read returned, not physical motion or bus integrity.
Offline reconstruction must also account for scaling, board rotation and
temperature compensation; do not infer those settings from raw provenance.
