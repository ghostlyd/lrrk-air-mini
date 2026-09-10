# Host USB transaction integration

`provisioning_transport.py` connects the actual private pending-bundle backend
to bounded stream transactions. `save_and_submit` completes the exclusive save
and sync before accessing the supplied transport, then attempts exactly one
credential write. `reconcile` validates a saved bundle and sends only status
queries. Neither function promotes, overwrites, or deletes bundles.

Only a matching transaction's finished/verified status establishes the `verified`
result. ACK means queued, and NACK describes that submission only; neither proves
the outcome of a prior accepted write. Other terminal results distinguish
not-written from uncertain. Partial writes, corruption, mismatched transactions,
disconnects, clock failures, timeout and cleanup blocked never imply verified.

The supplied stream must be exclusively owned, already at a UAVTalk frame
boundary, with read timeout at most 50 ms and write timeout at most 200 ms.
The module bounds each read to 256 bytes, polling to 25 requests, and work to
512 iterations and a five-second cooperative deadline. An in-progress call may
finish after that deadline; its late result is rejected. No unbounded custom
transport is made safe by merely declaring timeout attributes.

Actual decoder and wire-codec validation handle fragmented frames. Unrelated
telemetry is not captured or acknowledged. CRC detects corruption; this physical
USB maintenance protocol is not authenticated against an attacker controlling
the local stream. The future serial opener must establish identity, exclusive
access and frame alignment without resets or introducing a wireless/AI route.

Independent review of `296e900` found no blocking issue under that contract.
Follow-up tests cover disconnect, clock rollback/NaN, late status, all terminal
result values, and interleaved ordinary telemetry with ACK/NACK and status.
All 34 status split positions are exercised. Synthetic fixtures only were used.

At `5af02b4`, the full host suite ran 245 tests: 236 passed and nine optional
OpenAI-extra tests skipped. With interleaving coverage, the full suite ran 246
tests: 237 passed and the same nine optional tests skipped.
Real device opening, credential generation, bundle promotion, serial alignment,
combined firmware/host lifecycle and authorized on-board activation are not yet
implemented or verified by this increment. No serial port was opened and no
real credentials or motor commands were emitted.
