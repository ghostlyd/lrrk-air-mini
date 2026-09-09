"""Startup source drift/output aliasing must not rewrite inputs or old outputs."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ("libraries/alarms.c", "uavobjects/eventdispatcher.c")
OUTPUTS = ("alarms.c", "eventdispatcher.c")


class StartupPreparationTests(unittest.TestCase):
    def setUp(self):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            self.skipTest("pinned flight checkout not supplied")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        for name in INPUTS:
            dest = self.source / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(flight) / "flight" / name, dest)

    def invoke(self, output):
        return subprocess.run([sys.executable, str(ROOT / "prepare_startup.py"),
            "--source", str(self.source), "--output", str(output)],
            capture_output=True, text=True, timeout=5)

    def test_source_drift_is_rejected_before_any_output_changes(self):
        output = self.root / "build"
        output.mkdir()
        for name in OUTPUTS:
            (output / name).write_text("preserve " + name)
        for name in INPUTS:
            with self.subTest(input=name):
                source = self.source / name
                original = source.read_bytes()
                source.write_bytes(original + b"\n")
                self.assertEqual(self.invoke(output).returncode, 1)
                for target in OUTPUTS:
                    self.assertEqual((output / target).read_text(), "preserve " + target)
                source.write_bytes(original)

    def test_repeat_generation_preserves_input_bytes_and_output_mtimes(self):
        before = {name: (self.source / name).read_bytes() for name in INPUTS}
        output = self.root / "build"
        self.assertEqual(self.invoke(output).returncode, 0)
        times = {name: (output / name).stat().st_mtime_ns for name in OUTPUTS}
        self.assertEqual(self.invoke(output).returncode, 0)
        self.assertEqual(times, {name: (output / name).stat().st_mtime_ns for name in OUTPUTS})
        self.assertEqual(before, {name: (self.source / name).read_bytes() for name in INPUTS})

    def test_source_subtree_or_ancestor_is_not_an_output_directory(self):
        for output in (self.source, self.source / "generated", self.root):
            with self.subTest(output=output):
                self.assertEqual(self.invoke(output).returncode, 1)
                self.assertFalse((output / "alarms.c").exists())

    def test_symlink_and_hardlink_outputs_are_rejected_before_any_write(self):
        for alias in ("symlink", "hardlink"):
            with self.subTest(alias=alias):
                output = self.root / alias
                output.mkdir()
                (output / "alarms.c").write_text("preserve earlier output")
                external = self.source / INPUTS[1]
                original = external.read_bytes()
                if alias == "symlink":
                    (output / "eventdispatcher.c").symlink_to(external)
                else:
                    os.link(external, output / "eventdispatcher.c")
                self.assertEqual(self.invoke(output).returncode, 1)
                self.assertEqual((output / "alarms.c").read_text(), "preserve earlier output")
                self.assertEqual(external.read_bytes(), original)


class StartupBuildSelectionTests(unittest.TestCase):
    def test_real_generated_firmware_graph_selects_adapted_services(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build:
            self.skipTest("real generated IDF build graph not supplied")
        build = Path(build).resolve()
        commands = json.loads((build / "compile_commands.json").read_text())
        for name in OUTPUTS:
            with self.subTest(service=name):
                selected = [Path(entry["file"]).resolve() for entry in commands
                            if Path(entry["file"]).name == name]
                expected = build / "esp-idf/main/litewing_startup" / name
                self.assertEqual(selected, [expected])
                self.assertTrue(expected.is_file())
