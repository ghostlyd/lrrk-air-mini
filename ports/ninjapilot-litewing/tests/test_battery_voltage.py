"""Exercise the real voltage core: scaling, invalidation, and age boundaries."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Sample(ctypes.Structure):
    _fields_ = [("millivolts", ctypes.c_uint32),
                ("captured_us", ctypes.c_int64), ("valid", ctypes.c_bool)]


class BatteryVoltageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        destination = Path(cls.directory.name) / "battery.so"
        source = ROOT / "target/litewing_battery_voltage.c"
        if not source.exists():
            return
        subprocess.run([shutil.which("cc") or "cc", "-std=c11", "-Wall", "-Wextra",
                        "-Werror", "-shared", "-fPIC", "-I", str(ROOT / "target/include"),
                        str(source), "-o", str(destination)], check=True)
        cls.lib = ctypes.CDLL(str(destination))
        cls.lib.litewing_battery_update.argtypes = [ctypes.POINTER(Sample), ctypes.c_int,
                                                   ctypes.c_bool, ctypes.c_int64]
        cls.lib.litewing_battery_read.argtypes = [ctypes.POINTER(Sample), ctypes.c_int64,
                                                 ctypes.POINTER(ctypes.c_uint32)]
        cls.lib.litewing_battery_read.restype = ctypes.c_bool

    def setUp(self):
        self.assertTrue(hasattr(self, "lib"), "battery voltage core is not implemented")
        self.sample = Sample()

    def read(self, now):
        output = ctypes.c_uint32(9999)
        valid = self.lib.litewing_battery_read(ctypes.byref(self.sample), now,
                                               ctypes.byref(output))
        return valid, output.value

    def update(self, pad_mv, calibrated=True, timestamp=1000):
        self.lib.litewing_battery_update(ctypes.byref(self.sample), pad_mv,
                                         calibrated, timestamp)

    def test_nominal_equal_resistor_divider_doubles_calibrated_pad_voltage(self):
        self.update(1950)
        self.assertEqual(self.read(1000), (True, 3900))

    def test_uninitialized_and_uncalibrated_readings_are_unknown(self):
        self.assertEqual(self.read(0), (False, 0))
        self.update(1950)
        self.update(1950, calibrated=False)
        self.assertEqual(self.read(1000), (False, 0))

    def test_age_boundary_and_future_timestamp(self):
        self.update(2100)
        self.assertEqual(self.read(501000), (True, 4200))
        self.assertEqual(self.read(501001), (False, 0))
        self.assertEqual(self.read(999), (False, 0))

    def test_invalid_inputs_clear_previous_measurement(self):
        for pad_mv, timestamp in [(-1, 1000), (0, 1000), (3301, 1000),
                                   (2147483647, 1000), (1950, -1)]:
            with self.subTest(pad_mv=pad_mv, timestamp=timestamp):
                self.update(1950)
                self.update(pad_mv, timestamp=timestamp)
                self.assertEqual(self.read(1000), (False, 0))

    def test_clock_extremes_do_not_overflow(self):
        self.update(1950, timestamp=0)
        self.assertEqual(self.read(9223372036854775807), (False, 0))
        self.assertEqual(self.read(-9223372036854775808), (False, 0))


if __name__ == "__main__":
    unittest.main()
