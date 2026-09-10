"""Native adapter failure behavior. Crypto known-answer tests are separate."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PilotMacTests(unittest.TestCase):
    def test_sdk_failures_clear_tag(self):
        source = ROOT / "target/pios_litewing_pilot_mac.c"
        self.assertTrue(source.exists(), "IDF MAC adapter is not implemented")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "mbedtls").mkdir()
            (out / "mbedtls/md.h").write_text('#include "pilot_mac_sdk.h"\n')
            binary = out / "mac-test"
            result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(out), "-I", str(ROOT / "tests"),
                "-I", str(ROOT / "target/include"), str(source),
                str(ROOT / "tests/pilot_mac_test.c"), "-o", str(binary)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
