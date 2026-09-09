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

Preflight waits up to15s for fresh safe settings/status and actual no-input
timeout values. The four phases are input1/silence1/input2/silence2, each1.2s.
Input opportunities occur every40ms; >=80ms between scheduled inputs aborts
without a catch-up burst. Critical/Error alarms block input. Existing
BootFault Uninitialised and unused-sensor Uninitialised states are tolerated
only for this Always Disarmed, battery-absent trial. They are not cleared or
interpreted as flight readiness.

Known boundaries: initial UART synchronization can discard up to4096 bytes;
after sync, corruption fails. CRC provides integrity, not sender authentication.
Freshness and phase times are host receipt times; UART buffering and task
scheduling remain distinct from the driver's100ms age policy. The report does
not measure electrical motor-cut latency or establish powered/flight readiness.

Host verification, with no device access:

```sh
LRRK_TEST_FLIGHT_ROOT=/path/to/pinned/NinjaPilot \
  python3 -m unittest discover -s ports/ninjapilot-litewing/tests -p test_receiver_probe.py -v
```

The source CI job supplies that checkout. Runs without it explicitly skip the
protocol/serial-boundary tests, rather than claim they exercised the real schema.
