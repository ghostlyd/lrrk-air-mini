# Reset and current-configuration observations

## Purpose and installed image

Investigate the zero-byte session immediately after the previous application
installation, without changing firmware, timeouts, saved settings, or motor
commands. The installed application remains `4fb4938`, SHA-256
`47e805ad287a6fcd2a4be106bae7868036625100daa82a6cc3e0d38b4bdc91a2`.
A fresh readback of its 876,272 application bytes matched that hash.

## Bounded reset observations

| Experiment | Result |
| --- | --- |
| Reset-neutral collection from already-running board | Complete healthy snapshot in 139 ms; disarmed, four zero commands |
| RTS reset with 57600-baud serial handle held open | First CRC-valid telemetry at approximately 346 ms; 459 valid frames over five seconds; 135 initial bytes discarded before synchronization; no later parser error |
| Collection after closing that held handle | Complete snapshot in 159 ms; disarmed, zero commands, healthy IMU |
| RTS reset, one-second delay, close, then reset-neutral collection | Complete snapshot 1.178 s after reset; collection itself took 174 ms |
| 4 KiB application-prefix read through bootloader stub, no reset on exit, then the same reset/close sequence | Complete snapshot 1.191 s after reset; collection itself took 179 ms |
| Full `0..0x118000` readback through bootloader stub, then reset/close and installed offline launcher | Five-second launcher exited 0 with 23,759 captured bytes |

The reset assertion interval was 100 ms, matching the installed esptool 4.12
non-native-USB HardReset sequence. These timestamps are host observations, not
oscilloscope measurements of reset pins or guaranteed startup bounds. In
particular, the held-port trace retained initial input and reports first valid
telemetry rather than proving a hardware reset edge timestamp.

The full-read reproduction ended on a complete frame boundary: 634 valid
frames, zero NACKs, 25 disarmed FlightStatus observations, 30 actuator reports
with all twelve slots zero, and 75 healthy IMU reports with maximum reported age
2 ms. The three-event offline audit chain validated. Bootloader operations read
flash only; they did not rewrite the application, bootloader, partition table,
settings, or credentials.

**The earlier failure was not reproduced and is not declared fixed.** These
results do not justify changing firmware or widening transport deadlines.
They also do not constitute a physical USB power-cycle/cold-start reliability
qualification. Keep future first-attempt failures and their diagnostics visible;
do not hide them behind automatic retry or a successful later attempt.

## Current configuration: separate request-only observation

Using hash-verified pinned XML/codec definitions, one request each was sent for
FlightModeSettings, SystemSettings, FlightStatus, and ActuatorCommand over the
reset-neutral transport. Returned objects had valid framing, the expected
single instance and exact schema lengths. No settings, receiver, or motor
command was sent.

| Observed field | Value |
| --- | --- |
| AirframeType | QuadX |
| ThrustControl | Throttle |
| FlightModeSettings.Arming | Yaw Right |
| DisableSanityChecks | FALSE |
| Stabilization1Settings (Roll, Pitch, Yaw, Thrust) | Attitude, Attitude, Rate, Manual |
| FlightModePosition | Stabilized1 through Stabilized6 |
| Current FlightMode | Stabilized1 |
| Armed | Disarmed |
| Four mapped motor commands | 0, 0, 0, 0 |

The pinned stabilized handler selects Stabilization1Settings for Stabilized1;
the name alone is not sufficient evidence of its behavior. This observation
confirms the current tuple, not a permanent identity or proof that all six slots
share it. It does not change the generic host policy or establish currentness
for later advisory/approval decisions.

## Next integration boundary

Configuration-aware assistance must consume validated, connection-bound
configuration observations, preserve missing/expired/mismatched state as
unknown, and classify thrust as well as roll/pitch/yaw. It must not whitelist
`stabilized1` unconditionally. Added polling must account for the existing
57600-baud telemetry load rather than assuming unlimited serial bandwidth.
Elapsed IMU analysis age, required subsystem alarms, battery compatibility,
wireless acceptance and physical flight remain separate unfinished work.

All raw serial captures, full flash reads and complete configuration objects
remain in an owner-only local diagnostic directory outside Git. No OpenAI
request was made during these observations.
