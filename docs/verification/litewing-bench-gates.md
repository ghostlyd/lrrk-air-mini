# LiteWing bench gates

These gates are evidence requirements, not an authorization to power or fly
the aircraft. Keep the battery disconnected and propellers removed until the
operator explicitly opens the relevant electrical test. The existing
ESP-Drone firmware remains the recovery image.

This is the acceptance checklist, not a record that every item has passed.
See [the USB-only session report](usb-bringup-2026-09-09.md) for the verified
backup/flash, telemetry observations and remaining limitations. See the later
[software-arm and bounded nonzero-command report](armed-nonzero-motor-proof-2026-09-09.md)
for the attained command-path gate and its narrower claim boundary. The current
image, boot-readiness, mapping and reset-behavior results are recorded in the
[current flight-readiness report](current-image-flight-readiness-2026-09-09.md).

## Attained software arm/output gate

- [x] Propellers removed, board contained, battery absent, and USB-C treated as
  a live motor-power source.
- [x] Exact installed application and pinned UAVObject source verified before
  the one-shot transaction.
- [x] `FlightStatus=Armed` observed with six bounded nonzero motor-command
  samples; peak channels `[128, 0, 0, 118]` on the `0..1000` scale.
- [x] Eleven later zero-command samples observed while Armed; the final sample
  also had the receiver timed out and disconnected.
- [x] No persistence write, post-arm reset, direct `ActuatorCommand` write,
  flash, erase, or restore-to-`Always Disarmed` operation was sent.
- [ ] Electrical PWM duty/cutoff timing, physical rotation in this transaction,
  motor-corner mapping, and flight readiness remain unverified.

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
- [ ] A sequential visual spin-direction/assembled-continuity observation is
  still required before propellers are fitted; telemetry cannot observe shaft direction.

## Flight gate

- [ ] The current application source commit is merged and its exact installed
  identity is attached to that merged history.
- [ ] Battery, propeller, airframe, open-area, and emergency-disarm plan are
  explicitly documented.
- [ ] The operator, not the AI assistant, has final authority for arming and
  flight.
