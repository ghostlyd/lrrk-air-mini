# Configuration-aware USB Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry observed board settings into deterministic host mode assessment and OpenAI telemetry inputs.

**Architecture:** Add optional immutable configuration to normalized snapshots, decode two pinned settings objects, and poll them separately from fast mandatory telemetry. The analyzer selects the current slot's four-axis tuple with bounded age. Existing motor and approval authority is unchanged.

**Tech Stack:** Existing Python package, unittest, UAVTalk, pinned NinjaPilot generated C schemas.

**Spec:** `docs/superpowers/specs/2026-09-11-configuration-aware-telemetry-design.md` (user approved).

## Global Constraints

- Firmware, arming, motor commands, settings writes, and existing safety thresholds are outside this change.
- Use NinjaPilot revision `ac77304a58de6c8bd552f94668b46903adb71cb2`.
- Keep the five existing mandatory telemetry objects and their 200 ms request cadence unchanged.
- Request the two settings objects at session start and no more than once per second thereafter, with no catch-up bursts.
- Configuration is usable only when both ages are below 2000 ms; the exact boundary is stale.
- Clear configuration on connection-state invalidation, termination, and a new session. Never reuse it across devices.
- Do not retain SystemSettings aircraft-name bytes in normalized data or public evidence.
- No OpenAI call is necessary for the deterministic integration tests.

## Workspace and validation

Use the existing linked worktree `/private/tmp/lrrk-air-mini-battery-qualification`.
Python: `/private/tmp/lrrk-wifi-host.li3b7l/venv/bin/python`.
Pinned upstream: `/tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot`.
No additional installation is required. Baseline is 378 passing host tests, no skips.

## Task 1: Implement the complete configuration-aware host path

**Files:**
- Create: `ai_assistant/src/lrrk_litewing_ai/configuration.py` (immutable model, pinned symbolic enums and mode classification data).
- Modify: `ai_assistant/src/lrrk_litewing_ai/models.py` (schema 3 serialization and validation).
- Modify: `ai_assistant/src/lrrk_litewing_ai/uavobjects.py` (exact settings decoders).
- Modify: `ai_assistant/src/lrrk_litewing_ai/live_uavtalk.py` (slow request schedule and connection-bound observations).
- Modify: `ai_assistant/src/lrrk_litewing_ai/safety.py` (configuration-dependent stabilized-slot finding and analyzer version).
- Create: `ai_assistant/tests/test_configuration.py` (model, decode, policy, compatibility and binding tests).
- Create: `ai_assistant/tests/test_configuration_live.py` (end-to-end wire/collector/policy tests).
- Modify: existing tests only for intentional schema/analyzer identity changes or reuse of their fixtures.
- Modify: `ai_assistant/README.md` (data contract, sampled-settings limitations, collection behavior).

**Interfaces:**
- Consumes `UAVTalkFrame`, `snapshot_from_frame(frame, captured_at)`, existing strict collector, and `run_preflight(snapshot, policy, now)`.
- Produces `ConfigurationObservation(stabilization_slots=(), airframe_type=None, thrust_control=None, flight_mode_settings_age_ms=None, system_settings_age_ms=None)`.
- `stabilization_slots` is an immutable tuple of exactly six immutable four-string tuples when present, empty when unobserved. Other fields use optional symbolic strings and finite nonnegative ages. Provide `to_dict()` and `from_dict(value)` on this model.
- Add `TelemetrySnapshot.configuration: Optional[ConfigurationObservation] = None`. Partial settings snapshots can contain one observed component; live aggregation combines only observations from its own session.
- Export `FLIGHT_MODE_SETTINGS` and `SYSTEM_SETTINGS` constants from `uavobjects.py`. Keep pure decode free of hardware and provider calls.
- `safety._mode_finding` gains elapsed time as an argument supplied by `run_preflight`; unrelated named modes retain their existing behavior.

- [ ] **Step 1: Write failing model/decode/policy tests.** Use literal expectations and real normalized models. Example input for a fresh known configuration:

```python
config = ConfigurationObservation(
    stabilization_slots=(("Attitude", "Attitude", "Rate", "Manual"),) * 6,
    airframe_type="QuadX", thrust_control="Throttle",
    flight_mode_settings_age_ms=0, system_settings_age_ms=0,
)
snapshot = replace(base_snapshot, flight_mode="stabilized1", configuration=config)
finding = next(f for f in run_preflight(snapshot, now=snapshot.captured_at).findings
               if f.finding_id == "capabilities.mode")
self.assertEqual(finding.status, "PASS")
```

Use table-driven literal cases for all six slots, stale either age at 2000 ms,
elapsed-time expiry, missing components, wrong airframe/thrust control, each
unsupported thrust and axis enum, and selecting a different slot with different
values. Do not confer PASS from a generic capability. Check schema 1/2 input
without configuration remains unknown, schema 3 round trips, invalid collections
and numeric values reject, and configuration mutation changes snapshot bindings.
Check legacy schema cannot smuggle authoritative new configuration.

Verify layouts against pinned XML/generated headers (including enum bounds of
fields not retained). Exact payload sizes are 59 and 46 bytes; validate all enums,
message types, instances and lengths. An aircraft name must never enter normalized
JSON. Use the existing generator-interoperability test pattern when appropriate.

- [ ] **Step 2: Run the focused tests and record the missing-feature failures.**

```bash
env PYTHONPATH=ai_assistant/src /private/tmp/lrrk-wifi-host.li3b7l/venv/bin/python -m unittest discover -s ai_assistant/tests -p 'test_configuration*.py' -v
```

- [ ] **Step 3: Implement model, decode and analysis behavior to pass those tests.**

```python
# Data representation and the assessment boundary, not a live authority grant.
SCHEMA_VERSION = 3
# The reader explicitly accepts 1, 2, 3; only version 3 reads configuration.
# Both observed ages must exist and satisfy age + elapsed_ms < 2000.
# For QuadX/Throttle, all three rotational entries must be Rate or Attitude,
# and the fourth entry must be Manual. Other configurations stay UNKNOWN.
```

Keep enum tables and immutable configuration validation in the focused new
module. Decode complete pinned payloads before discarding unrelated fields.
Version the analyzer identity and test existing approval validation on changed
configuration and old analyzer hashes. Do not change battery/IMU/link limits.

- [ ] **Step 4: Write failing collection-to-preflight tests, then implement.**

Use real encoded UAVTalk packets, collector, normalized snapshot, and analyzer;
fake only clock and serial I/O. Reuse the existing fake-transport conventions.
Verify request timestamps, NACK revocation, malformed NACK failure, settings
absence without mandatory timeout, reconnection/termination clearing, changed
slot selection, ACK allowlisting, and settings arriving after fast telemetry.

```python
# Separate schedules; no catch-up bursts, and no settings in the fast set.
if now >= next_configuration_request:
    for object_id in sorted(CONFIGURATION_OBJECT_IDS):
        transport.request(object_id)
    next_configuration_request = now + 1.0
```

Apply scheduling consistently to `collect()` and `stream()` without duplicating
substantial logic. Keep configuration out of the fast-observation UTC anchor;
if a settings receipt is newer than that anchor, conservatively account for its
age without making existing mandatory data younger. Never remove cached
mandatory observations to wait for configuration. Keep framing completion strict.

- [ ] **Step 5: Run focused tests, then the full host suite once and inspect the diff.**

```bash
env PYTHONPATH=ai_assistant/src LW_IMU_GENERATOR=/tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/ground/uavobjgenerator/uavobjgenerator LW_IMU_EXISTING_HEADERS=/tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/build/uavobject-synthetics/flight /private/tmp/lrrk-wifi-host.li3b7l/venv/bin/python -m unittest discover -s ai_assistant/tests
git diff --check
```

Expected: all host tests pass with generator interoperability enabled, no skips.
Record RED and GREEN commands/output in the private task report. The existing
CLI tests print expected rejection diagnostics; distinguish these from failures.
Document the new field and freshness limits in the host README. Stage only the
explicit production/test/documentation files, never `.superpowers` artifacts.

- [ ] **Step 6: Commit, self-review, and return for independent task review.**

```bash
git diff --stat
git commit -m "feat: assess observed LiteWing stabilization configuration"
```

## Controller acceptance and delivery

- [ ] While the worker implements, capture a 15-second baseline with the installed
  unchanged host collector using a reset-neutral, request-only serial transport.
- [ ] After task review, run the new collector for 15 seconds against the same
  installed application. Do not flash or reset as part of this comparison.
- [ ] Compare RX/TX bytes, aggregate delivery, parser errors, timeouts, request
  cadence, and IMU age distribution. Require no timeouts or malformed frames,
  and at most a 10 percent aggregate-rate reduction. Observe the actual mode
  finding; do not interpret unrelated BLOCK/UNKNOWN findings as failures of
  configuration decoding or hide them.
- [ ] If acceptance fails, investigate the measured cause; keep the host-only
  architecture and its approved limits unless a separately approved change is
  genuinely needed. Preserve failed first attempts in the private evidence.
- [ ] Add a sanitized verification note, run final whole-branch review, then push,
  open the PR, wait for relevant CI, and merge under the user's standing authority.
  Install the tested host package and verify its import/version if acceptance
  succeeds. Keep the goal open for remaining flight/battery/wireless requirements.
