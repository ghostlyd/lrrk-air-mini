import tempfile
import unittest
from pathlib import Path
from test_live_uavtalk import FakeClock, FakeTransport, complete_stream, packet, FLIGHT_TELEMETRY_STATS
from lrrk_litewing_ai.live_uavtalk import LiveUAVTalkCollector, UAVTalkLiveError


class USBStreamTests(unittest.TestCase):
    def test_optional_nack_allows_legacy_stream_and_clears_health(self):
        health = packet(0x20, 0xDA60A0C6, bytes.fromhex('130000000101680101'))
        nack = packet(0x24, 0xDA60A0C6)
        legacy = complete_stream()
        for prior_health in (b'', health):
            with self.subTest(cached=bool(prior_health)):
                observations = []
                count = self.run_stream([legacy + prior_health, nack + legacy[48:], legacy[48:]], observations.append)
                self.assertEqual(count, 3)
                self.assertEqual(observations[0].sensors.imu_healthy, True if prior_health else None)
                for observation in observations[1:]:
                    self.assertIsNone(observation.sensors.imu_healthy)
                    self.assertIsNone(observation.sensors.imu_identity)
                    self.assertIsNone(observation.sensors.imu_sample_age_ms)
                    self.assertEqual(observation.attitude.roll_deg, 10)
                    self.assertEqual(observation.alarms, ())
                self.assertNotIn(('ack', 0xDA60A0C6, 0), self.transport.operations)

    def test_optional_health_ages_across_deliveries_without_blocking_legacy(self):
        observations = []
        health = packet(0x22, 0xDA60A0C6, bytes.fromhex('130000000101680101'))
        self.run_stream([complete_stream() + health, complete_stream()], observations.append)
        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[0].sensors.imu_sample_age_ms, 19)
        self.assertGreater(observations[1].sensors.imu_sample_age_ms, 20)
        self.assertIn(('request', 0xDA60A0C6), self.transport.operations)

    def test_reconnect_responder_requires_second_request(self):
        class Responder(FakeTransport):
            def __init__(self):
                super().__init__([])
                self.requests = 0
            def handshake(self, status):
                super().handshake(status)
                if status == 1:
                    self.requests += 1
                    if self.requests == 1:
                        self.chunks.append(packet(0x20, FLIGHT_TELEMETRY_STATS, bytes(37)))
                    elif self.requests == 2:
                        self.chunks.append(complete_stream())
        clock = FakeClock()
        transport = Responder()
        observations = []
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture',
                monotonic=clock.monotonic, wall_clock=clock.wall, sleep=clock.sleep)
            self.assertEqual(collector.stream(observations.append, lambda:False,
                                              duration_s=.1), 1)
        self.assertEqual([op[1] for op in transport.operations if op[0]=='handshake'], [1,1,3])
        self.assertTrue(transport.closed)

    def test_initial_disconnected_status_reissues_handshake_before_timeout(self):
        disconnected = packet(0x20, FLIGHT_TELEMETRY_STATS, bytes(37))
        observations = []
        self.run_stream([disconnected, complete_stream()], observations.append)
        self.assertEqual(self.transport.operations.count(('handshake', 1)), 2)
        self.assertEqual(len(observations), 1)

    def test_disconnect_in_deadline_completion_is_failure(self):
        clock = FakeClock()
        disconnected = packet(0x20, FLIGHT_TELEMETRY_STATS, bytes(37))
        transport = FakeTransport([complete_stream() + disconnected[:5], disconnected[5:]])
        observations = []
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture',
                monotonic=clock.monotonic, wall_clock=clock.wall,
                sleep=lambda seconds: clock.sleep(.1))
            with self.assertRaisesRegex(UAVTalkLiveError, 'disconnected'):
                collector.stream(observations.append, lambda: False, duration_s=.1)
        self.assertEqual(len(observations), 1)
        self.assertTrue(transport.closed)

    def run_stream(self, chunks, offer, stop=lambda: False, duration_s=.1):
        clock = FakeClock()
        transport = FakeTransport(chunks)
        self.transport = transport
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture',
                monotonic=clock.monotonic, wall_clock=clock.wall, sleep=clock.sleep)
            self.assertTrue(callable(getattr(collector, 'stream', None)),
                            'continuous acquisition is missing')
            return collector.stream(offer, stop, duration_s=duration_s)

    def test_silent_link_after_snapshot_fails_instead_of_reporting_success(self):
        observations = []
        with self.assertRaises(UAVTalkLiveError):
            self.run_stream([complete_stream()], observations.append, duration_s=2)
        self.assertEqual(len(observations), 1)
        self.assertTrue(self.transport.closed)

    def test_multiple_observations_on_one_transport(self):
        observations = []
        count = self.run_stream([complete_stream(), complete_stream()], observations.append)
        self.assertEqual(count, 2)
        self.assertEqual(len(observations), 2)
        self.assertLess(observations[0].captured_at, observations[1].captured_at)
        self.assertTrue(self.transport.closed)

    def test_corruption_after_sync_stops_and_closes(self):
        observations = []
        with self.assertRaises(UAVTalkLiveError):
            self.run_stream([complete_stream(), b'bad'], observations.append)
        self.assertEqual(len(observations), 1)
        self.assertTrue(self.transport.closed)

    def test_preexisting_stop_sends_nothing(self):
        self.assertEqual(self.run_stream([], lambda s: self.fail(), lambda: True), 0)
        self.assertEqual(self.transport.operations, [])
        self.assertTrue(self.transport.closed)

    def test_normal_deadline_finishes_started_frame_before_closing(self):
        clock = FakeClock()
        # Split a real packet header across the session deadline.
        packet = complete_stream()[:48]
        transport = FakeTransport([complete_stream() + packet[:5], packet[5:]])
        observations = []
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture',
                monotonic=clock.monotonic, wall_clock=clock.wall,
                sleep=lambda seconds: clock.sleep(.1))
            count = collector.stream(observations.append, lambda: False, duration_s=.1)
        self.assertEqual(count, 1)
        self.assertTrue(transport.closed)
