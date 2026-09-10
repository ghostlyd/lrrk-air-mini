import hashlib
import os
import stat
import struct
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.live_uavtalk import (  # noqa: E402
    FLIGHT_TELEMETRY_STATS,
    GCST_TELEMETRY_STATS,
    SELECTED_OBJECT_IDS,
    LiveUAVTalkCollector,
    OutboundProtocol,
    SerialTelemetryTransport,
    UAVTalkLiveError,
    _CAPTURE_LIMIT,
    _PrivateCapture,
    _Synchronizer,
)
from lrrk_litewing_ai.adapters import AdapterError, UAVTalkAdapter  # noqa: E402
from lrrk_litewing_ai.uavobjects import (  # noqa: E402
    ACTUATOR_COMMAND,
    ATTITUDE_STATE,
    BATTERY_STATE,
    FLIGHT_STATUS,
    SYSTEM_ALARMS,
)
from lrrk_litewing_ai.uavtalk import UAVTalkDecoder, crc8  # noqa: E402
from lrrk_litewing_ai.tools import AssistantRuntime, run_preflight_tool  # noqa: E402


CAPTURED = datetime(2026, 9, 10, 4, tzinfo=timezone.utc)


def packet(kind, object_id, payload=b"", instance=0):
    raw = struct.pack("<BBHIH", 0x3C, kind, 10 + len(payload), object_id, instance)
    raw += payload
    return raw + bytes([crc8(raw)])


def complete_stream(actuator_payload=None):
    if actuator_payload is None:
        actuator_payload = struct.pack("<12hHHB", *([0] * 12), 0, 0, 0)
    frames = [
        packet(0x20, FLIGHT_TELEMETRY_STATS, bytes(36) + bytes([2])),
        packet(0x20, ATTITUDE_STATE, struct.pack("<7f", 1, 0, 0, 0, 10, -20, 90)),
        packet(0x20, FLIGHT_STATUS, bytes([2, 0, 0, 0, 0, 1, 0, 0])),
        packet(0x20, BATTERY_STATE, struct.pack("<7f2B", 0, 0, 0, 0, 0, 0, 0, 1, 1)),
        packet(0x20, SYSTEM_ALARMS, bytes([1] * 21 + [0] * 4)),
        packet(0x22, ACTUATOR_COMMAND, actuator_payload),
    ]
    return b"".join(frames)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        self.value += 0.001
        return self.value

    def wall(self):
        return CAPTURED + timedelta(seconds=self.value)

    def sleep(self, seconds):
        self.value += seconds


class FakeTransport:
    identity = "usb-serial:1a86:7522:4-1"

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.operations = []
        self.closed = False

    def handshake(self, status):
        self.operations.append(("handshake", status))

    def request(self, object_id):
        self.operations.append(("request", object_id))

    def ack(self, object_id, instance_id):
        self.operations.append(("ack", object_id, instance_id))

    def read(self, maximum):
        self.operations.append(("read", maximum))
        if not self.chunks:
            return b""
        return self.chunks.pop(0)

    def close(self):
        self.closed = True


class LiveUAVTalkTests(unittest.TestCase):
    def collector(self, transport, capture):
        clock = FakeClock()
        return LiveUAVTalkCollector(
            transport,
            capture,
            duration_s=0.5,
            monotonic=clock.monotonic,
            wall_clock=clock.wall,
            sleep=clock.sleep,
        )

    def test_outbound_protocol_allows_only_handshake_requests_and_acks(self):
        writes = []
        protocol = OutboundProtocol(lambda value: writes.append(value) or len(value))

        protocol.handshake(1)
        protocol.handshake(3)
        for object_id in sorted(SELECTED_OBJECT_IDS):
            protocol.request(object_id)
        protocol.ack(ACTUATOR_COMMAND, 0)

        decoded = [UAVTalkDecoder().feed(value)[0] for value in writes]
        self.assertEqual(decoded[0].object_id, GCST_TELEMETRY_STATS)
        self.assertEqual(decoded[0].message_type, 0x20)
        self.assertEqual(decoded[0].payload[-1], 1)
        self.assertEqual(decoded[1].payload[-1], 3)
        self.assertEqual({item.object_id for item in decoded[2:-1]}, SELECTED_OBJECT_IDS)
        self.assertTrue(all(item.message_type == 0x21 for item in decoded[2:-1]))
        self.assertEqual((decoded[-1].message_type, decoded[-1].object_id),
                         (0x23, ACTUATOR_COMMAND))
        self.assertEqual(
            writes[0].hex(),
            "3c202f000adcd1ca000000000000000000000000000000000000000000000000"
            "00000000000000000000000000000196",
        )
        self.assertEqual(
            writes[1].hex(),
            "3c202f000adcd1ca000000000000000000000000000000000000000000000000"
            "00000000000000000000000000000398",
        )

        for call in (
            lambda: protocol.handshake(2),
            lambda: protocol.request(0xFFFFFFFF),
            lambda: protocol.ack(0xFFFFFFFF, 0),
            lambda: protocol.ack(ACTUATOR_COMMAND, 1),
        ):
            with self.assertRaises(UAVTalkLiveError):
                call()
        self.assertEqual(len(writes), 2 + len(SELECTED_OBJECT_IDS) + 1)

    def test_collects_one_coherent_snapshot_and_private_capture(self):
        stream = complete_stream()
        transport = FakeTransport([b"\x00\xff" + stream])
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "live.uavtalk"
            collector = self.collector(transport, capture)
            snapshot = collector.collect()

            self.assertEqual(capture.read_bytes(), b"\x00\xff" + stream)
            self.assertEqual(stat.S_IMODE(capture.stat().st_mode), 0o600)
            self.assertEqual(collector.capture_sha256, hashlib.sha256(b"\x00\xff" + stream).hexdigest())
            self.assertEqual(collector.initial_discarded_bytes, 2)

        self.assertTrue(transport.closed)
        self.assertTrue(snapshot.armed)
        self.assertEqual(snapshot.flight_mode, "manual")
        self.assertEqual(snapshot.attitude.roll_deg, 10)
        self.assertEqual(snapshot.battery.voltage_v, 0)
        self.assertEqual(snapshot.alarms, ())
        self.assertEqual(snapshot.actuators, (0, 0, 0, 0))
        self.assertLessEqual(snapshot.link_age_ms, 500)
        self.assertEqual(snapshot.source.adapter, "uavtalk-live-ac77304")
        self.assertEqual(snapshot.source.transport, transport.identity)
        self.assertIsNone(snapshot.source.board)
        self.assertIn(("handshake", 1), transport.operations)
        self.assertIn(("handshake", 3), transport.operations)
        for object_id in SELECTED_OBJECT_IDS:
            self.assertIn(("request", object_id), transport.operations)
        self.assertIn(("ack", ACTUATOR_COMMAND, 0), transport.operations)
        runtime = AssistantRuntime(operator_session="live-test")
        runtime.ingest(snapshot)
        report = run_preflight_tool(runtime)
        self.assertEqual(report["overall"], "BLOCKED")
        armed = next(
            item for item in report["findings"]
            if item["finding_id"] == "flight.armed"
        )
        self.assertEqual(armed["status"], "BLOCK")

    def test_aggregate_preserves_actuator_mapping_and_update_faults(self):
        outputs = [0] * 12
        outputs[4] = 7
        stream = complete_stream(struct.pack("<12hHHB", *outputs, 0, 0, 1))
        transport = FakeTransport([stream])
        with tempfile.TemporaryDirectory() as directory:
            snapshot = self.collector(
                transport, Path(directory) / "live.uavtalk"
            ).collect()

        self.assertIn("ActuatorCommand:UnmappedChannel5=7", snapshot.alarms)
        self.assertIn("ActuatorCommand:FailedUpdates=1", snapshot.alarms)

    def test_missing_or_corrupt_live_telemetry_fails_closed_and_closes(self):
        cases = [
            ("missing", complete_stream().replace(
                packet(0x20, SYSTEM_ALARMS, bytes([1] * 21 + [0] * 4)), b"")),
            ("corrupt", complete_stream() + b"\x3c\x20\x01\x00"),
        ]
        for label, stream in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                transport = FakeTransport([stream])
                capture = Path(directory) / "live.uavtalk"
                with self.assertRaises(UAVTalkLiveError):
                    self.collector(transport, capture).collect()
                self.assertTrue(transport.closed)

    def test_selected_objects_without_completed_handshake_fail_closed(self):
        flight_stats = packet(
            0x20, FLIGHT_TELEMETRY_STATS, bytes(36) + bytes([2])
        )
        transport = FakeTransport([complete_stream()[len(flight_stats):]])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(UAVTalkLiveError):
                self.collector(
                    transport, Path(directory) / "live.uavtalk"
                ).collect()
        self.assertTrue(transport.closed)

    def test_connected_heartbeat_never_reverts_to_handshake_request(self):
        flight_stats = packet(
            0x20, FLIGHT_TELEMETRY_STATS, bytes(36) + bytes([2])
        )
        transport = FakeTransport([flight_stats])
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(
                transport,
                Path(directory) / "live.uavtalk",
                duration_s=2.2,
                monotonic=clock.monotonic,
                wall_clock=clock.wall,
                sleep=clock.sleep,
            )
            with self.assertRaises(UAVTalkLiveError):
                collector.collect()

        statuses = [item[1] for item in transport.operations if item[0] == "handshake"]
        first_connected = statuses.index(3)
        self.assertGreaterEqual(statuses.count(3), 2)
        self.assertNotIn(1, statuses[first_connected + 1:])

    def test_initial_synchronization_reads_at_most_4096_bytes(self):
        synchronizer = _Synchronizer()
        self.assertEqual(synchronizer.feed(bytes(4095)), [])
        flight_stats = packet(
            0x20, FLIGHT_TELEMETRY_STATS, bytes(36) + bytes([2])
        )
        with self.assertRaises(UAVTalkLiveError):
            synchronizer.feed(flight_stats)

    def test_private_capture_must_not_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "live.uavtalk"
            capture.write_bytes(b"owner data")
            transport = FakeTransport([complete_stream()])

            with self.assertRaises(UAVTalkLiveError):
                self.collector(transport, capture).collect()

            self.assertEqual(capture.read_bytes(), b"owner data")
            self.assertTrue(transport.closed)
            self.assertFalse(any(item[0] == "handshake" for item in transport.operations))

    def test_private_capture_enforces_exact_one_megabyte_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.uavtalk"
            capture = _PrivateCapture(path)
            capture.open()
            try:
                capture.write(bytes(_CAPTURE_LIMIT))
                with self.assertRaises(UAVTalkLiveError):
                    capture.write(b"x")
            finally:
                capture.close()

            self.assertEqual(path.stat().st_size, _CAPTURE_LIMIT)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_serial_identity_is_checked_before_port_open(self):
        serial_factory = Mock()
        wrong = SimpleNamespace(
            device="/dev/cu.wchusbserial410", vid=0x1A86, pid=0x7523,
            location="4-1",
        )

        with self.assertRaises(UAVTalkLiveError):
            SerialTelemetryTransport(
                "/dev/cu.wchusbserial410",
                "4-1",
                serial_factory=serial_factory,
                comports=lambda: [wrong],
            )

        serial_factory.assert_not_called()

    def test_serial_transport_deasserts_reset_lines_and_uses_exclusive_57600(self):
        port = Mock()
        port.write.side_effect = lambda value: len(value)
        port.read.return_value = b""
        serial_factory = Mock(return_value=port)
        match = SimpleNamespace(
            device="/dev/cu.wchusbserial410", vid=0x1A86, pid=0x7522,
            location="4-1",
        )

        transport = SerialTelemetryTransport(
            "/dev/cu.wchusbserial410",
            "4-1",
            serial_factory=serial_factory,
            comports=lambda: [match],
        )
        transport.handshake(1)
        transport.close()

        serial_factory.assert_called_once_with(
            port=None, baudrate=57600, timeout=0.02,
            write_timeout=0.2, exclusive=True,
        )
        self.assertFalse(port.dtr)
        self.assertFalse(port.rts)
        self.assertEqual(port.port, "/dev/cu.wchusbserial410")
        port.open.assert_called_once_with()
        port.close.assert_called_once_with()
        self.assertTrue(port.write.called)

    def test_serial_open_failure_closes_port_and_is_a_live_error(self):
        port = Mock()
        port.open.side_effect = OSError("open failed")
        match = SimpleNamespace(
            device="/dev/cu.wchusbserial410", vid=0x1A86, pid=0x7522,
            location="4-1",
        )

        with self.assertRaises(UAVTalkLiveError):
            SerialTelemetryTransport(
                "/dev/cu.wchusbserial410",
                "4-1",
                serial_factory=Mock(return_value=port),
                comports=lambda: [match],
            )

        port.close.assert_called_once_with()

    def test_public_adapter_normalizes_transport_io_failures(self):
        transport = Mock()
        collector = Mock()
        collector.collect.side_effect = OSError("link lost")
        with patch(
            "lrrk_litewing_ai.live_uavtalk.SerialTelemetryTransport",
            return_value=transport,
        ), patch(
            "lrrk_litewing_ai.live_uavtalk.LiveUAVTalkCollector",
            return_value=collector,
        ):
            adapter = UAVTalkAdapter(
                "/dev/cu.wchusbserial410", "4-1", Path("capture.uavtalk")
            )
            with self.assertRaises(AdapterError):
                list(adapter.snapshots())


if __name__ == "__main__":
    unittest.main()
