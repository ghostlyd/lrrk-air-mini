"""Source identity, destination separation and no-op generation contracts."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = "a89228f3c6a3700cccb41b35bcf886672e901c6b18c6c851f11fcbeeaa9bb314"


class StabilizationPreparationTests(unittest.TestCase):
    def setUp(self):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight: self.skipTest("pinned flight checkout not supplied")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.source = self.base / "modules"
        self.input = self.source / "Stabilization/outerloop.c"
        self.input.parent.mkdir(parents=True)
        shutil.copyfile(Path(flight) / "flight/modules/Stabilization/outerloop.c", self.input)
        self.output = self.base / "generated"

    def prepare(self, source=None, output=None):
        return subprocess.run([sys.executable, str(ROOT / "prepare_stabilization.py"),
                               "--source", str(source or self.source), "--output", str(output or self.output)],
                              capture_output=True, text=True, timeout=10)

    def test_pinned_input_is_unchanged_and_generation_is_idempotent(self):
        before = self.input.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), PIN)
        result = self.prepare(); self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.output / "outerloop.c"
        text = generated.read_text()
        self.assertIn("GNU General Public License", text)
        self.assertIn("float stabilizationDesiredAxis[AXES]", text)
        self.assertIn("float rateDesiredAxis[AXES]", text)
        self.assertIn("rateDesired.Thrust = stabilizationDesired.Thrust;", text)
        mtime = generated.stat().st_mtime_ns
        result = self.prepare(); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(generated.stat().st_mtime_ns, mtime)
        self.assertEqual(self.input.read_bytes(), before)
        self.assertEqual([p.name for p in self.output.iterdir()], ["outerloop.c"])

    def test_changed_source_is_rejected_without_partial_writes(self):
        self.output.mkdir()
        sentinel = self.output / "outerloop.c"; sentinel.write_text("preserve me")
        self.input.write_bytes(self.input.read_bytes() + b"\n/* drift */\n")
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unreviewed stabilization input", result.stderr)
        self.assertEqual(sentinel.read_text(), "preserve me")

    def test_missing_source_is_rejected_without_creating_output(self):
        self.input.unlink()
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_source_and_ancestor_destinations_are_rejected(self):
        before = self.input.read_bytes()
        for path in (self.source, self.source / "generated", self.base):
            with self.subTest(path=path):
                result = self.prepare(output=path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("output must be separate", result.stderr)
        self.assertEqual(self.input.read_bytes(), before)

    def test_input_symlink_escape_is_rejected(self):
        outside = self.base / "outside.c"
        self.input.rename(outside); self.input.symlink_to(outside)
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("input escapes", result.stderr)
        self.assertFalse(self.output.exists())

    def test_output_symlink_cannot_overwrite_input(self):
        before = self.input.read_bytes()
        self.output.mkdir(); (self.output / "outerloop.c").symlink_to(self.input)
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not be a symlink", result.stderr)
        self.assertEqual(self.input.read_bytes(), before)

    def test_output_hardlink_cannot_overwrite_input(self):
        before = self.input.read_bytes()
        self.output.mkdir(); os.link(self.input, self.output / "outerloop.c")
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not be a hardlink", result.stderr)
        self.assertEqual(self.input.read_bytes(), before)

    def test_nonregular_output_is_rejected(self):
        before = self.input.read_bytes()
        self.output.mkdir(); (self.output / "outerloop.c").mkdir()
        result = self.prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a regular file", result.stderr)
        self.assertEqual(self.input.read_bytes(), before)
