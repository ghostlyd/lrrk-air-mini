from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BatteryWorkerTests(unittest.TestCase):
    def test_startup_and_publication(self):
        source = ROOT / "target/litewing_battery_module.c"
        self.assertTrue(source.exists(), "battery worker is not implemented")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for name in ("openpilot.h", "flightbatterystate.h", "esp_timer.h", "uavobjectmanager.h",
                         "freertos/FreeRTOS.h", "freertos/task.h"):
                header = out / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text('#include "battery_worker_sdk.h"\n')
            binary = out / "worker"
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread",
                            "-I", str(out), "-I", str(ROOT / "tests"),
                            "-I", str(ROOT / "target/include"),
                            str(ROOT / "tests/battery_worker_test.c"), str(source),
                            str(ROOT / "target/litewing_battery_voltage.c"),
                            str(ROOT / "target/litewing_battery_pack.c"),
                            "-o", str(binary)], capture_output=True, text=True, check=True)
            for case in ("success", "handle", "get-meta", "set-meta", "initial-publish",
                         "create", "adc-init", "read", "stale", "runtime-publish"):
                with self.subTest(case=case):
                    result = subprocess.run([str(binary), case], capture_output=True,
                                            text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), "PASS")
