# Task 1 report

Status: complete, native schema/exporter only. Branch: codex/imu-health-telemetry.
Worktree: /private/tmp/lrrk-air-mini-battery-qualification.
No hardware, network/provider calls, secrets, push, external-checkout edits, or subagents.
No integration or arming/motor-safeguard changes.

## Changed paths

- ports/ninjapilot-litewing/uavobjects/litewingimuhealth.xml
- ports/ninjapilot-litewing/target/include/litewing_imu_health.h
- ports/ninjapilot-litewing/target/litewing_imu_health.c
- ports/ninjapilot-litewing/tests/imu_health_test.c
- ports/ninjapilot-litewing/tests/test_imu_health.py
- .superpowers/sdd/2026-09-11-imu-health-telemetry/task-1-report.md

## Contract and self-review

The pure function writes exactly nine bytes, including little-endian unsigned age.
No seen sample gives UINT32_MAX and unknown even when healthy=false. A seen
explicit unhealthy sample remains unhealthy after expiry or identity failure.
Healthy requires caller-supplied compatible identity evidence, sample_seen,
driver healthy, and age strictly less than the supplied existing timeout.
WHO_AM_I is copied as observed, never guessed or treated as aircraft identity.
Tests exercise twelve literal fixtures: never sampled, no sample with either
health flag, fresh, equality/after expiry, unsigned rollover, fresh/stale failure,
unverified identity, zero timeout, and multibyte age. Guard bytes detect writes
outside the nine-byte output. ASan and UBSan are enabled, with no recovery.

Generated packed and aligned typedef sizes both compile to 9. Offsets:
SampleAgeMs=0, Version=4, IdentityVerified=5, WhoAmI=6, SampleSeen=7, Health=8.
Generated enum values inspected: False=0/True=1 and Unknown=0/Healthy=1/Unhealthy=2.
Generated defaults and a multibyte fresh sample are compared byte-for-byte with
the exporter using compiled declarations extracted from the generated header.
Generated GCS access is readonly; flight access is readwrite for publication;
singleinstance=true, settings=false, updates manual.

Object ID 0xDA60A0C6; metadata ID 0xDA60A0C7. Both checked against all 115 existing
generated object IDs and their adjacent metadata IDs in
/tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/build/uavobject-synthetics/flight,
and maintenance reservations 0x4C575046 and 0x4C575048 loaded from verify_usb_ids.py.
The pinned manager header defines MetaObjectId(id) as ((id) + 1).

Actual issue found and resolved: pinned flight generator uses QString::toInt()
for integer defaults (ground/uavobjgenerator/generators/flight/
uavobjectgeneratorflight.cpp:225). XML 4294967295 silently generated age 0.
A failing compiled defaults test reproduced this. XML now uses -1, which this
C generator assigns to uint32_t as UINT32_MAX. This compatibility detail is
documented in XML. Other language generators were not validated; later consumers
must preserve the unsigned sentinel. No external generator changes were made.

Caller must provide valid pointers, coherent snapshot and driver timeout.
Snapshot acquisition, resets, publication, host optional telemetry and firmware
integration remain later tasks. No hardware evidence is claimed. Missing optional
telemetry must remain unknown. No actual blocker or running test remains.
The schema test requires LW_IMU_GENERATOR and LW_IMU_EXISTING_HEADERS; it explicitly
skips without the generator environment variable. Both tests ran below with no skips.

## Red: missing exporter before implementation

Working directory for all unittest commands: /private/tmp/lrrk-air-mini-battery-qualification.

Command:
```sh
/private/tmp/lrrk-wifi-host.li3b7l/venv/bin/python -m unittest discover -s ports/ninjapilot-litewing/tests -p test_imu_health.py -v
```

Full output (exit 1):
```text
test_observation_wire_contract (test_imu_health.ImuHealthTests.test_observation_wire_contract) ... COMPILE: cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -I /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/include /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/tests/imu_health_test.c /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/litewing_imu_health.c -o /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-native-dqy_jd7a/imu_health
FAIL

======================================================================
FAIL: test_observation_wire_contract (test_imu_health.ImuHealthTests.test_observation_wire_contract)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/tests/test_imu_health.py", line 23, in test_observation_wire_contract
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 1 != 0 : clang: error: no such file or directory: '/private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/litewing_imu_health.c'


----------------------------------------------------------------------
Ran 1 test in 0.022s

FAILED (failures=1)
```

## First native green

Same command, after implementing exporter (exit 0):
```text
test_observation_wire_contract (test_imu_health.ImuHealthTests.test_observation_wire_contract) ... COMPILE: cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -I /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/include /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/tests/imu_health_test.c /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/litewing_imu_health.c -o /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-native-n_hd88oy/imu_health
RUN: /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-native-n_hd88oy/imu_health
IMU_HEALTH_NATIVE=PASS cases=12
ok

----------------------------------------------------------------------
Ran 1 test in 0.389s

OK
```

## Generated-defaults red

Command:
```sh
LW_IMU_GENERATOR=/tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/ground/uavobjgenerator/uavobjgenerator LW_IMU_EXISTING_HEADERS=/tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/build/uavobject-synthetics/flight /private/tmp/lrrk-wifi-host.li3b7l/venv/bin/python -m unittest discover -s ports/ninjapilot-litewing/tests -p test_imu_health.py -v
```

Full output before correcting the XML default (exit 1):
```text
test_generated_schema (test_imu_health.ImuHealthTests.test_generated_schema) ... GENERATE (fresh cwd): /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-xcjqrqvg /tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/ground/uavobjgenerator/uavobjgenerator -flight /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/uavobjects /tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot LiteWingIMUHealth
- OpenPilot UAVObject Generator -
Done: processed 1 XML files and generated 1 objects with no ID collisions. Total size of the data fields is 9 bytes.
generating flight code
IDS=PASS object=0xDA60A0C6 metadata=0xDA60A0C7 existing_objects=115 maintenance=[1280790598, 1280790600]
COMPILE: cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -I /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/include /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-xcjqrqvg/layout.c /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/litewing_imu_health.c -o /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-xcjqrqvg/layout
RUN: /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-xcjqrqvg/layout
FAIL
test_observation_wire_contract (test_imu_health.ImuHealthTests.test_observation_wire_contract) ... COMPILE: cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -I /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/include /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/tests/imu_health_test.c /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/litewing_imu_health.c -o /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-native-m1kabi7p/imu_health
RUN: /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-native-m1kabi7p/imu_health
IMU_HEALTH_NATIVE=PASS cases=12
ok

======================================================================
FAIL: test_generated_schema (test_imu_health.ImuHealthTests.test_generated_schema)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/tests/test_imu_health.py", line 87, in test_generated_schema
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: -6 != 0 : Assertion failed: (memcmp(&data, bytes, 9) == 0), function main, file layout.c, line 41.


----------------------------------------------------------------------
Ran 2 tests in 0.680s

FAILED (failures=1)
```

## Final green

Same environment-prefixed command above, after correcting the XML default.
Full output (exit 0):
```text
test_generated_schema (test_imu_health.ImuHealthTests.test_generated_schema) ... GENERATE (fresh cwd): /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-s6ybt1k0 /tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/ground/uavobjgenerator/uavobjgenerator -flight /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/uavobjects /tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot LiteWingIMUHealth
- OpenPilot UAVObject Generator -
Done: processed 1 XML files and generated 1 objects with no ID collisions. Total size of the data fields is 9 bytes.
generating flight code
IDS=PASS object=0xDA60A0C6 metadata=0xDA60A0C7 existing_objects=115 maintenance=[1280790598, 1280790600]
COMPILE: cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -I /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/include /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-s6ybt1k0/layout.c /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/litewing_imu_health.c -o /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-s6ybt1k0/layout
RUN: /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-schema-s6ybt1k0/layout
GENERATED_LAYOUT_DEFAULTS_WIRE=PASS size=9 offsets=0,4,5,6,7,8 access=gcs-readonly
ok
test_observation_wire_contract (test_imu_health.ImuHealthTests.test_observation_wire_contract) ... COMPILE: cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all -I /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/include /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/tests/imu_health_test.c /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/target/litewing_imu_health.c -o /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-native-kyfmpf_i/imu_health
RUN: /var/folders/x5/6vbbf_z93tjf4p2ffxtz9vlm0000gn/T/lw-imu-native-kyfmpf_i/imu_health
IMU_HEALTH_NATIVE=PASS cases=12
ok

----------------------------------------------------------------------
Ran 2 tests in 0.718s

OK
```

## Generator isolation

An initial manual generation also ran only inside a newly created directory:
```sh
mktemp -d /private/tmp/lrrk-imu-schema.XXXXXX
# output: /private/tmp/lrrk-imu-schema.gw5CKm
# cwd: /private/tmp/lrrk-imu-schema.gw5CKm
/tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot/ground/uavobjgenerator/uavobjgenerator -flight /private/tmp/lrrk-air-mini-battery-qualification/ports/ninjapilot-litewing/uavobjects /tmp/lrrk-litewing-wrapper.M3xItG/NinjaPilot LiteWingIMUHealth
```
Output (exit 0):
```text
- OpenPilot UAVObject Generator -
Done: processed 1 XML files and generated 1 objects with no ID collisions. Total size of the data fields is 9 bytes.
generating flight code
```
The subsequent repeatable tests each generated into their own fresh temporary
directory and removed their temporary artifacts on completion. The manual
directory retains the initial diagnostic output, not the final default fix.
No generated artifacts were added to Git.
