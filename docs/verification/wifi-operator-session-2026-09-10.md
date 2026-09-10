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
