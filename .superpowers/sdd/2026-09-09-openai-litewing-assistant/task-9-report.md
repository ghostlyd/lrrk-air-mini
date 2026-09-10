# Task 9 — advisory lifecycle audit chain

Date: 2026-09-10. Implementation complete locally; no independent review,
publication, provider smoke, or hardware validation is claimed.

## Scope and commits

- Worktree: `/private/tmp/lrrk-air-mini-provider-audit-chain`.
- Branch: `codex/provider-audit-chain`.
- Verified clean starting HEAD: `f9371f0045d96f57fe2150e9ccd56fe5d2000d1d`.
- Implementation/tests/operator docs commit:
  `45038c053c91cc637895a8714b1201227fe50a34`
  (`feat: audit advisory proposal lifecycle transitions`).
- This report is committed separately after the implementation.

Before editing, read completely:

1. `docs/superpowers/plans/2026-09-09-openai-litewing-assistant.md`.
2. `docs/superpowers/specs/2026-09-09-openai-litewing-assistant-design.md`.
3. `.superpowers/sdd/2026-09-09-openai-litewing-assistant/progress.md`.
4. `.superpowers/sdd/2026-09-09-openai-litewing-assistant/task-9-brief.md`.

The brief is beside this report, not at the worktree root. The existing linked
worktree and exact branch/base were verified; no worktree was created. One
writer performed all changes, without subagents. The TDD and executing-plans
skills guided test-first implementation; finishing followed the user's explicit
local-commits-only instruction. The SDD ledger is not changed to imply review
acceptance.

Implementation commit changed exactly seven files:

| File | Change |
| --- | --- |
| `ai_assistant/src/lrrk_litewing_ai/approval.py` | Optional synchronous recorder; enumerated reasons; centralized legal transitions; metadata-only payload; fail-closed writes and failure latch |
| `ai_assistant/src/lrrk_litewing_ai/audit.py` | Validate and refresh the chain head before each sequential append |
| `ai_assistant/src/lrrk_litewing_ai/tools.py` | Attach the native log through `AssistantRuntime`; retain observation updates on failed invalidation writes |
| `ai_assistant/src/lrrk_litewing_ai/cli.py` | Construct the runtime with the already configured native audit log |
| `ai_assistant/tests/test_transition_audit.py` | Sixteen focused tests, including table-driven lifecycle and failure cases |
| `ai_assistant/README.md` | Optional recording, privacy, failure semantics and compatibility |
| `docs/AI_ASSISTANT.md` | Exact event schema, reason codes, legal transitions and operational limits |

## Resulting contract

`AssistantRuntime(audit=log)` attaches `log.append` through the optional
`ApprovalStateMachine(..., transition_recorder=...)` callback. No destination
is selected by the machine. Unconfigured library use creates no file.

All successful appends use real `AuditLog` records and its existing envelope.
`source` is empty. The payload key set is exactly:

```text
from_state state reason_code proposal_id proposal_hash snapshot_hash
policy_version policy_hash action_kind
```

Events and stable internal reasons:

| Event | State | Reason codes |
| --- | --- | --- |
| `proposal_ready` | `PROPOSAL_READY` | `PROPOSAL_CREATED` |
| `proposal_approved` | `APPROVED` | `HUMAN_APPROVED` |
| `proposal_rejected` | `REJECTED` | `HUMAN_REJECTED` |
| `proposal_expired` | `EXPIRED` | `TIMEOUT` |
| `proposal_aborted` | `ABORTED` | `EXPLICIT_ABORT`, `SNAPSHOT_DRIFT`, `POLICY_DRIFT`, `SAFETY_REGRESSION` |

Metadata binds the original proposal even when new telemetry or policy causes
invalidation. Action kinds remain constrained to the existing allowlist.
There is no rationale, effect prose, reject/abort prose, human token or token
hash, raw telemetry, prompt/response, error content/class, credentials,
environment, serial data, or hidden reasoning in these lifecycle payloads.
The existing proposal hash still binds the complete proposal; no new
content-digest fields were added. Native audit session IDs remain caller
metadata and must be non-secret.

Proposal creation and approval append before installing new state. A failed
proposal write retains the prior state/proposal; a failed approval write
retains pending state with no approval digest. Terminal transitions clear the
digest and change state before attempting storage, so recording errors cannot
restore approval. Policy/telemetry changes still update the runtime and clear
cached reports. Every recorder exception surfaces as the generic
`ApprovalAuditError("advisory transition audit write failed")`, with backend
exception display suppressed.

The first recorder failure latches that machine against further grants. This
also handles a backend that appends a complete record and then raises: retry
cannot duplicate a grant event or install approval. Terminal invalidation
still occurs in memory if storage is already failed. Restoring storage does
not silently reactivate the failed machine.

## Offline test environment and baseline

All RED, GREEN and full-suite invocations used macOS network denial and an
unset `OPENAI_API_KEY`. The supported interpreter was the already installed
`/opt/homebrew/bin/python3`, CPython **3.14.7**. No dependency was installed.

Canonical command prefix, from the worktree root:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' \
  /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=ai_assistant/src /opt/homebrew/bin/python3
```

An explicit environment assertion also confirmed `OPENAI_API_KEY` was absent.
No network probe was attempted. Existing tests may substitute synthetic test
data internally; no real credential or external runner was used.

The initial baseline command accidentally selected `/usr/bin/python3`
(macOS Python 3.9). It ran 141 tests with seven errors and nine skips. All seven
errors were existing Task 7 test setup failures:
`AttributeError: 'CliProviderAuditTests' object has no attribute 'enterContext'`.
This unsupported-interpreter attempt is not counted as Task 9 RED evidence.
Switching to the existing supported interpreter required no code change.

Supported baseline:

```text
Ran 141 tests in 0.052s
OK (skipped=9)
132 passed, 9 optional SDK skips, 0 failures/errors
```

## TDD round 1 — runtime attachment and independent log heads

Added two tests before changing production code. Command suffix:

```sh
-m unittest -v ai_assistant.tests.test_transition_audit
```

RED: **2 tests, 2 failures, 0 errors/skips**, exit 1.

Exact assertion failures:

```text
test_alternating_independent_logs_refresh_chain_head:
AssertionError: independent sequential writers broke replay: audit hash chain broken at record 2

test_tool_proposal_is_recorded_before_return:
AssertionError: runtime has no optional audit attachment: AssistantRuntime.__init__() got an unexpected keyword argument 'audit'
```

The chain test constructs two logs before writing, alternates real appends,
and calls real `validate_replay`. It exposed the stale cached previous hash.
The tool test reports the missing constructor feature as a focused assertion,
then requires the exact on-disk proposal metadata before the tool returns.

Minimal first implementation attached the optional callback, recorded
proposal creation, and refreshed the chain head before append. GREEN included
the new tests and existing approval/audit/runtime tests:

```sh
-m unittest -v ai_assistant.tests.test_transition_audit \
  ai_assistant.tests.test_approval ai_assistant.tests.test_audit \
  ai_assistant.tests.test_tools
```

**44 tests passed**, zero failures/errors/skips (`Ran 44 tests in 0.012s`).

## TDD round 2 — lifecycle, privacy and failed storage

Added twelve further test methods before implementing the remaining behavior.
The focused RED invocation ran **14 tests**, with **47 failing assertions**
including subtests, **0 errors**, and **0 skips**, exit 1. Three methods passed:
the two round-1 tests and the no-recorder compatibility control. The latter is
explicitly not new RED evidence. A second compact RED run reproduced the same
47 failures before implementation.

The full failure accounting below identifies every failing case. For missing
events, the observed/expected rows are given without unittest's abbreviated
`[N chars]` diff formatting.

| Test / cases | Failures | Exact failed condition or assertion |
| --- | ---: | --- |
| `test_all_terminal_paths_record_exactly_once`: reject pending; abort pending/approved; explicit expire pending; timeout pending/approved; snapshot drift pending/approved; stale pending/approved; incomplete pending; blocked pending | 12 | Actual replay contained only `('IDLE', 'PROPOSAL_READY', 'PROPOSAL_CREATED')`; each expected its terminal row, plus `('PROPOSAL_READY', 'APPROVED', 'HUMAN_APPROVED')` for approved cases |
| `test_ambiguous_write_failure_cannot_retry_a_success_transition`, proposal | 1 | `AssertionError: OSError('private-storage-error-e82c') is not an instance of <class 'RuntimeError'>` |
| Same test, approval | 1 | `AssertionError: audit write failure did not surface` |
| `test_approval_write_failure_does_not_grant_approval` | 1 | `AssertionError: audit write failure did not surface` |
| `test_cli_attaches_audit_to_real_advisory_tool_path` | 1 | `AssertionError: Lists differ: ['snapshot_received', 'preflight_result'] != ['snapshot_received', 'preflight_result', 'proposal_ready']` |
| `test_metadata_key_sets_exclude_prose_tokens_and_raw_observations` | 1 | `AssertionError: 3 != 7` |
| `test_policy_and_ingestion_drift_record_bound_identity`: runtime policy, machine policy, ingest, analyzer-before-approve, analyzer-before-currentness; each pending/approved | 10 | `AssertionError: 'proposal_ready' != 'proposal_aborted'` |
| `test_proposal_write_failure_does_not_install_proposal` | 1 | `AssertionError: OSError('private-storage-error-e82c') is not an instance of <class 'RuntimeError'>` |
| `test_rejected_calls_and_unchanged_observations_add_no_event` | 1 | `AssertionError: 1 != 2` (successful approval lacked its event) |
| `test_safety_write_failures_still_invalidate_and_update_runtime`: abort pending/approved, reject pending, expire pending, timeout approved, snapshot approved, stale approved, policy pending/approved, ingest pending/approved | 11 | `AssertionError: audit write failure did not surface` |
| Same test, timeout pending | 1 | `AssertionError: ApprovalError('proposal has expired') is not an instance of <class 'RuntimeError'>` |
| Same test, snapshot pending | 1 | `AssertionError: ApprovalError('telemetry changed after proposal creation') is not an instance of <class 'RuntimeError'>` |
| Same test, stale pending | 1 | `AssertionError: ApprovalError('current safety report is not complete and clear') is not an instance of <class 'RuntimeError'>` |
| `test_shared_and_independent_logs_preserve_interleaved_machine_order` | 1 | Actual types were three `proposal_ready` events; expected the seven-event sequence below |
| `test_terminal_abort_is_illegal_even_without_a_recorder`: rejected, expired, aborted | 3 | `AssertionError: ApprovalError not raised` |

Expected terminal rows in the first test use `HUMAN_REJECTED`,
`EXPLICIT_ABORT`, `TIMEOUT`, `SNAPSHOT_DRIFT`, or `SAFETY_REGRESSION` according
to the triggering operation, with the precise source state pending/approved.
The interleaved sequence is:

```text
proposal_ready, proposal_ready, proposal_approved, proposal_rejected,
proposal_aborted, proposal_ready, proposal_expired
```

Implementation centralized transitions and reasons, attached the CLI runtime,
made terminal invalidation precede recording, and added a generic fail-stop
recording error. GREEN included all prior focused modules plus the original
Task 7 provider-audit tests:

```sh
-m unittest -v ai_assistant.tests.test_transition_audit \
  ai_assistant.tests.test_approval ai_assistant.tests.test_audit \
  ai_assistant.tests.test_tools ai_assistant.tests.test_cli_provider_audit
```

**63 tests passed**, zero failures/errors/skips (`Ran 63 tests in 0.066s`).

## TDD round 3 — review edge cases

Review identified two exceptions that could interrupt the state update order.
Added their tests before changing production code:

```sh
-m unittest -v \
  ai_assistant.tests.test_transition_audit.TransitionAuditTests.test_unencodable_token_adds_no_approval_event_or_state \
  ai_assistant.tests.test_transition_audit.TransitionAuditTests.test_policy_callback_failure_cannot_prevent_invalidation
```

RED: **2 tests, 2 failures, 0 errors/skips**, exit 1. Exact failures:

```text
test_unencodable_token_adds_no_approval_event_or_state:
AssertionError: 'APPROVED' != 'PROPOSAL_READY'

test_policy_callback_failure_cannot_prevent_invalidation:
AssertionError: 'APPROVED' != 'ABORTED'
```

Moved token digest computation ahead of approval recording/state installation.
Restored policy invalidation ahead of its callback, while invoking the callback
in `finally` so runtime cache invalidation survives audit-write failure.
The callback test also exercises the standalone recorder attachment using a
real `AuditLog`.

GREEN with the five focused modules above: **65 tests passed**, no
failures/errors/skips (`Ran 65 tests in 0.066s`).

Across the three distinct RED rounds: **51 failing assertions** (2 + 47 + 2),
with no test-harness errors. Repeated RED diagnostics are not counted twice.

## Final verification

Full suite command suffix under the same offline prefix:

```sh
-m unittest discover -s ai_assistant/tests -p 'test_*.py'
```

Final result on the implementation tree:

```text
Ran 157 tests in 0.089s
OK (skipped=9)
148 passed, 9 optional SDK skips, 0 failures/errors
```

The nine SDK skips are unchanged from the supported baseline. Expected CLI
negative-path messages and stale synthetic-fixture reports appeared during
the suite. No live provider, network, or hardware was contacted. The CLI
attachment test substitutes only the offline text facade and executes the
real proposal tool. Write-failure tests substitute only the append boundary;
one test deliberately performs the real append and then raises to exercise an
ambiguous completion. All normal event-order/privacy tests exercise actual
private files and actual replay validation.

Static scope/leak review, on the staged implementation:

- Exact changed-file set assertion passed for the seven files listed above.
- AST comparison against the requested base confirmed `TOOL_SCHEMAS`,
  `ALLOWED_ACTIONS`, and CLI `_live_prompt` are unchanged.
- Added source/test lines were scanned for subprocess/socket/network clients,
  serial access, environment/key lookup, key/bearer/private-key patterns,
  actuator/motor/arm/disarm/gain/failsafe command additions. No matches;
  `rg` exit 1 denotes the empty result.
- Manual diff review confirmed the single literal lifecycle payload key set,
  internal enum selection, empty native source, and absence of free-form
  logging. Privacy tests additionally exclude synthetic prose/observation
  markers, human token, and the independently computed token hash from disk.
- No firmware, UAVTalk transport, provider module, safety policy, dependency,
  package/build configuration, or model-visible schema changes.
- `git diff --check` and `git diff --cached --check` passed before commit.

## Compatibility judgment and limits

Task 7 provider metadata behavior and Task 8 canonical policy/safety binding
remain compatible, supported by the unchanged baseline tests and focused
regression runs. Existing API arguments and proposal/approval return shapes
are preserved; the recorder/runtime argument and lifecycle events are additive.
Unconfigured offline use still creates no file. No approval or command tool
was added, and an audited `APPROVED` record grants no execution authority.

Two deliberate tightenings are documented: aborting an already terminal record
now raises `ApprovalError` without a transition/event, and an audited machine
that experiences a recording error cannot grant again. Callers relying on
terminal abort as an idempotent cleanup call must guard its state. Token
encoding failure now leaves the proposal pending and adds no approval event.

Independent `AuditLog` instances refresh the prior hash for sequential writes;
multiple machines using the same object or preconstructed independent objects
preserve the tested global sequence. Refresh validates the entire file, so
append now costs a full replay. Callers must serialize operations; concurrent
threads/processes require external locking and were not claimed or implemented.

Storage and in-memory state are not a crash-atomic transaction. A terminal
write failure can leave an old approved disk record, and an append-then-raise
can leave an event for an operation that did not return success. The machine
remains non-approved and fail-stopped in those cases. Replay proves chain
integrity, not live authorization, freshness, or successful method return.
The existing writer supplies no new fsync/crash-recovery guarantee. Resolve
storage/replay failures before creating a fresh runtime and proposal; never
reconstruct approval automatically from the last event.

No push, PR, merge, external message, dependency installation, provider/API-key
operation, firmware action, or hardware operation was performed. The branch
and worktree are preserved for review.
