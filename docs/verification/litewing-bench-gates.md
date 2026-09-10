# LiteWing bench gates

These gates are evidence requirements, not an authorization to power or fly
the aircraft. Keep the battery disconnected and propellers removed until the
operator explicitly opens the relevant electrical test. The existing
ESP-Drone firmware remains the recovery image.

This is the acceptance checklist, not a record that every item has passed.
See [the USB-only session report](usb-bringup-2026-09-09.md) for the verified
backup/flash, telemetry observations and remaining limitations. See the later
[software-arm and bounded nonzero-command report](armed-nonzero-motor-proof-2026-09-09.md)
for the attained command-path gate and its narrower claim boundary.

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

- [ ] `SOURCE_MANIFEST.json` validates and every source/patch hash matches.
- [ ] POSIX/Gazebo simulation evidence is attached to the exact source commit;
  the maintained command is `ports/ninjapilot-litewing/simulate.sh` and a
  missing Qt/qmake dependency is recorded as unavailable, not as a pass.
- [ ] ESP-IDF version, target, build output, and compiler version are recorded.
- [ ] The target adapter is linked with the pinned reference I2C backend, with
  the reference ICM-20602 and servo-pulse sources excluded.
- [ ] No `idf.py flash`, `esptool`, arming, or motor command occurred during the
  source/build gate.

## Prop-off electrical checks

- [ ] USB identity is recorded as the expected CH340K/WCH bridge, currently
  observed on macOS as `/dev/cu.wchusbserial410` when connected.
- [ ] Physical board markings and fitted components are matched to the
  candidate design. Owner photos show V1.2 silkscreen, also present in the
  V2.6.C directory's PCB source; matching labels/layout are not net-by-net proof.
- [ ] MPU6050 I2C0 wiring is verified: SDA GPIO11, SCL GPIO10, interrupt GPIO12.
- [ ] `WHO_AM_I` is read and matches the expected MPU6050 identity.
- [ ] Watchdog and boot fault behavior are observed without enabling outputs.
- [ ] Initialization and disarm write zero to all four motor channels.
- [ ] Sensor fault, stale-link, transport-loss, and shutdown paths keep all four
  channels at zero.

## Human orientation gate

- [ ] A human verifies the IMU frame against the physical airframe.
- [ ] A human verifies motor corner order and documents the mapping; the
  schematic alone is not accepted as proof.
- [ ] No propeller is installed during orientation or channel-order checks.

## Flight gate

- [ ] All preceding evidence is attached to the exact merged source state.
- [ ] Battery, propeller, airframe, open-area, and emergency-disarm plan are
  explicitly documented.
- [ ] The operator, not the AI assistant, has final authority for arming and
  flight.
