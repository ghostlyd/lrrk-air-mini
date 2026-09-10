# LiteWing AI assistance

The assistant is a host-side advisory service. The flight controller remains
the sole owner of stabilization, arming, failsafe, and motor output. The
assistant receives normalized telemetry and can run deterministic checks,
explain findings, compare snapshots, and create a bounded proposal for human
review. It has no tool for raw motor values or direct flight commands.

## Offline first

Preflight analyzer `litewing-safety-3` counts elapsed wall-clock time since
capture against the 500 ms default freshness budget. Effective link age is
the recorded link age plus that elapsed time. Old replay fixtures therefore
produce blocked readiness reports when evaluated today, while remaining useful
for inspection. An unchanged snapshot can expire before a proposal does;
approval rechecks freshness. Capture timestamps must come from trusted metadata.
An already approved proposal also rechecks preflight whenever its currentness
is queried; an unchanged snapshot hash cannot extend telemetry freshness.

Approval is a short-lived advisory record bound to both telemetry and the
configured safety policy. Proposals and approval results include
`policy_version` (the analyzer version) and `policy_hash` (SHA-256 of canonical
JSON containing the analyzer version and every `SafetyPolicy` field). Both
fields are included in `proposal_hash`. Default thresholds remain unchanged;
new proposal hashes include the policy binding, so regenerate earlier proposals.
Numeric policy values accept integers or floats and are normalized to floats
before hashing; signed zero is normalized to `0.0`. Booleans, non-numeric
values, NaN, and infinities are rejected.
Link-age and future-skew limits must be non-negative, minimum battery voltage
must be positive, and battery warning percentage must be between 0 and 100.
`accepted_imu_identities` accepts only a list or tuple of non-empty strings.
It is normalized to an immutable, duplicate-free tuple in deterministic order,
while preserving the existing default order and policy hash. IMU identity
matching is exact; a substring such as `MPU` does not match `MPU6050`.
Canonical JSON also rejects non-standard numeric constants.

Configure `AssistantRuntime(policy=SafetyPolicy(...))`, and replace a policy
through `runtime.policy = SafetyPolicy(...)`. The runtime and
`runtime.approvals.policy` share one policy source; standalone state machines
also accept `ApprovalStateMachine(operator_session, policy=...)` and public
`machine.policy` replacement. Any changed policy identity immediately moves
a pending or approved record to `ABORTED` and clears its approval digest.
Replacement through either public path also invalidates the runtime's cached
preflight report, including direct assignment to `runtime.approvals.policy`.
An invalid replacement is rejected before changing the policy or cached report.
Replacing a policy with the same identity preserves the record. This includes
signed-zero variants and accepted-identity list/tuple inputs that differ only
in order or duplicates. Approval and currentness checks recheck the bound
identity and apply that exact configured policy, including customized
freshness budgets; they never revert to defaults.

`runtime.ingest(snapshot)` immediately aborts a pending or approved record when
the incoming snapshot hash differs from the proposal's snapshot hash.
Re-ingesting identical normalized telemetry preserves the record but does not
extend its expiry or freshness budget. Ingestion only updates observations and
advisory state. A new proposal and explicit human approval are required after
invalidation; restoring an earlier policy or snapshot cannot revive approval.
The raw human token is neither retained nor returned. Approval still grants
no flight execution authority.

Normalized snapshot schema **2** distinguishes unknown alarm state (`null`)
from a complete report with no alarms (`[]`). JSONL schema 1 remains readable,
but omitted/null alarms now stay unknown rather than silently becoming clear.
Alarms, actuators and capabilities accept arrays or null, never strings,
booleans or objects (for example, `{"gps": false}` is not a declared GPS).
Attitude, battery and sensors accept objects or null, not falsy scalar/array
substitutes. Consumers must accept schema 2 output; normalization changes the
snapshot hash, so old proposal bindings are not reusable.

Missing flight mode is unknown. Motor evidence must contain exactly four
finite numeric observations under the LiteWing mapping; a partial vector does
not pass merely because its available values are in range. Reported unsafe
values still block even when the vector is incomplete. Unknown state cannot
produce an approval through the normal proposal state machine.

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

## Advisory lifecycle audit events

Attach an existing native log with `AssistantRuntime(audit=audit_log)`.
The CLI passes its configured `--audit-log` to the runtime, including the
real `propose_action` path. A standalone state machine accepts
`ApprovalStateMachine(operator_session, transition_recorder=audit_log.append)`.
The optional callback takes `(event_type, payload)` synchronously. It must be
failure-atomic: return only after committing exactly one validated event, or
restore its pre-append storage state before raising. Native `AuditLog.append`
provides this exception-rollback contract. The state machine cannot roll back
arbitrary custom callback side effects; a callback that appends and then raises
without restoring storage violates the contract. The state machine does not
choose a destination or import CLI behavior. Omitting the recorder keeps
offline library use available without creating a file implicitly.

Each actual transition produces exactly one native event, with an empty
`source` and the existing event ID, UTC append timestamp, session ID,
previous hash and event hash envelope. Use a non-secret audit session ID.
All five event payloads have exactly these keys:
`from_state`, `state`, `reason_code`, `proposal_id`, `proposal_hash`,
`snapshot_hash`, `policy_version`, `policy_hash`, and `action_kind`.
Identity metadata refers to the bound proposal, including on drift; a changed
snapshot or policy is not copied into the terminal event. `action_kind` is
restricted to the existing advisory allowlist.

| Event | Target state | Enumerated reason codes |
| --- | --- | --- |
| `proposal_ready` | `PROPOSAL_READY` | `PROPOSAL_CREATED` |
| `proposal_approved` | `APPROVED` | `HUMAN_APPROVED` |
| `proposal_rejected` | `REJECTED` | `HUMAN_REJECTED` |
| `proposal_expired` | `EXPIRED` | `TIMEOUT` |
| `proposal_aborted` | `ABORTED` | `EXPLICIT_ABORT`, `SNAPSHOT_DRIFT`, `POLICY_DRIFT`, `SAFETY_REGRESSION` |

Reasons are selected internally, never copied from human/model prose. No
lifecycle event contains rationale, expected-effect text, free-form reject or
abort reasons, human tokens or token hashes, raw telemetry, prompts/responses,
exception text or classes, credentials, environment data, serial bytes, or
hidden reasoning. This schema applies to lifecycle events; the existing
snapshot/preflight and provider event schemas retain their separate scopes.
Proposal hashes bind the existing full proposal, but hashes are not encryption;
keep the audit file private.

Legal transitions are `IDLE` or a terminal state into `PROPOSAL_READY`,
`PROPOSAL_READY` into `APPROVED` or a terminal state, and `APPROVED` into
`EXPIRED` or `ABORTED`. Aborting an idle or terminal machine raises
`ApprovalError`, including repeated abort calls. Rejected operations that do
not change state append nothing. Unchanged telemetry, equivalent policies,
early expiry checks and repeated currentness checks also append nothing.
An operation that discovers expiry or drift records the terminal transition
even when approval is refused. Expiry remains checked by existing API calls;
there is no new background timer.

Recording is fail closed. A proposal is installed only after its event append
returns; approval is granted only after its event append returns. Failures
raise `ApprovalAuditError("advisory transition audit write failed")`, suppress
backend exception text, and leave no new in-memory approval. Safety
invalidation, explicit abort and rejection instead enter their non-approved
terminal state and clear the token digest before attempting the append.
Policy and telemetry updates still take effect and clear cached preflight
reports if that append fails. Failed recording never restores approval.

Any recorder failure permanently disables subsequent grant transitions
(`PROPOSAL_READY` and `APPROVED`) from that machine, even after native storage
has been restored. A distinct terminal transition still attempts recording:
after a failed approval write, an explicit abort or safety invalidation can
record its terminal event if storage recovers. If storage still fails, the
machine stays terminal with no approval digest and raises the generic error.
There is no automatic retry of a failed terminal event, and repeated calls
cannot duplicate it. A failed terminal write can leave an older `APPROVED`
event as the last disk record; it does not make in-memory approval current.
Resolve storage errors before starting a fresh runtime and proposal. Replay
validates integrity; it does not restore live approval or establish freshness.

Multiple machines can share one `AuditLog`, and independent log instances can
append concurrently within one process, including across repeated sessions.
A shared process-wide lock serializes construction/replay and the entire
append transaction: private descriptor setup, strict chain validation/head
refresh, binary write, post-append replay validation and exception rollback.
This also covers path aliases. Callers still serialize access to each mutable
state machine; multiple processes and external file mutations require separate
coordination. Validation before and after each append costs two full replays.

The native writer submits one UTF-8 record plus LF as a single binary write,
and checks the exact returned byte count. If it writes part or all of an event
and then raises, or post-append validation fails, the held descriptor is
truncated to its original length before the exception surfaces. Existing file
bytes and length are restored, including an initially empty file. A file
created by that failed append is removed after checking its identity; cleanup
never unlinks a substituted destination. Existing permissions stay private
(or are tightened), rather than restoring an unsafe earlier mode. macOS/Linux
descriptor permissions and the existing Windows ACL backend run before any
record bytes, with regular-file/identity checks before and after setup.
Windows descriptors are opened in binary mode and closed before new-file
cleanup. Native failed proposal/approval writes therefore leave no orphan
success event under coordinated access and functioning rollback storage.

Strict audit replay requires LF-terminated records; CRLF is also accepted,
but a bare CR does not commit a record. Any nonempty file without its final LF
is rejected even if its tail parses as complete JSON. Appending refuses that
file without appending bytes. `validate_replay(path,
allow_truncated_final_line=True)` ignores only the final unterminated suffix
before decoding it, including valid JSON or partial UTF-8 bytes. It validates
every terminated record and never edits the file. This inspection mode is not
automatic recovery; resolve the tail explicitly before attempting more writes.
The telemetry input adapter retains its existing final-newline behavior.

Exception rollback is not crash recovery or a transaction across process
memory and disk. Process termination, filesystem failure that prevents rollback,
or uncoordinated destination replacement still requires manual storage/replay
inspection. No fsync durability or cross-process lock is added, and replay
cannot prove a method returned success before a process crash.

Even a successfully recorded `APPROVED` state is only an advisory human-review
record. It exposes no model approval tool, command sink, or flight execution.

## Live provider

Live mode is opt-in and requires the `openai` extra plus an approved
process-level `OPENAI_API_KEY`. No key is written by this repository, and a
key is never sent to the LiteWing. If the key or optional SDK is unavailable,
live mode fails closed; offline mode remains usable.

The live agent is limited to the read-only tool surface in
`ai_assistant/src/lrrk_litewing_ai/tools.py`. Proposals are not execution.
Approval requires an operator-provided token, the same current snapshot and
policy identities, a short expiry, and a clear deterministic preflight report.
Link loss, state or policy drift, alarm escalation, or expiry invalidates approval.

### Provider audit events

When `--live-agent --prompt` and `--audit-log` are configured, the CLI writes
`provider_request` immediately before provider setup/execution, then one
`provider_result` for a completed run or a caught provider/setup exception.
Both use the existing private, hash-chained `AuditLog.append()` format. Their
`source` is empty; their payloads use this exact metadata schema:

| Event | Payload fields |
| --- | --- |
| `provider_request` | `mode: "openai"`, `snapshot_hash`, `prompt_bytes`, `prompt_sha256` |
| Successful `provider_result` | `outcome: "completed"`, `snapshot_hash`, `response_bytes`, `response_sha256` |
| Failed `provider_result` | `outcome: "blocked"`, `snapshot_hash`, `error_class` |

Byte counts and SHA-256 digests refer to UTF-8 encodings. The snapshot hash
identifies the latest observation at each event; it does not establish
freshness, preflight success, or approval. `error_class` is only the exception
class name, never its message or traceback. There is no raw prompt, response,
credential, authorization data, environment data, raw serial data, or hidden
reasoning in a provider event. Metadata hashes are not encryption and may
permit guessing short known texts; keep audit files private.

Successful human-readable and JSON stdout retain the final answer. Retained
stdout is separate sensitive material. Failures emit generic stderr and exit
3; no-prompt validation also suppresses exception details. Offline prompts,
no-prompt validation, and runs without `--audit-log` add no provider events.
An audit write failure blocks normal completion; a process interruption or
storage failure may leave an unmatched request, which is not completion proof.

Offline real-CLI tests verify metadata, ordering, replay, and privacy using only
a substituted external provider runner. These tests do not import the SDK or
exercise a live provider. The historical September 9 smoke predates these
events; a future separately authorized live-provider smoke must produce its
own evidence. This addition supplies no flight-control or proposal authority.

## Protocol boundary

The JSONL and saved-capture adapters are deterministic replay paths.
`UAVTalkAdapter` now provides a bounded live read-side path for the pinned
NinjaPilot schema. No adapter may issue an actuator, arming, settings,
persistence, receiver, gain, failsafe, takeoff, landing, or navigation write.

### Bounded live serial collection

Install the host-only transport extra in a Python 3.11+ environment:

```sh
python3 -m pip install './ai_assistant[uavtalk]'
```

Then select the exact serial node and USB topology location reported by
`serial.tools.list_ports`, and provide a new private capture destination:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input-format uavtalk-live \
  --device /dev/cu.wchusbserial410 \
  --usb-location 4-1 \
  --private-capture /path/to/new-private-capture.uavtalk \
  --duration 2 --json
```

Live and replay arguments are mutually exclusive, and private capture and
audit paths must be distinct. The live path requires an
exact `1A86:7522` identity/location match before opening, deasserts DTR/RTS
before the open, and uses exclusive 57600-baud access. It creates the inbound
capture with exclusive-create semantics and mode `0600`, caps it at 1 MiB,
and preserves a partial capture when collection fails. Initial framing noise
is tolerated only within the 4096-byte synchronization bound; framing errors
after synchronization are fatal.

The only outbound frames are GCS telemetry handshake status 1 or 3, read
requests for `AttitudeState`, `FlightStatus`, `FlightBatteryState`,
`SystemAlarms`, and `ActuatorCommand`, and acknowledgements required for those
objects or `FlightTelemetryStats`. The collector returns only after all five
selected objects form one aggregate. It records their receipt span as link
age, combines actuator mapping/update faults with system alarms, and leaves
unobserved sensor and board identity fields unknown. A disconnect clears every
partial object so aggregates cannot cross link epochs. An Armed aggregate is
deterministically `BLOCKED`; the optional model cannot override that result.
If the fifth object shares a read with the beginning of another frame, the
collector stops all outbound traffic and spends at most 250 ms reading exactly
the bytes needed to validate that already-started frame before returning.

### Binary capture inspection

The receive-only `lrrk_litewing_ai.uavtalk` module now decodes saved binary
captures into frame records, including object ID, instance ID, raw payload,
and optional device timestamp ticks:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.uavtalk capture.bin
```

Its format follows the manifest-pinned
[NinjaPilot sender](https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja/blob/ac77304a58de6c8bd552f94668b46903adb71cb2/flight/uavtalk/uavtalk.c):
every frame includes an instance ID, length excludes the CRC byte, and the
CRC uses polynomial `0x07`. The parser accepts arbitrary chunk boundaries,
rejects malformed types, lengths, checksums, and truncated captures, and caps
payloads at the pinned generated `UAVOBJECTS_LARGEST` of 217 bytes.
Fixed synthetic test vectors use independently calculated upstream-table CRCs.

Captures must begin at a frame boundary; corruption stops decoding. Earlier
records may already have been printed when a later frame fails, so consumers
must check the command exit status. CRC provides corruption detection, not
authentication. Timestamp ticks are not wall-clock freshness evidence.

The framing command above emits raw frames. No serial port is
opened and no acknowledgment, object request, or flight command is sent.

### Capture observations in the assistant

The assistant CLI decodes `AttitudeState`, `FlightStatus`, `FlightBatteryState`,
`SystemAlarms`, and `ActuatorCommand` into partial normalized snapshots using
the pinned generated object IDs and layouts (28, 8, 30, 25 and 29 payload bytes
respectively):

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input capture.bin --input-format uavtalk \
  --captured-at 2026-09-09T10:00:00Z --prompt status --json
```

Replace the example timestamp with the capture's recorded UTC time. Replay
never assigns today's time to an old capture, and link age stays unknown.
Each supported frame is a separate partial snapshot; this avoids combining
older battery/status data with a newer attitude into apparently current state.
An arming transition is treated as armed for preflight purposes. Unknown
object IDs and control frames are skipped; invalid selected-object lengths,
nonzero instances, enum values, and non-finite numbers reject the capture.

`SystemAlarms` preserves every non-OK state by its pinned field name, including
Uninitialised states, extended statuses and nonzero substatus bytes. Only a
complete all-OK alarm object with clear extended fields produces `alarms=[]`.
Uninitialised-only reports are unknown, not healthy; warning/critical/error or
other reported alarm evidence blocks. Optional subsystem states must not be
silently cleared merely to achieve a passing report.

`ActuatorCommand` maps channels 1–4 to LiteWing's `0..1000` brushed-duty
observations, despite the inherited XML's servo-pulse unit label. Negative or
over-range values are retained for blocking findings, not clamped. Nonzero
channels outside that mapping and the reported failed-update counter become
blocking evidence. A zero failure counter does not establish a clear global
alarm state or prove physical gate-pin timing.

The replay snapshot's source identifies the decoder schema, not the aircraft's actual
firmware. IMU identity/health, physical actuator outputs, battery percentage, and board
identity remain unknown. Battery voltage/current are received observations;
the current target wrapper has no verified battery measurement producer.
The live adapter adds bounded per-object receipt aggregation and USB-bridge
identity, but it still does not authenticate the aircraft, establish physical
motor output, prove flight readiness, or authorize an AI flight action.
