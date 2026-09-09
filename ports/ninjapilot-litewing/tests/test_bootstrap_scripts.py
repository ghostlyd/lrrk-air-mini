import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BootstrapScriptTests(unittest.TestCase):
    def run_script(self, name, *args):
        return subprocess.run(
            [str(ROOT / name), *map(str, args)],
            cwd=str(ROOT.parent.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_shell_scripts_parse(self):
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "bootstrap.sh"), str(ROOT / "verify_source.sh"), str(ROOT / "revert.sh"), str(ROOT / "simulate.sh")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_does_not_touch_a_device(self):
        result = self.run_script("bootstrap.sh", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("WORKSPACE", result.stderr)

    def test_verify_rejects_wrong_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "NinjaPilot"
            checkout.mkdir()
            subprocess.run(["git", "-C", str(checkout), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(checkout), "remote", "add", "origin", "https://github.com/MAVProxyUser/NinjaPilot-15.02.ninja.git"], check=True)
            (checkout / "placeholder").write_text("wrong revision\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(checkout), "add", "placeholder"], check=True)
            subprocess.run(["git", "-C", str(checkout), "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "wrong"], check=True)
            result = self.run_script("verify_source.sh", checkout, Path(directory) / "patches")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source commit mismatch", result.stderr)

    def test_bootstrap_rejects_checkout_outside_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            outside = Path(directory) / "outside"
            result = self.run_script("bootstrap.sh", workspace, outside)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("inside the selected workspace", result.stderr)

    def test_simulation_requires_a_checkout(self):
        result = self.run_script("simulate.sh", "/not/a/checkout")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a Git checkout", result.stderr)


if __name__ == "__main__":
    unittest.main()
