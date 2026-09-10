# Read-only advisory handoff — 2026-09-10

Based on merged publisher revision `7b304697`, this host-only change implements
the approved wireless design's pilot-to-advisory handoff. It does not add OpenAI
API calls or alter firmware, protocol, arming, receiver ownership or settings.

The pilot owner offers an accepted immutable telemetry observation to one slot.
Offer uses a non-waiting mutex attempt; contention drops the incoming observation.
A new accepted offer replaces pending data. The assistant worker drains one item
under the mutex, releases it, then calls the real runtime's ingest method. Slow or
failed analysis does not hold the producer mutex and a failed ingest is not retried.
One worker must serialize all access to its AssistantRuntime; the handoff does not
make that existing mutable runtime generally thread-safe.

Close discards pending data and prevents reopening. An already-drained item can
finish analysis as historical data. Close cannot cancel a remote API request or
clear a runtime owned by another worker. Callers must close the inbox during pilot
retirement. It contains no pilot key, socket, command surface or automatic thread.

No aggregate snapshot or freshness claim is added: all partial fields, timestamps,
unknown link age and unknown battery fields are preserved exactly. Slow consumers
may miss entire object types. A complete launcher, multi-object display and actual
board connectivity remain outstanding; this library boundary is not those features.

## Executed evidence

- New test initially failed on the absent handoff module, then all seven focused
  tests passed: latest replacement, empty drain, closed queue, real lock contention,
  stalled consumer, failure with newer pending data, and wrong-input rejection.
- Tests use real authenticated telemetry decoding, snapshot parsing, runtime
  ingestion and preflight checks. The stalled/failing runtime subclasses wrap only
  the consumer boundary; they do not simulate the inbox implementation.
- The existing real C command task/controller/mbedTLS localhost suite now routes
  each observation through the inbox and actual AssistantRuntime. Distinct values
  and all five omission cases still pass. Unknown link age never becomes a complete
  preflight PASS. The run also includes STOP/loss and telemetry failure scenarios.
- Full assistant suite: 300 run, 291 passed, 9 optional environment skips.
- Independent review found no actionable issues and reran the focused and
  C/Python integration tests. Loopback analysis runs inline for data-path testing;
  it is not a scheduling-isolation demonstration. The stalled-worker test proves
  the separate, narrower mutex contract. Deployment scheduling is still unmeasured.

No credential access, OpenAI request, board access, radio association, reset,
flash, arming, motor command or physical flight occurred in this work.
