import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExternalSourceVerifierTests(unittest.TestCase):
    def test_verifier_help_is_available_without_network(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "verify_external_sources.py"), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--flight", result.stdout)
        self.assertIn("--reference", result.stdout)


if __name__ == "__main__":
    unittest.main()
