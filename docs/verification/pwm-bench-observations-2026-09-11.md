# PWM deployment and secured-bench observations

## Installed application

PR #84 merged as `a5521f53259e3326eee4edfbf8fb370a4812917d`.
The application was built from reviewed source
`cc399bca6d8031fca8b93abfd3a9c4a3f95404b3`; its source tree matches the merge.
The application is 877,248 bytes, SHA-256
`46e185505637c0806813414e2a4970de5bf71f366fc3749c5a43882c628dd990`.
It was written only at `0x10000` and read back byte-for-byte. The running
FirmwareIAPObj identity matched the build. A private 8 MiB recovery backup was
taken first. Before/after comparisons preserved bootloader, partition table,
NVS, PHY, settings, and coredump regions. No credentials or settings were reset.

The build retained the existing 2,096-byte FreeRTOS ISR stack configuration.
Successful flashing and boot identity are not flight qualification.

## What the bench observations establish

- The request-only PWM object is available on the installed image. Its zero
  snapshots reported known zero submissions on all four channels, with no
  write or stop errors.
- Normal Yaw Right arming reached Armed. No AlwaysArmed/AlwaysDisarmed change
  or direct actuator-object write was used.
- One 8% throttle step produced requested duties `[461, 592, 0, 0]` and
  successful LEDC submissions `[944, 1212, 0, 0]`. No suppression or peripheral
  error was reported. The host stopped the test at its reactive output limit.
  An 8% throttle input is **not** an 8% per-motor output limit: stabilization
  corrections are mixed into each motor command.
- A later test first matched the attitude command at zero throttle. During its
  throttle-only pulse, a snapshot reported requested duties `[68, 101, 60, 86]`
  and submissions `[139, 207, 123, 176]`, with no errors or suppression. All
  four channels therefore received non-zero peripheral API submissions.
- The operator subsequently observed short pulses from all four motors, but
  did not report complete rotations. This is qualitative physical-response
  evidence, not an RPM, thrust, motor-direction, or sustained-rotation test.
- A subsequent request-only check observed Armed, twelve zero actuator-command
  slots, four known zero PWM submissions, and no peripheral errors. This is a
  time-bounded observation; the normal 30-second arming timeout remains enabled.

Submitted LEDC values use a 0..2047 scale. They represent successful peripheral
API calls, not electrical feedback. Neither the observation getter nor host
telemetry provides an oscilloscope measurement of motor voltage or duty.

## Test and transport findings

The live AttitudeSettings object has ZeroDuringArming=TRUE. The pinned Attitude
module changes accelerometer correction and gyro-bias adaptation during Arming.
The pre-arming attitude is consequently an unsuitable fixed reference for this
bench sequence. The revised private test waits for post-arming zero output,
collects a stable attitude window, and computes the receiver inputs with the
pinned controller's actual deadband and fastPow/expo implementation.

The test also initially sent seven request packets in a burst. In one run,
host input writes remained less than 46 ms apart while receiver observations
intermittently expired. The receiver's 100 ms timeout was not changed. Request
replies and object processing share a UAVTalk connection lock, and UART writes
can block when the transmit ring fills. This is a plausible transport mechanism,
not a directly measured lock-duration diagnosis. After requests were paced and
fresh periodic data was reused, one complete connected-session trace contained
no receiver disconnects. This does not establish long-duration link reliability.

Independent object polling does not preserve the ordering of internal controller
stages. Requiring a PWM telemetry packet to arrive after an actuator-command
packet falsely rejected a run with valid, fresh non-zero observations from both.
Evidence must retain phase boundaries, values, and freshness without treating
telemetry arrival order as an internal execution trace.

## Remaining flight-readiness work

Short pulses still coincide with attitude excursions, including a roughly
2.2-degree reported roll change in the operator-observed four-motor pulse.
The evidence does not yet distinguish fixture compliance, motor vibration,
sensor disturbance, or a controller transient. No PID tuning or safety-alarm
bypass is justified by these observations alone.

### Subsequent ramp comparison

A bounded comparison held the measured attitude command constant and increased
throttle in 1% steps at approximately 40 ms intervals, with an unchanged 8%
ceiling and one-second maximum powered phase. It stopped after transmitting
the 4% step because the reported roll changed by approximately 0.84 degrees.
A following diagnostic snapshot reported requested duties `[0, 1000, 0, 737]`
and successful submissions `[0, 2047, 0, 1509]`, without driver errors or
suppression. The operator reported slight physical vibration.

This rules out the single abrupt 8% throttle step as the sole explanation.
It does **not** establish whether vibration, electrical interference, supply
disturbance, or controller behavior caused the saturation. Further powered
retries were paused. A subsequent request-only check confirmed Armed with all
twelve actuator-command slots and all four known PWM submissions at zero.

The bench limit was reactive telemetry monitoring, not a firmware-enforced
ceiling; the saturation observation demonstrates that distinction materially.
Do not use a low throttle input as a substitute for a per-channel output bound.
Before another motor test, resolve the inertial-data/power investigation and
provide a suitable enforced bound for the intended test.

Next comparisons should isolate throttle slew from attitude-command changes,
retain bounded outputs and stop behavior, and correlate inertial observations
with physical motion. Sustained rotation, corner/direction mapping under the
installed image, battery/power qualification, pilot-link reliability, and
controlled-flight acceptance remain separate incomplete requirements.

Raw serial captures, full configuration records, device identifiers, and flash
backups remain private and outside Git. This report contains selected aggregate
observations only. No flight was attempted or qualified.
