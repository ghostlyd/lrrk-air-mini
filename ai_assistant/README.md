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

UAVTalk is an adapter boundary, not a flight-command channel. Deterministic
JSONL and saved-capture replay keep safety behavior testable without a board.
The optional `uavtalk` extra also enables one bounded live aggregate from the
exact CH340 USB identity and location selected by the operator:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input-format uavtalk-live \
  --device /dev/cu.wchusbserial410 \
  --usb-location 4-1 \
  --private-capture /path/to/new-private-capture.uavtalk \
  --duration 2 --json
```

The destination must not already exist. It is created mode `0600`, capped at
1 MiB, and never committed automatically. Live transport deasserts DTR/RTS
before opening the port, uses exclusive 57600-baud access, and matches USB
`1A86:7522` plus the exact topology location before opening. Its outbound
allowlist contains only telemetry handshake states, five selected object-read
requests, and required acknowledgements. There is no receiver, arming,
settings, persistence, actuator, navigation, or flight-command write API.

Version 0.2 emits snapshot schema 2. Missing/null alarm telemetry remains
unknown; only an explicit empty alarm array reports clear. Schema 1 input is
still accepted with these corrected unknown-state semantics. Preflight needs
a known mode and exactly four numeric motor observations, and approved
proposals cannot outlive their telemetry freshness budget. See
[the protocol and migration details](../docs/AI_ASSISTANT.md).

Saved UAVTalk captures can report named SystemAlarms and four-channel
ActuatorCommand observations through the same advisory tools. These remain
partial snapshots: no missing battery, sensor health, timestamp freshness or
physical output measurement is inferred from a successfully decoded frame.
The live aggregate likewise identifies the USB bridge in `source.transport`
while leaving `source.board` unknown; a CH340 identity is not aircraft identity.
