# Session-bound telemetry consumer — 2026-09-10

Scope: host-side continuation of the approved wireless design, based on codec
commit `b4a4b4f`. Not a live wireless-link or flight acceptance record.

## Data path

`TelemetrySession.receive` authenticates a canonical telemetry datagram,
checks its session, strictly increasing sequence and non-regressing clocks,
then uses the existing pinned object parser to validate numeric/enum data.
Only after all checks pass does it advance accepted state. A lock serializes
receive and close, so concurrent duplicates cannot both be accepted.

It returns `TelemetryObservation`: a partial `TelemetrySnapshot` plus board
serialization time, optional sample age, local monotonic receipt time and UTC
receipt time. The snapshot explicitly identifies receipt-time provenance and
keeps `link_age_ms` null. It does not combine observations across objects.
Unknown sensor values and unknown timing remain unknown. An unseen delayed
packet can be observed but cannot establish freshness or clear preflight.

The existing `AssistantRuntime.ingest(observation.snapshot)` accepts that
snapshot without receiving a key, session identifier or socket. Tests exercise
the real runtime export and deterministic preflight analyzer. No OpenAI API
call or external telemetry transfer is part of these tests.

## Ownership contract

The trusted local pilot owner supplies only the derived telemetry key and
session to the constructor. The consumer cannot locate provisioning bundles,
derive root/pilot keys, send packets, claim control or issue keepalives. Python
object encapsulation is not a process security boundary: keep this object and
its key out of model tools and untrusted code.

The owner captures receipt clocks with each datagram before queue/processing
delay. It must call `close()` on STOP, session loss, rotation and shutdown; a
new consumer requires a new trusted handoff. Returned observations remain
historical values after closure, not evidence of an active session. Closing
drops key references, not a secure erase of immutable Python memory.

## Verification

- Test-first run failed on the absent consumer module before implementation.
- Eleven focused tests pass: clock provenance, real AI runtime ingestion,
  replay/reorder/exhaustion, invalid-frame and invalid-semantic rollback,
  regressing clocks, delayed unseen observations, concurrent duplicates,
  closure/new sessions and constructor validation. Follow-up cases cover
  ordered receive/close across threads, battery NaN preservation, infinity
  rejection and invalid alarm enums without consuming sequence state.
- Existing seven actual-C telemetry interoperability/sanitizer tests pass with
  the new host module present.
- Full host suite: 287 run, 278 passed, 9 optional OpenAI SDK skips, using
  Homebrew CPython 3.14.7 and `PYTHONPATH=ai_assistant/src python3 -m unittest
  discover -s ai_assistant/tests`.
- No firmware, transport or pilot-control code changes in this component.
- Independent read-only review found no blocking correctness or security
  issues. The two suggested nonblocking test additions are included above;
  production code is unchanged after review.

## Remaining integration

The firmware publisher, coherent measurement timestamp export, trusted local
pilot key handoff, socket demultiplexer and close-on-loss wiring are still
required. This component does not open a radio link or enforce retirement
without that owner wiring. Runtime load/latency, target builds and physical
radio/USB recovery checks remain separate. No board or motor action occurred.
