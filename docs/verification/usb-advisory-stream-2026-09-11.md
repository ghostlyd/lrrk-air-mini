# USB advisory streaming implementation

Status: host-library implementation; not a flight qualification or continuous
OpenAI service claim.

The collector now offers repeated, complete five-object snapshots on one
reset-neutral transport. Every subsequent delivery requires fresh receipt of
each selected object. Invalid framing, handshake loss, or one second without
a complete aggregate terminates collection. Sessions are bounded to 60 seconds
and the existing private capture byte limit remains enforced. Cancellation
does not initiate a final protocol transaction; transport cleanup still runs.

`USBObservation` preserves the collector snapshot and leaves board serialization
time and sensor sample age unknown. It does not claim authenticated Wi-Fi
provenance. The latest-only inbox supports both explicitly distinct observation
types without copying, accumulating, or manufacturing telemetry fields.

`run_usb_advisory` owns a separate advisory thread and closes its inbox whenever
USB collection exits. Its count is offered snapshots, not completed analyses.
The supplied analysis callback must have its own deadline. Python cannot kill
an arbitrary callback; a one-second unsuccessful join is an error, not successful
shutdown. In-flight results remain historical. This API exposes no motor tools.

Tests exercise repeated acquisition, corruption, cancellation before writes,
silent-link expiry, observation preservation, invalid handoff input, concurrent
acquisition during blocked analysis, and transport cleanup on corruption.

Remaining integration work: launcher options, explicit provider call budget and
deadlines, private audit wiring, result freshness/session labeling, live USB
qualification, and a bounded end-to-end OpenAI session. These host tests do not
resolve the previously observed intermittent framing failure or qualify the
temporary diagnostic firmware for flight.
