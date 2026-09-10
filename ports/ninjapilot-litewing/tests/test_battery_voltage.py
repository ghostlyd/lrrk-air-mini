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

    def test_voltage_export_reaches_host_without_inventing_other_measurements(self):
        import math
        import struct
        import sys
        from datetime import datetime, timezone
        sys.path.insert(0, str(ROOT.parents[1] / "ai_assistant/src"))
        from lrrk_litewing_ai.uavobjects import BATTERY_STATE, snapshot_from_frame
        from lrrk_litewing_ai.uavtalk import UAVTalkFrame

        self.assertTrue(hasattr(self.lib, "litewing_battery_export"),
                        "battery telemetry field exporter is missing")
        export = self.lib.litewing_battery_export
        export.argtypes = [ctypes.POINTER(Sample), ctypes.c_int64,
                           ctypes.POINTER(ctypes.c_float)]
        self.update(1950)
        for now, expected in ((1000, 3.9), (501001, None)):
            fields = (ctypes.c_float * 7)()
            export(ctypes.byref(self.sample), now, fields)
            self.assertTrue(all(math.isnan(value) for value in fields[1:]))
            packet = UAVTalkFrame(0x20, BATTERY_STATE, 0, None,
                                  struct.pack("<7f2B", *fields, 1, 0))
            result = snapshot_from_frame(packet, datetime.now(timezone.utc))
            if expected is None:
                self.assertIsNone(result.battery.voltage_v)
            else:
                self.assertAlmostEqual(result.battery.voltage_v, expected, places=5)
            self.assertIsNone(result.battery.current_a)
            self.assertIsNone(result.battery.percent)

    def process_dma(self, words=None, *, captured=1000, now=1000, failure_at=None,
                    converted=None):
        self.assertTrue(hasattr(self.lib, "litewing_battery_process_dma"),
                        "ADC batch processing is missing")
        callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                                        ctypes.POINTER(ctypes.c_int))
        def calibrate(context, raw, output):
            if raw == failure_at:
                return -1
            # Nonlinear test calibration: averaging raw counts first is wrong.
            output[0] = converted if converted is not None else raw * raw
            return 0
        callback = callback_type(calibrate)
        values = [0x2000 | 40] * 16 if words is None else words
        data = (ctypes.c_uint32 * len(values))(*values)
        process = self.lib.litewing_battery_process_dma
        process.argtypes = [ctypes.POINTER(Sample), ctypes.POINTER(ctypes.c_uint32),
                            ctypes.c_size_t, ctypes.c_int64, ctypes.c_int64,
                            callback_type, ctypes.c_void_p]
        process.restype = ctypes.c_bool
        return process(ctypes.byref(self.sample), data, len(values), captured, now,
                       callback, None)

    def test_dma_calibrates_each_sample_before_averaging(self):
        # Eight 40-count and eight 42-count samples: calibrated average 1682mV.
        self.assertTrue(self.process_dma([0x2028] * 8 + [0x202A] * 8))
        self.assertEqual(self.read(1000), (True, 3364))

    def test_dma_wrong_unit_channel_or_clipping_invalidates_entire_batch(self):
        for bad in (0x22028, 0x4028, 0x2000, 0x2FFF):
            for index in (0, 15):
                with self.subTest(bad=bad, index=index):
                    self.update(1950)
                    words = [0x2028] * 16
                    words[index] = bad
                    self.assertFalse(self.process_dma(words))
                    self.assertEqual(self.read(1000), (False, 0))

    def test_dma_rejects_partial_oversize_and_failed_calibration(self):
        for size in (0, 1, 15, 17, 64):
            self.update(1950)
            self.assertFalse(self.process_dma([0x2028] * size))
            self.assertEqual(self.read(1000), (False, 0))
        self.update(1950)
        self.assertFalse(self.process_dma([0x2028] * 15 + [0x202A], failure_at=42))
        self.assertEqual(self.read(1000), (False, 0))

    def test_dma_rejects_invalid_calibration_output(self):
        for value in (-1, 0, 3301, 2147483647):
            self.update(1950)
            self.assertFalse(self.process_dma(converted=value))
            self.assertEqual(self.read(1000), (False, 0))

    def test_dma_retains_acquisition_time_and_rejects_old_or_future_batches(self):
        self.assertTrue(self.process_dma(captured=1000, now=501000))
        self.assertEqual(self.read(501001), (False, 0))
        for captured, now in ((1000, 501001), (1001, 1000), (-1, 1000)):
            self.update(1950)
            self.assertFalse(self.process_dma(captured=captured, now=now))
            self.assertEqual(self.read(1000), (False, 0))


if __name__ == "__main__":
    unittest.main()
