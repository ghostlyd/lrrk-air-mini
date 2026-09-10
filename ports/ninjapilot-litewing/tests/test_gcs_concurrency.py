from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GcsConcurrencyTests(unittest.TestCase):
    def test_delayed_competing_writer_does_not_resurrect_expired_input(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "gcs-concurrency"
            result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread",
                "-I", str(ROOT / "tests/gcs_stubs"), "-I", str(ROOT / "target/include"),
                str(ROOT / "target/pios_litewing_gcsrcvr.c"),
                str(ROOT / "tests/gcs_session_unused.c"),
                str(ROOT / "tests/gcs_concurrency_test.c"), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
