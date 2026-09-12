"""Host decoding distinguishes peripheral API results from unknown outputs."""
import importlib.util
from pathlib import Path
import struct
import unittest

PATH = Path(__file__).resolve().parents[1] / 'diagnostics/pwm_observation.py'


class PwmDecodeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.exists(), 'PWM diagnostic decoder missing')
        spec = importlib.util.spec_from_file_location('pwm_decode', PATH)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def packet(self, age=0, version=1, available=1, mask=15, suppression=0):
        return struct.pack('<4I8H4B', age, 12, 2, 1,
                           80, 81, 82, 83, 164, 166, 168, 170,
                           version, available, mask, suppression)

    def test_success_and_partial_known_channels(self):
        result = self.module.decode(self.packet(mask=11, suppression=1))
        self.assertEqual(result['requested_duty'], [80,81,82,83])
        self.assertEqual(result['submitted_ledc'], [164,166,None,170])
        self.assertEqual(result['suppression'], ['hardware_unavailable'])
        self.assertEqual(result['write_errors'],2)
        self.assertNotIn('rpm', result)

    def test_unavailable_never_fabricates_zero_output(self):
        packet = struct.pack('<4I8H4B', 0xffffffff,0,0,0,*([0]*8),1,0,0,0)
        result = self.module.decode(packet)
        self.assertFalse(result['available'])
        self.assertEqual(result['submitted_ledc'],[None]*4)
        self.assertIsNone(result['requested_duty'])
        self.assertIsNone(result['suppression'])

    def test_invalid_or_stale_validity_is_rejected(self):
        for packet in (b'', self.packet()+b'\0', self.packet(version=2),
                       self.packet(available=2), self.packet(mask=16),
                       self.packet(suppression=64), self.packet(age=100)):
            with self.assertRaises(ValueError): self.module.decode(packet)


if __name__ == '__main__':
    unittest.main()
