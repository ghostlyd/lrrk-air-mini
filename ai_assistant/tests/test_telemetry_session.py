"""Exercise authenticated observations through the existing AI runtime."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event
import struct
import unittest

from lrrk_litewing_ai.telemetry_session import TelemetrySession
from lrrk_litewing_ai.telemetry_wire import TelemetryRecord, encode_telemetry
from lrrk_litewing_ai.safety import run_preflight
from lrrk_litewing_ai.tools import AssistantRuntime, get_latest_telemetry


class TelemetrySessionTests(unittest.TestCase):
    key, session_id = b"k"*32, b"s"*16
    wall = datetime(2026, 9, 10, tzinfo=timezone.utc)

    def setUp(self):
        self.consumer = TelemetrySession(self.session_id, self.key)

    def packet(self, seq=1, stamp=100, age=None, obj=0xEF69B6BC, data=bytes(8), session=None, key=None):
        return encode_telemetry(TelemetryRecord(obj, stamp, age, data),
                                self.session_id if session is None else session,
                                seq, self.key if key is None else key)

    def receive(self, packet, mono=1000, wall=None):
        return self.consumer.receive(packet, mono, self.wall if wall is None else wall)

    def test_observation_preserves_separate_clocks_and_unknown_link_age(self):
        observation = self.receive(self.packet(age=20))
        self.assertEqual((observation.serialized_us, observation.sample_age_us,
                          observation.received_monotonic_us, observation.received_at),
                         (100, 20, 1000, self.wall))
        snapshot = observation.snapshot
        self.assertIsNone(snapshot.link_age_ms)
        self.assertEqual(snapshot.captured_at, self.wall)
        self.assertEqual(snapshot.source.adapter, "wifi-telemetry-v1-receipt-time")
        self.assertFalse(snapshot.armed)
        self.assertIsNone(snapshot.alarms)
        self.assertEqual(snapshot.actuators, ())

    def test_runtime_receives_partial_snapshot_without_credentials(self):
        observation = self.receive(self.packet())
        runtime = AssistantRuntime()
        runtime.ingest(observation.snapshot)
        exported = get_latest_telemetry(runtime)
        self.assertTrue(exported["available"])
        self.assertIsNone(exported["snapshot"]["link_age_ms"])
        report = run_preflight(runtime.latest, now=self.wall)
        self.assertEqual(next(f.status for f in report.findings if f.finding_id == "link.freshness"), "UNKNOWN")
        self.assertNotEqual(report.overall, "PASS")
        self.assertNotIn(self.key.decode(), str(exported))
        self.assertNotIn(self.session_id.decode(), str(exported))

    def test_replay_reordering_and_sequence_exhaustion(self):
        self.receive(self.packet(seq=2))
        for seq in (1, 2):
            with self.assertRaises(ValueError):
                self.receive(self.packet(seq=seq), mono=1001)
        self.receive(self.packet(seq=2**64-1), mono=1002)
        with self.assertRaises(ValueError):
            self.receive(self.packet(seq=3), mono=1003)

    def test_invalid_packets_cannot_advance_accepted_state(self):
        self.receive(self.packet())
        invalid = (self.packet(seq=9, session=b"x"*16),
                   self.packet(seq=9, key=b"x"*32),
                   self.packet(seq=9, data=b"\xff"+bytes(7)),
                   self.packet(seq=9, stamp=99),
                   self.packet(seq=9)[:-1])
        for wire in invalid:
            with self.assertRaises(ValueError):
                self.receive(wire, mono=9999)
        observation = self.receive(self.packet(seq=2), mono=1001)
        self.assertEqual(observation.serialized_us, 100)

    def test_clock_and_api_errors_do_not_consume_sequence(self):
        self.receive(self.packet())
        for mono in (-1, 999, True, 1.5, 2**63):
            with self.assertRaises(ValueError):
                self.receive(self.packet(seq=2), mono=mono)
        with self.assertRaises(ValueError):
            self.receive(self.packet(seq=2), wall=datetime(2026, 9, 10))
        self.receive(self.packet(seq=2), mono=1000)

    def test_delayed_unseen_data_is_not_certified_fresh_or_aggregated(self):
        first = self.receive(self.packet())
        data = struct.pack("<7f", 1, 0, 0, 0, 12, 13, 14)
        second = self.receive(self.packet(seq=2, stamp=101, obj=0xD7E0D964, data=data), mono=10**9)
        self.assertIsNone(second.snapshot.link_age_ms)
        self.assertIsNone(second.snapshot.armed)
        self.assertEqual(second.snapshot.attitude.roll_deg, 12)
        self.assertNotEqual(first.snapshot.snapshot_id, second.snapshot.snapshot_id)

    def test_concurrent_replay_accepts_once(self):
        wire = self.packet()
        def attempt(_):
            try:
                self.receive(wire)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(32))), 1)

    def test_close_and_new_session(self):
        self.consumer.close()
        self.consumer.close()
        with self.assertRaises(ValueError):
            self.receive(self.packet())
        self.consumer = TelemetrySession(b"n"*16, self.key)
        with self.assertRaises(ValueError):
            self.receive(self.packet())
        self.receive(self.packet(session=b"n"*16))

    def test_receive_and_close_ordering(self):
        received, closed = Event(), Event()
        def receive_first():
            observation = self.receive(self.packet())
            received.set()
            self.assertTrue(closed.wait(2))
            with self.assertRaises(ValueError):
                self.receive(self.packet(seq=2))
            return observation
        def close_second():
            self.assertTrue(received.wait(2))
            self.consumer.close()
            closed.set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(receive_first), pool.submit(close_second)
            observation = first.result(timeout=3)
            second.result(timeout=3)
        self.assertFalse(observation.snapshot.armed)

    def test_battery_unknowns_and_semantic_errors_preserve_sequence(self):
        invalid_battery = struct.pack("<7f2B", float("inf"), 0, 0, 0, 0, 0, 0, 0, 0)
        invalid_alarms = bytes([255]) + bytes(24)
        for obj, data in ((0x26962352, invalid_battery), (0x6B7639EC, invalid_alarms)):
            with self.assertRaises(ValueError):
                self.receive(self.packet(seq=10, obj=obj, data=data))
        battery = struct.pack("<7f2B", 3.9, float("nan"), float("nan"),
                              float("nan"), float("nan"), float("nan"), float("nan"), 0, 0)
        observation = self.receive(self.packet(seq=1, obj=0x26962352, data=battery))
        self.assertAlmostEqual(observation.snapshot.battery.voltage_v, 3.9, places=5)
        self.assertIsNone(observation.snapshot.battery.current_a)
        self.assertIsNone(observation.sample_age_us)

    def test_constructor_rejects_invalid_material(self):
        for session, key in ((bytes(16), self.key), (b"s"*15, self.key),
                             (bytearray(16), self.key), (self.session_id, b"k"*31),
                             (self.session_id, bytearray(32))):
            with self.assertRaises(ValueError):
                TelemetrySession(session, key)
