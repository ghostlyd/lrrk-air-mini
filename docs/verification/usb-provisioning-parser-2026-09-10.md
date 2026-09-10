# USB provisioning parser integration

Production revision: `01ea9a9`, draft PR #65. Later changes in this slice add
test-only Python/C frame interoperability.

The hash-checked UAVTalk build copy now intercepts only the two reserved
maintenance IDs after CRC completion. Submission requires untimestamped
OBJ_ACK, instance zero, a 152-byte payload and declared size 162. Status requires
untimestamped OBJ_REQ, instance zero, no payload and declared size 10. The
submission call only copies/queues through the existing worker API; no NVS work
or cooperative-shutdown wait runs under the parser connection lock.

Runtime lookup of either reserved ID as a registered UAVObject disables both
maintenance routes. Neither route falls back to normal unpack/pack. Replies
contain only ACK/NACK or the 24-byte nonsecret status. Generic relay rejects both
reserved IDs. Handled requests and parser errors wipe the owned receive buffer;
reset from a completed/error state also clears it. An already handled parsed
request cannot be delivered twice without parsing a new frame.

## Verified

- All 162 possible two-chunk splits of the 163-byte submission passed through
  the actual adapted C parser. Tests check exact queue bytes, nonsecret ACK,
  pending rejection on replay, no ordinary-object unpack, and receive-buffer
  clearing.
- Status, wrong instance/type/length, malformed LWCF, runtime collision, bad CRC
  and relay-rejection cases passed. The queue and status storage are test
  doubles; the actual parser, receiver and LWCF decoder are compiled.
- Fragment testing exposed a pinned upstream TYPE-state out-of-chunk read when
  SYNC consumed the last byte. The generated copy now waits for TYPE input;
  upstream source files were not modified.
- Python-generated submission bytes are consumed by the C parser; Python checks
  the resulting C ACK and C status frame. Twelve parser test groups pass,
  including pre-existing telemetry, packet-age and battery-serialization cases.
- ESP-IDF 5.3.2 build at `01ea9a9` passed; persistence-link verification passed.
  Image `0xd44a0`, 17% free in the unchanged application partition. Existing
  CMake deprecation warning remains.

## Still not activated or fully integrated

The worker startup function is not called yet, so the current firmware route
cannot accept a credential transaction for storage. No firmware was flashed.
The integration still needs abandoned-partial-frame lifetime handling, wiping
the separate TelemetryRx UART chunk buffer, build-time reserved-ID collision
validation, startup tests, and the host's durable private-bundle/serial workflow.
An incomplete frame must retain bytes while being assembled; this change does
not claim immediate wiping of an abandoned connection or SDK UART ring copies.

No board access, real credential generation, radio activation, arming or motor
commands occurred. Build and synthetic framing evidence do not establish flight
readiness or on-device provisioning success.

Follow-up review accepted `393cd3c..01ea9a9` without blocking findings. Its test
gaps were addressed: the collision fixture now uses a matching payload size,
and each reserved ID independently disables submission and status. Failed and
short output writes preserve the accepted mailbox, wipe parser-owned input,
increment the transmit-error count, and permit subsequent status and ordinary
telemetry requests. The rejection/status group now covers 13 cases; the full
parser suite remains 12 passing test groups, including 162 frame splits and
Python/C envelope interoperability.

## Build-time schema reservation check — `f196698`

The target now runs `verify_usb_ids.py` against all generated UAVObject headers
before adapting/compiling the parser. It checks literal 32-bit data IDs and the
pinned manager's adjacent metadata IDs. Reserved IDs, missing/unrecognized
definitions, and empty input fail configuration. Runtime collision rejection
remains independent. The normal CMake pass tracks header changes and added or
removed headers; ESP-IDF's requirements script-mode pass uses a plain glob
because CMake prohibits CONFIGURE_DEPENDS in script mode.

Four test groups passed, including both reserved data IDs, both possible
metadata collisions, decimal/hex representations, malformed definitions and
collisions in a later header. The actual generated schema passed with 115
objects. An initial real target configure exposed the script-mode incompatibility;
the conditional-glob fix was followed by a successful ESP-IDF 5.3.2 build at
`f196698`, with USB_ID_RESERVATIONS=PASS in both passes and a passing persistence
link check. Image size remains `0xd44a0` with 17% partition headroom.

This completes the build-time collision check, not the remaining partial-buffer,
UART-buffer, startup, or private host-bundle integration. No board operations
were performed.

Independent source review accepted the conditional-glob fix at `f196698` with
no new issue; the successful target rebuild supplies its requested build check.
