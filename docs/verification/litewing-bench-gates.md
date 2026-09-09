# LiteWing bench gates

These gates are evidence requirements, not an authorization to power or fly
the aircraft. Keep the battery disconnected and propellers removed until the
operator explicitly opens the relevant electrical test. The existing
ESP-Drone firmware remains the recovery image.

## Source and build

- [ ] `SOURCE_MANIFEST.json` validates and every source/patch hash matches.
- [ ] POSIX/Gazebo simulation evidence is attached to the exact source commit;
  the maintained command is `ports/ninjapilot-litewing/simulate.sh` and a
  missing Qt/qmake dependency is recorded as unavailable, not as a pass.
- [ ] ESP-IDF version, target, build output, and compiler version are recorded.
- [ ] No `idf.py flash`, `esptool`, arming, or motor command occurred during the
  source/build gate.

## Prop-off electrical checks

- [ ] USB identity is recorded as the expected CH340K/WCH bridge, currently
  observed on macOS as `/dev/cu.wchusbserial410` when connected.
- [ ] The board revision is physically identified as LiteWing V2.6.C or the
  manifest is updated before testing.
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
