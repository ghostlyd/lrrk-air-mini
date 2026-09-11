import unittest

from lrrk_litewing_ai import usb_advisory


class AdvisoryBudgetTests(unittest.TestCase):
    def budget(self, callback, clock, **kwargs):
        cls = getattr(usb_advisory, 'BoundedAnalysis', None)
        self.assertIsNotNone(cls, 'analysis budget is missing')
        return cls(callback, monotonic=clock, **kwargs)

    def test_interval_and_total_budget_limit_calls_without_waiting(self):
        now, calls = [0.0], []
        callback = self.budget(lambda r, item: calls.append(item), lambda: now[0],
                               interval_s=5, max_calls=2)
        for timestamp, item in ((0, 'first'), (1, 'drop'), (5, 'second'), (10, 'over')):
            now[0] = timestamp
            callback(None, item)
        self.assertEqual(calls, ['first', 'second'])
        self.assertEqual(callback.calls, 2)

    def test_failed_attempt_consumes_budget_and_is_not_retried(self):
        calls = []
        def fail(*args):
            calls.append(True)
            raise RuntimeError('provider failed')
        callback = self.budget(fail, lambda: 0, interval_s=1, max_calls=1)
        with self.assertRaises(RuntimeError): callback(None, None)
        callback(None, None)
        self.assertEqual(calls, [True])

    def test_clock_regression_stops_before_another_call(self):
        now, calls = [3], []
        callback = self.budget(lambda *args: calls.append(True), lambda: now[0],
                               interval_s=1, max_calls=2)
        callback(None, None)
        now[0] = 2
        with self.assertRaises(ValueError): callback(None, None)
        self.assertEqual(calls, [True])

    def test_invalid_configuration_cannot_start(self):
        for interval, maximum in ((0, 1), (float('nan'), 1), (1, True), (1, 0), (1, 13)):
            with self.subTest(interval=interval, maximum=maximum):
                with self.assertRaises(ValueError):
                    self.budget(lambda *args: None, lambda: 0,
                                interval_s=interval, max_calls=maximum)
