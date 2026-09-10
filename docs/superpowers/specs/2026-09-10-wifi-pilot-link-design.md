# LiteWing authenticated wireless pilot link

## Status and scope

The operator approved the direction on 2026-09-10: drone-hosted Wi-Fi,
authenticated commands, replay protection, link-loss failsafe, and USB recovery
retained. This written design is proposed for review before implementation.
It extends the approved NinjaPilot port, not the stock ESP-Drone/CRTP client.

Deliver a working operator-controlled wireless link and telemetry adapter, not
only a read-only exporter. The OpenAI assistant remains host-side and advisory:
it neither owns pilot credentials nor generates the real-time control stream.
No firmware flash, radio activation, credential provisioning, or motor operation
is performed by source/build tests.

## Approach and alternatives

Use a bounded datagram protocol over a private drone-hosted access point, with
application authentication independent of the network password. Keep USB UART
telemetry/recovery operating. Reusing the reference raw UAVTalk socket would
expose unrestricted object writes and replace UART, so it is not selected.
TLS/TCP would provide a standard secure channel but still needs command-age
checks and careful handling of ordered retransmissions. The selected datagram
protocol requires independent protocol review and shared C/Python test vectors;
it is not claimed to be a standardized secure transport.

## Components and trust boundary

- `wifi_link` owns ESP-IDF AP lifecycle, bounded sockets, and fixed-size queues.
- `pilot_protocol` validates framing, HMAC, session, sequence, and freshness.
- `pilot_owner` arbitrates UART and wireless receiver ingress explicitly.
- The existing receiver and flight tasks retain stabilization and motor control.
- A separate host pilot client reads operator inputs and sends bounded controls.
- A read-only host telemetry adapter feeds the existing AI runtime. It cannot
  import or acquire the pilot command credential through its telemetry API.

Wireless ingress is not passed to general `UAVObjUnpack`. Only normalized pilot
channels and a stop/release operation are accepted. Settings, persistence,
firmware updates, gains, raw actuator values, and arbitrary UAVObject writes
remain outside the wireless protocol. Arming uses the existing pilot-input
policy; authentication alone never arms the aircraft.

## Provisioning and network lifecycle

Provision a unique AP password and a separate random 256-bit application key
through a local USB maintenance workflow while disarmed. No built-in key, SSID
derived from private hardware identifiers, console secret output, or checked-in
credential is permitted. Missing or invalid configuration leaves Wi-Fi disabled
without disabling USB recovery. Configuration failures do not erase NVS or
flight settings. Credential rotation invalidates all sessions.

The first version supports one pilot and one fixed bounded telemetry stream.
Use WPA2-Personal or stronger supported AP configuration; application HMAC
provides authenticity, not payload encryption. Network encryption is not a
claim of end-to-end confidentiality or resistance to physical key extraction.
Secrets are kept outside firmware source and public artifacts. Board storage
protection and any use of encrypted NVS must be stated explicitly in deployment
documentation; no eFuse or secure-boot changes are implicit in this feature.

## Authentication, replay, and command age

Use the IDF-provided cryptographic implementation for HMAC-SHA-256, and Python
standard-library HMAC for host vectors. Authenticate the complete canonical
binary envelope: protocol version, direction, message type, session identity,
sequence, challenge identity, payload length, and payload. Reject extra bytes,
unknown versions/types, malformed lengths, and invalid tags before state changes.
Use constant-time tag comparison. Never implement a new cryptographic primitive.

Opening a session requires mutual possession proof bound to fresh board and
host random nonces. Derive direction-specific session keys using a reviewed
standard KDF; the implementation plan must specify exact labels and wire bytes
before coding. Session creation is allowed only while disarmed with no active
pilot owner. Reboot, stop, expiry, or rotation retires the session. Session and
challenge randomness must come from the platform cryptographic random source,
not counters or clocks. Invalid traffic cannot replace or renew an owner.

Within a session, each accepted command has a strictly increasing 64-bit
sequence; wrapping requires a new session. Duplicate or reordered commands do
not refresh receiver freshness. Sequence checking alone is insufficient for
delay protection, so the board emits authenticated random challenges every
20 ms and retains a fixed ring of four issuance records. A command must echo
a challenge no older than 75 ms on the board's monotonic clock. These are
initial engineering limits to verify under load, not measured radio guarantees.

Publish the challenge's issuance time as the conservative input-age origin,
not socket-read or lock-release time. Reject a command whose challenge origin
would regress the accepted origin; equal origins may carry increasing sequence
values without extending freshness. The existing 100 ms receiver timeout then
bounds input validity from that origin. A delayed command cannot receive a new
100 ms lease merely by arriving late. All authentication, sequence, ownership,
and publication decisions must form one serialized transaction.

Challenges are issued only for an authenticated session and cannot be renewed
by unauthenticated traffic. Rate-limit setup/authentication work, cap datagrams
at a fixed schema-derived maximum, and reject truncation. Receive timestamps
are recorded before task/lock delays. Host input must be sampled after receipt
of its challenge; this is an operator-client requirement, not something a board
can prove against a malicious holder of the application key.

## Control ownership and stop behavior

Only one transport may supply receiver input. Claiming wireless ownership
requires disarmed state and neutral controls. While owned wirelessly, UART
telemetry requests remain available but UART receiver/settings/persistence
writes are rejected. There is no automatic transport takeover in flight.
After a stop or loss, another claim requires observed Disarmed and neutral
input; reconnection does not automatically re-arm or resume old commands.

An authenticated STOP retires the session and invalidates receiver input.
Socket failure, task failure, AP disconnect, and timeout also invalidate it.
Use the flight stack's failsafe path rather than a network task writing PWM.
The physical motor-zero latency must be measured separately: the 100 ms input
age contract is not itself a motor-cut timing guarantee. Demonstrate STOP and
timeout propagation through the real control tasks and later on the board.
STOP is a motor-stop request, not an autonomous landing command.

USB recovery is preserved through the existing serial/bootloader path. A
deliberate reboot clears wireless ownership and returns to disarmed startup;
recovery never requires a working radio. Do not introduce Always Armed or
Always Disarmed settings, bypass startup alarms, or silently rewrite policy.

## Telemetry and scheduling

Authenticate telemetry with a distinct direction key and sequence space.
Include board monotonic serialization time and session identity; host reception
time must remain distinct. Battery serialization uses the merged sample-age
boundary. Unknown values remain unknown. Only reviewed telemetry objects are
exported; private hardware identifiers and raw debug logs are excluded.

Use separate bounded queues for pilot input and telemetry. Drop obsolete
telemetry instead of blocking control. No allocation, networking, or HMAC runs
inside stabilization or PWM callbacks. Limit receive work per scheduling turn,
and verify Wi-Fi driver task interference, heap/stack usage, and watchdog
behavior under load before calling the link flight-ready. Retain UART even
when AP setup fails. Successful compilation does not qualify scheduling.

## Acceptance and delivery sequence

1. Freeze the exact wire schema, KDF labels, and cross-language vectors; review
   authentication and state transitions independently before deployment.
2. Test the real protocol core: corrupted tags/headers, replay, reordering,
   expiry at boundaries, future/regressing clock, restart, sequence exhaustion,
   malformed/truncated datagrams, peer replacement, and flood work bounds.
3. Test ownership and failsafe with the real receiver/control tasks. Prove
   non-owner writes cannot mutate storage first and be rejected afterward.
4. Implement AP provisioning/lifecycle and host operator client; exercise a
   loopback simulator with loss, jitter, delay, duplicates, and host termination.
5. Feed authenticated telemetry into the existing host analyzer and advisory
   assistant without adding a model-owned command tool or sharing pilot keys.
6. Build the pinned ESP-IDF image and test startup failure injection, disabled
   configuration, USB coexistence, and recovery. Keep compatibility tests green.
7. Conduct separately authorized props-off board tests, including measured
   stop/timeout output latency, long-running scheduling load, and USB recovery.
8. Flight acceptance additionally requires a qualified battery, correct props,
   physical setup checks, and an operator-controlled flight test. No source,
   simulator, or bench result is substituted for that evidence.

## Dependencies and exclusions

Reuse ESP-IDF 5.3.2 Wi-Fi, network interfaces/events, lwIP, NVS, timer, and
cryptographic components; verify the exact enabled configuration during build.
Host remains CPython 3.11–3.14. The operator input-device dependency is selected
in the implementation plan and kept separate from the AI extra. No extra radio,
onboard AI computer, GPS, ToF, or optical flow is required for this attitude/rate
link. Those sensors and autonomous navigation are separate enhancements.
