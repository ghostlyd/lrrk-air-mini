# Disarmed receiver-loss probe implementation plan

> **For agentic workers:** Use inline test-first execution for this tightly
> coupled control boundary and request independent review before physical use.

**Goal:** Exercise real receiver input-loss and recovery while keeping arming disabled.
**Architecture:** Pure evidence/state controller plus a restricted serial CLI.
**Tech stack:** Python3, pyserial, pinned upstream UAVObject codec, strict local decoder.
**Spec:** ../specs/2026-09-09-receiver-loss-probe.md

## Global constraints

The spec is binding. No firmware changes, settings writes, arming or motor
commands; preserve the existing dirty checkout. No serial access during tests.
No physical use until review approves the actual code and host tests pass.

## Task 1: One reviewed diagnostic boundary

Files: diagnostics/receiver_contract.py, diagnostics/receiver_probe.py under
ports/ninjapilot-litewing; tests/test_receiver_probe.py; diagnostics/README.md.

- [ ] Write behavioral tests before implementation: instantiate Evidence,
  observe safe objects at monotonic times, start a phase, and assert that
  `check(now)` rejects missing/stale/armed/nonzero data before any input.
  Example: `with self.assertRaises(ProbeFailure): Evidence().check(1.0)`.
- [ ] Implement `Evidence.observe(name, data, now)`, `check(now)`, and phase
  transitions. Explicit literals in fixtures define safe settings and neutral
  channels; no expected values derived from the implementation under test.
- [ ] Test then implement the send allowlist and receive parser boundary using
  actual pinned XML/codec objects. Assert altered throttle/axis, settings,
  metadata, bad CRC and nonzero instance frames never reach serial.write.
- [ ] Test then implement CLI transport and scheduling with an injected clock
  and serial transport. Assert no first input until preflight, no catch-up
  burst, abort on stale state/write failure and owned-handle closure.
- [ ] Run `python -m unittest discover -s ports/ninjapilot-litewing/tests -p
  'test_receiver_probe.py' -v` with LRRK_TEST_FLIGHT_ROOT set to the pinned tree.
- [ ] Run host suite and source CI; independently review the actual diff.
- [ ] Only after review, run one gated physical test with private captures,
  inspect all phase evidence, and record actual result without overstating it.
- [ ] Commit, PR and merge verified source/evidence under standing authority.

An incomplete phase or unavailable physical test keeps issue23 open. The
overall port/AI/BOM goal remains separate from this one bench acceptance task.
