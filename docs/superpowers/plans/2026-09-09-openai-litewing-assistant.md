# OpenAI LiteWing Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a host-only, offline-capable OpenAI assistant that reads normalized LiteWing telemetry, runs deterministic safety checks, explains findings, and creates human-reviewed proposals without any authority over motors or flight-critical state.

**Architecture:** A Python package owns versioned telemetry models, deterministic safety analysis, structured JSONL audit records, and a proposal approval state machine. Protocol adapters feed snapshots into that core. An optional OpenAI Agents SDK adapter exposes read-only tools and proposal creation only. The default CLI remains useful without a network connection, SDK, or API key.

**Tech Stack:** Python 3.11+, standard library, pytest, optional `cflib`/UAVTalk adapter extras, optional `openai-agents` live-AI extra, JSONL, environment-based secret lookup.

**Spec:** `docs/superpowers/specs/2026-09-09-openai-litewing-assistant-design.md`

## Global Constraints

- No assistant component may write a motor value, arm/disarm command, gain, failsafe setting, or direct flight-control command.
- No API key is created, printed, committed, or written to a file by this implementation.
- Missing or unknown telemetry stays unknown; it is never coerced into a safe value.
- Offline/dry-run behavior must be fully testable with no network and no credentials.
- Proposals are advisory records; approval is explicit, short-lived, bound to a snapshot/proposal hash, and invalidated by state drift.
- Redact secrets and credentials from all logs and exception text.

---

### Task 1: Establish the package and normalized telemetry contract

**Files:**
- Create: `ai_assistant/pyproject.toml`
- Create: `ai_assistant/src/lrrk_litewing_ai/__init__.py`
- Create: `ai_assistant/src/lrrk_litewing_ai/models.py`
- Create: `ai_assistant/tests/test_models.py`
- Create: `ai_assistant/README.md`
- Modify: `.gitignore`

- [x] Define versioned immutable models for `TelemetrySnapshot`, attitude, battery, sensor health, alarms, actuator state, and source identity.
- [x] Represent unknown values explicitly with optional fields and validation rather than sentinel numbers.
- [x] Require timezone-aware timestamps, non-negative link age, finite actuator observations, and a declared source adapter.
- [x] Reject malformed input where it could hide a schema mistake, while allowing forward-compatible unknown telemetry fields at the adapter boundary.
- [x] Add JSON serialization/deserialization with stable key ordering and no secret fields.
- [x] Add tests for valid snapshots, malformed timestamps, invalid actuator ranges, absent optional capabilities, and round trips.
- [x] Add `.env`, `.env.*`, and key-like file patterns to `.gitignore` while preserving `.env.example` if later added.
- [ ] Commit as `feat: add normalized LiteWing telemetry contract`.

### Task 2: Implement deterministic safety analysis

**Files:**
- Create: `ai_assistant/src/lrrk_litewing_ai/safety.py`
- Create: `ai_assistant/tests/test_safety.py`
- Modify: `ai_assistant/README.md`

- [x] Define structured findings with stable IDs, severity, evidence, remediation, and analyzer version.
- [x] Check link freshness, armed state, IMU identity/health, battery state, alarms, actuator bounds, and optional positioning capability presence.
- [x] Distinguish `PASS`, `WARN`, `BLOCK`, and `UNKNOWN`; do not pass an unknown value merely because no fault was observed.
- [x] Make the preflight result deterministic for the same snapshot and policy.
- [x] Add hostile-input tests for stale/future timestamps, negative battery values, NaN/infinite numbers, missing IMU identity, false-safe alarm values, and actuator overflow.
- [ ] Commit as `feat: add fail-closed LiteWing safety analyzer`.

### Task 3: Add structured audit and JSONL replay

**Files:**
- Create: `ai_assistant/src/lrrk_litewing_ai/audit.py`
- Create: `ai_assistant/src/lrrk_litewing_ai/jsonl.py`
- Create: `ai_assistant/tests/test_audit.py`
- Create: `ai_assistant/tests/fixtures/telemetry.jsonl`

- [x] Write append-only JSONL events for snapshot receipt and preflight results, with the same event API available for proposal/approval transitions.
- [x] Include event ID, UTC timestamp, session ID, source identity, prior event hash, and canonical event hash.
- [x] Redact values matching API-key/token/credential patterns and never include full environment dumps.
- [x] Implement replay validation that detects malformed lines, broken hash chains, duplicate event IDs, and tampering.
- [x] Add tests proving deterministic hashes, redaction, replay rejection, and safe recovery after a truncated final line.
- [ ] Commit as `feat: add LiteWing assistant audit log`.

### Task 4: Implement proposal and approval state machine

**Files:**
- Create: `ai_assistant/src/lrrk_litewing_ai/approval.py`
- Create: `ai_assistant/tests/test_approval.py`
- Modify: `ai_assistant/src/lrrk_litewing_ai/audit.py`

- [x] Implement `IDLE`, `PROPOSAL_READY`, `APPROVED`, `EXPIRED`, `REJECTED`, and `ABORTED` transitions with explicit transition validation.
- [x] Bind approval to proposal hash, snapshot timestamp/hash, operator session, policy version, and a short expiry.
- [x] Invalidate approval on state drift, snapshot mismatch, timeout, or reuse; the no-write first release keeps link/disarm enforcement in the deterministic preflight boundary.
- [x] Require a caller-provided human approval token; no model output can satisfy this requirement implicitly.
- [x] Add tests for legal transitions and rejection of replay, cross-proposal approval, stale approval, and incomplete flight state.
- [ ] Commit as `feat: add bounded assistant approval state machine`.

### Task 5: Add read-only assistant tools and optional OpenAI adapter

**Files:**
- Create: `ai_assistant/src/lrrk_litewing_ai/tools.py`
- Create: `ai_assistant/src/lrrk_litewing_ai/agent.py`
- Create: `ai_assistant/src/lrrk_litewing_ai/providers.py`
- Create: `ai_assistant/tests/test_tools.py`
- Create: `ai_assistant/tests/test_agent_offline.py`
- Modify: `ai_assistant/pyproject.toml`

- [x] Expose only `get_latest_telemetry`, `run_preflight`, `explain_finding`, `compare_snapshots`, and `propose_action`.
- [x] Validate every tool input and return schema; keep `propose_action` side-effect-free and return a proposal record only.
- [x] Add an offline provider that never imports or contacts OpenAI and is the default when optional dependencies or credentials are absent.
- [x] Add an optional Agents SDK provider using a narrow system policy and read `OPENAI_API_KEY` only from the process environment at call time.
- [x] Refuse live mode when the key is absent or malformed; include no credential content in errors.
- [x] Add tests that inspect tool schemas and prove no motor/actuator-write command exists.
- [ ] Commit as `feat: add optional read-only OpenAI assistant adapter`.

### Task 6: Add the dry-run CLI and protocol boundary

**Files:**
- Create: `ai_assistant/src/lrrk_litewing_ai/cli.py`
- Create: `ai_assistant/src/lrrk_litewing_ai/adapters.py`
- Create: `ai_assistant/tests/test_cli.py`
- Create: `docs/AI_ASSISTANT.md`

- [x] Accept JSONL telemetry from a fixture path and emit a human-readable report plus machine-readable findings.
- [x] Keep offline behavior as the default and require an explicit `--live-agent` switch for the optional provider.
- [x] Add a protocol adapter interface for UAVTalk, with a file/JSONL adapter as the first implemented adapter; leave transport writes unimplemented.
- [x] Make adapter disconnects and malformed frames fail closed rather than look like success.
- [x] Document host dependencies, optional extras, key handling, the no-flight-control boundary, and sample offline commands.
- [x] Add CLI tests for valid input, malformed input, empty input, stale input, and missing-key live-mode refusal.
- [ ] Commit as `feat: add offline LiteWing assistant CLI`.

### Task 7: Review and integration gate

- [ ] Run the assistant test suite with no API key and network disabled.
- [ ] Run a static review for actuator-write strings, secret leaks, unsafe subprocesses, and overly broad tools.
- [ ] Run package metadata/build checks and confirm optional live dependencies are not required for offline use.
- [ ] Open a focused pull request with the safety model and test evidence; explicitly state that live OpenAI calls were not exercised without an approved secret destination.
- [ ] Merge only after the required checks are green and the PR contains no claim that the assistant controls flight.
