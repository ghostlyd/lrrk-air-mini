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

- [x] Write behavioral tests before implementation: instantiate Evidence,
  observe safe objects at monotonic times, start a phase, and assert that
  `check(now)` rejects missing/stale/armed/nonzero data before any input.
  Example: `with self.assertRaises(ProbeFailure): Evidence().check(1.0)`.
- [x] Implement `Evidence.observe(name, data, now)`, `check(now)`, and phase
  transitions. Explicit literals in fixtures define safe settings and neutral
  channels; no expected values derived from the implementation under test.
- [x] Test then implement the send allowlist and receive parser boundary using
  actual pinned XML/codec objects. Assert altered throttle/axis, settings,
  metadata, bad CRC and nonzero instance frames never reach serial.write.
- [x] Test then implement CLI transport and scheduling with an injected clock
  and serial transport. Assert no first input until preflight, no catch-up
  burst, abort on stale state/write failure and owned-handle closure.
- [x] Run `python -m unittest discover -s ports/ninjapilot-litewing/tests -p
  'test_receiver_probe.py' -v` with LRRK_TEST_FLIGHT_ROOT set to the pinned tree.
- [x] Run host suite and source CI; independently review the actual diff.
- [x] Only after review, run one gated physical test with private captures,
  inspect all phase evidence, and record actual result without overstating it.
- [x] Commit and open PR under standing authority; integration status is tracked
  by [PR32](https://github.com/ghostlyd/lrrk-air-mini/pull/32), not this checklist.

An incomplete phase or unavailable physical test keeps issue23 open. The
overall port/AI/BOM goal remains separate from this one bench acceptance task.

Initial independent review required six corrections: I/O ageing/deadlines,
verified-byte execution/parsing, consecutive phase endpoint matches, final
framing validation, capture-before-report finalization, and raw settings-byte
immutability. All have host regressions observed failing before correction.
The next review closed those six, but reproduced an overdue/catch-up write
between scheduling decision and transmission, plus missing post-close freshness
validation. Transmission-boundary cadence accounting and post-close freshness
checks now have failing-first regressions too. The focused suite has37 tests,
including port-close deadline and initial clock-failure cleanup. Re-review
accepted commit1ec2973 for one trial. That trial observed all four phases but
failed final framing validation (truncated AttitudeState). It is inconclusive,
not accepted physical receiver-loss proof. No retry occurred; see the
[trial report](../../verification/disarmed-receiver-probe-2026-09-09.md).
