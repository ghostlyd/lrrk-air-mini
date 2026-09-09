# USB configuration and persistence diagnosis — 2026-09-09

## Confirmed findings

The flashed application has a settings-persistence linking defect: its
`UAVObjSave`, `UAVObjLoad` and `UAVObjDelete` resolve to the upstream weak stub,
which returns success without storing or loading data. This report records a
diagnosis, not a corrected firmware or permission to bypass a readiness gate.

The inspected build application SHA-256 is
`27694eae6e58cee9a554aece8965363824873557d5a3abcd28fcbc11d93a83c3`,
matching the [verified flashed candidate](usb-bringup-2026-09-09.md).
Its ELF/link map resolves all three functions and `UAVObjPers_stub` to
`0x42032b14`. Disassembly confirms a return-zero stub; the board's save calls
resolve there before invoking the real NVS provisioning-marker function.

The real persistence object is compiled into `libmain.a` but not extracted into
the executable. NinjaPilot's `flight/uavobjects/uavobjectpersistence.c` describes
this weak-symbol/archive failure and provides `uavobject_persistence_linked`.
The pinned reference board references that anchor; the current LiteWing board
does not. Pins:

- NinjaPilot: `ac77304a58de6c8bd552f94668b46903adb71cb2`.
- OpenPilotESP32-WROOM-32E reference: `7233c97f844c0377930bcdf22998e289638b64c6`.
- LiteWing source baseline: `f2e20f75222f0e302c30ac689fd8627e611fe24a`.

## Runtime configuration evidence

A further 30-second USB-only capture at 57600 baud contained 115,647 bytes,
SHA-256 `4081b1f009460ee0b8c6476c1acf107d943178aaf277b568b48477cc50bbe543`.
It remains private, owner-readable and Git-ignored. The allowlisted diagnostic
sent only telemetry handshake/status frames and object read requests, not
settings writes, receiver inputs, arming or motor commands. The serial port
was released afterward. Props remained removed and the battery absent.

- All 28 decoded `ManualControlSettings` samples had receiver groups `None`
  and channel numbers zero; all 28 `MixerSettings` samples had twelve disabled
  mixers, zero vectors and a zero throttle curve.
- The prior state capture's receiver channels were `65534` (invalid), not
  the timeout value. The disconnected Receiver Critical path is therefore
  explained by invalid configuration, not merely no control traffic.
- `ActuatorDesired` was publishing changing values. Zero enabled mixers is a
  sufficient cause of the Actuator module's explicit Critical/failsafe branch;
  missing desired updates are not needed to explain the observations.
- Observed arm state remained Disarmed and the four command channels zero.
  No electrical output, motor direction or receiver-loss test was performed.

## Initialization and inference boundary

Board initialization registers objects, applies custom first-boot defaults and
attempts three saves before flight modules initialize. Generated object
initializers detect existing objects and return without resetting their data;
ordinary module initialization is not the overwrite cause.

An unprovisioned boot can apply correct defaults in RAM, call no-op saves, and
still commit the separate NVS provisioning marker. On a subsequent boot,
generated defaults remain because loads do nothing; an existing marker then
skips the board defaults. This deterministic sequence explains the captured
generic configuration. The actual marker value and its write history were
**not read**, so that historical sequence remains an inference, not a directly
observed NVS history.

## Required correction and acceptance

Tracked in [issue #22](https://github.com/ghostlyd/lrrk-air-mini/issues/22).
Link the real persistence implementation and verify its actual ELF resolution,
not just compilation or a source-string check. Check save failures and commit
the provisioning marker only after successful persistent writes. Define a
bounded, non-destructive recovery path for an existing marker with missing
settings; do not erase storage or overwrite valid operator settings by default.
Test failure paths and reboot round trips before claiming persistence works.

Separate unresolved gates also remain: the GCS receiver's input-age supervisor
is conditional on RTC support absent from this target, BootFault is not
explicitly set OK after successful initialization, and watchdog motor-cut
latency is [not yet bounded](https://github.com/ghostlyd/lrrk-air-mini/issues/19).
The stale-input defect is tracked in [issue #23](https://github.com/ghostlyd/lrrk-air-mini/issues/23).
Do not send GCS control inputs until stale-input supervision is corrected and
verified. Do not clear diagnostic alarms to manufacture an all-clear result.
