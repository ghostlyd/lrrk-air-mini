# Host operator session (source only)

The board/controller foundation merged as PR #60, `0911c06`, after its target
build, 370-test regression (12 skips), whole-branch review and hosted CI passed.

OperatorSession is an operator-only protocol component, not an AI tool. It
authenticates board challenges with b2c, validates session/type/sequence, then
invokes the supplied operator sampler. It emits bounded eight-channel PILOT
payloads with increasing c2b-authenticated sequences. Callback failure, invalid
samples, processing-clock rollback, delayed sampling or local link expiry retire
the session. The board remains authoritative for challenge age including network
transit; host receive-time checks cannot establish board-time freshness.

STOP may use a fresh challenge or the last successfully used still-live proof,
with a new command sequence but its original receive time. It encodes once and
retires locally. A successful encoding is not a send or board acknowledgement.
No automatic command resend, arming, socket or key discovery is implemented.

Sampled, mutually accepted PilotAdmission transfers its credential references
once into OperatorSession; legacy empty-CLAIM admission cannot transfer. Close
drops Python references without promising physical memory erasure. No operator
keys or commands are added to the OpenAI tool surface.

Tests failed for missing implementation/handoff before coding, and for cached
STOP reuse before its correction. The full assistant suite passes: 207 run,
198 passed, 9 optional SDK skips. Fixtures cover bad role keys before sampling,
replay/no resampling, encoded channel bytes, input failure, timing bounds,
strict samples, one-shot STOP and single-use accepted handoff. Review pending.
Real socket integration, physical input-device selection, loss/jitter testing,
separate telemetry export and deployment remain required.

## Review correction

Review found that an exception from the initial clock callback escaped without
retiring the session. A regression reproduced retained credentials after that
failure. The initial read is now protected by the same retirement-on-exception
contract as later sampling/clock work. Tests cover initial clock exceptions for
both PILOT and STOP, prevent subsequent command generation, and prove a cached
STOP cannot receive a new lifetime from a falsely refreshed receive timestamp.
The full assistant suite passes: 209 run, 200 passed, 9 skipped. Scoped re-review
is pending; no networking or hardware operations were performed.

## Connected UDP transport

Scoped re-review accepted the initial-clock fix and independently ran seven
operator tests. OperatorUDP now owns an explicitly supplied connected UDP socket
and accepted OperatorSession. It reads at most one datagram per step with a 20ms
socket timeout, rejects oversized datagrams using a maximum-plus-one buffer,
checks session expiry during silence, and sends no command for invalid proofs.
Kernel peer filtering supplements, but does not replace, authentication. Input,
clock or socket errors close credentials/socket; there is no automatic resend or
reconnect. STOP uses the cached live proof and closes after one send attempt.

Six real loopback tests cover PILOT/STOP bytes, oversized/bad authentication with
no sampling or response, silence expiry, sampler failure, send failure without
retry and wrong-peer filtering. Keys are synthetic fixtures. Full assistant
suite: 215 run, 206 passed, 9 optional SDK skips. The missing transport test failed
before implementation. UDP review pending; this exercised only local loopback.

Admission over UDP, physical input-device integration and board AP/socket tasks
are still absent. The transport requires an already accepted session; these tests
do not claim a full handshake with board firmware, radio performance, or flight.

## UDP admission

Transport review accepted `a57d58f` and independently passed 13 operator/UDP
tests. The host now performs one sampled UDP admission attempt with a fresh
CSPRNG nonce, one-second core deadline, 20ms socket timeout and 64-receive work
cap. It does not automatically retransmit or reconnect. Proof authentication and
nonce binding precede the operator callback; after sampling, the clock and 75ms
receive-to-sample age are rechecked before CLAIM encoding. The sampler must be
bounded/nonblocking: Python cannot preempt a stuck callback; board expiry remains
independent. Missing samples cannot fall back to the legacy empty CLAIM path.

Accepted admission transfers once into OperatorUDP. Any unsuccessful attempt
closes socket and admission key references. Eight loopback tests now include the
full HELLO/CHALLENGE/sampled CLAIM/ACCEPT/PILOT/STOP exchange and silent admission
expiry with no retransmission. The peer is a Python protocol fixture, not the
firmware. Test-driven fixes cover None-sample fallback and pre-begin invocation
state corruption. Full suite: 220 run, 211 passed, 9 optional SDK skips.

UDP admission review pending. Real-C interoperability, radio provisioning,
physical input-device handling, telemetry-only export and board AP/task lifecycle
remain required. All network tests used local loopback with synthetic keys.

## Python-to-C interoperability

Review accepted UDP admission at `3822bf1` and independently passed 26 host
admission/operator/UDP tests. A new POSIX loopback fixture compiles the actual C
controller, session, wire codec, mbedTLS HMAC/HKDF and receiver with fatal
ASan/UBSan. It verifies the Python admit_udp/OperatorUDP sequence through sampled
admission, all eight receiver-channel values, and STOP invalidation while
retaining ownership. A separate process verifies input invalidation during
silence without STOP. Both scenarios pass with real monotonic clocks and the
existing protocol deadlines; deadlines were not widened for the test.

Platform time, synthetic mapping/object storage and deterministic test-only RNG
are fixture adapters. This is neither ESP-IDF AP code nor physical motor-output
or radio-load evidence. All datagrams bind to 127.0.0.1; no board is contacted.
The initial fixture compile exposed a macOS POSIX feature-macro visibility issue
for INADDR_LOOPBACK, corrected by inet_pton of the explicit loopback address.
Interoperability fixture review is pending; production AP/task integration,
provisioning, physical input and telemetry-only assistance remain unfinished.

## STOP attribution correction

Review found the first C fixture could confuse expiry with STOP retirement. A
deliberately delayed STOP (120 ms before processing) reproduced the false pass.
The fixture now requires the session to have been active and its saved input
origin to remain within the 100 ms lease through completion of STOP processing.
The delayed case must fail with the specific expired-lease assertion; ordinary
STOP and silence-expiry cases pass. Protocol deadlines remain unchanged.
The pre-correction full port suite ran 371 tests with 12 skips; a fresh full
regression and review of this correction are pending.
