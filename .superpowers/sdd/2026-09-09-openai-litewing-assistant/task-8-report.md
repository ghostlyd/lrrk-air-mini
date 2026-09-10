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
- Initial report/review-round-1 base commit: `207a7dc4ceef66bccb2792f35e95e31bb40dfd27`
- Initial report subject: `docs: record Task 8 policy binding verification`
- Review-round-1 fix commit: `48b4329837b217943851fc7f4dc93f0a718b5161`
- Review-round-1 fix subject: `fix: validate assistant safety policy lifecycle`
- Review-round-1 fix tree: `158ee30427ef8e9d3e3a73a52d8ff62af9eb71d2`
- Review-round-1 delta: 8 files, 184 insertions, 8 deletions.
- Report updates remain report-only commits. The latest containing commit can be
  resolved with `git log -1 --format=%H -- .superpowers/sdd/2026-09-09-openai-litewing-assistant/task-8-report.md`.

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
- Numeric policy inputs are now normalized and validated under the host-side
  `SafetyPolicy` contract. This slice does not add model policy editing,
  generalized configuration parsing, concurrent lifecycle synchronization, or
  an execution sink.
- Analyzer behavior changes must continue to bump the analyzer version. The
  identity covers the declared version and all policy fields, not a hash of the
  Python source implementation.
- The policy hash is deterministic identity, not authentication. Existing token
  hashing is unchanged; raw human tokens are not retained or returned.
- The review was local and performed by the implementing writer. No independent
  reviewer/subagent or remote integration gate was used or claimed.

## Task 8 review round 1

Round 1 reported one Important policy-input defect and one Minor cache defect.
Both were reproduced against clean review base
`207a7dc4ceef66bccb2792f35e95e31bb40dfd27`, fixed through strict behavioral
TDD, and committed in
`48b4329837b217943851fc7f4dc93f0a718b5161`. This report update is committed
separately; its containing commit is intentionally resolved from Git rather
than embedded in its own bytes.

All commands in this section ran from the worktree root. Every Python test and
behavioral check used macOS `sandbox-exec` profile
`(version 1)(allow default)(deny network*)`, explicitly unset
`OPENAI_API_KEY`, and used CPython 3.14.7. No dependency, provider, network,
hardware, firmware, transport, push, PR, merge, or subagent operation occurred.

### Review-round baseline

Exact command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_*.py'
```

Result: exit 0, `Ran 128 tests in 0.047s`, `OK (skipped=9)`: 119 passed,
9 optional SDK tests skipped, and no failures or errors.

### Review cycle 1: reject invalid numeric safety policies

The RED tests covered every numeric `SafetyPolicy` field:
`max_link_age_ms`, `max_future_skew_ms`, `min_battery_voltage_v`, and
`warn_battery_percent`. For each field they exercised NaN, positive infinity,
and negative infinity at construction and, using a deliberately malformed
immutable-object fixture, at policy identity, preflight, and proposal creation.
Additional cases covered booleans, null/non-numeric values, negative timing
budgets, non-positive minimum voltage, warning percentages outside 0..100,
integer/float identity equivalence, standards-valid canonical JSON, and the
reviewer's exact NaN policy/3.0 V approval path.

Exact RED command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_safety.SafetyTests.test_nonfinite_policy_values_are_rejected_at_construction ai_assistant.tests.test_safety.SafetyTests.test_nonfinite_policy_values_cannot_be_hashed_analyzed_or_proposed ai_assistant.tests.test_safety.SafetyTests.test_policy_numeric_types_and_ranges_are_validated ai_assistant.tests.test_safety.SafetyTests.test_equivalent_integer_and_float_policy_values_share_identity ai_assistant.tests.test_safety.SafetyTests.test_canonical_json_rejects_nonstandard_numeric_constants ai_assistant.tests.test_tools.ToolTests.test_nan_battery_policy_cannot_approve_three_volt_snapshot
```

Result: exit 1, `Ran 6 tests in 0.008s`, `FAILED (failures=75)`. The failures
were all expected behavior gaps:

- 12 non-finite construction cases were accepted.
- 36 non-finite identity/preflight/proposal boundary cases proceeded.
- 16 boolean/null/string field cases and 6 invalid-range cases were accepted.
- Numerically equivalent integer and float policies produced different hashes.
- Three canonical JSON cases emitted NaN or infinity instead of rejecting it.
- The reproduced NaN minimum policy approved the 3.0 V snapshot.

No RED was an import, syntax, fixture, or environment error.

Minimal GREEN implementation:

- `SafetyPolicy.__post_init__()` accepts only non-boolean integers/floats,
  normalizes them to floats, requires finite values, and enforces non-negative
  timing budgets, positive minimum battery voltage, and warning percentage in
  0..100 inclusive.
- `SafetyPolicy.validate()` is re-run before policy hashing, preflight, state
  machine construction, and public replacement, so a malformed/tampered policy
  cannot become an identity, analyzer policy, or proposal policy.
- `canonical_json()` now uses `allow_nan=False`. Constructor/use validation is
  the analyzer boundary; strict serialization is an additional wire-format
  guarantee, not the sole fix.

Exact GREEN command was the same six-test command. Result: exit 0,
`Ran 6 tests in 0.001s`, `OK`.

### Review cycle 2: invalidate cached preflight on either public replacement path

The existing direct-state-machine policy test was strengthened to create a
real cached PASS, assign 4.10 V through `runtime.approvals.policy`, require the
cache to become `None`, then require a fresh preflight to return BLOCKED for
the same 3.90 V snapshot.

Exact RED command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_tools.ToolTests.test_runtime_and_state_machine_share_policy_updates
```

Result: exit 1, `Ran 1 test in 0.001s`, `FAILED (failures=1)`. The assertion
showed the previous `PreflightReport(overall='PASS', ...)` remained cached
after direct public state-machine replacement.

Minimal GREEN implementation: `ApprovalStateMachine` accepts an optional
policy-change notification. `AssistantRuntime` registers a narrow callback
that sets `last_report` to `None`; both `runtime.policy = ...` and
`runtime.approvals.policy = ...` pass through the same setter and callback.
Standalone state machines remain compatible because the callback defaults to
`None`.

Exact GREEN command was the same one-test command. Result: exit 0,
`Ran 1 test in 0.001s`, `OK`.

### Review cycle 3: reject malformed public replacement before mutation

The state-machine setter's input validation received its own strict cycle. The
test begins with a real cached report, attempts direct replacement with a
deliberately malformed NaN policy, and requires rejection before either the
valid policy or its corresponding cached report changes.

Exact RED command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_tools.ToolTests.test_direct_policy_replacement_rejects_malformed_policy_before_installing_it
```

Result: exit 1, `Ran 1 test in 0.001s`, `FAILED (failures=1)` because no
`ValueError` was raised. Adding validation before setter mutation was the
minimal fix. The identical GREEN command returned exit 0,
`Ran 1 test in 0.001s`, `OK`.

### Focused and full verification

Exact focused command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_safety ai_assistant.tests.test_approval ai_assistant.tests.test_tools
```

Result: exit 0, `Ran 53 tests in 0.009s`, `OK`, with no skips.

Exact final full-suite command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_*.py'
```

Result: exit 0, `Ran 135 tests in 0.048s`, `OK (skipped=9)`: 126 passed,
9 unchanged optional SDK tests skipped, zero failures/errors. Expected generic
CLI failure-path messages and stale replay preflight findings appeared on the
test streams and were not failures. Seven test methods were added; one existing
runtime test was strengthened.

### Static scope, leak, and canonical-format verification

`git diff --check` and the following allowlist diff against the review base
both returned exit 0 with no output:

```sh
git diff --exit-code 207a7dc4ceef66bccb2792f35e95e31bb40dfd27 -- . ':(exclude)ai_assistant/src/lrrk_litewing_ai/approval.py' ':(exclude)ai_assistant/src/lrrk_litewing_ai/jsonl.py' ':(exclude)ai_assistant/src/lrrk_litewing_ai/safety.py' ':(exclude)ai_assistant/src/lrrk_litewing_ai/tools.py' ':(exclude)ai_assistant/tests/test_safety.py' ':(exclude)ai_assistant/tests/test_tools.py' ':(exclude)ai_assistant/README.md' ':(exclude)docs/AI_ASSISTANT.md'
```

The changed production-file scope scan returned the expected ripgrep no-match
status (exit 1, no output):

```sh
rg -n 'socket|requests|urllib|httpx|subprocess|os\.system|\bexec\(|\beval\(|\bserial\b|OPENAI_API_KEY|\b(arm|disarm|takeoff|land|write_actuator|set_gain|set_failsafe)\(' ai_assistant/src/lrrk_litewing_ai/approval.py ai_assistant/src/lrrk_litewing_ai/jsonl.py ai_assistant/src/lrrk_litewing_ai/safety.py ai_assistant/src/lrrk_litewing_ai/tools.py
```

The changed-file credential-pattern scan also returned exit 1 with no output:

```sh
rg -n 'sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----|Bearer [A-Za-z0-9._-]{16,}' ai_assistant/src/lrrk_litewing_ai/approval.py ai_assistant/src/lrrk_litewing_ai/jsonl.py ai_assistant/src/lrrk_litewing_ai/safety.py ai_assistant/src/lrrk_litewing_ai/tools.py ai_assistant/tests/test_safety.py ai_assistant/tests/test_tools.py ai_assistant/README.md docs/AI_ASSISTANT.md
```

This deny-network behavioral check returned exit 0 and printed
`strict canonical JSON and normalized policy identity: OK`:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src /opt/homebrew/bin/python3 -c 'import json, os; from lrrk_litewing_ai.jsonl import canonical_json; from lrrk_litewing_ai.safety import SafetyPolicy; assert "OPENAI_API_KEY" not in os.environ; encoded=canonical_json({"policy": {"value": 4.1}}); json.loads(encoded, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))); assert SafetyPolicy(min_battery_voltage_v=4).policy_hash() == SafetyPolicy(min_battery_voltage_v=4.0).policy_hash(); print("strict canonical JSON and normalized policy identity: OK")'
```

Manual review confirmed that the change adds no flight execution authority and
does not alter firmware, UAVTalk, provider execution, API-key handling, motor
or actuator writes, arm/disarm commands, gains, failsafes, or allowed assistant
actions. The shared canonical serializer now rejects non-finite audit payloads
instead of emitting non-standard JSON; the full audit/assistant suite passed.

### AssistantRuntime compatibility self-check

Repository search found no consumer of `AssistantRuntime` generated dataclass
repr, value equality, `asdict`, `is_dataclass`, or `__dataclass_fields__`.
Runtime construction sites use named/default arguments and operational fields.
The live introspection check reported this compatible constructor shape:

```text
(policy: 'SafetyPolicy' = SafetyPolicy(...), operator_session: 'str' =
'offline-session', latest: 'Optional[TelemetrySnapshot]' = None, previous:
'Optional[TelemetrySnapshot]' = None, last_report: 'Optional[PreflightReport]'
= None)
```

It also confirmed `is_dataclass(AssistantRuntime) == False` and distinct runtime
instances compare unequal. Those repr/equality/introspection differences were
introduced by the original Task 8 explicit runtime class, are already recorded
above, and have no concrete repository consumer. Round 1 therefore made no
compatibility refactor beyond the requested policy-change notification.

### Review-round changed files and hashes

These SHA-256 values were recorded from clean implementation commit
`48b4329837b217943851fc7f4dc93f0a718b5161`:

| File | SHA-256 |
| --- | --- |
| `ai_assistant/README.md` | `1b36eb8a2cca182af3cca2f09aef7fb5b4399c31a6958de9cd5a945b0228fbdd` |
| `ai_assistant/src/lrrk_litewing_ai/approval.py` | `6cb9a49d6c25dfea992fdbbf9e26d9137bca5283cca90a25ad378432f286c784` |
| `ai_assistant/src/lrrk_litewing_ai/jsonl.py` | `2aa1b2ce19e1abe333166da502c622c929e32e9f67d7726348a70d450d0c6846` |
| `ai_assistant/src/lrrk_litewing_ai/safety.py` | `8cf2cd64e0d87a2bc028e959fe2d3fe30842bba81aa97d99cb4b2aa5e5fd5af3` |
| `ai_assistant/src/lrrk_litewing_ai/tools.py` | `00038fef0527012c23490875bc74a531a3527a49c79c95343d1b5e1505f679bc` |
| `ai_assistant/tests/test_safety.py` | `b93fb9893d1522871c23675e07aed9fc4f8f246a761465766f9fbe03b41e386e` |
| `ai_assistant/tests/test_tools.py` | `8c21ed6c78e011e982da6989e61aefcce124f76bd3673e9088899f5185c03bab` |
| `docs/AI_ASSISTANT.md` | `92a13381e45f4b1c56a87f4be8549dc240fecbcf90657d29eed92d8fb62a45b3` |

### Remaining concerns after round 1

- Nine optional SDK tests remain skipped exactly as at the review baseline; no
  live provider or hardware proof is claimed.
- The valid numeric ranges are explicit: timing budgets may be zero, minimum
  battery voltage must be greater than zero, and warning percentage is 0..100
  inclusive. No upper cap was invented for finite timing or voltage thresholds.
- `canonical_json(allow_nan=False)` affects every canonical audit/proposal path:
  a non-finite payload now fails closed. Existing normalized models already
  reject non-finite values, and all audit regressions passed.
- The state-machine notification retains `runtime.approvals` as a documented
  compatible public access path. Its optional callback is host lifecycle state,
  not proposal identity, model authority, or execution authority.
- Review round 1 was fixed and verified by the sole implementing writer. A later
  independent re-review remains a separate gate.

## Task 8 review round 2

Review round 2 started from clean branch `codex/provider-audit-chain` at
`f533a2493bacb0571020c2a56a2f64f0021de034`. The production, behavioral-test,
and public-documentation changes are committed as
`a1c2bc22d56c9ebb8a74e5728ba84b7edf6e2e69` (`fix: canonicalize assistant
safety policy values`), tree
`58e5c37c82d8b2f275a0e48677d20eaa29df2aa8`. This report update is committed
separately; its containing commit is intentionally resolved from Git rather
than embedded in its own bytes.

All Python tests and behavioral checks in this section ran from the worktree
root under macOS `sandbox-exec` policy
`(version 1)(allow default)(deny network*)`. Every command explicitly unset
`OPENAI_API_KEY`. No provider, network, dependency, hardware, firmware,
transport, push, PR, merge, or subagent operation occurred.

### Review cycle 4: reject and canonicalize accepted IMU identities

The behavioral regressions cover rejected bare strings, bytes, null, numeric,
set, frozenset, and mapping containers; rejected empty, whitespace-only,
null, numeric, boolean, and byte entries; immutable normalization of valid
list/tuple inputs; deterministic duplicate and order handling; exact rather
than substring identity matching; validation before policy hashing and
preflight; and an approval-level reproduction using accepted policy
`"MPU6050"` with reported identity `"MPU"`.

Exact RED command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant/tests/test_safety.py ai_assistant/tests/test_approval.py
```

Result: exit 1, `Ran 40 tests in 0.007s`, `FAILED (failures=18)`. All failures
were the intended behavior gaps: fourteen malformed container/entry cases were
accepted, canonical tuple normalization was absent, two deliberately tampered
policy use-boundary checks proceeded, and the approval regression reached
`APPROVED` (`'APPROVED' == 'APPROVED'`). No failure was an import, fixture,
syntax, sandbox, or environment error.

Minimal GREEN implementation:

- `SafetyPolicy.__post_init__()` accepts only list/tuple containers whose
  entries are non-empty strings and replaces valid inputs with an immutable,
  duplicate-free tuple.
- A deterministic canonical ordering retains the existing default identity
  order first, then orders custom identities lexically. Equivalent list/tuple,
  duplicate, and ordering variants therefore share one policy hash while the
  default policy's canonical bytes remain unchanged.
- `SafetyPolicy.validate()` repeats the accepted-identity checks at policy
  identity, analyzer, state-machine construction, and replacement boundaries.
  Deliberately bypassing the frozen constructor cannot revive bare-string
  substring membership.
- Analyzer membership remains exact tuple membership: `MPU` cannot satisfy
  an accepted `MPU6050` identity.

The exact GREEN command was the same 40-test command. Result: exit 0,
`Ran 40 tests in 0.006s`, `OK`.

### Review cycle 5: canonicalize semantically equivalent signed zero

The direct policy-hash regression covers every field whose valid range permits
zero: `max_link_age_ms`, `max_future_skew_ms`, and
`warn_battery_percent`. The lifecycle regression covers both pending and
approved records for each field, replaces `0.0` with `-0.0`, and requires the
pending proposal to remain approvable and the existing approval to remain
current.

Exact RED command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_safety.SafetyTests.test_signed_zero_policy_values_share_canonical_identity ai_assistant.tests.test_approval.ApprovalTests.test_signed_zero_policy_replacement_preserves_active_records
```

Result: exit 1, `Ran 2 tests in 0.002s`, `FAILED (failures=9)`. The three
positive-zero/negative-zero policy hashes differed, and all six pending or
approved lifecycle cases moved to `ABORTED`. No failure was environmental.

The minimal production change maps every already type-checked, finite numeric
zero to positive `0.0` inside the existing `SafetyPolicy` normalization. Range
validation remains unchanged, so both signs of zero remain invalid for the
strictly positive minimum-battery field.

The exact GREEN command was the same two-test command. Result: exit 0,
`Ran 2 tests in 0.001s`, `OK`.

### Focused and full final verification

Exact focused command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant.tests.test_safety ai_assistant.tests.test_approval ai_assistant.tests.test_tools
```

Result: exit 0, `Ran 59 tests in 0.010s`, `OK`, no skips.

Exact full-suite command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_*.py'
```

Result: exit 0, `Ran 141 tests in 0.051s`, `OK (skipped=9)`: 132 passed,
9 unchanged optional-SDK tests skipped, with zero failures or errors. Expected
generic CLI failure-path messages and stale replay preflight findings appeared
on the streams and were not failures. Six test methods were added in round 2.

### Static scope, leak, and canonical-format verification

`git diff --check` returned exit 0 with no output. The review-base allowlist
also returned exit 0 with no output:

```sh
git diff --exit-code f533a2493bacb0571020c2a56a2f64f0021de034 -- . ':(exclude)ai_assistant/src/lrrk_litewing_ai/safety.py' ':(exclude)ai_assistant/tests/test_safety.py' ':(exclude)ai_assistant/tests/test_approval.py' ':(exclude)ai_assistant/README.md' ':(exclude)docs/AI_ASSISTANT.md'
```

The production authority scan returned expected ripgrep no-match status,
exit 1 with no output:

```sh
rg -n 'socket|requests|urllib|httpx|subprocess|os\.system|\bexec\(|\beval\(|\bserial\b|OPENAI_API_KEY|\b(arm|disarm|takeoff|land|write_actuator|set_gain|set_failsafe)\(' ai_assistant/src/lrrk_litewing_ai/safety.py
```

The changed-file credential-pattern scan also returned expected no-match
status, exit 1 with no output:

```sh
rg -n 'sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----|Bearer [A-Za-z0-9._-]{16,}' ai_assistant/src/lrrk_litewing_ai/safety.py ai_assistant/tests/test_safety.py ai_assistant/tests/test_approval.py ai_assistant/README.md docs/AI_ASSISTANT.md
```

This exact deny-network behavioral check returned exit 0 and
`canonical policy identity OK 7d379a97585a3b1dab4c4c74b304916efe23d07522b33cebba650330726358bc`:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp /opt/homebrew/bin/python3 -c 'import hashlib,json,os; from dataclasses import asdict; from lrrk_litewing_ai.jsonl import canonical_json; from lrrk_litewing_ai.safety import SafetyPolicy; reject=lambda value: (_ for _ in ()).throw(ValueError(value)); default=SafetyPolicy(); expected={"analyzer_version":"litewing-safety-3","policy":{"max_link_age_ms":500.0,"max_future_skew_ms":5000.0,"min_battery_voltage_v":3.3,"warn_battery_percent":20.0,"accepted_imu_identities":["MPU6050","0x68","0x69","104","105"]}}; assert "OPENAI_API_KEY" not in os.environ; assert default.policy_hash()==hashlib.sha256(canonical_json(expected).encode()).hexdigest(); assert SafetyPolicy(max_link_age_ms=0.0).policy_hash()==SafetyPolicy(max_link_age_ms=-0.0).policy_hash(); assert SafetyPolicy(accepted_imu_identities=["0x68","MPU6050","0x68"]).policy_hash()==SafetyPolicy(accepted_imu_identities=("MPU6050","0x68")).policy_hash(); encoded=canonical_json({"policy":asdict(SafetyPolicy(warn_battery_percent=-0.0))}); json.loads(encoded,parse_constant=reject); assert "-0.0" not in encoded; print("canonical policy identity OK", default.policy_hash())'
```

The check independently parsed canonical policy JSON with non-standard
constants rejected, verified normalized signed-zero and accepted-identity
equivalence, and confirmed that the pre-round default policy hash is unchanged.

### Round-2 changed files and hashes

These SHA-256 values were recorded from clean implementation commit
`a1c2bc22d56c9ebb8a74e5728ba84b7edf6e2e69`:

| File | SHA-256 |
| --- | --- |
| `ai_assistant/README.md` | `ce9ba7ea333f8c38be06b5b7b000759435f99545f9b8daf658284e2b3bdff003` |
| `ai_assistant/src/lrrk_litewing_ai/safety.py` | `07786883694ee14b15bef4aecc6fcc5794e63cdd967dd536f82774b1b8cfc35c` |
| `ai_assistant/tests/test_approval.py` | `4dc3e2300d6ec52ca841ec0c3da046b825f73b1caf1b37d96db575be4feabd19` |
| `ai_assistant/tests/test_safety.py` | `3cf20dcc80a9448d2365f39901cfd4c41db5386f1ffbbfef1fdde760148ac519` |
| `docs/AI_ASSISTANT.md` | `f8e398c4b16195953ee9f5091e534255e3b7d60479da169c934015a49c69e17a` |

### Scope and compatibility review

- The only production file changed in round 2 is host-side
  `safety.py`. The patch adds validation and canonical value normalization; it
  adds no I/O, provider call, secret access, transport, hardware, flight
  command, actuator write, or execution sink.
- The default thresholds, default accepted identities, default canonical bytes,
  default policy hash, analyzer version `litewing-safety-3`, finding behavior,
  action allowlist, and advisory-only authority remain unchanged.
- Valid accepted-identity list/tuple inputs now expose an immutable tuple;
  duplicates collapse and semantically irrelevant input order is canonical.
  Existing noncanonical custom policy hashes intentionally converge on the
  semantic identity. The default tuple order is preserved for compatibility.
- Identity strings are not coerced, trimmed, case-folded, or substring-matched.
  Whitespace-only entries are rejected; otherwise matching remains exact.
  Empty list/tuple policies remain valid deny-all configurations and cannot
  make an IMU pass.
- Signed zero is normalized only after numeric type and finiteness checks.
  This preserves valid range behavior and prevents equivalent replacement from
  aborting pending or approved records.
- `AssistantRuntime` repr, equality, constructor, and introspection behavior
  were not changed in round 2. No concrete repository consumer required any
  expansion of the round-1 compatibility assessment.
- Nine optional SDK tests remain skipped because the optional package is not
  installed. No live provider or hardware evidence is claimed. Review round 2
  was implemented and verified by the sole writer; independent re-review
  remains a separate gate.
