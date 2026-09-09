# LiteWing GCS receiver freshness — 2026-09-09

## Scope and diagnosis

Addresses the source correction in [issue #23](https://github.com/ghostlyd/lrrk-air-mini/issues/23),
starting at `6dd8612c08793e0cb374cafdf77ec33104679a96`. The pinned NinjaPilot
`ac77304a58de6c8bd552f94668b46903adb71cb2` and ESP32 reference
`7233c97f844c0377930bcdf22998e289638b64c6` remain unchanged.

The shared `pios_gcsrcvr.c` only registers its stale-input supervisor with
`PIOS_INCLUDE_RTC`, absent on this target. Its read method returns cached
channels without consulting time. Generated GCSReceiver callbacks subscribe to
all update/logging events; they are delivered through an asynchronous event
queue and read the latest object value, not necessarily the triggering packet.
Starting a timer in that callback would therefore not establish packet age.

Native tests compiled the actual pinned driver without RTC support. The
startup/no-input case passed; twelve tests failed, including returning 1500
instead of timeout after the 100 ms boundary and after long repeated reads.
The old driver also ignored device identity. No control input was sent to the
physical board to reproduce this defect.

## Target correction

The target replaces the shared GCS receiver and adapts the pinned UAVTalk
parser in the build directory. It uses the
ESP32 64-bit monotonic microsecond clock and a small critical section around
cached channels, timestamp and validity. It allocates no task or heap memory.

- The parser records local microsecond time on successful packet completion,
  after length/CRC validation and before its state becomes COMPLETE. The time
  is stored with that connection's parsed packet and passed through
  `receiveObject` into `PIOS_LiteWing_GCSReceiver_Unpack`, before any publication.
- Only successful unpacking of GCSReceiver instance zero through this received
  packet path supplies input. The adapter copies the packet, delegates normal
  object storage, and returns the original result. Timestamp capture is before
  connection-lock and post-parse object-lookup waits. Delayed delivery of an
  already parsed packet cannot receive a younger timestamp.
- `prepare_uavtalk.py` checks exact source hashes and replacement anchors before
  generating the target-only source/header pair. Original GPL notices remain;
  external trees and the UAVObject manager are not edited or renamed. A changed
  input fails configuration rather than silently selecting an unadapted parser.
- Queued callbacks, setters, manual/periodic/logging notifications and unrelated
  objects cannot refresh the cache. Identical channel values in a new packet
  can refresh it. An older or equal-timestamp completion cannot overwrite a
  newer accepted packet.
- Every consumer read returns timeout at age **100 ms or greater**. A negative
  age also invalidates input. Recovery requires a new packet whose timestamp
  exceeds the previous accepted timestamp; following a backward clock jump,
  this intentionally fails closed until the clock catches up.
  Expiry requires neither another packet nor an RTC tick. Startup has no valid
  input. Invalid handles and channel numbers use existing PiOS error codes.
- The 64-bit clock avoids both 32-bit microsecond and millisecond rollover.
  Time is local protocol acceptance time, not authenticated sender time or a
  claim about UART receive-buffer residence time. Replay prevention and remote
  sender identity are not provided by this unencrypted UAVTalk link.

The 100 ms limit is a conservative target input-age policy, not a measured
motor-stop deadline. The Receiver module samples on a nominal 20 ms loop and
requires more than ten invalid observations before changing Connected. Its
downstream failsafe/controller scheduling and electrical output timing remain
distinct; [issue #19](https://github.com/ghostlyd/lrrk-air-mini/issues/19) is not
resolved by this change. There is no new flight mode, arming setting or AI
command path. The user's arming authorization is separate from readiness;
Always Disarmed remains unchanged for this correction.

## Verification and remaining gates

Fourteen native cases exercise the production target source with only clock,
object storage and OS critical-section bindings replaced. Coverage includes
startup, timeout boundary, repeated reads, non-input events, delayed unpacking,
reconnect, identical new packets, 32-bit boundaries, backward time, storage
failure, unrelated objects/instances, out-of-order completion and invalid IDs.
Another barrier-controlled two-task test checks readers while an older unpack
is pending, newer publication, expiry, and delayed older completion after expiry.
Seven integration tests compile the actual adapted pinned UAVTalk parser with
the target driver: OBJ/OBJ_ACK, 150 ms connection/lookup-lock waits, a pause
between parse and receive, repeated parsed-packet delivery, invalid CRC/length,
failed storage, and rejection of changed source without overwriting output.

Independent review found the original wrapper timestamp was too late: it
followed connection-lock and object-lookup waits. A late-timestamp mutation of
the actual parser path fails four integration tests; packet-completion time
passes all of them. This corrected design removes the initial manager-symbol
rename entirely. The source-gate CI job supplies the pinned checkout and runs
the parser integration tests; host-only runs without that checkout explicitly
skip that integration class rather than claiming it ran.
The first real target compile found an explicit header dependency that the
initial fixture had hidden; both target include and fixture dependency were
corrected. Host tests alone are not target-build or flight proof.

The revised ESP-IDF 5.3.2 ESP32-S3 build passed. The full local run passed
**82 assistant and 92 port tests**, with no skips: the pinned parser source,
actual ELF and generated build graph were explicitly supplied. Source-gate CI
also executes the parser integration rather than relying on the optional skip.
The build retains upstream warnings; it is not described as warning-free.

Focused independent re-review found no remaining critical, important or minor
findings. It inspected the actual ELF timestamp ordering and verified selection
of the generated parser. The reviewed ELF SHA-256 is
`f03e001ef7405460320956ece9dd9c8919c02e9b06977e6f819087cb7929826f`.
This is a development build; an exact clean-commit candidate must be rebuilt
and checked before any further authorized flash.

The next physical acceptance step is a props-off, battery-absent,
Always Disarmed receiver-loss test. No such physical test has yet been completed
for this change, and this report does not close the physical acceptance of #23.
The verified currently flashed persistence candidate remains distinct from
this source change. No motor command, arming or flight is established here.
