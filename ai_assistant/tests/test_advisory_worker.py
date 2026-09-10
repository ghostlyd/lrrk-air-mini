import threading
import unittest
import builtins
from unittest.mock import patch

from lrrk_litewing_ai import advisory_handoff
from lrrk_litewing_ai.tools import run_preflight_tool
from test_advisory_handoff import observation


class AdvisoryWorkerTests(unittest.TestCase):
    def worker(self, callback):
        cls = getattr(advisory_handoff, 'AdvisoryWorker', None)
        self.assertIsNotNone(cls, 'session-owned advisory worker is missing')
        return cls(callback)

    def test_preserves_observation_and_runs_real_analysis_off_producer(self):
        seen = []
        done = threading.Event()
        def analyze(runtime, item):
            seen.append((runtime.latest, item, threading.get_ident(),
                         run_preflight_tool(runtime)['overall']))
            done.set()
        worker = self.worker(analyze)
        item = observation()
        worker.offer(item)
        thread = threading.Thread(target=worker.run)
        thread.start()
        try:
            self.assertTrue(done.wait(2))
        finally:
            worker.close(); thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIs(seen[0][0], item.snapshot)
        self.assertIs(seen[0][1], item)
        self.assertNotEqual(seen[0][2], threading.get_ident())
        self.assertNotEqual(seen[0][3], 'PASS')

    def test_slow_analysis_does_not_block_offer_or_close(self):
        entered, release = threading.Event(), threading.Event()
        seen = []
        def analyze(runtime, item):
            seen.append(item)
            entered.set()
            release.wait(3)
        worker = self.worker(analyze)
        first = observation()
        worker.offer(first)
        thread = threading.Thread(target=worker.run)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertTrue(worker.offer(observation(2)))
            closed = threading.Event()
            closer = threading.Thread(target=lambda: (worker.close(), closed.set()))
            closer.start()
            self.assertTrue(closed.wait(.5))
            self.assertFalse(worker.offer(observation(3)))
        finally:
            release.set(); thread.join(2)
        closer.join(2)
        self.assertEqual(seen, [first])
        self.assertFalse(thread.is_alive())

    def test_failure_closes_without_retry_or_exception_text(self):
        calls = []
        def fail(runtime, item):
            calls.append(item)
            raise RuntimeError('private telemetry')
        worker = self.worker(fail)
        worker.offer(observation())
        worker.run()
        self.assertTrue(worker.failed)
        self.assertFalse(worker.offer(observation(2)))
        self.assertEqual(len(calls), 1)
        self.assertNotIn('private telemetry', repr(vars(worker)))

    def test_runtime_import_failure_retires_worker(self):
        worker = self.worker(lambda *args: None)
        worker.offer(observation())
        real_import = builtins.__import__
        def unavailable(name, *args, **kwargs):
            if name == 'tools':
                raise ImportError('runtime unavailable')
            return real_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=unavailable):
            worker.run()
        self.assertTrue(worker.failed)
        self.assertFalse(worker.offer(observation(2)))
        with self.assertRaises(RuntimeError): worker.run()

    def test_close_before_run_discards_pending_and_run_cannot_restart(self):
        seen = []
        worker = self.worker(lambda *args: seen.append(args))
        worker.offer(observation())
        worker.close(); worker.run()
        self.assertEqual(seen, [])
        with self.assertRaises(RuntimeError): worker.run()

    def test_new_session_has_fresh_runtime(self):
        runtimes = []
        for seq in (1, 2):
            def analyze(runtime, item):
                runtimes.append(runtime)
                worker.close()
            worker = self.worker(analyze)
            worker.offer(observation(seq))
            worker.run()
        self.assertIsNot(runtimes[0], runtimes[1])
        self.assertIsNone(runtimes[1].previous)

    def test_second_concurrent_consumer_rejected(self):
        entered, release = threading.Event(), threading.Event()
        def analyze(*args):
            entered.set(); release.wait(3)
        worker = self.worker(analyze)
        worker.offer(observation())
        thread = threading.Thread(target=worker.run)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(RuntimeError): worker.run()
        finally:
            worker.close(); release.set(); thread.join(2)
