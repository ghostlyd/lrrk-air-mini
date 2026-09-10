"""Run the actual worker and receiver; simulate RTOS, radio and flash boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class USBMaintenanceTests(unittest.TestCase):
    def test_worker_transaction_and_failure_boundaries(self):
        source = ROOT / "target/pios_litewing_usb_maintenance.c"
        self.assertTrue(source.exists(), "asynchronous maintenance worker is not implemented")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "maintenance"
            result = subprocess.run([
                "cc", "-std=c11", "-D_XOPEN_SOURCE=700", "-Wall", "-Wextra", "-Werror", "-pthread",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "tests/maintenance_stubs"),
                "-I", str(ROOT / "tests/gcs_stubs"),
                "-I", str(ROOT / "target/include"), str(source),
                str(ROOT / "target/pios_litewing_gcsrcvr.c"),
                str(ROOT / "target/litewing_wifi_config.c"),
                str(ROOT / "tests/gcs_session_unused.c"),
                str(ROOT / "tests/usb_maintenance_test.c"), "-o", str(binary),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            for case in ("success", "armed", "flight-read-error", "arm-during-stop",
                         "timeout", "rollback", "owner", "admission", "fresh-input",
                         "cleanup", "uncertain", "not-written", "invalid-store", "create-fail",
                         "getter-timeout", "getter-rollback", "final-getter-timeout"):
                with self.subTest(case=case):
                    result = subprocess.run([str(binary), case], capture_output=True,
                                            text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
