# Zero-wait telemetry object reads — 2026-09-10

Firmware-publisher foundation based on host-lifecycle revision `b2f6947`.
The publisher/send path is not connected by this change.

The pinned `UAVObjPack` acquires the object-manager recursive mutex with
`portMAX_DELAY`. Calling it directly from the command task could therefore
block pilot processing behind another task. The generated object manager now
adds `lw_telemetry_try_pack`: take that same mutex with zero wait, then invoke
the ordinary packer while already owning the recursive lock. Busy/uninitialized
locks skip the read. No object or flight-setting writes are introduced.

Only AttitudeState, FlightStatus, SystemAlarms and ActuatorCommand exact
ID/size pairs are accepted, with instance zero and checked output capacity.
Battery is explicitly excluded: it must use the existing acquisition-age
export rather than the cached UAVObject. Handles must be trusted registered
objects, not wire-provided pointers. Failure leaves the caller buffer untouched.
This is a zero-wait lock contract, not measured scheduling or execution latency.

The adapter is appended to the hash-verified generated object manager, leaving
the upstream checkout unchanged. CMake tracks the included adapter source as a
configure dependency. Its public header is local to the target port.

Tests run with NinjaPilot `ac77304a58de6c8bd552f94668b46903adb71cb2`:

- Actual pinned packer plus generated read guard, real recursive pthread mutex,
  a contending holder, all selected object sizes/capacities, NULL/uninitialized
  cases, battery rejection and untouched-buffer canaries: passed under ASan/UBSan.
- Mutation changing zero-wait to blocking: deliberately deadlocks behind the
  holder and is terminated by the test timeout; the unmodified guard passes.
- Existing arming-maintenance write exclusion regression: passed, including
  its original unguarded-write mutation test.
- Independent review found no blocking issues and confirmed the pinned
  recursive-owner path. The source CI job explicitly runs the new test with
  pinned flight source, rather than relying on the optional no-source skip.
- Full port suite with the pinned flight root: 380 run, 359 passed, 21 optional
  environment skips. The new contention/mutation test ran rather than skipped.

This evidence does not qualify task priority/interference, radio load, battery
timing association or physical stop latency. No board operation occurred.

## Target build

Clean committed source `804f9ea` builds with pinned ESP-IDF 5.3.2 for ESP32-S3.
The image is `0xd4d90` bytes in the unchanged `0x100000`-byte application
partition, leaving 17% free. USB ID reservations pass for 115 objects and the
persistence link check passes. The generated object-manager compilation is
exercised; the read guard has no publisher caller yet and is not claimed as an
active telemetry path. Flash instructions printed by the build were not run.

Core dumps remain disabled (`CONFIG_ESP_COREDUMP_ENABLE_TO_NONE=y`, neither
flash nor UART enabled). Build output includes packed-pointer conversion
warnings in the pinned upstream object-manager code and an upstream mbedTLS
CMake compatibility warning. Build success is not a warning-free or physical
execution claim.
