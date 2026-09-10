"""Compile real native adapter; fake only ESP-IDF/RTOS boundaries, no hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeBatteryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        out = Path(cls.directory.name)
        for name in ("esp_adc/adc_continuous.h", "esp_adc/adc_cali.h",
                     "esp_adc/adc_cali_scheme.h", "esp_timer.h",
                     "freertos/FreeRTOS.h", "freertos/task.h"):
            header = out / name
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text('#include "battery_sdk.h"\n')
        cls.binary = out / "battery-native"
        result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-I", str(out), "-I", str(ROOT / "tests"),
                        "-I", str(ROOT / "target/include"),
                        str(ROOT / "tests/battery_native_test.c"),
                        str(ROOT / "target/pios_litewing_battery.c"),
                        str(ROOT / "target/litewing_battery_voltage.c"),
                        "-o", str(cls.binary)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def test_native_lifecycle_and_acquisition(self):
        for case in ("success", "mapping", "allocate", "configure", "calibration-init",
                     "callbacks", "cleanup", "core", "task", "partial", "timeout",
                     "overflow", "conversion", "stop"):
            with self.subTest(case=case):
                result = subprocess.run([str(self.binary), case], capture_output=True,
                                        text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "PASS")
