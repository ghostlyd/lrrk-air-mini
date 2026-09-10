# Firmware telemetry publisher integration

Approved scope: connect the existing authenticated telemetry codec and host
consumer to the owning command task. No new command, receiver writer, credential
discovery, radio association, flashing or hardware actuation in this implementation.

- [x] Add a coherent battery snapshot returning bytes, exporter time and voltage
  sample age from one acquisition record; test replacement during serialization,
  stale/future/unknown samples and failure buffers with ASan/UBSan.
- [x] Select the five pinned schemas in a target adapter. Four cached objects use
  the reviewed zero-wait guard and unknown measurement age; battery bypasses the
  cached object. Assert generated IDs and sizes in target compilation.
- [x] Add one attempt per 100 ms to the owning low-priority task, rotate all five
  objects and use fixed local buffers with no queue or retry. Authenticate only
  with the active session's derived telemetry key and a nonwrapping independent
  sequence. Recheck expiry/stop/AP fault and elapsed budget after reads and MAC.
- [x] Keep telemetry EAGAIN/EWOULDBLOCK/EINTR as a dropped packet with sequence
  consumed; short/fatal sends follow the existing transport-fault cleanup.
- [x] Test the real command task/controller/receiver/crypto with thirteen added
  stream/busy/slow/expiry/stop/rollback/backpressure/send-fault scenarios,
  including expiry/STOP during MAC and interrupted sends.
- [x] Test all five records from the real C sender over localhost UDP through
  the production Python demultiplexer and semantic consumer, then STOP or loss.
- [x] Complete full host/port regressions, independent review and pinned target build.
- [x] Prepare reviewed source with truthful build/host-only evidence for a CI-gated
  pull request. Merge acceptance requires green live checks on its exact head.

Target radio timing, stack high-water mark, association, key provisioning,
USB recovery under live load, and motor-stop behavior are separate physical
qualification checks. Host tests and target compilation are not flight proof.
