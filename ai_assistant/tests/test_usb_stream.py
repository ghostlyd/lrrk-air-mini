import tempfile
import unittest
from pathlib import Path
from test_live_uavtalk import FakeClock, FakeTransport, complete_stream, packet, FLIGHT_TELEMETRY_STATS
from lrrk_litewing_ai.live_uavtalk import LiveUAVTalkCollector, UAVTalkLiveError


class USBStreamTests(unittest.TestCase):
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
