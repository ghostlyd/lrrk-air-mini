# Advisory alarm evidence — 2026-09-09

## Result and scope

The host-only assistant now preserves unknown alarm state, requires all four
motor observations, and rejects approval reuse after telemetry becomes stale.
Its strict saved-capture decoder supports the pinned `SystemAlarms` and
`ActuatorCommand` objects. This is offline analysis, not a live command path,
provider-backed run, complete streaming telemetry aggregator or flight release.

The approved design remains [host-only and advisory](../superpowers/specs/2026-09-09-openai-litewing-assistant-design.md).
No receiver inputs, arming commands, motor commands or settings writes were
sent to verify these changes. No OpenAI credential or paid API call was used.

## Regressions and migration

Before correction, missing alarms were converted to an empty list, missing
mode passed its readiness check, incomplete in-range motor observations passed,
and an approved unchanged snapshot could remain current after its telemetry
age exceeded policy. Regression tests reproduced these paths before the fix.

- Snapshot output schema is **2**; input schemas 1 and 2 are accepted.
  Omitted/null alarms mean unknown; only explicit `[]` means reported clear.
  Malformed alarm values and null/bool actuator elements are rejected.
- Independent review reproduced a pre-existing capability coercion:
  `{"gps": false}` became a declared GPS and could reach approval. Both-schema
  regressions failed before explicit list/object-or-null validation corrected
  this path, including other malformed optional containers.
- Four motor observations are required. Out-of-range evidence is not hidden
  by an incomplete channel count. Missing mode remains unknown.
- Analyzer version is **litewing-safety-3**. Approval-current checks rerun
  preflight at the supplied current time, aborting stale approvals even when
  the snapshot hash is unchanged.
- Consumers must accept schema 2 and nullable alarms. Normalization changes
  snapshot hashes; regenerate proposals instead of reusing prior digests.

Pinned layouts were checked against NinjaPilot revision
`ac77304a58de6c8bd552f94668b46903adb71cb2` XML and generated packed C definitions:
`SystemAlarms` ID `0x6B7639EC`, 25 bytes; `ActuatorCommand` ID `0xB8229FE4`,
29 bytes. The decoder rejects incorrect sizes, nonzero instances and invalid
alarm enums. Uninitialised states remain unknown, critical/warning/error or
extended fault evidence blocks, and explicit all-OK state is distinguished.
Motor values retain their signed range; nonzero auxiliary channels and failed
updates become blocking evidence. These are reported values, not measured pins.

## Actual captured-byte integration

The private USB-only state capture described in [the bring-up report](usb-bringup-2026-09-09.md)
was hash-checked (`39662bb4cff08a5f724f7b8a3a211823bad2a0bf784c4ed56ea03f919d102af4`).
Its filesystem creation timestamp was `2026-09-09T13:08:59.363886+00:00`.
The complete capture contains non-frame bytes and is **rejected** by the strict
production parser; no claim of whole-stream acceptance or lossless decoding is
made. The pinned upstream parser located candidates; each selected frame was
then matched byte-for-byte within the original capture, extracted without
rewriting it, and independently CRC-validated by the production parser.

| Exact original frame | Byte offset | Bytes | SHA-256 |
| --- | --- | --- | --- |
| SystemAlarms | 1185 | 36 | `1f78f35cf1bcdb53b5a0d8f38cee777b718c5ead02e315a9982a517ef05254ff` |
| ActuatorCommand | 3240 | 40 | `c0510cfb0d397c5e0f9ac0caca4027e8f97075bf140b4c9eb9ca53331ac31a0a` |

At approximately `2026-09-09T13:31:01Z`, each frame was passed through the
production CLI's offline preflight/assistant path using the original capture
timestamp. Both analyses exited successfully and returned **BLOCKED** readiness,
not a successful flight gate. The alarm sample preserved Receiver, Actuator and
CPUOverload Critical plus uninitialised states. CPUOverload was transient: the
last sample in the original report was OK, not every sample throughout.
The actuator sample retained four zero commands but kept global alarm state
unknown. Both partial historical snapshots retained unknown battery/IMU-health,
link-age, board identity and arm-state fields; neither was relabeled fresh.

Raw captures, extracted frames and board identifiers remain private and
Git-ignored. The evidence does not show a networked AI provider, complete live
field aggregation, calibrated sensors, physical output shutdown or flight.

## Automated checks

The expanded assistant suite has **82 passing tests**, covering strict models, alarm decoding, approval
freshness, the CLI/audit path and real Agents SDK function-tool invocation with
network and DNS blocked. The **49 passing port tests** check existing
source/build/PWM contracts. The combined host gate passed. A local `0.2.0`
wheel build, offline installation in a fresh virtual environment, installed
`litewing-ai --help`, and dependency check succeeded. Independent read-only
review approved the corrected changes with no remaining actionable findings.
See the associated PR for CI results; these checks do not clear the remaining
hardware gates.
