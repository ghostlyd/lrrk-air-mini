# Wi-Fi runtime integration

Approved scope remains the full drone-hosted pilot link and host-side advisory
telemetry, not only protocol libraries. Base: merged PR #61 (`f941d4c`).

## Credential load boundary

Implemented the first runtime dependency: a bounded configuration decoder and
NVS loader. The loader initializes the existing `nvs` partition, opens namespace
`lw_pilot` read-only, and reads key `config` once into a fixed 136-byte buffer.
It never erases a partition, writes flight settings, starts radio, or provisions
credentials. Failed loads clear output. Temporary credential bytes are wiped
through volatile stores; callers must clear their returned configuration when
finished. This does not promise removal of all compiler/driver copies.

The atomic provisioning unit is a single blob, not separate password/key values:

| Byte offset | Content |
| --- | --- |
| 0 | Four bytes `LWCF` |
| 4 | Version 1 |
| 5 | SSID length, 1–32 |
| 6 | AP password length, 16–63 |
| 7 | Reserved zero |
| 8 | Independent 32-byte application root key |
| 40 | SSID, 32-byte padded field |
| 72 | Password, 64-byte padded field |

Text is printable ASCII; unused field bytes must be zero. All-zero root keys
are rejected. The parser cannot prove entropy, independence, uniqueness, or that
an SSID contains no identifying data. The provisioning workflow must generate
independent CSPRNG credentials and a non-identifying SSID. Fixture constants are
test data only. No storage encryption, eFuse or secure-boot changes are claimed.
Existing partition offsets and the separate flight `settings` partition remain
unchanged. ESP-IDF 5.3.2 local NVS headers supplied the read-only API contract.

TDD: decoder and loader fixtures each failed against a minimal stub before
implementation. Fatal ASan/UBSan tests now pass valid/boundary inputs, malformed
lengths/header/padding/text, zero key, null input/output, output clearing, NVS
initialization/open/read errors, short data and malformed stored data. The
loader fixture replaces flash APIs only; it supplies no erase/write/commit/radio
symbols. Two new test methods and eight existing flashfs methods pass.

## Remaining integration sequence

1. Implement ESP-IDF AP lifecycle with explicit WPA2-or-stronger settings, RAM
   Wi-Fi storage, bounded socket and setup error cleanup. Missing configuration
   must return without affecting USB. Do not wire startup before this is tested.
2. One owning task serializes controller calls, authenticated peer binding,
   bounded ingress and challenge/expiry ticks. AP disconnect/send/socket/task
   failures retire input; retired ownership is not automatically released.
3. Wire startup only after flight settings initialization is complete; verify
   local settings writers cannot race admission, in addition to the UART guard.
4. Add disarmed USB provisioning/rotation and host operator input selection.
   Credentials must never enter source, logs, AI tools, or public captures.
5. Integrate separately authenticated bounded telemetry export and host advisory
   ingestion. Exercise loss, jitter, overload, and recovery end to end.
6. Build and review; then qualify radio timing, receiver-to-motor failsafe latency
   and USB recovery on a freshly confirmed props-off setup. Flight acceptance
   still requires physical configuration and a qualified flight power source.

This increment is not called from startup yet. It is not evidence of a working
AP, installed firmware, motor safety, or flight readiness.

## Verified checkpoint

At `77dd2e9`, the full local port suite passed: 373 run, 361 passed, 12 skipped.
The pinned ESP-IDF build passed with persistence-link verification and a
0x5f900-byte image. Uncalled loader functions may be linker-discarded; this build
does not prove runtime reachability. Review accepted the credential boundary
with no Critical/Important findings. Explicit tests for oversized stored blobs,
missing config key, and new-version initialization failure remain coverage gaps.

Startup inspection also established a required integration correction: pinned
`flight/modules/System/systemmod.c` dequeues ObjectPersistence events and can
call `UAVObjLoad`/`UAVObjLoadSettings` while disarmed. An event accepted before
the UART admission guard could execute afterward. Before admission is wired,
serialize this consumer-side persistence operation against wireless reservation;
blocking only new UART writes does not close the race. Board boot settings
setters are in target `firmware/pios_board.c`, before module startup, but the
System queue is a continuing writer and needs its own exclusion test.
