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
## Pilot-owned wireless telemetry (source integration)

The admitted `OperatorUDP` client can now receive authenticated telemetry on
its existing connected socket. Its serialized owner can drain the latest
observation and pass only its snapshot to the advisory runtime:

```python
observation = link.take_telemetry()
if observation is not None:
    runtime.ingest(observation.snapshot)
```

Keep `link`, the operator session and all credentials outside model tools.
The owner still runs the normal bounded `step` loop and samples physical pilot
inputs only after authenticated challenges. Telemetry itself sends nothing
and never extends the pilot-input deadline. Closing the link closes the
consumer and clears pending telemetry. Do not process model requests on the
time-sensitive pilot loop; hand key-free snapshots to a separate advisory
worker. Returned observations are historical, not live-session tokens.

Snapshots are partial and labeled with receipt-time provenance. Link age stays
unknown; a valid MAC or recent receipt is not a freshness or flight-readiness
certificate. The firmware publisher and physical radio checks are not yet
integrated. See the [lifecycle evidence](../docs/verification/wifi-telemetry-lifecycle-2026-09-10.md).
## Wireless advisory handoff

`AdvisoryWorker` now supplies the session-owned consumer loop. Create a fresh
worker for each authenticated pilot session and run `worker.run` on a dedicated
host thread. Forward only validated observations using `worker.offer(item)`.
The worker creates its own `AssistantRuntime`; its trusted analysis callback
receives `(runtime, observation)`, preserving the timestamp/age sidecar. Neither
the worker API nor its runtime exposes pilot credentials or command methods.
Do not capture those capabilities in a callback closure: this is not a sandbox.

Call `worker.close()` in pilot-session cleanup. It discards pending data and
does not join or wait for analysis. An already-admitted callback may complete
historically after closure; it must not present its output as current-session
authority. Join the thread from supervision, outside the pilot loop. Set finite
API deadlines: Python cannot forcibly cancel a hung callback. An analysis
exception terminates the worker, closes its inbox and sets `worker.failed`,
without retaining or logging exception text. Do not retry/restart that worker.

Example consumer setup (offline analysis; no network request):

```python
from threading import Thread
from lrrk_litewing_ai.advisory_handoff import AdvisoryWorker
from lrrk_litewing_ai.tools import run_preflight_tool

def analyze(runtime, observation):
    report = run_preflight_tool(runtime)
    # Deliver report plus observation metadata to trusted historical display.

worker = AdvisoryWorker(analyze)
thread = Thread(target=worker.run, name="litewing-advisory")
thread.start()
# Pilot owner: worker.offer(validated_observation)
# Session cleanup: worker.close()
# Supervisor: thread.join(timeout=2); check thread.is_alive() and worker.failed
```

The idle poll interval is 50 ms, not a real-time delivery guarantee. Slow analysis
still sees only the latest partial observation, not a synchronized full-aircraft
snapshot. The integrated pilot launcher, physical wireless qualification and
live wireless-to-OpenAI acceptance remain outstanding.

`AdvisoryTelemetryInbox` in `lrrk_litewing_ai.advisory_handoff` transfers an
already-accepted `TelemetryObservation` from the local pilot owner to a separate
assistant worker. It owns no key, socket, command method, API client or thread.
The caller remains responsible for the operator loop and worker lifecycle:

- Create a fresh inbox for each admitted session. After the pilot owner calls
  `link.step(sample)` and `link.take_telemetry()`, offer any returned observation
  with `inbox.offer(observation)`. An offer that finds the lock busy or the inbox
  closed returns `False`; do not retry it in the control loop.
- Only the assistant worker calls `inbox.ingest_latest(runtime)` and then performs
  analysis or API work. Keep every use of that runtime serialized in this worker.
  The handoff releases its lock before calling `runtime.ingest`.
- In the pilot owner's cleanup, close the inbox on STOP, loss, socket failure or
  maintenance retirement, alongside existing link cleanup. This discards pending
  data and refuses new offers. It does not reopen a link or replace its failsafe.
- Closing does not cancel previously drained analysis/API work or erase an already
  loaded runtime snapshot. Such results are historical observations, not proof of
  a connected aircraft. Do not use an assistant response as a live control token.

The inbox holds **one latest partial observation**, not a complete five-object
state: newer telemetry replaces older pending data. It deliberately does not merge
old fields, renew capture times, infer link freshness, or synthesize battery values.
Its returned observation retains serialization/sample-age metadata separately from
the runtime snapshot. Python scheduling is not hard real-time. A complete operator
launcher and board-side load/recovery qualification remain separate deliverables.
