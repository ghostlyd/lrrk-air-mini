# LiteWing AI assistant

This package is a host-only advisory layer for the NinjaPilot LiteWing port.
It reads normalized telemetry, runs deterministic preflight checks, records
redacted hash-chained audit events, and creates bounded proposals for explicit
human review.

The default mode is offline. It needs no API key, network, firmware change, or
flight-controller write path:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input ai_assistant/tests/fixtures/telemetry.jsonl \
  --audit-log /tmp/litewing-audit.jsonl \
  --prompt 'run preflight' \
  --json
```

The optional `openai` extra enables a read-only Agents SDK provider. Live mode
requires an explicitly exported `OPENAI_API_KEY`; this repository does not
create, store, or transmit that key to the aircraft. The provider has no tool
for arming, taking off, landing, changing gains, changing failsafes, writing
actuators, or executing flight actions.

UAVTalk is an adapter boundary, not a command channel. The first implemented
adapter is deterministic JSONL replay so safety behavior can be tested without
the board or a radio link.
