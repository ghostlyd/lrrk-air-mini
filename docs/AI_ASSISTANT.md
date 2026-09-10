# LiteWing AI assistance

The assistant is a host-side advisory service. The flight controller remains
the sole owner of stabilization, arming, failsafe, and motor output. The
assistant receives normalized telemetry and can run deterministic checks,
explain findings, compare snapshots, and create a bounded proposal for human
review. It has no tool for raw motor values or direct flight commands.

## Offline first

Preflight analyzer `litewing-safety-3` counts elapsed wall-clock time since
capture against the 500 ms default freshness budget. Effective link age is
the recorded link age plus that elapsed time. Old replay fixtures therefore
produce blocked readiness reports when evaluated today, while remaining useful
for inspection. An unchanged snapshot can expire before a proposal does;
approval rechecks freshness. Capture timestamps must come from trusted metadata.
An already approved proposal also rechecks preflight whenever its currentness
is queried; an unchanged snapshot hash cannot extend telemetry freshness.

Normalized snapshot schema **2** distinguishes unknown alarm state (`null`)
from a complete report with no alarms (`[]`). JSONL schema 1 remains readable,
but omitted/null alarms now stay unknown rather than silently becoming clear.
Alarms, actuators and capabilities accept arrays or null, never strings,
booleans or objects (for example, `{"gps": false}` is not a declared GPS).
Attitude, battery and sensors accept objects or null, not falsy scalar/array
substitutes. Consumers must accept schema 2 output; normalization changes the
snapshot hash, so old proposal bindings are not reusable.

Missing flight mode is unknown. Motor evidence must contain exactly four
finite numeric observations under the LiteWing mapping; a partial vector does
not pass merely because its available values are in range. Reported unsafe
values still block even when the vector is incomplete. Unknown state cannot
produce an approval through the normal proposal state machine.

The deterministic path requires only Python and the standard library. The
current workstation has Python 3.9.6, while the package metadata requires
Python 3.11+ for the maintained runtime; the source is intentionally kept
portable enough for host-only syntax checks on the current machine.

Run the fixture without a key or network:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input ai_assistant/tests/fixtures/telemetry.jsonl \
  --audit-log /tmp/litewing-audit.jsonl \
  --prompt 'run preflight' \
  --json
```

Run host tests on a Python 3.11+ environment with the optional test extra, or
use the standard-library fallback on the current workstation:

```sh
PYTHONPATH=ai_assistant/src python3 -m unittest discover \
  -s ai_assistant/tests -p 'test_*.py'
```

## Live provider

Live mode is opt-in and requires the `openai` extra plus an approved
process-level `OPENAI_API_KEY`. No key is written by this repository, and a
key is never sent to the LiteWing. If the key or optional SDK is unavailable,
live mode fails closed; offline mode remains usable.

The live agent is limited to the read-only tool surface in
`ai_assistant/src/lrrk_litewing_ai/tools.py`. Proposals are not execution.
Approval requires an operator-provided token, the same current snapshot hash,
a short expiry, and a clear deterministic preflight report. Link loss, state
drift, alarm escalation, or expiry invalidates approval.

## Protocol boundary

The JSONL and saved-capture adapters are deterministic replay paths.
`UAVTalkAdapter` now provides a bounded live read-side path for the pinned
NinjaPilot schema. No adapter may issue an actuator, arming, settings,
persistence, receiver, gain, failsafe, takeoff, landing, or navigation write.

### Bounded live serial collection

Install the host-only transport extra in a Python 3.11+ environment:

```sh
python3 -m pip install './ai_assistant[uavtalk]'
```

Then select the exact serial node and USB topology location reported by
`serial.tools.list_ports`, and provide a new private capture destination:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input-format uavtalk-live \
  --device /dev/cu.wchusbserial410 \
  --usb-location 4-1 \
  --private-capture /path/to/new-private-capture.uavtalk \
  --duration 2 --json
```

Live and replay arguments are mutually exclusive. The live path requires an
exact `1A86:7522` identity/location match before opening, deasserts DTR/RTS
before the open, and uses exclusive 57600-baud access. It creates the inbound
capture with exclusive-create semantics and mode `0600`, caps it at 1 MiB,
and preserves a partial capture when collection fails. Initial framing noise
is tolerated only within the 4096-byte synchronization bound; framing errors
after synchronization are fatal.

The only outbound frames are GCS telemetry handshake status 1 or 3, read
requests for `AttitudeState`, `FlightStatus`, `FlightBatteryState`,
`SystemAlarms`, and `ActuatorCommand`, and acknowledgements required for those
objects or `FlightTelemetryStats`. The collector returns only after all five
selected objects form one aggregate. It records their receipt span as link
age, combines actuator mapping/update faults with system alarms, and leaves
unobserved sensor and board identity fields unknown. An Armed aggregate is
deterministically `BLOCKED`; the optional model cannot override that result.

### Binary capture inspection

The receive-only `lrrk_litewing_ai.uavtalk` module now decodes saved binary
captures into frame records, including object ID, instance ID, raw payload,
and optional device timestamp ticks:

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.uavtalk capture.bin
```

Its format follows the manifest-pinned
[NinjaPilot sender](https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja/blob/ac77304a58de6c8bd552f94668b46903adb71cb2/flight/uavtalk/uavtalk.c):
every frame includes an instance ID, length excludes the CRC byte, and the
CRC uses polynomial `0x07`. The parser accepts arbitrary chunk boundaries,
rejects malformed types, lengths, checksums, and truncated captures, and caps
payloads at the pinned generated `UAVOBJECTS_LARGEST` of 217 bytes.
Fixed synthetic test vectors use independently calculated upstream-table CRCs.

Captures must begin at a frame boundary; corruption stops decoding. Earlier
records may already have been printed when a later frame fails, so consumers
must check the command exit status. CRC provides corruption detection, not
authentication. Timestamp ticks are not wall-clock freshness evidence.

The framing command above emits raw frames. No serial port is
opened and no acknowledgment, object request, or flight command is sent.

### Capture observations in the assistant

The assistant CLI decodes `AttitudeState`, `FlightStatus`, `FlightBatteryState`,
`SystemAlarms`, and `ActuatorCommand` into partial normalized snapshots using
the pinned generated object IDs and layouts (28, 8, 30, 25 and 29 payload bytes
respectively):

```sh
PYTHONPATH=ai_assistant/src python3 -m lrrk_litewing_ai.cli \
  --input capture.bin --input-format uavtalk \
  --captured-at 2026-09-09T10:00:00Z --prompt status --json
```

Replace the example timestamp with the capture's recorded UTC time. Replay
never assigns today's time to an old capture, and link age stays unknown.
Each supported frame is a separate partial snapshot; this avoids combining
older battery/status data with a newer attitude into apparently current state.
An arming transition is treated as armed for preflight purposes. Unknown
object IDs and control frames are skipped; invalid selected-object lengths,
nonzero instances, enum values, and non-finite numbers reject the capture.

`SystemAlarms` preserves every non-OK state by its pinned field name, including
Uninitialised states, extended statuses and nonzero substatus bytes. Only a
complete all-OK alarm object with clear extended fields produces `alarms=[]`.
Uninitialised-only reports are unknown, not healthy; warning/critical/error or
other reported alarm evidence blocks. Optional subsystem states must not be
silently cleared merely to achieve a passing report.

`ActuatorCommand` maps channels 1–4 to LiteWing's `0..1000` brushed-duty
observations, despite the inherited XML's servo-pulse unit label. Negative or
over-range values are retained for blocking findings, not clamped. Nonzero
channels outside that mapping and the reported failed-update counter become
blocking evidence. A zero failure counter does not establish a clear global
alarm state or prove physical gate-pin timing.

The replay snapshot's source identifies the decoder schema, not the aircraft's actual
firmware. IMU identity/health, physical actuator outputs, battery percentage, and board
identity remain unknown. Battery voltage/current are received observations;
the current target wrapper has no verified battery measurement producer.
The live adapter adds bounded per-object receipt aggregation and USB-bridge
identity, but it still does not authenticate the aircraft, establish physical
motor output, prove flight readiness, or authorize an AI flight action.
