"""Hardware-free regression for stale, request-only output observations."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1]/'diagnostics/bench_cleanup.py'


class BenchCleanupTests(unittest.TestCase):
    def run_cleanup(self, mode='delayed'):
        self.assertTrue(MODULE.exists(), 'bounded cleanup implementation missing')
        spec = importlib.util.spec_from_file_location('bench_cleanup', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        t = [100.0]  # independent of an already expired transaction clock
        writes = []
        latest = {}
        def write(packet):
            writes.append((t[0], packet))
            return 0 if mode == 'short' else len(packet)
        def read():
            if mode == 'read_error':
                raise RuntimeError('CRC error')
            requests = sum(p == b'pwm' for _, p in writes)
            zero = mode != 'never' and requests >= 3
            stamp = 99.0 if mode == 'stale' else t[0]
            if requests:
                latest['LiteWingPWMObservation'] = ({
                    'available': True, 'submitted_ledc': [0 if zero else 172]*4,
                    'write_errors': 0, 'stop_errors': int(mode == 'fault'),
                }, stamp)
                latest['ActuatorCommand'] = ({
                    'Channel': ([0]*12 if zero else [84]*12),
                    'NumFailedUpdates': 0,
                }, stamp)
        result = module.stop_and_confirm(
            clock=lambda: t[0], sleep=lambda dt: t.__setitem__(0, t[0]+dt),
            write=write, read=read, latest=latest, neutral=b'neutral',
            requests=(b'pwm', b'actuator'))
        return result, writes, t[0]

    def test_repeated_requests_replace_early_nonzero_reply(self):
        result, writes, end = self.run_cleanup()
        self.assertTrue(result['confirmed_zero'], result)
        self.assertGreaterEqual(sum(p == b'pwm' for _, p in writes), 3)
        self.assertEqual(writes[0][1], b'neutral')
        self.assertLess(end, 102)
        self.assertTrue(all(p in (b'neutral', b'pwm', b'actuator') for _, p in writes))

    def test_no_zero_is_explicit_bounded_failure(self):
        result, _, end = self.run_cleanup('never')
        self.assertFalse(result['confirmed_zero'])
        self.assertEqual(result['error'], 'zero-output evidence timeout')
        self.assertLessEqual(end, 102.01)

    def test_stale_zero_does_not_count(self):
        result, _, _ = self.run_cleanup('stale')
        self.assertFalse(result['confirmed_zero'])

    def test_pwm_fault_does_not_count(self):
        result, _, _ = self.run_cleanup('fault')
        self.assertFalse(result['confirmed_zero'])

    def test_short_neutral_write_is_reported(self):
        result, writes, _ = self.run_cleanup('short')
        self.assertFalse(result['confirmed_zero'])
        self.assertIn('short cleanup write', result['error'])
        self.assertEqual(len(writes), 1)

    def test_parser_failure_is_not_silenced(self):
        result, _, _ = self.run_cleanup('read_error')
        self.assertFalse(result['confirmed_zero'])
        self.assertIn('CRC error', result['error'])
