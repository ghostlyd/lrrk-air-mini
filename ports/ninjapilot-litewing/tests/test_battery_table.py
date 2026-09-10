from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BatteryTableTests(unittest.TestCase):
    def test_real_module_table_propagates_battery_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "table"
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "target/include"),
                            str(ROOT / "tests/battery_table_test.c"),
                            str(ROOT / "target/firmware/InitMods.c"),
                            "-o", str(binary)], check=True, capture_output=True, text=True)
            for case in ("success", "init-fail", "start-fail"):
                with self.subTest(case=case):
                    result = subprocess.run([str(binary), case], capture_output=True,
                                            text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), "PASS")
