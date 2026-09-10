# LiteWing AI assistant

This package is a host-only advisory layer for the NinjaPilot LiteWing port.
It reads normalized telemetry, runs deterministic preflight checks, records
redacted hash-chained audit events, and creates bounded proposals for explicit
human review.

Separate operator tools, not AI tools, provide USB credential maintenance and
an authenticated application-key reachability check. See [operator provisioning](#operator-provisioning).

Approval is a short-lived advisory record bound to the exact telemetry hash
and configured safety policy. Proposals and approval results carry the
human-readable analyzer/policy version and a canonical JSON SHA-256 policy
hash; both participate in the proposal hash. Changing `runtime.policy` or
ingesting telemetry with a different bound snapshot hash immediately aborts
pending/approved state and clears the approval digest. Identical telemetry or
an equivalent policy does not create drift or extend freshness. Approval
requires an explicit human token, which is never stored or returned raw, and
grants no flight execution authority. See [approval policy binding](../docs/AI_ASSISTANT.md#offline-first).
Policy numeric fields must be finite numbers within their documented ranges;
signed zero is canonicalized to `0.0`. Accepted IMU identities must be a list
or tuple of non-empty strings and are normalized to a deterministic immutable
tuple for exact identity matching; bare strings are rejected.
Policy replacement through either `runtime.policy` or
`runtime.approvals.policy` clears the cached preflight report.

Optional lifecycle recording is configured with
`AssistantRuntime(audit=AuditLog(path, session_id))`; the CLI attaches its
`--audit-log` destination to that same runtime. Without a recorder, library
use creates no audit file. Every actual lifecycle transition appends one
`proposal_ready`, `proposal_approved`, `proposal_rejected`, `proposal_expired`,
or `proposal_aborted` event. These events contain only state/from-state,
proposal ID/hash, snapshot hash, policy version/hash, allowlisted action kind,
and an enumerated reason code. They exclude rationale, expected effect,
reject/abort prose, human tokens and token hashes, raw observations, and
provider content. See [lifecycle audit fields](../docs/AI_ASSISTANT.md#advisory-lifecycle-audit-events).

Audited proposal/approval creation cannot succeed if recording fails.
Invalidation still clears approval and enters a terminal state before raising
`ApprovalAuditError`; policy/observation updates also clear cached reports.
A write error permanently disables further grants from that machine, while
distinct abort/invalidation/rejection/expiry transitions still attempt their
terminal event once. Native `AuditLog` rolls back partial or complete failed
appends to the prior file bytes and existence, and validates replay before
returning success. A custom recorder must provide the same failure-atomic
contract; the state machine cannot undo arbitrary callback side effects.
Terminal records cannot be aborted again.

Primary descriptor close is part of the native transaction. An independent
rollback descriptor retains the exact inode across close failures; rollback
truncates and syncs that inode before reporting failure. Ambiguously closed
descriptor numbers are never retried. A final redundant handle-close error is
cleanup, so it cannot report a failed grant after commit. OS close errors can
leave an open handle until process exit; see the documented
[close and recovery limits](../docs/AI_ASSISTANT.md#advisory-lifecycle-audit-events).

Audit records commit with a terminating LF (CRLF is readable). Unterminated
tails are refused even if they contain valid JSON. Truncated-tail replay is
read-only inspection of the committed prefix; it does not repair the file.
Native logs and replay share a process-wide lock, so separate log instances
can safely append concurrently within one process. Cross-process access still
requires external serialization; this is not a crash-atomic transaction log.
An audited `APPROVED` record remains advisory and grants no flight execution.

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

With `--live-agent --prompt ... --audit-log ...`, the CLI appends native
hash-chained `provider_request` and `provider_result` events. They contain only
provider mode, the current snapshot hash, UTF-8 text byte counts and SHA-256
digests, and a completed/blocked outcome (only the exception class on failure).
Raw prompts, responses, exception messages, credentials, authorization and
environment data, raw serial bytes, and hidden reasoning are excluded from
these events. Successful response stdout is unchanged; provider-failure stderr
is generic. Treat stdout separately if retaining a response transcript.

Offline prompts, no-prompt validation, and runs without an audit destination
produce no provider events. The offline CLI integration tests substitute only
the external provider runner and exercise the real audit chain without the
SDK, a key, or network access. They establish implementation behavior; a
future live-provider smoke requires separate authorization and evidence.
See [provider event fields](../docs/AI_ASSISTANT.md#provider-audit-events).

UAVTalk is an adapter boundary, not a flight-command channel. Deterministic
JSONL and saved-capture replay keep safety behavior testable without a board.
The optional `uavtalk` extra also enables one bounded live aggregate from the
exact CH340 USB identity and location selected by the operator:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input-format uavtalk-live \
  --device /dev/cu.YOUR_DEVICE \
  --usb-location YOUR_USB_LOCATION \
  --private-capture /path/to/new-private-capture.uavtalk \
  --duration 2 --json
```

The destination must not already exist or alias `--audit-log`. It is created
mode `0600`, capped at 1 MiB, and never committed automatically. Live transport deasserts DTR/RTS
before opening the port, uses exclusive 57600-baud access, and matches USB
`1A86:7522` plus the exact topology location before opening. Its outbound
allowlist contains only telemetry handshake states, five selected object-read
requests, and required acknowledgements. There is no receiver, arming,
settings, persistence, actuator, navigation, or flight-command write API.

The host package supports CPython 3.11 through 3.14 on macOS, Linux, and
Windows. Audit files are made private before any record bytes are written:
macOS and Linux use descriptor-bound `fchmod`, while Windows installs the
pinned `oschmod` 0.3.12 and `pywin32` 312 ACL backend. The destination is
checked against the open descriptor before and after permissions are applied,
so a symlink or path replacement is rejected instead of receiving telemetry.

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

## Operator provisioning

Install this package with its `uavtalk` extra. The current serial operator
commands support macOS CH340 devices; private provisioning storage supports
macOS/Linux, not Windows. Use an existing owner-only, ACL-free `0700` directory
outside Git. Never pass credentials as command arguments or capture outbound
provisioning traffic in an audit log.

```text
litewing-provision create --directory PRIVATE_DIRECTORY --device EXACT_PORT --location EXACT_USB_LOCATION
litewing-provision reconcile --bundle EXISTING_PENDING_FILE --device EXACT_PORT --location EXACT_USB_LOCATION
litewing-check-link --bundle EXISTING_PENDING_FILE --host EXPLICIT_IPV4
```

`create` saves fresh credentials before opening serial, then submits once.
After any ambiguous result, retain all bundles and use `reconcile` on the same
pending file; do not use `create` as an automatic retry. Verified storage and
cleanup produce a separate `.stored` copy while preserving pending/old records.
File existence alone is not a successful promotion result.

`litewing-check-link` requires an already joined network and verifies a fresh
application-key challenge at UDP port 2390. It never sends CLAIM or flight
commands. It does not verify AP password, firmware identity, reboot or flight
readiness, and must not run concurrently with pilot admission. No tool performs
automatic network association, activation or reset.

Opening serial is a hardware operation: DTR/RTS are deasserted before opening,
but driver line transients remain possible. Use a secured props-removed bench;
USB-C can power motors without a battery. Source and simulated integration tests
are complete for the documented paths; physical provisioning/activation is not
yet established. See [operator CLI evidence](../docs/verification/provisioning-operator-cli-2026-09-10.md),
[storage promotion](../docs/verification/credential-storage-promotion-2026-09-10.md)
and [key probe limits](../docs/verification/application-key-probe-2026-09-10.md).
