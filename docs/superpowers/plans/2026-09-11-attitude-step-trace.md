# Attitude-step trace Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Capture the estimator updates missed by UART polling to diagnose the
attitude transient blocking live-flight qualification.

**Architecture:** A pure bounded ring core, a target-only capture/packer adapter,
and a generated request-only object. The existing hash-checked control adapter
inserts one call after each completed attitude update.

**Tech Stack:** C11, Python unittest, pinned NinjaPilot and ESP-IDF 5.3.2.

**Spec:** `docs/superpowers/specs/2026-09-11-attitude-step-trace-design.md`

## Global constraints

- Fixed 512-record RAM buffer; 64 pretrigger updates.
- 96-byte request-only wire record; no controller or motor-policy changes.
- Disabled builds allocate no trace buffer and do not register its object.
- Raw captures remain private; no hardware readiness inferred from host tests.

## Task 1: Ring core and wire adapter

Files: `target/litewing_attitude_trace.c`, `target/include/litewing_attitude_trace.h`,
`tests/attitude_trace_test.c`, `tests/test_attitude_trace.py` under the port.

Interfaces: `lw_trace_push(struct lw_trace *, const struct lw_trace_record *, bool)`
and `lw_trace_read(const struct lw_trace *, uint16_t, struct lw_trace_record *)`.
Zero initialization creates a rolling buffer; false reads leave output untouched.

- [ ] Write a C test: push 1000 unpowered samples, then 448 powered/post samples;
  assert count512, trigger_index64, first timestamp936 and last timestamp1447.
- [ ] Run the native test and observe failure before implementing ring behavior.
- [ ] Implement bounded rolling append, one-shot trigger and immutable frozen read.
- [ ] Cover early trigger, invalid index, incomplete read, and zero after trigger.

## Task 2: Target and transport integration

Files: `target/litewing_attitude_trace_module.c`, `prepare_control.py`,
`prepare_attitude_trace.py`, `uavobjects/litewingattitudetrace.xml`,
`target/litewing_battery_pack.c`, `target/firmware/InitMods.c`, `target/sources.cmake`,
`esp-idf/main/CMakeLists.txt`, `esp-idf/main/Kconfig.projbuild`,
`esp-idf/sdkconfig.trace.defaults`, native integration tests.

- [ ] Define 96-byte version1 schema and reject collisions with pinned/custom IDs.
- [ ] Add `LiteWingAttitudeTraceRecord` after `AttitudeStateSet`, passing original
  gyro input separately from corrected local rates; preserve early-return behavior.
- [ ] Record using `esp_timer_get_time`, zero-wait PWM observation and trace lock.
  Pack read-only virtual indexes without writing registered object storage.
- [ ] Verify real packer output, disabled behavior, and generated adaptation.
- [ ] Run port tests and compile a clean, committed trace image with pinned sources.
- [ ] Review, address findings, merge and record build identity. Do not claim flash.

## Task 3: Hardware evidence

- [ ] Back up and application-only flash, verify exact readback and marker.
- [ ] Run one bounded props-off trial; read indexes0..511 only after state frozen.
- [ ] Validate sequence/time order and compare input/corrected gyro, dt and RPY
  across the jump. Report missing/incomplete evidence rather than assuming cause.
- [ ] Use the identified cause to determine the flight-image fix and qualification.
