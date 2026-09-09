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

    def test_full_gate_requires_external_checkouts_before_idf(self):
        environment = os.environ.copy()
        environment["LRRK_BUILD_TEST"] = "1"
        environment.pop("LRRK_NINJAPILOT_ROOT", None)
        environment.pop("LRRK_OPENPILOT_ESP32_ROOT", None)
        result = subprocess.run(
            [str(ROOT / "build.sh")],
            cwd=str(ROOT.parent.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
        self.assertEqual(result.returncode, 20, result.stderr)
        self.assertIn("external checkouts not supplied", result.stderr)

    def test_full_gate_can_activate_the_manifest_pinned_local_idf(self):
        build_script = (ROOT / "build.sh").read_text(encoding="utf-8")
        self.assertIn(".toolchains/esp-idf-v5.3.2", build_script)
        self.assertIn(".toolchains/espressif", build_script)
        self.assertIn('idf_project_dir="$script_dir/esp-idf"', build_script)
        self.assertIn("ESP-IDF v5.3.2", build_script)
        self.assertIn('export NINJAPILOT_ROOT="$flight_checkout"', build_script)
        self.assertIn('export OPENPILOT_ESP32_ROOT="$reference_checkout"', build_script)
        self.assertIn("no firmware claim made", build_script)


if __name__ == "__main__":
    unittest.main()
