# Task 8 implementation and verification report

## Status and source identity

Task 8 is implemented and locally verified. Approval uses the runtime's exact
safety policy, binds its identity into the proposal, and aborts active advisory
records on policy or ingested telemetry drift. No flight execution authority
was added.

- Worktree: `/private/tmp/lrrk-air-mini-provider-audit-chain`
- Branch: `codex/provider-audit-chain`
- Clean starting HEAD: `d0a609e393e221812917665d8fd4f869de4232ff`
- Implementation commit: `8023254843423d0db22aa7901a74a35fffb500e9`
- Implementation commit subject: `fix: bind advisory approvals to runtime safety policy`
- Implementation tree: `4fff37499c23bc6d7430e237bc76e01cfc7feccb`
- Implementation delta: 7 files, 343 insertions, 21 deletions.
- After the implementation commit, `git status --short` was empty.
- This report is the only file in the separate report commit, intended subject
  `docs: record Task 8 policy binding verification`. Its containing commit can
  be resolved with `git log -1 --format=%H -- .superpowers/sdd/2026-09-09-openai-litewing-assistant/task-8-report.md`.

The complete task brief, implementation plan, design, and progress ledger were
read before editing. The supplied existing linked worktree and branch were
verified; no worktree or branch was created. Work was performed by one writer,
without subagents, network use, dependency installation, a real API key,
provider calls, or hardware access. There was no push, PR, or merge.

## Implementation

`SafetyPolicy.policy_hash()` hashes canonical JSON containing
`analyzer_version` and all dataclass policy fields. It uses the existing
sorted-key, compact, ASCII-escaped canonical JSON serializer and SHA-256 over
UTF-8. `policy_version` is the human-readable analyzer version,
`litewing-safety-3`. The version is shared with preflight reports. All existing
analyzer thresholds and finding semantics remain unchanged.

`ActionProposal` includes `policy_version` and `policy_hash` in serialization
and in the bytes used to calculate `proposal_hash`. Approval results return
the same bound identity. Tests hold proposal ID and time constant to show
that changing any of the five policy fields, or the analyzer version, changes
both identities independently of UUID randomness. An independent literal
canonical JSON fixture verifies the policy digest.

`ApprovalStateMachine` accepts a policy at construction and exposes public
`policy` replacement. Replacement compares against the proposal-bound version
and hash and immediately aborts pending or approved state on mismatch, using
the existing abort path to clear the approval digest. Both `approve()` and
`approval_is_current()` recheck identity before approving/reporting currentness
and explicitly supply that configured policy to the analyzer. Restoring the
old policy does not revive an aborted record.

`AssistantRuntime.policy` delegates to the state machine's policy, so there
is one authoritative source for runtime preflight, proposal creation,
approval, and currentness. Replacing `runtime.policy` also clears the cached
report. `ingest()` compares the incoming snapshot hash directly with the
active proposal's binding and immediately aborts on mismatch. It then retains
the normal previous/latest observation and report-cache behavior. Identical
normalized telemetry does not invalidate a record or reset its times.

The allowed advisory actions, explicit human token requirement, proposal ID,
operator session and snapshot binding, one-use approval transition, expiry,
and rejection of BLOCKED/INCOMPLETE reports remain intact. Raw token retention
and output are absent; only the existing token digest is retained on approval.
Operator documentation now explains the policy binding, public replacement,
telemetry drift, compatibility implications, and lack of execution authority.

## Offline execution environment

Every baseline, RED, focused GREEN, and full-suite test command below ran from
the worktree root under macOS `sandbox-exec` with this profile:

```text
(version 1)(allow default)(deny network*)
```

All test processes explicitly removed `OPENAI_API_KEY`, set
`PYTHONDONTWRITEBYTECODE=1`, and used the existing private scratch directory
as `TMPDIR`. The interpreter was `/opt/homebrew/bin/python3`, CPython 3.14.7.
Standard-library unittest discovery required no package installation.

An additional environment assertion ran successfully (exit 0):

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src /opt/homebrew/bin/python3 -c 'import os, sys; assert "OPENAI_API_KEY" not in os.environ; print("OPENAI_API_KEY absent; Python", sys.version.split()[0])'
```

Output: `OPENAI_API_KEY absent; Python 3.14.7`. No environment values or
credentials were printed.

## Baseline

Exact command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_*.py'
```

Result: exit 0, `Ran 114 tests in 0.043s`, `OK (skipped=9)`:
105 passed and 9 optional SDK tests skipped.

## TDD evidence

Production changes followed observed behavioral failures. The unchanged-policy
and identical-telemetry cases are compatibility controls: they intentionally
passed before implementation and were not counted as new RED evidence.
Subtest failures are counted separately by unittest from test methods.

### Cycle 1: configured policy must govern approval and currentness

The first two test bodies were added without production changes. Exact initial
command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_tools.ToolTests.test_configured_battery_block_cannot_be_approved ai_assistant.tests.test_tools.ToolTests.test_approval_and_currentness_use_configured_freshness_budget
```

Initial result: exit 1, 2 tests, 1 failure and 1 error. The strict 4.10 V policy
reported the 3.90 V snapshot BLOCKED, yet approval returned successfully
(`ApprovalError not raised`). The longer freshness-budget case raised
`ApprovalError` because approval used the 500 ms default instead of the
configured 2000 ms budget. This was a real behavior error, not a missing
import or fixture failure.

Before changing production, the latter test converted that unexpected
exception into an explicit assertion failure, and a separate currentness
regression was added to exercise that boundary independently. Exact RED:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_tools.ToolTests.test_configured_battery_block_cannot_be_approved ai_assistant.tests.test_tools.ToolTests.test_approval_and_currentness_use_configured_freshness_budget ai_assistant.tests.test_tools.ToolTests.test_currentness_does_not_fall_back_to_default_freshness_budget
```

Result: exit 1, `Ran 3 tests in 0.002s`, `FAILED (failures=3)`, no errors.
Failures were unexpected strict-policy approval, unexpected refusal under
the longer configured freshness budget, and false currentness under that
same budget.

Minimal production change: pass the configured policy into the state machine
and into both analyzer calls. Exact GREEN:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_approval ai_assistant.tests.test_tools
```

Result: exit 0, `Ran 19 tests in 0.003s`, `OK`. The longer-budget test also
checks the exact effective-age boundary: 2000 ms passes and 2001 ms aborts.

### Cycle 2: canonical policy identity and proposal binding

Added tests for canonical identity and matching approval output, every policy
field changing proposal identity, and analyzer-version changes. Exact RED:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_approval.ApprovalTests.test_proposal_policy_identity_is_canonical_and_shared_with_approval ai_assistant.tests.test_approval.ApprovalTests.test_every_policy_field_changes_proposal_identity ai_assistant.tests.test_approval.ApprovalTests.test_analyzer_version_changes_policy_and_proposal_identity
```

Result: exit 1, `Ran 3 tests in 0.002s`, `FAILED (failures=7)`. Policy identity
was absent from serialization; all five field variations and an analyzer
version change left the fixed-ID/fixed-time proposal hash unchanged.

Minimal production change: canonical policy digest/version, shared analyzer
version constant, and bound proposal/approval fields. Exact GREEN:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_approval ai_assistant.tests.test_tools ai_assistant.tests.test_safety
```

Result: exit 0, `Ran 38 tests in 0.004s`, `OK`.

### Cycle 3: public policy replacement and drift rechecks

Added tests for immediate pending/approved invalidation for all five policy
fields, unchanged-policy compatibility, version drift at approval and both
pending/approved currentness boundaries, runtime replacement and reproposal,
and shared runtime/state-machine policy. Exact RED:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_approval.ApprovalTests.test_policy_replacement_aborts_pending_and_approved_records ai_assistant.tests.test_approval.ApprovalTests.test_equivalent_policy_replacement_preserves_pending_and_approved_records ai_assistant.tests.test_approval.ApprovalTests.test_analyzer_drift_is_rechecked_before_approval_and_currentness ai_assistant.tests.test_tools.ToolTests.test_runtime_policy_replacement_aborts_active_records_and_updates_preflight ai_assistant.tests.test_tools.ToolTests.test_runtime_and_state_machine_share_policy_updates
```

Result: exit 1, `Ran 5 tests in 0.004s`, `FAILED (failures=16)`. Ten field/state
combinations retained PROPOSAL_READY or APPROVED; three version-drift checks
failed; two runtime replacement cases retained active state; direct public
state-machine replacement left runtime preflight on the old policy. The
equivalent-policy compatibility control passed.

Minimal production change: public policy setters, one shared policy source,
active-record invalidation, and identity checks before approval/currentness.
The runtime constructor was made explicit to expose a property backed by that
single source while preserving its argument names, order, and defaults.

GREEN used the exact three-module command from Cycle 2. Result: exit 0,
`Ran 43 tests in 0.006s`, `OK`.

### Cycle 4: immediate invalidation during ingestion

Added pending/approved tests for changed snapshot ID, armed state, and unknown
alarm state; identical object and reconstructed identical telemetry controls;
and a proposal created before the runtime has any prior ingested snapshot.
Exact RED:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_tools.ToolTests.test_changed_snapshot_ingestion_immediately_aborts_active_records ai_assistant.tests.test_tools.ToolTests.test_identical_snapshot_ingestion_preserves_active_records ai_assistant.tests.test_tools.ToolTests.test_ingestion_compares_with_proposal_bound_snapshot
```

Result: exit 1, `Ran 3 tests in 0.003s`, `FAILED (failures=7)`. Six changed
snapshot/state combinations and the proposal-without-prior-ingestion case
remained active. Identical telemetry controls passed.

Minimal production change: compare the incoming hash with the active
proposal's bound hash and invoke advisory abort before updating observations.
GREEN used the exact three-module command from Cycle 2. Result: exit 0,
`Ran 46 tests in 0.007s`, `OK`. This includes 30 approval/runtime tests and
16 analyzer tests; there are no focused-suite skips.

## Full final assistant suite

After all production changes and operator documentation updates, exact command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_*.py' -v
```

Result: exit 0, `Ran 128 tests in 0.048s`, `OK (skipped=9)`:
119 passed, 9 skipped, zero failures/errors. There are 14 new test methods;
no pre-existing test was removed or weakened.

All nine skips say `install the optional openai extra`, matching baseline.
No dependency was installed to remove those skips. Existing CLI failure-path
tests print expected generic blocked messages and stale-fixture preflight
reports; these were not test failures. Existing transport tests use synthetic
fixtures/test doubles, not a connected device. No live provider was exercised.

## Static scope and leak checks

These exact read-only scans ran on the final implementation before commit:

```sh
rg -n 'socket|requests|urllib|httpx|subprocess|os\.system|\bexec\(|\beval\(|\bserial\b|OPENAI_API_KEY|\b(arm|disarm|takeoff|land|write_actuator|set_gain|set_failsafe)\(' ai_assistant/src/lrrk_litewing_ai/approval.py ai_assistant/src/lrrk_litewing_ai/safety.py ai_assistant/src/lrrk_litewing_ai/tools.py
```

Result: exit 1, no matches (the expected ripgrep no-match status).

```sh
rg -n 'sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----|Bearer [A-Za-z0-9._-]{16,}' ai_assistant/src/lrrk_litewing_ai/approval.py ai_assistant/src/lrrk_litewing_ai/safety.py ai_assistant/src/lrrk_litewing_ai/tools.py ai_assistant/tests/test_approval.py ai_assistant/tests/test_tools.py ai_assistant/README.md docs/AI_ASSISTANT.md
```

Result: exit 1, no matches. This is a targeted pattern scan, complemented by
manual diff review and the raw-token non-retention/output regression test;
it is not a claim that a regex proves the absence of every possible secret.

Exact out-of-scope tracked-diff check:

```sh
git diff --exit-code d0a609e -- . ':(exclude)ai_assistant/src/lrrk_litewing_ai/approval.py' ':(exclude)ai_assistant/src/lrrk_litewing_ai/safety.py' ':(exclude)ai_assistant/src/lrrk_litewing_ai/tools.py' ':(exclude)ai_assistant/tests/test_approval.py' ':(exclude)ai_assistant/tests/test_tools.py' ':(exclude)ai_assistant/README.md' ':(exclude)docs/AI_ASSISTANT.md'
git diff --check
git diff --cached --check
```

All returned exit 0 with no output. Manual review of the complete production
and test diffs confirmed:

- No change to firmware, UAVTalk transport, adapters, providers, CLI execution,
  dependency metadata, motor/actuator writes, arming/disarming, gains, or
  failsafe settings.
- `ALLOWED_ACTIONS` and `TOOL_SCHEMAS` are unchanged. Policy assignment is a
  host Python lifecycle API, not a new model tool or flight command.
- New production operations are hashing/serialization, policy delegation,
  deterministic analyzer calls, and advisory state invalidation.
- No new network, subprocess, filesystem-write, environment-read, or hardware
  path exists in the changed production code.
- Existing approval replay, snapshot freshness, expiry, missing-evidence,
  BLOCKED/INCOMPLETE, and forbidden-action regressions still pass.
- New tests only substitute the clock, UUID source, or analyzer version to control
  nondeterminism and test identity drift. The runtime, policy hashing, analyzer,
  and approval state machine are real components.

Implementation staging and commit also ran under deny-network with the API key
unset. The report path is ignored by `.superpowers/sdd/.gitignore:1:*` and is
force-added explicitly for the separate report commit.

## Changed files and SHA-256

Hashes below were read from the clean implementation commit with
`shasum -a 256` after committing. Paths are relative to the worktree root.

| File | Purpose | SHA-256 |
| --- | --- | --- |
| `ai_assistant/src/lrrk_litewing_ai/approval.py` | Policy-bound records and lifecycle checks | `a11e845e718eed4dd2e503a3ccbfe1d87ddca3303d6ae7b6c9b0b19dd06b4058` |
| `ai_assistant/src/lrrk_litewing_ai/safety.py` | Canonical policy identity and shared analyzer version | `bf13cbf4e2a9f26fe23966534f2df3b3ac84980ec9ded5cbd25ede39936e623e` |
| `ai_assistant/src/lrrk_litewing_ai/tools.py` | Shared runtime policy and ingestion invalidation | `39c94651ec08cdff0e1c619eea65967884d1aee1abb0b484f7c3dcc6e73b7bef` |
| `ai_assistant/tests/test_approval.py` | Six identity/invalidation test methods | `0c4c0251158a0d7a9b4c4b593aa2c8890293525fbb51ed5b0a13791820bed139` |
| `ai_assistant/tests/test_tools.py` | Eight configured-policy/ingestion test methods | `db2824e354234a43ac20a408cf8acf41b4b60a182e6b519976905b8d27fd1631` |
| `ai_assistant/README.md` | Advisory policy-binding overview | `2d583bf4f7fe571a206199c79a401699536723be10497ca66e738fa84c648ec2` |
| `docs/AI_ASSISTANT.md` | Operator API, invalidation and migration details | `45d58169d1a8656c1c9c381c9d69490f242674b3a56ea32badf51d117d9d266b` |

The eighth changed file across both commits is this report. Its own hash and
commit ID are deliberately not embedded in its content to avoid self-reference.

## Concerns and limits

- No unresolved failure was found within Task 8. Nine optional SDK tests remain
  skipped, as at baseline; there is no claim of live provider or hardware proof.
- Proposal serialization now requires policy version/hash and therefore changes
  proposal hashes even for default policy values. External consumers that
  instantiate `ActionProposal` directly must supply the new binding; earlier
  proposals need regeneration rather than invented default policy attribution.
- `AssistantRuntime` preserves constructor arguments and operational defaults,
  but is now an ordinary class with an explicit constructor and policy property.
  Generated dataclass equality/repr/introspection are not preserved. Repository
  consumers use its operational API; the full assistant suite passed.
- Policy inputs remain trusted host-side `SafetyPolicy` values under the existing
  typed contract. This slice does not add policy editing through the model,
  generalized configuration validation, concurrent lifecycle synchronization,
  or an execution sink.
- Analyzer behavior changes must continue to bump the analyzer version. The
  identity covers the declared version and all policy fields, not a hash of the
  Python source implementation.
- The policy hash is deterministic identity, not authentication. Existing token
  hashing is unchanged; raw human tokens are not retained or returned.
- The review was local and performed by the implementing writer. No independent
  reviewer/subagent or remote integration gate was used or claimed.
