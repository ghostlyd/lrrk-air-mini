# Authenticated Wi-Fi command owning task — 2026-09-10

Based on `6b92178`, `codex/wifi-runtime`. This increment adds the actual IDF
task, header, focused fixtures and source registration. No AP edits, startup
hook, CI changes, provisioning, hardware/serial/flashing, radio operation or
push was performed. Main's separate startup edits are excluded from this commit.

## Runtime contract

Trusted `lw_wifi_command_start()` creates one 8192-byte, idle+1 priority IDF
task. Success means task creation only. Creation failure touches no AP and can
be retried; successful creation permanently consumes the launch until reboot,
even if credentials are absent or the task later exits. Main must call only
after checked boot readiness and successful System queue/callback connections.
Optional launch/config failure does not stop System/USB. No keys leave the task.

The task initializes the real controller, starts AP/load-root, waits at most
two seconds for the actual `WIFI_AP_DEF` interface to be up, queries/validates
its IPv4 address and contiguous netmask, and binds a nonblocking IPv4 UDP socket
to that exact address. `getsockname` verifies family, address and port. No ANY
binding, default IP or inferred interface address. Default command port is
**2390**, compile-time override `LW_WIFI_COMMAND_PORT` must be 1..65535.

Each turn reads at most four datagrams, checks a 2000-us budget between reads,
services tick/challenges before and after ingress, and delays at least one tick.
These are work bounds, not measured preemption/latency guarantees. A 595-byte
buffer detects truncation above the 594-byte wire limit. Zero/oversize packets,
missing source addresses/ports, non-IPv4/non-unicast/off-subnet sources are
rejected. Setup authentication has a two-request burst and one token per 10ms;
tokens do not reset on pending expiry. The burst permits immediate HELLO/CLAIM
from the existing client, which does not retransmit CLAIM.

Only `lw_controller_receive_observed` with the current
`PIOS_LiteWing_PilotReadAdmissionMapping` can admit/publish. IP/port is pinned
only on authenticated HELLO's `LW_HANDSHAKE_REPLY`/PENDING transition. Pending
and active peers cannot be replaced; other peers are filtered before controller
entry and cannot retire the live owner, even with a correctly signed STOP.
Ordinary unowned pending expiry may clear peer state for another admission.
STOP, active expiry or any owning retirement ends command service; no fresh
session starts while ownership is retained.

Handshake/periodic-challenge short sends or errors (including EAGAIN), receive
errors, AP flags and controlled task exit call controller fault. Randomness uses
only `esp_fill_random`, after healthy AP/interface readiness, with AP flag checks
before and after filling. No controller call runs in AP event context.
Cleanup retires input and wipes root/wire/reply, closes the socket and stops AP.
Failed close/AP stop retries once per cleanup turn with at least 100ms/one-tick
delay; permanent failure keeps a sleeping cleanup task rather than reporting
success. Full task/controller state is wiped before self-deletion. Wireless
ownership is never released automatically; **v1 recovery after retirement is
explicit reboot**. No PWM, settings wire APIs or telemetry export are added.

## Evidence

TDD and writing-good-tests guidance were applied. Compiled initial stub failed
all task-creation/body scenarios. A separate RED/GREEN regression caught socket
leak on failed close. Actual C/Python loopback exposed dropped immediate CLAIM;
the bounded two-token admission burst fixed it without removing flood limits.

Focused command (Python 3.11+ for operator loopback):

```sh
LRRK_TEST_MBEDTLS_ROOT="$IDF_PATH/components/mbedtls/mbedtls" \
  python3.14 -m unittest discover -s ports/ninjapilot-litewing/tests \
  -p test_wifi_command.py -v
```

Passed **29 deterministic scenarios plus 2 actual UDP loopback cases** under
fatal ASan/UBSan. Cases cover launch/duplicate failure, absent credentials,
interface/readiness/address/socket/fcntl/bind-verification failures, malformed
and addressless datagrams, pending/active peer replacement, replay, auth flood,
count/time budgets and mandatory yield, pending expiry, handshake/challenge
send failure, receive/AP/RNG/clock failure, STOP/loss and cleanup retry. Loopback
uses the existing Python client and the actual task body for PILOT→STOP and
PILOT→loss expiry, checking real receiver timeout and retained UART exclusion.

Fixtures compile real controller, session, wire codec, MAC/KDF, neutral checks
and receiver with clean pinned mbedTLS `98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8`.
The controller is included under an observing wrapper to count actual setup
entries; authentication/publication are not mocked. SDK AP/netif/task/time/RNG,
mapping observations and deterministic socket failures are fixtures. Loopback
uses real host sockets/time with synthetic AP/interface/readiness and RNG.
Absent explicit mbedTLS checkout clearly skips this optional backend. The tests
do not depend on private SDK paths or generated target build configuration.

The final task translation unit compiled with the pinned ESP32-S3 compiler,
actual IDF 5.3.2 headers and `-Werror`, reusing the AP compile-command flags with
task source and temporary output substituted. SDK source inspection confirmed
FreeRTOS stack sizes are bytes; lwIP `recvfrom` returns copied length on UDP
truncation; failed `lwip_close` can retain its descriptor; fcntl supports
nonblocking mode; `esp_fill_random` inherits RF entropy prerequisites.
`git diff --check` passed. No full suite/target build was run; main owns it.

## Unverified scope

Full target linkage and startup integration await main's build/review. No
radio/DHCP/provider acceptance, scheduling under Wi-Fi load, stack high-water,
USB coexistence under load or receiver-to-motor timing is established. The
single-owner contract excludes external task deletion/suspension and competing
Wi-Fi/interface operations; controlled exits are tested, arbitrary RTOS task
destruction is not recoverable through this task body. AP internal SDK cleanup
limitations remain as documented by the AP boundary. Cleanup retries have
bounded work/yield but no claim of eventual success. Wipes are best effort.
Telemetry export, provisioning/rotation and physical qualification remain
pending; this increment is not a flight-verification result.

## Admission-guard cleanup correction

Review found that clock rollback during guarded admission can make
`EndAdmission` fail. Socket/AP cleanup success must not permit controller wipe
or task deletion while `admission_guard` remains nonzero. Cleanup now retains
that token/context and retries controller fault after the existing bounded
100ms/minimum-one-tick delay. Clock recovery clears the unowned admission guard;
permanent failure keeps the task parked. This does not release a retired
wireless ownership reservation or restart sessions.

TDD regression injects rollback on the real guarded second mapping read. With
socket close and AP stop both successful, the old task deleted prematurely
(observed RED). The corrected task retains its guard and retired session over
three cleanup delays, then ordinary clock recovery allows admission cleanup
and USB writes before task deletion (GREEN). Existing STOP/expiry ownership
retention and active-clock-rollback cases remain unchanged and pass.
`test_wifi_command.py` passed **30 deterministic scenarios plus 2 C/Python UDP
loopback cases** using Python 3.14, the actual pinned SDK mbedTLS checkout and
fatal ASan/UBSan. No full suite, target build, hardware or workflow changes.
