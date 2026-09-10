"""Source identity, destination separation and no-op generation contracts."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from itertools import product

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "stabilization.c": "0bf808ebe597aa76abefbe026e1d40ade38ec2fe5645400aac7ea6cd2b347918",
    "outerloop.c": "a89228f3c6a3700cccb41b35bcf886672e901c6b18c6c851f11fcbeeaa9bb314",
    "innerloop.c": "9de7fe11cba25a25e226414471d10001824c07e5345cfcfe763960a2eae0d1b9",
}


class StabilizationPreparationTests(unittest.TestCase):
    def setUp(self):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight: self.skipTest("pinned flight checkout not supplied")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.source = self.base / "modules"
        self.input = self.source / "Stabilization"
        self.input.mkdir(parents=True)
        for name in PINS:
            shutil.copyfile(Path(flight) / "flight/modules/Stabilization" / name,
                            self.input / name)
        self.output = self.base / "generated"

    def prepare(self, source=None, output=None):
        return subprocess.run([sys.executable, str(ROOT / "prepare_stabilization.py"),
                               "--source", str(source or self.source), "--output", str(output or self.output)],
                              capture_output=True, text=True, timeout=10)

    def test_pinned_input_is_unchanged_and_generation_is_idempotent(self):
        before = {name: (self.input / name).read_bytes() for name in PINS}
        self.assertEqual({name: hashlib.sha256(data).hexdigest()
                          for name, data in before.items()}, PINS)
        result = self.prepare(); self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.output / "outerloop.c"
        text = generated.read_text()
        self.assertIn("GNU General Public License", text)
        self.assertIn("float stabilizationDesiredAxis[AXES]", text)
        self.assertIn("float rateDesiredAxis[AXES]", text)
        self.assertIn("rateDesired.Thrust = stabilizationDesired.Thrust;", text)
        for name in PINS:
            self.assertIn("GNU General Public License", (self.output / name).read_text())
        mtimes = {name: (self.output / name).stat().st_mtime_ns for name in PINS}
        result = self.prepare(); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({name: (self.output / name).stat().st_mtime_ns for name in PINS}, mtimes)
        self.assertEqual({name: (self.input / name).read_bytes() for name in PINS}, before)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), sorted(PINS))

    def test_each_changed_source_is_rejected_without_partial_writes(self):
        for name in PINS:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "modules"
                output = Path(directory) / "generated"
                shutil.copytree(self.source, source)
                output.mkdir()
                for item in PINS: (output / item).write_text("preserve " + item)
                (source / "Stabilization" / name).write_bytes(
                    (source / "Stabilization" / name).read_bytes() + b"\n/* drift */\n")
                result = self.prepare(source=source, output=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unreviewed stabilization input", result.stderr)
                self.assertEqual({item: (output / item).read_text() for item in PINS},
                                 {item: "preserve " + item for item in PINS})

    def test_each_missing_source_is_rejected_without_creating_output(self):
        for name in PINS:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "modules"
                output = Path(directory) / "generated"
                shutil.copytree(self.source, source)
                (source / "Stabilization" / name).unlink()
                result = self.prepare(source=source, output=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())

    def test_source_and_ancestor_destinations_are_rejected(self):
        before = {name: (self.input / name).read_bytes() for name in PINS}
        for path in (self.source, self.source / "generated", self.base):
            with self.subTest(path=path):
                result = self.prepare(output=path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("output must be separate", result.stderr)
        self.assertEqual({name: (self.input / name).read_bytes() for name in PINS}, before)

    def test_each_input_symlink_escape_is_rejected(self):
        for name in PINS:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "modules"
                output = Path(directory) / "generated"
                outside = Path(directory) / name
                shutil.copytree(self.source, source)
                path = source / "Stabilization" / name
                path.rename(outside); path.symlink_to(outside)
                result = self.prepare(source=source, output=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("input escapes", result.stderr)
                self.assertFalse(output.exists())

    def test_each_aliased_or_nonregular_output_is_rejected_before_any_write(self):
        for kind, name in product(("symlink", "hardlink", "directory"), PINS):
            with self.subTest(kind=kind, output=name), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "modules"
                output = Path(directory) / "generated"
                shutil.copytree(self.source, source)
                output.mkdir()
                for item in PINS: (output / item).write_text("preserve " + item)
                target = output / name
                target.unlink()
                if kind == "symlink": target.symlink_to(source / "Stabilization" / name)
                elif kind == "hardlink": os.link(source / "Stabilization" / name, target)
                else: target.mkdir()
                before = {item: (source / "Stabilization" / item).read_bytes() for item in PINS}
                result = self.prepare(source=source, output=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("output file must", result.stderr)
                self.assertEqual({item: (source / "Stabilization" / item).read_bytes()
                                  for item in PINS}, before)
                for item in PINS:
                    if item != name: self.assertEqual((output / item).read_text(), "preserve " + item)
