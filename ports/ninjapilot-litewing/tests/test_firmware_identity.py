"""Wrapper identity generation must bind firmware to a clean exact commit."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "generate_wrapper_identity.py"


class FirmwareIdentityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Identity Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "identity@example.invalid"], check=True)
        (self.repo / "source.txt").write_text("reviewed\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "source.txt"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "fixture"], check=True)
        self.output = Path(self.directory.name) / "generated" / "lrrk_wrapper_identity.h"

    def run_generator(self, output=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repository", str(self.repo),
             "--output", str(output or self.output)],
            capture_output=True, text=True, timeout=10,
        )

    def test_clean_exact_commit_generates_twenty_byte_marker_and_is_idempotent(self):
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        commit = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        data = self.output.read_text()
        self.assertIn(f'LRRK_WRAPPER_COMMIT "{commit}"', data)
        marker = "LRRK" + commit[:16]
        self.assertEqual(len(marker.encode("ascii")), 20)
        self.assertIn(f'LRRK_WRAPPER_IDENTITY_MARKER "{marker}"', data)
        before = self.output.stat().st_mtime_ns
        time.sleep(0.01)
        self.assertEqual(self.run_generator().returncode, 0)
        self.assertEqual(self.output.stat().st_mtime_ns, before)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o644)

    def test_dirty_worktree_is_rejected_without_changing_existing_output(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"trusted-before\n")
        (self.repo / "source.txt").write_text("dirty\n")
        result = self.run_generator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("worktree must be clean", result.stderr)
        self.assertEqual(self.output.read_bytes(), b"trusted-before\n")

    def test_nested_repository_path_is_rejected(self):
        nested = self.repo / "nested"
        nested.mkdir()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repository", str(nested),
             "--output", str(self.output)], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact Git worktree root", result.stderr)

    def test_symlink_and_hardlink_outputs_are_rejected(self):
        target = Path(self.directory.name) / "target"
        target.write_text("do-not-change\n")
        symlink = Path(self.directory.name) / "identity-symlink.h"
        symlink.symlink_to(target)
        hardlink = Path(self.directory.name) / "identity-hardlink.h"
        os.link(target, hardlink)
        for output in (symlink, hardlink):
            with self.subTest(output=output.name):
                result = self.run_generator(output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("identity output", result.stderr)
                self.assertEqual(target.read_text(), "do-not-change\n")

    def test_esp_idf_build_generates_identity_and_orders_it_before_component_compile(self):
        cmake = (ROOT / "esp-idf/main/CMakeLists.txt").read_text()
        self.assertIn('generate_wrapper_identity.py"', cmake)
        self.assertIn("add_custom_target(lrrk_wrapper_identity", cmake)
        self.assertIn("add_dependencies(${COMPONENT_LIB} lrrk_wrapper_identity)", cmake)


if __name__ == "__main__":
    unittest.main()
