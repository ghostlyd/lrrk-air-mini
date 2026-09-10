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

The immediate unresolved issue is application startup/USB telemetry, not a
confirmed wireless authentication failure. No AP association or live wireless
telemetry was established. The reset reason alone cannot establish why startup
does not reach a responsive telemetry service. Serial-opening line transients
remain a possible confounder.

No credentials were resubmitted. No flash, saved-settings, arming or motor-output
commands were issued. Raw UART captures remain private and outside Git.

Next: inspect the boot/application boundary and the credential-enabled Wi-Fi
startup path; if necessary, verify the installed application against the retained
image before considering a firmware change. Do not claim an Armed state, a
working STOP path, or flight readiness from these observations.
