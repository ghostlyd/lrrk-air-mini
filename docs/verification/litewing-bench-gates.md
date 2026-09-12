# LiteWing bench gates

These gates are evidence requirements, not an authorization to power or fly
the aircraft. Keep the battery disconnected and propellers removed until the
operator explicitly opens the relevant electrical test. The existing
ESP-Drone firmware remains the recovery image.

This is the acceptance checklist, not a record that every item has passed.
The [latest qualification checkpoint](flight-qualification-2026-09-11.md)
records the installed diagnostic image and unresolved gyro transient; earlier
passed items below retain their original, narrower evidence scope.
See [the USB-only session report](usb-bringup-2026-09-09.md) for the verified
backup/flash, telemetry observations and remaining limitations. See the later
[software-arm and bounded nonzero-command report](armed-nonzero-motor-proof-2026-09-09.md)
for the attained command-path gate and its narrower claim boundary. The current
image, boot-readiness, mapping and reset-behavior results are recorded in the
[current flight-readiness report](current-image-flight-readiness-2026-09-09.md).
The persisted normal-arming, fitted-direction, IMU-acceptance and closing-idle
results are consolidated in the
[final flight-configuration report](final-flight-configuration-2026-09-10.md).

## Attained software arm/output gate

- [x] Propellers removed, board contained, battery absent, and USB-C treated as
  a live motor-power source.
- [x] Exact installed application and pinned UAVObject source verified before
  the one-shot transaction.
- [x] Normal `Yaw Right` arming persisted with a completed single-object save
  and survived a deliberate reset.
- [x] `FlightStatus=Armed` observed with four bounded nonzero motor-command
  samples under normal arming; peak channels `[59, 0, 0, 62]` on the `0..1000`
  scale.
- [x] Twelve later zero-command samples observed while Armed; the terminal
  sample also had the receiver timed out and disconnected.
- [x] A later reset-neutral snapshot observed Disarmed state with four zero
  commands and the normal arming policy still loaded; this is consistent with
  the configured timeout but is not represented as a continuous trace.
- [x] No persistence write, direct `ActuatorCommand` write, flash, or erase was
  sent during the normal arm/motor transaction.
- [ ] Direct electrical PWM duty/cutoff timing and battery-powered flight
  readiness remain unverified.

## Source and build

- [x] `SOURCE_MANIFEST.json` validates and every source/patch hash matches.
- [x] POSIX/Gazebo simulation and host evidence is attached to the exact source commit;
  the maintained command is `ports/ninjapilot-litewing/simulate.sh` and a
  missing Qt/qmake dependency is recorded as unavailable, not as a pass.
- [x] ESP-IDF 5.3.2, ESP32-S3 target, build output and application hash are recorded.
- [x] The target adapter is linked with the pinned reference I2C backend, with
  the reference ICM-20602 and servo-pulse sources excluded.
- [x] Source/build verification completed before the separately authorized
  app-only flash and bounded arming transaction.

## Prop-off electrical checks

- [x] USB identity is recorded as the expected CH340K/WCH bridge, currently
  observed on macOS as `/dev/cu.wchusbserial410` when connected.
- [x] Physical board markings and fitted components are matched to the
  candidate design. Owner photos show V1.2 silkscreen, also present in the
  V2.6.C directory's PCB source; matching labels/layout are not net-by-net proof.
- [x] MPU6050 I2C0 wiring is verified: SDA GPIO11, SCL GPIO10, interrupt GPIO12.
- [x] `WHO_AM_I` is read and matches the expected MPU6050 identity.
- [x] Whole-boot readiness waits for a healthy MPU sample and required tasks;
  live telemetry reports `BootFault=OK` on the flashed image.
- [x] Initialization and disarm write zero to all four motor channels.
- [x] Sensor fault, stale-link, transport-loss, and shutdown paths keep all four
  channels at zero.

## Human orientation gate

- [x] Owner-supplied front/back photos, PCB coordinates, fitted package
  orientation and stationary gravity agree on the IMU body transform.
- [x] Owner-supplied photos, connector coordinates, A/B markings and fitted
  wire pairs establish the four documented motor corners and intended rotations.
- [x] No propeller was installed during the current mapping and command checks.
- [x] A user-supplied sequential four-corner recording establishes physical
  fitted direction/continuity: front-right CCW, rear-right CW, rear-left CCW,
  front-left CW. It is preserved as private evidence and is not represented as
  synchronized with the later UART transaction.

## Flight gate

- [x] The current application source commit is merged and its exact installed
  identity is attached to merged history through PR #51 / `dc3345d`.
- [ ] Battery, propeller, airframe, open-area, and emergency-disarm plan are
  explicitly documented.
- [ ] The operator, not the AI assistant, has final authority for arming and
  flight.
