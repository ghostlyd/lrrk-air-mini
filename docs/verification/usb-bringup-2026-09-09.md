# LiteWing USB-only bring-up — 2026-09-09

## Scope and physical prerequisites

The owner expressly authorized flashing and flight, then confirmed that all
four propellers had been removed with USB unplugged and that the battery was
still absent. USB was reconnected for this session. Authorization is separate
from technical readiness: this session is limited to backup, firmware loading
and disarmed bench observation. It does not establish flight readiness.

The owner's board photographs identify LiteWing V1.2 silkscreen, an
ESP32-S3-WROOM-1 module, MPU6050 and CH340K. The photographs and unique device
identifiers are not included in this public report.

## Bootloader observations

| Check | Observed result |
| --- | --- |
| USB bridge | WCH `1A86:7522`, one matching callout device |
| Chip | ESP32-S3 QFN56 revision v0.2; 40 MHz crystal |
| SPI flash | Manufacturer `20`, device `4017`; 8 MB; quad data lines |
| Secure Boot | Disabled, read-only query |
| Flash encryption | Disabled, read-only query |
| Tool | Installed esptool 4.12.0 in ESP-IDF 5.3.2's Python environment |

No eFuses, security settings or flash-voltage settings were changed. The
esptool RAM stub was used for reading flash. Security-state inspection does
not constitute a security endorsement of the device.

## Recovery gate

A full-flash read at 460800 baud failed with a short data packet: expected
`0x1000` bytes, received `0xffb`. No recovery file was produced and no erase or
write was issued. A full 8 MB read was retried at 115200 baud.

Recovery status: **BYTE-CONSISTENCY VERIFIED**. The retry read exactly
8,388,608 bytes in 737.0 seconds. A subsequent, separate `verify_flash`
command compared the saved image with the device and returned
`verify OK (digest matched)`. File mode was 0600. This cleared the backup gate
before the first write command was issued. The backup's SHA-256 is
`5f0cb43767be0a65bd30f6232972574cee70bd8c4b554955aa38de113eb9aade`.

Recovery files are local only, inside a Git-ignored directory with mode 0700
and a restrictive creation mask. Firmware backups may contain credentials or
private settings. Do not attach the backup, raw dumps or unique identifiers to
GitHub. A digest comparison proves byte consistency, not that a restore has
been exercised.

## Candidate image and layout

The candidate is the real ESP-IDF build from the corrected driver described in
[the PWM verification report](brushed-pwm-driver-2026-09-09.md), merged by
[PR #20](https://github.com/ghostlyd/lrrk-air-mini/pull/20). Its embedded build
metadata predates the merge; the digests below identify the actual files.

| Artifact | Offset | SHA-256 |
| --- | --- | --- |
| Bootloader | `0x0` | `3d2d5b1543a2a27371bbd5521a9b1d9cbb3a4404ce0387cb77f8fa8d3156a11f` |
| Partition table | `0x8000` | `a84ab9b6709ab8803191f08586451681c906dc441870525b44da907f9c142b51` |
| Application | `0x10000` | `27694eae6e58cee9a554aece8965363824873557d5a3abcd28fcbc11d93a83c3` |

Both image integrity checks pass; the bootloader identifies ESP32-S3 and
accepts the observed chip revision. Application size is 354,832 bytes. The
generated flashing parameters are DIO, 80 MHz and a **4 MB logical image
layout** on the detected **8 MB physical flash**. The layout fits; it does not
use or certify the upper 4 MB. No unverified flash-size override is applied.

The partition table contains default NVS at `0x9000` (24 KB), PHY data at
`0xf000` (4 KB), factory application at `0x10000` (1 MB), dedicated settings
at `0x110000` (32 KB), and coredump at `0x118000` (64 KB). Replacing the
partition table changes interpretation of existing data. First boot can
initialize or erase the new settings region. A full backup, not an assumption
of preserved old settings, is the recovery mechanism.

The pinned default arming setting is `Always Disarmed`. Diagnostic telemetry
must not change it, send receiver inputs or send motor commands. The initial
serial diagnostic allows only selected object requests, acknowledgements and
the telemetry handshake. It captures bounded local evidence and does not
claim a physical output measurement from reported actuator values.

## Physical validation

### Flash result

Flashing completed at 115200 baud. Each write reported a verified data hash;
a separate `verify_flash` invocation with all image parameters set to `keep`
then matched the bootloader, partition table and application against the
candidate files above. Erased sectors were limited to `0x0..0x5fff`,
`0x8000..0x8fff`, and `0x10000..0x66fff`. No whole-chip erase was requested.
The old firmware in those sectors was replaced; the verified full-flash backup
is retained for recovery. A full restore has not been attempted.

### UART diagnosis

The first 30-second diagnostic at 115200 baud saw the ROM boot banner but no
decodable telemetry. The application is not fixed at board-init speed:
`Telemetry/updateSettings()` applies the pinned `HwSettings.TelemetrySpeed`
default, **57600 baud**. Reopening the diagnostic at 57600 established the
normal flight-side handshake without changing firmware or settings.

Bootloader access uses 115200 here; application telemetry uses 57600 for this
default configuration. A saved `HwSettings` change could alter application
speed later. Do not infer runtime speed solely from `init_baud` in the board
file.

### Disarmed observations

The final 30-second, 57600-baud capture was 106,053 bytes, SHA-256
`39662bb4cff08a5f724f7b8a3a211823bad2a0bf784c4ed56ea03f919d102af4`.
Raw captures remain local and mode 0600. The pinned upstream parser
resynchronizes around non-frame bytes; these counts are decoded observations,
not a claim of a lossless whole-capture stream or measured control-loop rate.

| Object | Decoded samples | Observation |
| --- | --- | --- |
| FlightStatus | 29 | Every observed state was `Disarmed` |
| ActuatorCommand | 58 | All four motor-command channels were zero in every sample |
| FlightModeSettings | 28 | `Arming=Always Disarmed`; sanity checks enabled |
| AttitudeState | 777 | All angles finite; 775 distinct angle vectors |
| GyroState | 58 | All values finite; 58 distinct vectors |
| AccelState | 58 | All values finite; 58 distinct vectors |
| SystemAlarms | 58 | Receiver and Actuator remained Critical; see limits below |
| SystemStats | 58 | Last heap report 261,732 bytes; reported CPU load 51% |

The last acceleration vector was approximately `[-0.053, 0.718, -9.391] m/s²`,
norm `9.418 m/s²`. These are uncalibrated observations, not an accepted
scale/orientation calibration. No known-level fixture or human axis check was
performed. Changing sensor-state and attitude values demonstrate that the
application is consuming IMU data, not that the complete sensor error/fault
handling gate has passed. `WHO_AM_I` was checked internally by the driver;
its register value was not separately captured in this diagnostic.

An earlier successful-link capture requested `GyroSensor` and `AccelSensor`
and received zero-initialized values. The pinned complementary-filter path
publishes `GyroState` and `AccelState`; its optional raw/temperature publication
requires `PIOS_INCLUDE_RAW_SENSORS`, which this target does not define. Do not
interpret those raw-object zeros as measured motion or temperature. Thermal
calibration support remains incomplete.

The critical Receiver/Actuator alarms were not cleared. No receiver inputs
were sent. A subsequent read-only configuration capture and artifact analysis
identified invalid receiver mappings, disabled mixers and a settings-persistence
linking defect. That evidence supersedes the initial missing-desired-update
hypothesis; see [the configuration diagnosis](settings-persistence-2026-09-09.md).
This is not a validated human-control/failsafe test. BootFault reported
Uninitialised, not an explicit OK. Telemetry and Attitude reported OK in the
last alarm sample. No claim is made that all alarms or all physical gates pass.

The local diagnostic's outbound guard was checked by five test methods,
including rejection of arming/state, receiver, motor and settings writes,
malformed frames, nonzero instances and unlisted requests. The final run sent
only telemetry-handshake frames (`0x20`, constrained to GCSTelemetryStats) and
selected object requests (`0x21`); no settings/control write or motor pulse was
sent. The diagnostic exited and released the serial port. The flashed firmware
was left configured `Always Disarmed`.

Even a successful USB boot cannot establish motor mapping, IMU orientation,
calibration, receiver-loss behavior or electrical shutdown timing. The
watchdog timing limitation in [issue #19](https://github.com/ghostlyd/lrrk-air-mini/issues/19)
remains open. Battery connector pitch, polarity, fit, mass and charger
compatibility also remain unresolved before powered motor tests or flight.
