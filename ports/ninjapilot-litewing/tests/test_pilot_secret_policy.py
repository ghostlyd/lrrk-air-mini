"""Exercise the real build policy; no IDF installation or hardware required."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1] / "esp-idf"
PREFIX = "CONFIG_ESP_COREDUMP_ENABLE_TO_"


class PilotSecretPolicyTests(unittest.TestCase):
    def run_policy(self, values):
        cmake = shutil.which("cmake")
        self.assertIsNotNone(cmake, "CMake is required for the build-policy gate")
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "policy.cmake"
            script.write_text(
                "\n".join(f"set({PREFIX}{key} {value})" for key, value in values.items())
                + f'\ninclude("{(PROJECT / "pilot_secret_policy.cmake").as_posix()}")\n',
                encoding="utf-8",
            )
            return subprocess.run([cmake, "-P", str(script)], capture_output=True,
                                  text=True, timeout=20)

    def assert_denied(self, values):
        result = self.run_policy(values)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pilot credentials require core dumps disabled", result.stderr)

    def test_accepts_explicit_none_with_disabled_outputs(self):
        for values in ({"NONE": "y"}, {"NONE": "ON", "FLASH": "OFF", "UART": "0"}):
            with self.subTest(values=values):
                result = self.run_policy(values)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_missing_or_disabled_none(self):
        for values in ({}, {"NONE": "OFF"}):
            with self.subTest(values=values):
                self.assert_denied(values)

    def test_rejects_flash_output(self):
        self.assert_denied({"FLASH": "y"})

    def test_rejects_uart_output(self):
        self.assert_denied({"UART": "y"})

    def test_none_cannot_override_enabled_output(self):
        for output in ("FLASH", "UART"):
            with self.subTest(output=output):
                self.assert_denied({"NONE": "y", output: "y"})

    def test_repository_defaults_satisfy_policy(self):
        values = {}
        for line in (PROJECT / "sdkconfig.defaults").read_text(encoding="utf-8").splitlines():
            if line.startswith(PREFIX) and "=" in line:
                name, value = line.split("=", 1)
                values[name.removeprefix(PREFIX)] = value
        result = self.run_policy(values)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
