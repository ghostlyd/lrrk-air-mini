"""Reject source drift without modifying upstream or existing build artifacts."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("Attitude", "Receiver", "Actuator")


class ControlPreparationTests(unittest.TestCase):
    def setUp(self):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            self.skipTest("pinned flight checkout not supplied")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        for module in MODULES:
            dest = self.source / module / (module.lower() + ".c")
            dest.parent.mkdir(parents=True)
            shutil.copyfile(Path(flight) / "flight/modules" / module / dest.name, dest)

    def invoke(self, destination):
        return subprocess.run([sys.executable, str(ROOT / "prepare_control.py"),
            "--source", str(self.source), "--output", str(destination)],
            capture_output=True, text=True, timeout=5)

    def test_changed_input_rejected_before_any_output_write(self):
        for module in MODULES:
            with self.subTest(module=module):
                file = self.source / module / (module.lower() + ".c")
                original = file.read_bytes()
                file.write_bytes(original + b"\n")
                output = self.root / "build"
                output.mkdir(exist_ok=True)
                for name in MODULES:
                    (output / (name.lower() + ".c")).write_text("preserve " + name)
                result = self.invoke(output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(module + "/" + module.lower() + ".c", result.stderr)
                for name in MODULES:
                    self.assertEqual((output / (name.lower() + ".c")).read_text(), "preserve " + name)
                file.write_bytes(original)

    def test_noop_does_not_rewrite_outputs_or_sources(self):
        output = self.root / "build"
        before = {p: p.read_bytes() for p in self.source.rglob("*.c")}
        self.assertEqual(self.invoke(output).returncode, 0)
        self.assertEqual({p.name for p in output.iterdir()}, {name.lower() + ".c" for name in MODULES})
        times = {p: p.stat().st_mtime_ns for p in output.iterdir()}
        self.assertEqual(self.invoke(output).returncode, 0)
        self.assertEqual(times, {p: p.stat().st_mtime_ns for p in output.iterdir()})
        self.assertEqual(before, {p: p.read_bytes() for p in self.source.rglob("*.c")})

    def test_source_subtree_cannot_be_used_as_output(self):
        for output in (self.source, self.source / "generated"):
            self.assertNotEqual(self.invoke(output).returncode, 0)
        self.assertFalse((self.source / "receiver.c").exists())
        self.assertFalse((self.source / "generated").exists())
