import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildScriptTests(unittest.TestCase):
    def test_host_only_gate_passes_without_idf(self):
        environment = os.environ.copy()
        environment["LRRK_BUILD_TEST"] = "1"
        result = subprocess.run(
            [str(ROOT / "build.sh"), "--host-only"],
            cwd=str(ROOT.parent.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HOST_GATES=PASS", result.stdout)
        self.assertIn("ESP_IDF_BUILD=SKIPPED", result.stdout)


if __name__ == "__main__":
    unittest.main()
