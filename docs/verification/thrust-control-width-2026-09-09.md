# LiteWing thrust-control storage and failure handling

## Scope

Source correction for [issue 28](https://github.com/ghostlyd/lrrk-air-mini/issues/28),
based on `e184a013fa737557d5e60e969c8f10b0e083705c` and pinned NinjaPilot
`ac77304a58de6c8bd552f94668b46903adb71cb2`. This is not arming or flight acceptance.
No device connection, flash, receiver packet, arm command, or physical motor
command was used for this verification. The latest physically verified firmware
remains the earlier persistence-corrected image; this source fix is not yet on it.

## Root cause and reproduction

The generated `SystemSettingsThrustControlGet(uint8_t *)` calls
`UAVObjGetDataField` with offset 45 and size 1, discarding its return code.
Pinned Receiver passes a pointer to an uninitialized four-byte enum; Actuator
passes a pointer to a statically initialized enum. The ESP32 compiler diagnosed
both incompatible pointers. Disassembly of the previous target ELF confirmed
the one-byte read and Receiver's later four-byte load from its enum stack slot.
Static zero initialization made Actuator's normal path appear correct but did
not handle missing reads or invalid values.

Host regression uses the complete task translation units and actual generated
UAVObject C/headers. `-ftrivial-auto-var-init=pattern` makes Receiver's otherwise
indeterminate upper enum bytes repeatable; it is a test flag, not a firmware fix.
The harness asserts the four-byte enum ABI and actual one-byte field layout.
OS scheduling, object-manager storage and hardware writes are host substitutes.
The test's simulated ARMED state never reaches the drone.

Before correction, eight of ten initial tests failed:

- Receiver retained the previous thrust of 0.75 instead of the requested 0.2
  throttle or 0.4 collective. Invalid, NONE and failed reads also retained it.
- Actuator produced host-captured output 200 or 400 after failed/invalid/NONE
  reads instead of selecting its configured failsafe output. Normal throttle
  and collective tests passed, demonstrating that this was not a blanket
  broken fixture.

These are reproducible source/host consequences, not an observed flight symptom.

## Correction

`prepare_control.py` creates target-only copies of Receiver and Actuator in the
ESP-IDF build directory. SHA-256 and exact replacement anchors are checked before
any writes. Upstream files remain untouched and retain their GPL notices.

`LiteWingThrustControlRead` uses the generated field's offset with byte-sized
storage, checks the object-manager result and validates the value before
assigning the complete enum. Throttle and Collective remain supported. `None`
is a valid upstream schema option but deliberately unsupported as a LiteWing
thrust source: it no longer falls through to stale/direct bypass control.
Unknown byte values and unsuccessful reads are faults, even if a failing
storage implementation wrote an otherwise valid value.

- Receiver reports a critical alarm, disconnects input, clears connection
  counters and publishes throttle/thrust -1 with roll/pitch/yaw/collective zero.
  It does not continue consuming input until a valid read occurs.
- Actuator reads a local validated mode each iteration instead of relying on an
  asynchronously refreshed global enum. Invalid reads take its existing
  `setFailsafe()` path before mixing. For the verified LiteWing configuration,
  the motor minima are zero; arbitrary user-configured minima are not certified.

The generated wire schema, arming settings, pin mapping, mixer and calibration
are unchanged. The extra per-cycle object-manager read is not a claim of bounded
mutex wait or electrical stop latency; those remain issue 19 work.

## Verification

Run from the repository root with the pinned external checkout and generated
objects available:

```sh
LRRK_TEST_FLIGHT_ROOT=/path/to/NinjaPilot \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p 'test_thrust_*.py' -v
```

`LRRK_TEST_ORIGINAL_THRUST=1` selects the unadapted task sources for the failing
comparison. It never edits production files. Explicitly supplying a checkout
without generated objects is an error, not a silently skipped integration test.

The 12 task tests cover both modes, NONE/unknown values, failed reads, errors
after valid control, write-then-error storage and recovery. Three preparation
tests cover source drift, unchanged-output timestamps and source-tree protection.
GitHub's source gate now generates the actual objects using Qt 5 and runs these
tests, in addition to the real-parser receiver-age tests.

Local full validation: 82 assistant tests plus 107 port tests passed with no
skips when the real ELF, build graph and generated source inputs were supplied.
ESP-IDF 5.3.2 built the ESP32-S3 target: application size `0x56e00` (355,840
bytes), 66% of the 1 MiB application partition free. Both adapted consumers
compiled without the thrust-pointer diagnostic; the existing CMake deprecation
warning remains. The persistence link gate also passed.

Disassembly confirms both consumers use a one-byte read and branch on its
failure result. The build graph selects the adapted task files. This establishes
source/build integration, not runtime hardware or scheduler validation.

## Remaining physical gates

The user's arming authorization is recorded separately from readiness. Arming
remains disabled pending disarmed receiver-loss validation (issue 23), startup
alarm investigation (issue 27), and the remaining bench/calibration gates.
No battery is present according to the user's latest confirmation. No flight
or public binary release is claimed by this correction.
