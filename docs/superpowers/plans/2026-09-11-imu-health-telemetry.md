# IMU Health Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Carry explicit MPU6050 identity, sample age and driver health from the board to USB advisory preflight.

**Architecture:** A coherent driver snapshot feeds a separate generated read-only UAVObject. Serialization independently expires samples. The host optionally consumes the object without changing old-firmware five-object acquisition.

**Tech Stack:** C11, ESP-IDF 5.3.2, pinned NinjaPilot UAVObject generator, CPython 3.11–3.14.

**Spec:** ../specs/2026-09-11-imu-health-telemetry-design.md

## Global Constraints

- No arming-policy or motor-safeguard changes.
- Missing optional health telemetry remains unknown.
- Unknown sample age uses UINT32_MAX.
- Generated identifiers must not collide with existing objects or maintenance IDs.
- Firmware build, flash identity, live observations and flight qualification are separate evidence.

## Task 1: Schema and native snapshot contract

Files: create `ports/ninjapilot-litewing/uavobjects/litewingimuhealth.xml`,
`target/include/litewing_imu_health.h`, `target/litewing_imu_health.c`,
`tests/imu_health_test.c`, `tests/test_imu_health.py` below the same port root.

Interface: `struct lw_imu_observation` contains `bool identity_verified`,
`uint8_t who_am_i`, `bool sample_seen`, `bool healthy`, `uint32_t sample_ms`.
`lw_imu_health_export(const struct lw_imu_observation *, uint32_t now_ms,
uint32_t timeout_ms, uint8_t output[9])` writes a little-endian uint32 age,
then version, identity-verified, WHO_AM_I, sample-seen and health bytes.
Version is 1. Health codes are 0 unknown, 1 healthy, 2 unhealthy. Age is unsigned
elapsed milliseconds when sampled, otherwise UINT32_MAX. Healthy requires a
verified compatible identity, a seen sample, driver healthy, and age below the
existing stale threshold. Expired healthy becomes unknown; explicit unhealthy
remains unhealthy. No sample may be reported healthy.

- [ ] Add native assertions for never-sampled age UINT32_MAX; healthy fresh data;
      threshold equality expiry; unsigned rollover; explicit unhealthy; and
      identity failure preventing healthy. Compile with `cc -std=c11 -Wall
      -Wextra -Werror -fsanitize=address,undefined` through unittest.
- [ ] Run the test before implementation and confirm missing exporter failure.
- [ ] Implement the pure exporter and XML with matching fields/access policy.
- [ ] Generate C with the pinned generator and compare layout/size to all nine
      exporter bytes; check both object and metadata identifiers for collisions.
- [ ] Run native tests and commit only the schema/exporter/test unit.

## Task 2: Firmware driver and publication

Modify `target/pios_litewing_mpu6050.c`, its header, wrapper
`esp-idf/main/CMakeLists.txt`, and object initialization/packing preparation.
Create `target/litewing_imu_health_module.c` and native worker/packer tests.

Interface: `PIOS_LiteWing_MPU6050_GetObservation(struct lw_imu_observation *)`
returns one coherent observation. Use a short FreeRTOS critical section only
for copying/updating primitive snapshot fields; do not hold it over I2C,
queue operations, object-manager calls or motor-lock operations. Record identity
only after successful probe/validation; invalidate on reset/shutdown. Publication
runs outside the control loop at 100 ms intervals. Object pack-time export uses
the current clock and a copied observation, not a cached healthy payload.

- [ ] Add failing tests for reset invalidation, stale pack-time request, queued
      update expiry, failed publication, and no motor-policy writes.
- [ ] Connect driver observations to the pure exporter without changing existing
      calls to `PIOS_LiteWing_BrushedPWM_SetImuHealthy`.
- [ ] Generate/register the separate object through repository-owned build input;
      refuse inbound data writes using read-only GCS access metadata.
- [ ] Test coherent snapshot under competing updates and pack-time clock advance.
- [ ] Run full port tests, wrapper build and schema collision checks; commit.

## Task 3: Optional host decoding and acquisition

Modify `ai_assistant/src/lrrk_litewing_ai/uavobjects.py` and `live_uavtalk.py`;
extend `test_live_uavtalk.py`, `test_usb_stream.py` and schema decoder tests.

Interface: decode the generated object ID and exact nine-byte layout as an
optional observation. Do not add it to the five mandatory objects. Requests and
ACK allowlists explicitly admit only this new object in addition to existing
objects. Clear cached health at handshake reset/disconnect. Compute effective
sample age from board age plus monotonic time since receipt; never assign board
UTC from host wall time. Unknown version, invalid booleans, health outside 0..2,
wrong length or instance must fail decoding. A missing optional object cannot
prevent delivery of otherwise complete legacy telemetry.

- [ ] Add red tests for missing-object legacy operation, exact golden C bytes,
      malformed versions/enums/length, host-age expiry and reconnect clearing.
- [ ] Decode verified identity and explicit health into existing SensorState;
      keep unrelated sensors/alarms unchanged.
- [ ] Add native-generated-byte interoperability coverage, then run the full
      assistant suite with the optional OpenAI SDK installed; commit.

## Task 4: Review and deployment evidence

- [ ] Independently review immutable source diff and fault-path test coverage.
- [ ] Verify full CI and build output; retain previous application image.
- [ ] Perform application-only bench flash with settings/credential preservation,
      then verify image identity separately from successful transfer.
- [ ] Collect bounded read-side USB observations; verify explicit identity/age/
      health and no motor commands. Keep raw captures private.
- [ ] Install the built host wheel and repeat the installed-entry-point check.
- [ ] Record measured results and limitations in the dependency inventory.

No task above establishes flight readiness or qualifies the arriving battery.
