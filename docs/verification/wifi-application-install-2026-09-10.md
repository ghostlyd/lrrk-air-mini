# Wi-Fi application installation — 2026-09-10

## Installed artifact

Clean merged source `fe42ec2b0f2b140a06726ceb9d00a1f18ebf8bb8`
built with the existing pinned ESP-IDF 5.3.2 ESP32-S3 configuration.
Application length: 873440 bytes (`0xd53e0`), with 17% of the 1 MiB
application partition free. SHA-256:
`bc5af53b2f534a3c17774aae35f3af30d26f574517a85d5f92f14f67bfc7da3f`.
Image checksum and validation hash passed; flash/UART core dumps are disabled.
The build retained the upstream mbedTLS CMake compatibility warning.

## Hardware transaction

The owner authorized Wi-Fi deployment and confirmed startup/physical bench
checks. A bounded read-only UART capture immediately before bootloader access
reported disarmed and four zero actuator commands. The collector's outbound
surface contains only telemetry handshake, selected reads and acknowledgements.
This is sampled software state, not electrical motor measurement.

The lower `0x118000` bytes were backed up privately (1146880 bytes, mode 0600)
and independently compared with the board using esptool `verify_flash`.
This is not a new full-physical-flash backup or an exercised restore.
The backed-up partition table matched the built table byte for byte.

Only the application at `0x10000` was written, using esptool 4.12.0 at
115200 baud with flash mode/frequency/size set to keep. No whole-chip erase,
bootloader/partition rewrite, credential provisioning, arming request, receiver
input, motor command or intentional settings write was issued.

A separate read of `0..0x118000` after flashing established:

- Installed application bytes exactly equal the candidate image.
- Bytes `0..0x10000` equal the pre-flash backup, including bootloader,
  partition table, default NVS and PHY storage.
- Saved-settings bytes `0x110000..0x118000` equal the pre-flash backup.

Those byte comparisons precede the reset into the new application. They do not
claim a second post-runtime persistence comparison. After reset, a bounded
read-only UART capture returned valid aggregate telemetry: disarmed and four
zero actuator commands. Both captures and backups remain private outside Git.
The prior application is recoverable from the retained backup; restoration was
not attempted. No always-disarmed policy was restored.

## Remaining acceptance

### Subsequent USB provisioning

The first one-shot alignment query produced no status reply; no credential
submission was enabled at that point. Bounded status-only polling observed
canonical idle status responses. The reviewed host polling correction then
passed live read-only alignment. The previous private pending bundle was
retained, not regenerated.

After observing idle/not-attempted status with a zero transaction, that saved
transaction was submitted once. The firmware reported matching persisted and
finished status (commit/readback plus cleanup), and the private host `.stored`
copy was created successfully. This later authorized provisioning writes
credential NVS; it does not invalidate the earlier pre-provisioning equality
comparison or imply that NVS remains equal after provisioning.

No AP association, reboot durability or application-key probe follows merely
from successful storage. Credentials and transaction identifiers are not
included in this report.

AP association, authenticated wireless telemetry,
physical wireless STOP/link-loss timing and USB recovery qualification remain.
The keyboard launcher and live wireless-to-OpenAI acceptance are not established
by this installation. This report is not flight acceptance.
