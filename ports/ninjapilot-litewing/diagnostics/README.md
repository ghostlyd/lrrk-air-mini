# Disarmed receiver-loss diagnostic

`receiver_probe.py` is a separate bench instrument, not an AI tool or GCS.
It cannot configure or arm the drone. It writes only one literal GCSReceiver
packet: throttle minimum, neutral sticks, first mode. It never writes settings,
metadata, persistence, flight state or actuator outputs. Do not add arbitrary
channel arguments or call it from the advisory assistant.

Prerequisites: reviewed installed application from
[PR31 installation evidence](../../../docs/verification/control-fixes-usb-install-2026-09-09.md),
props removed, battery absent, no other serial owner, and the actual callout and
USB location freshly checked. Python3, pyserial (available in the existing
ESP-IDF Python environment), and the pinned NinjaPilot checkout are required.
No ESP-IDF build, flashing, reset, Wi-Fi association or OpenAI request is part
of this diagnostic.

Run only after the code's independent bench review is accepted. Example argument
structure (replace the paths/device with your explicitly verified values):

```sh
python3 ports/ninjapilot-litewing/diagnostics/receiver_probe.py \
  --flight-root /path/to/pinned/NinjaPilot \
  --device /dev/cu.wchusbserial410 --location 4-1 \
  --output /private/path/to/new-receiver-trial \
  --execute --props-removed --battery-absent \
  --installed-app-sha256 3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8
```

The SHA argument is the operator's installation attestation, **not a live
firmware readback**. Do not infer it from the source checkout, an arbitrary
local image, or USB VID/PID. Changed firmware requires a newly reviewed bench
contract, not substituting another hash or bypassing the check.

The output directory must not exist. It is created private (0700), with
exclusively created 0600 raw capture and JSON report. Keep those artifacts out
of Git; they may include device/private settings data. Exit0 means four bounded
phases met sampled host-observation criteria; exit2 is a blocked/failed test,
not a retry instruction. Disconnects, parsing faults and missing phase evidence
never count as PASS. The serial handle closes on completion/failure; cleanup
does not send controls. The probe does not electrically disconnect USB power.
The final `report.json` is published without overwrite only after capture
flush/fsync/close and report flush/fsync/close succeed. A `report.pending` file
is incomplete evidence, never a completed result. A capture finalization failure
changes the result to FAIL. Unresolved trailing framing also prevents PASS;
the [first trial](../../../docs/verification/disarmed-receiver-probe-2026-09-09.md)
remains a historical FAIL/inconclusive result, not a retrospectively repaired pass.

After all four phases, completion may read for at most250ms (still inside the
21s total deadline), solely to finish a frame already in progress. Read sizes
stop at that frame's boundary; a partial header is completed first to obtain
the remaining length. No new whole frame is started, and no request, handshake,
ACK or receiver packet is sent in completion. The completed bytes still undergo
CRC, schema, settings and safety validation. Missing/late/corrupt bytes or a
contrary final receiver state fail; nothing is discarded to manufacture PASS.
The report's `completion` records host-relative start/end, additional bytes and
whether a pending frame was completed and validated. Failed attempts also retain
these metrics; `end_s` is the last checked host time before port closure, not an
electrical timestamp. This finite capture does not assert
anything about later unread telemetry or continuous electrical safety.

Preflight waits up to15s for fresh safe settings/status and actual no-input
timeout values. The four phases are input1/silence1/input2/silence2, each1.2s.
Each phase must end with at least three consecutive matching receiver samples;
early matches followed by contrary state cannot satisfy acceptance. Selected
settings are compared as complete raw payload bytes, not just decoded values.
Input opportunities occur every40ms; >=80ms since the previous host write attempt aborts
without a catch-up burst. Cadence is revalidated and recorded immediately before
the host write attempt, not at the earlier scheduling decision. A delayed
decision cannot authorize an overdue packet or a compressed catch-up interval;
`neutral_packets` counts attempted writes, not electrically timed delivery.
Host scheduling can still delay the OS call after its final check: this is not
a realtime/electrical guarantee. Critical/Error alarms block input. Existing
BootFault Uninitialised and unused-sensor Uninitialised states are tolerated
only for this Always Disarmed, battery-absent trial. They are not cleared or
interpreted as flight readiness.

Known boundaries: initial UART synchronization can discard up to4096 bytes;
after sync, corruption fails. CRC provides integrity, not sender authentication.
The verified codec bytes are compiled directly and the verified XML bytes are
parsed from memory; cached Python bytecode and second source reads are not used.
Freshness conservatively starts just before each nonblocking serial read, not
after capture writing or decoding. Deadline/freshness checks surround outgoing
writes and repeat before success and after port close. The 21s trial deadline
cannot preempt a blocked OS call; a late return fails instead of passing or
authorizing further writes. Final disk publication is outside this trial timer.
Freshness and phase times are host observations; UART buffering and task
scheduling remain distinct from the driver's100ms age policy. The report does
not measure electrical motor-cut latency or establish powered/flight readiness.

Host verification, with no device access:

```sh
LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_receiver_probe.py -v
```

The source CI job supplies that checkout. Runs without it explicitly skip the
protocol/serial-boundary tests, rather than claim they exercised the real schema.
