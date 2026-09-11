# Explicit IMU health telemetry

Owner approved implementation of a versioned read-only IMU-health object on
2026-09-11. This document records that approved scope. It is not deployment
evidence.

## Purpose

The five-object USB aggregate carries attitude but not sensor identity or driver
health. Generic Sensors:Uninitialised cannot be interpreted as a failed MPU6050:
the wrapper runs Attitude, not the upstream Sensors module that owns that alarm.
The existing driver already tracks sample freshness and gates motor output.
Expose explicit observations without changing that gate or clearing alarms.

## Contract

Add an independently versioned, single-instance, read-only UAVObject for this
wrapper. Generate its identifier from its schema using the pinned UAVObject
generator; reject collisions with existing objects and maintenance IDs. Do not
modify any existing upstream object layout or reuse an unrelated object ID.

Version 1 reports protocol version, successful identity-probe evidence, observed
WHO_AM_I value, sample-seen status, driver-health state, and sample age in
milliseconds. Unknown sample age uses UINT32_MAX. Identity is observed, not a
hardcoded statement that any connected board is a LiteWing. A valid MPU6050
identity probe establishes the compatible sensor identity, not aircraft identity.

Firmware obtains an internally consistent snapshot without blocking the flight
loop. It evaluates freshness against the existing driver stale-time threshold
at serialization, including explicit requests and queued updates. Never publish
healthy before a valid sample; failures and resets invalidate health. Unknown
or expired observations cannot be upgraded by later host receipt time. Telemetry
publication failure must not modify motor safety or arming configuration.

## Compatibility and host behavior

The existing five-object acquisition remains usable on old images. Missing
health-object support leaves SensorState fields unknown and does not prevent
ordinary telemetry delivery. Unsupported versions, malformed payloads or invalid
enums are rejected rather than interpreted optimistically. Health data must
expire independently and must not carry across reconnects. The host reports
healthy only while both board-reported sample age and host receipt age satisfy
the documented freshness bounds. Explicit unhealthy is retained as unhealthy;
expired formerly healthy observations become unknown.

The assistant may explain those states and existing alarms. It receives no new
arming, motor, calibration, reset or firmware tools. API credentials remain on
the host. Raw captures and physical identifiers remain outside Git.

## Implementation boundaries

Driver snapshot: target/pios_litewing_mpu6050.c and its public header.
Schema/build registration: repository-owned object schema and wrapper CMake;
generated files remain in build output. Publication and pack-time expiry follow
the existing battery module/packer separation. Host decoding and aggregation
extend uavobjects.py and live_uavtalk.py with a separate optional health field.
Do not reinterpret all generic alarms as sensor health or suppress them.

## Verification

Native tests cover never sampled, valid probe/sample, read failure, stale sample,
reset, clock rollover, concurrent snapshot consistency and publication failure.
Protocol tests compare generated C and Python layouts/IDs, collision checks,
invalid versions/enums/lengths, and read-only access. Host tests cover missing
object on old firmware, malformed object, stale receipt, reconnect clearing and
healthy-to-unhealthy transitions. Full host and firmware source gates must pass.

Build the wrapper with ESP-IDF 5.3.2. Review before application-only bench flash;
preserve settings and credentials and verify installed image separately. Live
telemetry must show explicit health without motor commands. A healthy report is
not a substitute for battery compatibility, physical orientation, motor mapping,
radio qualification or a controlled flight test.
