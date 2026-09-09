# OpenAI LiteWing Assistant Design

## Status

Approved as part of the LiteWing/NinjaPilot target. This is a host-side
advisory system, not an onboard flight controller.

## Goal

Provide an OpenAI-assisted operator interface that can inspect telemetry,
explain faults, run deterministic preflight checks, and propose bounded actions
without bypassing the human pilot, the flight controller, or the emergency
disarm path.

## Safety boundary

```text
LiteWing flight controller
  ^  read-only telemetry / UAVTalk
  |
Host adapter -> deterministic safety analyzer -> human approval -> proposal log
                                      |
                                      +-- optional deterministic command sink
                                          (disabled by default; never model-owned)
```

The model never receives a motor-output tool. The assistant has no authority to
arm, take off, land, change gains, or alter failsafe settings automatically.
The first release exposes proposals only. Any future command sink must require
an explicit operator approval token, validate state again immediately before
execution, enforce a timeout, and support an independent kill switch.

## Components

### 1. Normalized telemetry contract

Define a versioned, JSON-serializable `TelemetrySnapshot` containing timestamp,
link age, armed state, flight mode, attitude, gyro/accelerometer health,
battery state, sensor alarms, actuator values, and source identity. Unknown
fields remain unknown; the adapter must never fabricate GPS, altitude, or
position data.

Adapters:

- `UAVTalk` adapter for the NinjaPilot target;
- a JSONL/file adapter for deterministic tests and offline review; and
- a future ESP-Drone/cflib adapter that maps into the same contract.

### 2. Deterministic safety analyzer

The analyzer runs without an API key and returns structured findings with
severity, evidence, and remediation. It checks link freshness, armed state,
IMU identity/health, battery thresholds, alarm state, sensor availability,
actuator bounds, and whether optional positioning capabilities are actually
present. A failing preflight result is never converted into a model-approved
flight action.

### 3. OpenAI agent

Use the host Python Agents SDK only as an advisory layer. Tools are narrow,
read-only, and schema-validated:

- `get_latest_telemetry()`;
- `run_preflight()`;
- `explain_finding(finding_id)`;
- `compare_snapshots(before, after)`; and
- `propose_action(action_kind, rationale, expected_effect, expiry_seconds)`.

`propose_action` returns a proposal object; it does not call a flight command.
The agent runs in offline/dry-run mode when the SDK or API key is unavailable.
The API key is read only from the host process environment or an approved local
secret store and is never sent to the aircraft or committed to Git.

### 4. Approval and audit state machine

States are `IDLE`, `PROPOSAL_READY`, `APPROVED`, `EXPIRED`, `REJECTED`, and
`ABORTED`. Approval is bound to a proposal hash, current telemetry timestamp,
operator identity/session, and short expiry. Any link loss, state drift,
disarm, alarm escalation, or timeout invalidates approval. Every transition is
written as structured JSON with secret redaction.

### 5. CLI and test harness

The first executable is a dry-run CLI that accepts JSONL telemetry, prints a
human-readable preflight report, and records proposal/approval transitions.
Tests must prove:

- malformed and stale telemetry is rejected;
- unknown values are not treated as safe values;
- a proposal cannot become approved after its snapshot expires;
- an approval cannot be reused for another proposal;
- no tool schema contains motor outputs or raw actuator writes; and
- the assistant remains usable with no API key and no network.

## Dependencies

- Python 3.11+ for the assistant service;
- standard library for the deterministic core;
- `pytest` for tests;
- `cflib` or the pinned NinjaPilot `pyuavtalk` client only in protocol adapter
  extras;
- `openai-agents` only in the optional live-AI extra;
- an explicitly approved host secret destination for `OPENAI_API_KEY` before
  any live API call.

No dependency is installed on the ESP32-S3 flight image for AI assistance.

## Acceptance criteria

- Dry-run mode passes all safety tests without credentials or network.
- Live-agent mode can only inspect telemetry and create proposals.
- No repository file contains a secret or a default live credential.
- Disabling the host process leaves ordinary pilot control unchanged.
- The assistant reports “not enough evidence” rather than inventing missing
  position, battery, or sensor data.
- The implementation is independently testable from the firmware build.
