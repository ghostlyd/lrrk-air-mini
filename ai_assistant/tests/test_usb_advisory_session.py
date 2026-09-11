import importlib
import tempfile
import threading
import unittest
from pathlib import Path

from test_live_uavtalk import FakeClock, FakeTransport, complete_stream
from lrrk_litewing_ai.live_uavtalk import LiveUAVTalkCollector, UAVTalkLiveError


class USBAdvisorySessionTests(unittest.TestCase):
    def runner(self):
        name = 'lrrk_litewing_ai.usb_advisory'
        self.assertIsNotNone(importlib.util.find_spec(name), 'USB supervisor missing')
        return importlib.import_module(name).run_usb_advisory

    def test_invalid_budget_closes_before_any_serial_operation(self):
        run = self.runner()
        transport = FakeTransport([])
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture')
            with self.assertRaises(ValueError):
                run(collector, lambda *args: None, lambda: False,
                    duration_s=.1, max_calls=0)
        self.assertTrue(transport.closed)
        self.assertEqual(transport.operations, [])

    def test_session_exit_sets_analysis_cancellation_signal(self):
        run = self.runner()
        cancelled = threading.Event()
        transport = FakeTransport([])
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture')
            run(collector, lambda *args: None, lambda: True,
                duration_s=.1, cancellation=cancelled)
        self.assertTrue(cancelled.is_set())

    def test_analysis_runs_off_acquisition_and_cleanup_retires_thread(self):
        run = self.runner()
        entered, release = threading.Event(), threading.Event()
        seen = []
        producer_id = threading.get_ident()
        clock = FakeClock()
        transport = FakeTransport([complete_stream(), complete_stream()])
        sleeps = []

        def analyze(runtime, item):
            seen.append((runtime.latest, item, threading.get_ident()))
            entered.set()
            release.wait(2)

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 1:
                self.assertTrue(entered.wait(1))
            elif len(sleeps) == 2:
                # Both serial chunks were read while analysis was blocked.
                self.assertEqual(transport.chunks, [])
                release.set()
            clock.sleep(seconds)

        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture',
                monotonic=clock.monotonic, wall_clock=clock.wall, sleep=sleep)
            try:
                count = run(collector, analyze, lambda: False, duration_s=.1)
            finally:
                release.set()
        self.assertEqual(count, 2)
        self.assertTrue(transport.closed)
        self.assertTrue(seen)
        self.assertIs(seen[0][0], seen[0][1].snapshot)
        self.assertNotEqual(seen[0][2], producer_id)

    def test_bad_serial_data_closes_transport_and_propagates_failure(self):
        run = self.runner()
        clock = FakeClock()
        transport = FakeTransport([complete_stream(), b'bad'])
        with tempfile.TemporaryDirectory() as directory:
            collector = LiveUAVTalkCollector(transport, Path(directory)/'capture',
                monotonic=clock.monotonic, wall_clock=clock.wall, sleep=clock.sleep)
            with self.assertRaises(UAVTalkLiveError):
                run(collector, lambda *args: None, lambda: False, duration_s=.1)
        self.assertTrue(transport.closed)
