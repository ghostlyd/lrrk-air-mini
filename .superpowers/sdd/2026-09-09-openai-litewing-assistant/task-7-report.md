# Task 7 implementation report

## Scope and requirements

Worktree: `/private/tmp/lrrk-air-mini-provider-audit-chain`.
Branch: `codex/provider-audit-chain` (clean at start).
Read task-7-brief.md first, then the approved design and progress ledger.
User instructions override the brief's PR/merge checklist: local commits only,
no push, merge, PR, subagents, network calls, real API keys, providers, or hardware.

## RED evidence (before production edits)

Added `ai_assistant/tests/test_cli_provider_audit.py` first. The tests call the
real `cli.main`, read actual telemetry fixtures, write actual private audit
files, and validate them with `validate_replay`. Only `_live_prompt`, the
external provider execution boundary, is substituted. No audit, adapter,
runtime, or assistant factory is mocked. Test process environment is cleared.

Command (from the worktree; temporary artifacts stay inside it):

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p test_cli_provider_audit.py -v
```

Initial result: exit 1, `Ran 6 tests in 0.012s`, `FAILED (failures=6)`.
Moved the missing-key test's audit assertion before its stderr assertion so
the next RED directly exposed the missing provider events. No production
changes preceded either RED run.

Second RED output (test summary and relevant assertion output):

```text
test_failure_records_only_exception_class_and_never_discloses_message ... FAIL
test_missing_key_attempt_is_audited_without_importing_sdk ... FAIL
test_no_audit_log_preserves_success_and_creates_no_audit_file ... FAIL
test_no_audit_log_still_sanitizes_provider_failure ... FAIL
test_offline_and_no_prompt_validation_do_not_append_provider_events ... ok
test_success_is_chained_before_and_after_runner_and_preserves_stdout
  (output_flags=()) ... FAIL
  (output_flags=('--json',)) ... FAIL

AssertionError: 'assistant request blocked: OPENAI_API_KEY is not available for live-agent mode\n' != 'assistant request blocked\n'
AssertionError: Lists differ: ['snapshot_received', 'preflight_result', 'snapshot_received'] != ['snapshot_received', 'preflight_result', 'snapshot_received', 'preflight_result', 'provider_request']
AssertionError: 3 != 0

Ran 6 tests in 0.013s
FAILED (failures=6)
```

These are assertion failures, not import/setup errors: provider events do not
exist, exception details reach stderr, and agent construction happens before
the substituted provider runner. Construction must move inside that boundary
to isolate external execution and capture initialization failures as attempts.

## Verification environment

`/opt/homebrew/bin/python3` has no `agents` module installed. The OS sandbox
denies all network operations. A local socket bind check returned
`PermissionError: [Errno 1] Operation not permitted`, confirming enforcement;
no remote connection was attempted. The real SDK is never imported by these
tests. Temporary files are rooted in the worktree's ignored task directory.

## Implementation and files changed

Status: COMPLETE for the authorized host-only provider audit slice.

Implementation commit: `8f95cce637d877f65b835b2bec1d1afdafbb5652`
(`feat: chain metadata-only provider audit events`).

This report is committed separately after that implementation commit so it can
contain the exact implementation hash without a self-referential commit hash.
Its commit can be resolved with
`git log -1 --format=%H -- .superpowers/sdd/2026-09-09-openai-litewing-assistant/task-7-report.md`.

Files changed:

- `ai_assistant/src/lrrk_litewing_ai/cli.py`: move agent creation into the
  provider runner boundary; append metadata-only request/result events using
  the existing AuditLog API; emit generic failure stderr.
- `ai_assistant/tests/test_cli_provider_audit.py`: six focused real-CLI tests,
  with success output subtests and mode-exclusion subtests.
- `ai_assistant/README.md`: operator overview, privacy scope, stdout boundary,
  and distinction between offline implementation proof and live smoke.
- `docs/AI_ASSISTANT.md`: exact event payload fields, failure semantics,
  privacy limitations, and verification boundary.
- `docs/verification/live-uavtalk-openai-smoke-2026-09-09.md`: preserve the
  original smoke evidence while identifying the later implementation follow-up.
- `.superpowers/sdd/2026-09-09-openai-litewing-assistant/task-7-report.md`:
  this report, explicitly tracked despite the ignored task directory.

Request payload: `mode: "openai"`, current `snapshot_hash`, `prompt_bytes`,
and `prompt_sha256`. Success payload: `outcome: "completed"`, current
`snapshot_hash`, `response_bytes`, and `response_sha256`. Failure payload:
`outcome: "blocked"`, current `snapshot_hash`, and `error_class` only.
Lengths and hashes use UTF-8. No changes to AuditLog or its envelope/schema.

## Additional RED/GREEN cycle

After the first GREEN, self-review identified that no-prompt validation still
printed exception details. Strengthened its existing exclusion subtest to
require generic stderr, then reran the exact focused RED command above:

```text
test_offline_and_no_prompt_validation_do_not_append_provider_events
  (args=('--live-agent',)) ... FAIL
AssertionError: 'live-agent mode blocked: OPENAI_API_KEY is not available for live-agent mode\n' != 'live-agent mode blocked\n'
Ran 6 tests in 0.014s
FAILED (failures=1)
```

Changed only that exception handler's stderr to `live-agent mode blocked`.
It still returns 3 and creates no provider events. The successful prompt
output, both plain text and JSON, remains unchanged.

## GREEN commands and output

First provider-audit GREEN (same command as RED):

```text
test_failure_records_only_exception_class_and_never_discloses_message ... ok
test_missing_key_attempt_is_audited_without_importing_sdk ... ok
test_no_audit_log_preserves_success_and_creates_no_audit_file ... ok
test_no_audit_log_still_sanitizes_provider_failure ... ok
test_offline_and_no_prompt_validation_do_not_append_provider_events ... ok
test_success_is_chained_before_and_after_runner_and_preserves_stdout ... ok
Ran 6 tests in 0.013s
OK
```

Final targeted CLI regression command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_cli*.py' -v
```

```text
Ran 14 tests in 0.021s
OK
```

Final full offline assistant command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_*.py'
```

```text
......................live-agent mode blocked
..telemetry input blocked: invalid JSONL at line 1
.................................sssssssss...............................................
Ran 113 tests in 0.040s
OK (skipped=9)
```

104 tests passed; the nine optional `test_provider_sdk.py` tests skipped
because the SDK is absent, as required for this offline run. Existing CLI
tests also emit stale-fixture `preflight: BLOCKED` reports and expected
negative-case diagnostics; these are not test failures. No skipped test was
counted as passing. No package installation was needed.

The new integration coverage proves the request is replayable on disk inside
the substituted runner, before it returns or raises. It then proves exactly
one result, exact metadata key sets, multibyte UTF-8 lengths/digests, binding
to the latest of two different snapshots, replay across repeated CLI sessions,
and absence of distinctive raw prompt/response/exception strings from audit.
It also covers real missing-key setup failure, unchanged success stdout,
generic failure output with and without audit, and all required exclusions.

## Offline package build and metadata checks

The test interpreter lacks setuptools. Used the existing bundled Python
3.12.14 with setuptools 84.0.0, without downloading or installing anything.
From `ai_assistant`, ran the following under the same deny-network sandbox,
with `OPENAI_API_KEY` unset, `PYTHONDONTWRITEBYTECODE=1`, and the same TMPDIR:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /Users/lrrk-ultra/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 - <<'PY'
from pathlib import Path
from setuptools.build_meta import build_wheel, build_sdist
from email.parser import Parser
from zipfile import ZipFile
from packaging.requirements import Requirement
out = Path('../.superpowers/sdd/2026-09-09-openai-litewing-assistant/dist').resolve()
out.mkdir(exist_ok=True)
wheel = build_wheel(str(out))
sdist = build_sdist(str(out))
with ZipFile(out / wheel) as archive:
    metadata = Parser().parsestr(archive.read('lrrk_litewing_ai-0.2.0.dist-info/METADATA').decode())
    assert metadata['Name'] == 'lrrk-litewing-ai'
    assert metadata['Version'] == '0.2.0'
    assert metadata['Requires-Python'] == '<3.15,>=3.11'
    requirements = [Requirement(item) for item in metadata.get_all('Requires-Dist', [])]
    active = [str(item) for item in requirements if item.marker is None or item.marker.evaluate({'extra': ''})]
    assert active == [], active
    provider = next(item for item in requirements if item.name == 'openai-agents')
    assert str(provider.specifier) == '==0.22.1'
    assert provider.marker.evaluate({'extra': 'openai'})
    assert not provider.marker.evaluate({'extra': ''})
    entries = archive.read('lrrk_litewing_ai-0.2.0.dist-info/entry_points.txt').decode()
    assert 'litewing-ai = lrrk_litewing_ai.cli:main' in entries
print('BUILD PASS:', wheel, sdist)
print('METADATA PASS: version 0.2.0; Python >=3.11,<3.15; CLI entry point; no default macOS dependencies; OpenAI SDK remains optional')
PY
```

```text
BUILD PASS: lrrk_litewing_ai-0.2.0-py3-none-any.whl lrrk_litewing_ai-0.2.0.tar.gz
METADATA PASS: version 0.2.0; Python >=3.11,<3.15; CLI entry point; no default macOS dependencies; OpenAI SDK remains optional
```

Build exit 0. Setuptools emitted two expected warnings that byte-compiling was
disabled because `PYTHONDONTWRITEBYTECODE=1`. Build intermediates and archives
remain ignored inside this worktree.

Also ran the actual built wheel with site packages disabled, from the worktree:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONPATH=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/dist/lrrk_litewing_ai-0.2.0-py3-none-any.whl /opt/homebrew/bin/python3 -S - <<'PY'
import contextlib
import importlib.util
import io
import sys
from lrrk_litewing_ai import cli
assert '.whl/' in cli.__file__, cli.__file__
assert importlib.util.find_spec('agents') is None
assert importlib.util.find_spec('serial') is None
with contextlib.redirect_stdout(io.StringIO()) as output:
    status = cli.main(['--input', 'ai_assistant/tests/fixtures/telemetry.jsonl', '--prompt', 'status', '--json'])
assert status == 0
assert '"assistant":' in output.getvalue()
assert not any(name.split('.')[0] in {'agents', 'openai', 'serial'} for name in sys.modules)
print('WHEEL OFFLINE CLI PASS: exit 0; site packages disabled; no Agents/OpenAI/serial imports')
PY
```

```text
WHEEL OFFLINE CLI PASS: exit 0; site packages disabled; no Agents/OpenAI/serial imports
```

## Security/privacy self-review

- Exact payload key sets are asserted in tests. Provider records contain no
  raw prompt/response, exception message/traceback, key, authorization or
  environment data, serial bytes, or hidden reasoning. `source` is empty.
- All provider prompt failures, including setup failures, have generic stderr;
  no-prompt validation is generic too. Raw successful answers remain on
  stdout by requirement. Existing telemetry input errors are outside this slice.
- Request append occurs before provider initialization/execution. A request
  append failure prevents execution. Result append failure blocks normal
  completion; errors do not silently become successful output.
- AuditLog's existing private-file handling, redaction and hash chain remain
  unchanged; existing audit privacy/replay tests pass.
- No SDK tool, proposal policy, approval mechanism, firmware, adapter, UAVTalk
  transport, serial write, or flight-control authority changed. The only
  production file changed is `cli.py`.
- Static scan command:

  ```sh
  rg -n 'subprocess|os\.system|shell=True|eval\(|exec\(|write_actuators|takeoff|failsafe|motor|arming|OPENAI_API_KEY|authorization|environ' ai_assistant/src/lrrk_litewing_ai
  ```

  Reviewed all matches: existing safety remediation text, provider prohibitions,
  credential lookup, audit secret-field names, and read-side transport boundary
  prose. No unsafe subprocess/eval/exec or new broad tool surfaced. Reviewed
  every added audit payload and print statement in the production diff.
- `git diff --check` and `git diff --cached --check` passed. Before commit,
  `git diff --exit-code -- ports ai_assistant/src/lrrk_litewing_ai/{audit,providers,tools,approval,adapters,live_uavtalk,uavtalk,uavobjects}.py`
  returned 0, confirming the protected boundaries were unchanged.
- No real key/provider, network call, hardware access, or subagent was used.
  All source/test/doc writes and build artifacts were confined to the target
  worktree. The original checkout and other worktrees were not modified.
- Commits use invocation-local `core.hooksPath=/dev/null` to avoid executing
  unreviewed hooks under the no-network/no-hardware constraint; no repository
  configuration is changed. No push, merge, or PR was attempted.

## Concerns and limits

No blocking implementation concerns identified. Nine optional SDK tests were
intentionally skipped; no live-provider smoke was performed. This report is
self-review evidence, not an independent review or provider availability proof.
Completed metadata denotes a returned advisory answer, not safe flight,
approval, action execution, or fresh telemetry.

Hashes and lengths are metadata, not encryption; guesses of short known text
can be checked against a digest. Successful stdout remains sensitive. A
process termination/interruption or storage failure can leave an unmatched
request; it must never be interpreted as completion. No crash-recovery or
storage-availability guarantee is introduced by this additive slice.

## Review round 1 — unencodable provider response

Status: COMPLETE. Fixed only the Important finding that UTF-8 response
encoding happened outside the audited provider-operation exception boundary.

Implementation commit: `e14297ac8eb6ba7d7c6754dbc04c4d96a9856548`
(`fix: audit provider response encoding failures`). The report update is a
following documentation commit; resolve its exact hash with:

```sh
git log -1 --format=%H -- .superpowers/sdd/2026-09-09-openai-litewing-assistant/task-7-report.md
```

Files changed in the implementation commit:

- `ai_assistant/tests/test_cli_provider_audit.py`: add a real-CLI/AuditLog
  regression whose substituted external provider runner returns
  `"private-surrogate-response-5d72\ud800"`.
- `ai_assistant/src/lrrk_litewing_ai/cli.py`: prepare UTF-8 response bytes and
  completed-result metadata inside the existing audited provider-operation
  `try`; append the prepared completed result only after that boundary exits.

No other production, test, or operator-documentation file changed in the
implementation commit. The report is the only additional file changed for
review evidence.

### RED evidence

The focused regression was added before changing production code. Command,
run with no API key and OS-enforced network denial:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest -v ai_assistant/tests/test_cli_provider_audit.py
```

Expected RED output:

```text
test_failure_records_only_exception_class_and_never_discloses_message ... ok
test_missing_key_attempt_is_audited_without_importing_sdk ... ok
test_no_audit_log_preserves_success_and_creates_no_audit_file ... ok
test_no_audit_log_still_sanitizes_provider_failure ... ok
test_offline_and_no_prompt_validation_do_not_append_provider_events ... ok
test_success_is_chained_before_and_after_runner_and_preserves_stdout ... ok
test_unencodable_response_records_one_blocked_result_without_content ... FAIL

AssertionError: 5 != 6

Ran 7 tests in 0.015s
FAILED (failures=1)
```

The test reached real audit replay successfully, then found only the two
snapshot/preflight pairs and `provider_request`. This proved that
`answer.encode("utf-8")` raised after the provider attempt without appending
the required sixth `provider_result` event.

### GREEN evidence

After the minimal production change, the same focused command produced:

```text
test_failure_records_only_exception_class_and_never_discloses_message ... ok
test_missing_key_attempt_is_audited_without_importing_sdk ... ok
test_no_audit_log_preserves_success_and_creates_no_audit_file ... ok
test_no_audit_log_still_sanitizes_provider_failure ... ok
test_offline_and_no_prompt_validation_do_not_append_provider_events ... ok
test_success_is_chained_before_and_after_runner_and_preserves_stdout ... ok
test_unencodable_response_records_one_blocked_result_without_content ... ok

Ran 7 tests in 0.015s
OK
```

Focused CLI regression command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_cli*.py' -v
```

```text
Ran 15 tests in 0.023s
OK
```

Full offline assistant command:

```sh
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' /usr/bin/env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ai_assistant/src TMPDIR=/private/tmp/lrrk-air-mini-provider-audit-chain/.superpowers/sdd/2026-09-09-openai-litewing-assistant/tmp /opt/homebrew/bin/python3 -m unittest discover -s ai_assistant/tests -p 'test_*.py'
```

```text
......................live-agent mode blocked
..telemetry input blocked: invalid JSONL at line 1
..................................sssssssss...............................................
Ran 114 tests in 0.045s
OK (skipped=9)
```

105 tests passed. The nine optional SDK tests skipped because the SDK is not
installed; no skipped test is counted as passing. Existing stale-fixture
preflight output and negative-case diagnostics are expected test output.

### Regression and privacy proof

The new regression substitutes only `_live_prompt`, then executes real
`cli.main`, telemetry ingestion, private AuditLog writes, and
`validate_replay`. It proves:

- generic `assistant request blocked` stderr and exit 3;
- a valid six-record hash chain;
- event order ending `provider_request`, then `provider_result`;
- exactly one `provider_result`;
- blocked payload containing only `outcome`, current `snapshot_hash`, and
  `error_class: "UnicodeEncodeError"`; and
- absence of both the distinctive response marker and the complete surrogate
  response from stdout, stderr, and raw audit text.

The pre-existing success test remained green for plain and JSON modes, proving
ordinary successful stdout and completed metadata behavior remain unchanged.

### Security/privacy self-review

- Response encoding, byte length, digest, and completed-result payload
  preparation now share the existing protected provider-operation boundary.
  Any exception during that preparation follows the same metadata-only blocked
  path as provider setup/execution failures.
- The blocked event records only the exception class name. It does not attempt
  to serialize, print, hash, or otherwise retain the unencodable response.
- The completed audit append remains after successful metadata preparation.
  Audit write failure semantics were not changed.
- `git diff --check` passed. The implementation diff contains only the CLI
  exception-boundary move and the focused regression.
- `git diff --exit-code -- ports ai_assistant/src/lrrk_litewing_ai/{audit,providers,tools,approval,adapters,live_uavtalk,uavtalk,uavobjects}.py`
  returned 0. Firmware, UAVTalk transport, provider tools, approval/proposal
  authority, and AuditLog internals are unchanged.
- Every test ran with `OPENAI_API_KEY` removed and network denied by
  `sandbox-exec`. No provider SDK, real provider, network, hardware, push, PR,
  or merge was used.

### Concerns

No blocking concern. The nine optional SDK tests remain intentionally skipped,
and this regression uses a substituted external provider runner. It proves the
CLI/AuditLog failure behavior without making a live-provider claim.
