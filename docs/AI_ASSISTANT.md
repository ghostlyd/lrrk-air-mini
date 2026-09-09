# LiteWing AI assistance

The assistant is a host-side advisory service. The flight controller remains
the sole owner of stabilization, arming, failsafe, and motor output. The
assistant receives normalized telemetry and can run deterministic checks,
explain findings, compare snapshots, and create a bounded proposal for human
review. It has no tool for raw motor values or direct flight commands.

## Offline first

The deterministic path requires only Python and the standard library. The
current workstation has Python 3.9.6, while the package metadata requires
Python 3.11+ for the maintained runtime; the source is intentionally kept
portable enough for host-only syntax checks on the current machine.

Run the fixture without a key or network:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input ai_assistant/tests/fixtures/telemetry.jsonl \
  --audit-log /tmp/litewing-audit.jsonl \
  --prompt 'run preflight' \
  --json
```

Run host tests on a Python 3.11+ environment with the optional test extra, or
use the standard-library fallback on the current workstation:

```sh
PYTHONPATH=ai_assistant/src python3 -m unittest discover \
  -s ai_assistant/tests -p 'test_*.py'
```

## Live provider

Live mode is opt-in and requires the `openai` extra plus an approved
process-level `OPENAI_API_KEY`. No key is written by this repository, and a
key is never sent to the LiteWing. If the key or optional SDK is unavailable,
live mode fails closed; offline mode remains usable.

The live agent is limited to the read-only tool surface in
`ai_assistant/src/lrrk_litewing_ai/tools.py`. Proposals are not execution.
Approval requires an operator-provided token, the same current snapshot hash,
a short expiry, and a clear deterministic preflight report. Link loss, state
drift, alarm escalation, or expiry invalidates approval.

## Protocol boundary

The first adapter is JSONL replay. `UAVTalkAdapter` is a deliberately
read-only boundary until the NinjaPilot telemetry schema and transport are
validated against the selected target. No adapter may issue an actuator,
arming, gain, failsafe, takeoff, landing, or navigation write.
