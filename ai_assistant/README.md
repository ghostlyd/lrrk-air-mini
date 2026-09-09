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

The optional extra pins the tested Agents SDK version, currently `0.22.1`.
Its comparison tool takes no model-supplied telemetry: it compares only the
previous and latest snapshots ingested by the runtime, and reports unavailable
until both exist. Comparison does not establish freshness or a preflight pass.

To check the actual SDK wrappers locally without a real key or provider call,
use a separate Python 3.11+ virtual environment:

```sh
python3 -m venv .venv-sdk
.venv-sdk/bin/python -m pip install './ai_assistant[openai]'
.venv-sdk/bin/python -m pip check
.venv-sdk/bin/python -m unittest discover -s ai_assistant/tests -p test_provider_sdk.py -v
```

These tests use the real optional dependency, block socket/DNS operations,
disable tracing, and temporarily substitute an explicitly fake test credential.
The dedicated CI job installs the extra so these tests cannot silently skip for
a missing SDK. Ordinary offline tests still need no third-party packages.
Local tool tests do **not** verify API credentials, model replies, latency,
provider billing, or live flight telemetry.

UAVTalk is an adapter boundary, not a command channel. The first implemented
adapter is deterministic JSONL replay so safety behavior can be tested without
the board or a radio link.
