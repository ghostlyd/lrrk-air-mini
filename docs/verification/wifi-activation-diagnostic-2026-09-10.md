# Wi-Fi activation diagnostic — 2026-09-10

## Source and launcher

PR #74 merged as `080fc8736fb3825117b021e97a2fac8e4ccffe44` after all
25 CI checks succeeded (the optional Mermaid check was skipped). The local
host suite ran 328 tests: 319 passed and 9 optional tests skipped. The installed
host package passed all 18 focused keyboard tests, including Tk.

This is host-source evidence, not proof of a running pilot link or flight.
The installed aircraft application was not reflashed in this diagnostic.

## Observations

- Exactly one expected USB bridge was present; its private identity was not
  published.
- Two bounded 57600-baud status-only collections failed with
  `no valid UAVTalk frame was received`. One private capture contained 110
  bytes, with no UAVTalk synchronization marker.
- Passive 115200-baud observation detected ESP-ROM startup text. A subsequent
  four-second sample contained one boot marker and reported reset reason
  `0x1 (POWERON)` and boot mode `0x9 (SPI_FAST_FLASH_BOOT)`.
- The sampled text did not contain the checked panic, brownout, invalid-header
  or download-wait markers. Their absence does not prove healthy startup.
- A single-open test allowed ten seconds of passive startup grace, followed
  by five seconds of the existing status-only collector. It saw startup bytes
  but no subsequent telemetry response.
- One authorized external-UART hard reset used the installed Espressif
  esptool HardReset sequence: RTS asserted for 100 ms, then deasserted.
  After a three-second grace period, a five-second status-only collection
  again received no valid UAVTalk frame (zero capture bytes).

## Limits and next investigation

### Temporary console diagnostic changes the failure boundary

A separately built bench image enabled the UART console at 115200 and selected
silent panic reboot, with core dumps still disabled. No flight-control policy
was changed. Its application-only write passed esptool hash verification; no
bootloader, partition table, settings or credential write was requested.

The first capture reached `app_main`, printed `board startup failed; modules not
initialized`, and returned from `app_main`. Thus the current evidence does not
support the earlier hypothesis of failure inside credential-enabled Wi-Fi
initialization: startup stops before modules and Wi-Fi are launched.

A second diagnostic added a source-line marker to the existing board fault
handler. All five board-startup tests passed; build and persistence-link checks
passed. Its application SHA-256 is
`fd0f07f92fec80c0db44943397642e9a6df7ae366e722766519ca630f94a0c7a`.
The application-only write passed hash verification. The private boot capture
reported line 393 of `target/firmware/pios_board.c` at source commit `c1410f3`:
the failure return from `PIOS_LiteWing_Board_Init()`.

That adapter has three failure stages: brushed PWM initialization, I2C
initialization, and MPU6050 initialization. The exact failed stage is not yet
known. The temporary console image remains installed and is not flight-qualified;
console text can interfere with binary telemetry. The original verified image
is retained for recovery. No arming or motor-output command was issued.

Subsequent return-code diagnostics narrowed this further. Adapter result `-3`
confirmed that PWM and I2C adapter initialization succeeded but MPU6050
initialization failed. The MPU6050 routine then reported `-2`: failure in the
address probe or `configure_sensor()`, before queue allocation, registration,
or task creation. Probe failure versus register configuration failure remains
unresolved; this does not yet prove a defective physical sensor.

The latest installed diagnostic is built from `1ff5726`, SHA-256
`49552d1fd53c9758fac26dcdcdafbdc18e58f74f873885f2cede3bc489df30c6`.
Its application-only write passed esptool hash verification. The two MPU6050
contract tests and firmware/persistence-link checks passed before this flash;
the five board-startup tests passed for the preceding adapter-code diagnostic.
Raw boot captures remain private. No initialization failure was bypassed.

The expanded diagnostic at source `e9c96a9`, application SHA-256
`9c7e4731d7785739d27e31141175426a95f98ced5cb329d406713e46b6ca7181`,
reported `MPU address probe=0`. Identity/register configuration was not reached.
The application-only write passed hash verification and remains installed.
The configured sensor address is `0x68`, SDA GPIO11 and SCL GPIO10; these do not
overlap the configured motor pins. The pinned probe returns false for an invalid
bus handle or any unsuccessful SDK address probe, so this boolean alone does
not distinguish a NACK, timeout, power issue or physical sensor fault.

Next physical diagnostic: a complete USB power removal/reconnection with any
battery disconnected and propellers removed. An MCU reset is not equivalent to
removing power from the sensor. No automatic sensor-address changes or health
check bypasses were implemented.

### Follow-up identity and persistence checks

The installed esptool 4.12.0 `verify_flash` command exited successfully for the
application at `0x10000`, against the retained 873440-byte image with SHA-256
`bc5af53b2f534a3c17774aae35f3af30d26f574517a85d5f92f14f67bfc7da3f`.
The local image hash was checked before invoking verification. This esptool
implementation compares the flash MD5 with the input-image MD5 and raises a
fatal error on mismatch. This is application-content verification, not proof
that application startup completed. The command resets through the bootloader
and back to application boot; it does not write flash. A subsequent five-second
USB collection still found no valid UAVTalk frame.

A separate read of the 32768-byte settings partition at `0x110000` matched the
same region in the private preflash backup byte-for-byte. Current settings
therefore do not differ from that backup. No settings were restored or erased.

The expected SSID was absent from macOS's Wi-Fi inventory. Inventory absence is
not definitive evidence of an inactive AP: scan visibility and OS permissions
were not independently qualified. No network association was attempted and no
SSID, password, key, transaction ID or raw inventory was published.

The immediate unresolved issue is hardware-adapter startup/USB telemetry, not a
confirmed wireless authentication failure. No AP association or live wireless
telemetry was established. The reset reason alone cannot establish why startup
does not reach a responsive telemetry service. Serial-opening line transients
remain a possible confounder.

No credentials were resubmitted. No flash, saved-settings, arming or motor-output
commands were issued. Raw UART captures remain private and outside Git.

### Cold power-cycle follow-up

After the operator confirmed USB power removal/reconnection, a reset-neutral
POSIX descriptor was used without modem-control ioctls, input flushing, reset,
flash, credential submission, settings changes or motor commands. Passive
115200-baud capture was followed by bounded 57600-baud status-only UAVTalk
handshake/read requests on the same descriptor.

Live telemetry succeeded: FlightStatus was disarmed and all four mapped motor
outputs were zero. Three attitude samples changed during collection. System
alarms still reported Receiver:Warning and several Uninitialised services,
including Sensors and I2C; this is not an all-clear startup result. The decoder
also flagged unused ActuatorCommand channels 5 through 12 at 1000, separately
from the four mapped motor outputs. No fresh sensor-identity response was
collected. The status capture contained 822 bytes, with 111 initial bytes
discarded by the existing bounded synchronizer before valid frames. Captures
remain private and outside Git.

This supersedes the earlier assertion that the board currently cannot reach
telemetry. Recovery after full power removal is evidence of a state-dependent
failure, not proof of its root cause or reliable warm-reset recovery. The same
temporary diagnostic application remains installed. AP activation, wireless
telemetry, normal-console image qualification and flight remain unverified.

A fresh macOS Wi-Fi inventory after this recovery did not produce an exact
configured-SSID match. Subsequent inspection established that 11 of its 13
name fields were redacted, including network inventory entries. Consequently,
this comparison cannot establish AP presence or absence; the earlier negative
SSID comparisons above must not be used as evidence that the radio failed.
No association or credential submission was attempted.

The native System Settings Wi-Fi panel then displayed a secured network whose
SSID matched the saved private credential bundle exactly, with three signal
bars. This establishes that the configured network is visible to the host;
SSID visibility alone does not authenticate the board or establish a working
command link. The host remained on its existing network. Secure association
and authenticated wireless telemetry are the next checks. The SSID and nearby
network inventory are intentionally omitted from this public record.

Next: qualify the normal-console image and investigate reset-dependent MPU6050
startup behavior before claiming a permanent fix. Do not claim an Armed state,
a working STOP path, or flight readiness from these observations.
