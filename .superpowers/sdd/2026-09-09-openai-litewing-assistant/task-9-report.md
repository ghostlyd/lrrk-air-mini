# Task 9 — advisory lifecycle audit chain

Date: 2026-09-10. Implementation complete locally; no independent review,
publication, provider smoke, or hardware validation is claimed.

**Review status:** The original implementation below received three Important
independent-review findings supplied by the user. Fix round 1 is recorded at
the end of this report and supersedes the original storage/latch/concurrency
limitations where stated. The earlier sections preserve the original TDD
history; no independent re-review acceptance is claimed for the fixes.

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

## Task 9 fix round 1 — independent-review Important findings

Starting HEAD: `c69ef71693bab2349ad8d277e641221aabf83816`, verified clean on
`codex/provider-audit-chain` in the same requested worktree. The three supplied
review findings were reproduced before any production changes. No subagents,
dependencies, external provider, network, credential, firmware or hardware
operation was used. The receiving-code-review and TDD skills guided this round.

Implementation/tests/operator docs commit:
`fbc3571ee9fd320a6470d245674dbb9b0a7e591a`
(`fix: make native advisory audit appends failure-atomic`). This report update
is a separate subsequent commit.

### Corrected behavior

1. Strict audit replay requires LF record terminators. CRLF is readable;
   bare CR is not a commit delimiter. A nonempty file missing its final LF is
   rejected even when the tail is syntactically complete JSON. Native append
   refuses it without adding bytes. Explicit truncated-tail inspection drops
   only the final unterminated suffix before UTF-8 decoding, including valid
   JSON, incomplete UTF-8, or whitespace, and strictly checks every terminated
   record. It never edits the file. The telemetry input adapter retains its
   previous final-newline behavior through the default helper option.
2. Native audit append now holds a process-wide reentrant lock over private
   descriptor setup, pre-append replay/head refresh, one binary record-plus-LF
   write, exact byte-count checking, post-append replay validation, and rollback.
   Replay must contain exactly one additional expected event before returning.
   Missing, corrupt, duplicate, short, partial-then-raise and complete-then-raise
   writes cannot return success. Rollback truncates the held inode to its
   original length; new-file rollback closes and identity-checks the created
   file before unlinking it. Existing empty files remain present and empty.
   Successful restoration preserves exact prior bytes, length and existence;
   permissions remain private or are tightened. No unsafe old mode is restored.
3. A recording failure still permanently blocks grant transitions, but no
   longer suppresses a distinct terminal recording attempt. After failed
   approval, recovered storage can record explicit abort, snapshot/policy
   invalidation, expiry or rejection. Still-failing storage is attempted once,
   then the generic error surfaces with terminal state and no approval digest.
   Later grants remain blocked and repeated terminal calls append nothing.

The native low-level writer receives the descriptor owned by the rollback
transaction. The existing standalone `append_record(path, record)` form also
retains its private-file protections. The optional Windows binary-open flag
avoids text translation. The permission setter and regular-file/path identity
guard are unchanged, including the Windows ACL backend and its fail-closed
missing-dependency behavior. The transaction checks the target before and
after permission setup and again before commit/cleanup.

Custom transition recorders must themselves provide the same failure-atomic
contract: commit exactly one validated event on return, or restore prior
storage before raising. The state machine cannot undo arbitrary callback
side effects. The earlier report's append-then-raise example is now exercised
inside the native transaction and its orphan event is removed before failure
surfaces; this is a storage-layer fix, not an arbitrary-callback guarantee.

### Test environment and baseline

All tests used the same command prefix recorded above:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' \
  /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=ai_assistant/src /opt/homebrew/bin/python3
```

Interpreter: existing CPython 3.14.7 on macOS. Baseline full suite at the
requested HEAD: `Ran 157 tests in 0.088s`, `OK (skipped=9)` — **148 passed,
9 skipped, zero failures/errors**. No dependency installation was needed.

### RED before production changes — all three findings

Added `test_audit_atomicity.py`, strengthened the existing no-retry test with
exact no-orphan assertions, and added the recovered/still-failed terminal
matrix. The focused suite comprised these names:

```text
ai_assistant.tests.test_audit_atomicity
ai_assistant.tests.test_transition_audit.TransitionAuditTests.test_ambiguous_write_failure_cannot_retry_a_success_transition
ai_assistant.tests.test_transition_audit.TransitionAuditTests.test_failed_approval_latches_grants_but_attempts_distinct_terminal_record
```

It was run with `unittest.defaultTestLoader.loadTestsFromNames(...)` and
`unittest.TextTestRunner`, printing each assertion's diagnostic and returning
exit 1 when unsuccessful. An initial diagnostic run produced **9 tests,
26 failures and 3 errors**. The three errors were production rejections of
uncommitted tails in explicit inspection mode: a `UnicodeDecodeError`,
`ValueError: blank JSONL line at 2`, and
`ValueError: audit record 1 is missing event_id`. Tests were adjusted to report
these missing behaviors as assertions and isolate each corrupt-write case;
no production code changed between the two RED invocations.

The definitive RED run reproduced **9 tests, 29 failing assertions, 0 errors,
0 skips**, exit 1. Complete failure accounting:

| Test / cases | Failures | Exact diagnostic or byte comparison |
| --- | ---: | --- |
| `test_append_refuses_complete_unterminated_tail_without_mutation` | 1 | `AssertionError: ValueError not raised` |
| `test_append_then_raise_restores_exact_prior_bytes_and_existence`: missing, empty and populated destinations, each complete/partial append | 6 | Exact pre/post byte-or-None comparisons failed with `failed append changed pre-append bytes/existence`; complete writes retained the failed event, partial writes retained `b'{"event_at":"2026'` as added bytes |
| `test_complete_json_without_newline_is_not_committed`, complete JSON | 1 | `AssertionError: ValueError not raised` |
| Same test, invalid UTF-8 suffix | 1 | `AssertionError: uncommitted tail was parsed: UnicodeDecodeError` |
| Same test, whitespace suffix | 1 | `AssertionError: uncommitted tail was parsed: ValueError` |
| `test_post_append_validation_rejects_missing_or_corrupt_record`, missing/corrupt/duplicate | 3 | `AssertionError: ValueError not raised` |
| `test_short_binary_write_cannot_commit_an_event` | 1 | `AssertionError: OSError not raised` |
| `test_truncated_mode_skips_only_unterminated_tail` | 1 | `AssertionError: complete JSON tail was validated as a committed record` |
| `test_two_logs_serialize_refresh_write_and_rollback`, success/failure | 2 | `AssertionError: True is not false : second append overtook uncommitted first append` |
| Strengthened `test_ambiguous_write_failure_cannot_retry_a_success_transition`, proposal/approval | 2 | Exact pre/post byte-or-None comparisons failed with `native failed grant left an orphan success event` |
| `test_failed_approval_latches_grants_but_attempts_distinct_terminal_record`, still failing: abort/snapshot/policy/expire/reject | 5 | `AssertionError: 0 != 1 : terminal recorder was not attempted` |
| Same test, recovered: abort/snapshot/policy/expire/reject | 5 | `AssertionError: recovered recorder was suppressed for distinct terminal transition` |

Random event IDs and timestamps make full byte-diff strings vary between runs;
the tests compare the exact byte snapshots, not event counts alone. Both
absent-file and existing-empty-file states are explicitly distinct assertions.

The concurrency test holds the first low-level append behind an event while
a second preconstructed `AuditLog` tries to append. It witnessed the second
writer finishing prematurely in RED. In GREEN the second writer waits until
the first commits or rolls back. The failure case also proves rollback cannot
remove a subsequent writer's committed event.

### Initial GREEN and additional boundary review

Implemented the three fixes minimally, then ran:

```sh
-m unittest ai_assistant.tests.test_audit_atomicity \
  ai_assistant.tests.test_transition_audit ai_assistant.tests.test_audit \
  ai_assistant.tests.test_approval ai_assistant.tests.test_tools \
  ai_assistant.tests.test_cli_provider_audit
```

Result: **73 tests passed**, no failures/errors/skips
(`Ran 73 tests in 0.318s`). Existing Windows permission-backend tests passed
unchanged, including their exact permission-call expectations.

Added five file-boundary tests. The single-write framing, symlink/nonregular
destination, permission-failure rollback, and destination-replacement controls
passed immediately and are not counted as RED evidence. The fifth exposed
the existing parser's `splitlines()` acceptance of bare CR between records:

```text
test_strict_replay_requires_lf_between_committed_records:
AssertionError: ValueError not raised
Ran 5 tests in 0.005s
FAILED (failures=1)
```

Changed strict audit parsing to split on LF while retaining CRLF acceptance.
The same focused modules then passed **78 tests**, no failures/errors/skips
(`Ran 78 tests in 0.322s`). This is an additional RED-before-fix iteration.

Added two further integration controls without production changes:

- Actual `os.write` calls that write a partial or complete event and then
  raise, for both new proposal and approval: exact original bytes/existence,
  no orphan event, pending/idle state, and no approval digest.
- Two concurrent machines with independently constructed logs and different
  sessions, each completing three proposal/approval/abort lifecycles: one
  replayable 18-event chain, six unique proposals, correct per-proposal order,
  unchanged privacy key sets and empty sources.

Final focused result: **80 passed**, no failures/errors/skips
(`Ran 80 tests in 0.333s`). Distinct definitive RED evidence in this fix round:
**30 failing assertions** (29 + 1). Repeated diagnostics and initially passing
controls are not counted as additional RED evidence.

### Full suite, scope, leaks and compatibility

Full suite suffix: `-m unittest discover -s ai_assistant/tests -p 'test_*.py'`.

```text
Ran 172 tests in 0.359s
OK (skipped=9)
163 passed, 9 unchanged optional SDK skips, 0 failures/errors
```

The fix adds fifteen test methods and strengthens one prior method. Existing
Task 7/8 and Task 9 privacy/lifecycle tests remain green. Expected CLI failure
messages and stale synthetic-fixture output are unchanged. No provider or
hardware operation was exercised.

Staged checks before the implementation commit:

- Exact file-set assertion passed: `approval.py`, `audit.py`, `jsonl.py`,
  `test_audit_atomicity.py`, `test_transition_audit.py`, `ai_assistant/README.md`
  and `docs/AI_ASSISTANT.md` (all code/tests under their existing package paths).
- AST comparison against `c69ef71693bab2349ad8d277e641221aabf83816` confirmed
  unchanged `TOOL_SCHEMAS`, `ALLOWED_ACTIONS`, `TransitionReason`, provider
  execution function, `_private_mode_setter`, and `_require_regular_target`.
- Added source/test lines had no matches for subprocess/socket/network clients,
  serial calls, environment/key lookups, credential/bearer/private-key patterns,
  or flight-command additions (`rg` exit 1, empty result).
- Changed Python source/tests parse with Python 3.11, 3.12, 3.13 and 3.14 grammar.
  Runtime tests executed only on macOS CPython 3.14.7; Windows ACL backend
  branches were simulated by the existing tests. No native Windows/Linux or
  alternate Python runtime execution is claimed.
- The explicit key-absence assertion passed under the deny-network sandbox.
- `git diff --check` and `git diff --cached --check` passed.

Declared Python/platform support and dependencies are unchanged. No firmware,
transport, provider, CLI/runtime wiring, policy or model-visible schema change
was made in this round. Custom recorders now have an explicit failure-atomic
contract. Audit files with unterminated or bare-CR-delimited records must be
inspected/repaired explicitly; telemetry adapter input compatibility remains
unchanged. An audited `APPROVED` state is still advisory only.

The shared lock serializes native operations in one process, including aliases
and readers using `validate_replay`. Callers still serialize each mutable state
machine, and coordinate cross-process or external file access themselves.
The writer's rollback contract covers append exceptions while the held file
and rollback operations remain available. It is not fsync-backed crash
recovery, cannot restore a destination replaced by an uncoordinated actor,
and cannot overcome filesystem failures that prevent truncate/unlink. Those
conditions still require storage inspection; they never authorize a new
in-memory approval. No arbitrary callback rollback guarantee is claimed.

No push, PR, merge, external message, installation, subagent, provider/key,
firmware or hardware operation occurred. The branch/worktree are retained for
the next independent review.
