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

## Queued-load exclusion

`04c065a` adds a receiver-locked in-flight guard around the real `UAVObjLoad`
execution, not its earlier queue submission. Admission and reservation refuse
while loads run; loads refuse while admission or wireless ownership exists.
Boot loads remain permitted before receiver initialization. Storage work runs
outside the spinlock and original failure codes propagate. Bulk settings and
metaobject loads call this same wrapper per object; this does not make an entire
bulk operation atomic. It prevents mutation from an individual load overlapping
admission/ownership, including synchronous callbacks, not deferred callbacks.

The new ASan/UBSan regression failed before the guard and then passed boot,
admission/ownership rejection, in-load claim attempts, failure cleanup, and
explicit-release recovery. Receiver suite: 21 methods, 20 passed, one optional
protocol skip. Actual target compilation caught missing PiOS prerequisites in
the wrapper; `9d9b547` fixes include order and passes the focused regression and
ESP-IDF build. Image size is 0x5f9b0; persistence-link check passes. Disassembly
shows `UAVObjLoad` calling `PIOS_LiteWing_GCSReceiver_SettingsLoad` with the
renamed upstream implementation as its callback. Review accepted this scope.

Before runtime admission is wired, still audit direct setters and deferred
callbacks for settings mutations. No AP/socket task or live board operation is
introduced by this change.

## AP implementation build checkpoint

`9f810df` adds the actual ESP-IDF AP lifecycle adapter and focused SDK-boundary
tests. The full pinned ESP-IDF build passed, including the persistence-link
check. The image remains 0x5f9b0 because startup does not reference this adapter
yet; linker garbage collection is not evidence of AP runtime reachability.
No radio was activated. AP review and removal of machine-local test dependencies
are in progress. The authenticated UDP owning task, startup hook, provisioning,
operator input and telemetry integration still remain.

## Integrated command startup checkpoint

`054853d` implements the actual AP-bound UDP owning task; `3b97fa8` wires its
launch into generated System startup after checked boot readiness and all three
System queue/callback connections succeed. Optional task-creation failure does
not stop System/USB. The startup caller passed 24 System/scheduler tests and
scoped review. Source startup is now wired; earlier uncalled-dependency notes
above describe historical increments, not the current source state.

Integrated build at `1080561` passes with application size 0xd7740 and 16% of the
unchanged 1 MiB application partition free. Persistence-link verification passes.
The linked command task, AP start and real controller symbols are present.
This is compile/link evidence only; no flashing or radio activation occurred.

The broad regression completed 379 methods (367 passed, 12 skipped) while the
final cleanup correction was being prepared; do not attribute that whole run to
the final commit. At `1080561`, fresh six-method Wi-Fi tests passed, including
30 command scenarios and two C/Python loopback cases. Review confirmed the fix
keeps the task/context until a rollback-held admission guard can be released,
with bounded cleanup sleeps; retired wireless ownership is still not released.

CI now supplies both pinned SDK headers and pinned mbedTLS to the non-skipping
Wi-Fi job. Hosted verification of the integrated revision and whole-branch
review remain pending. Provisioning/rotation, operator input, telemetry-only AI
integration, real radio scheduling and physical flight qualification remain
required. Missing credentials still leave Wi-Fi disabled at runtime.
