"""Scheduler generation must preserve pinned sources and reject unsafe paths."""
import os
import json
from itertools import product
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ("pios/common/pios_callbackscheduler.c", "modules/System/systemmod.c",
          "modules/ManualControl/manualcontrol.c")
OUTPUTS = ("pios_callbackscheduler.c", "systemmod.c", "manualcontrol.c")


class SchedulerPreparationTests(unittest.TestCase):
    def setUp(self):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            self.skipTest("pinned flight tree not supplied")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source, self.output = self.root / "source", self.root / "build"
        self.output.mkdir()
        for name in INPUTS:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(flight) / "flight" / name, path)
        for name in OUTPUTS:
            (self.output / name).write_text("keep " + name)

    def invoke(self, output=None):
        return subprocess.run([sys.executable, str(ROOT / "prepare_scheduler.py"),
            "--source", str(self.source), "--output", str(output or self.output)],
            capture_output=True, text=True, timeout=5)

    def test_valid_repeat_preserves_source_and_output_timestamps(self):
        before = {n: (self.source / n).read_bytes() for n in INPUTS}
        self.assertEqual(self.invoke().returncode, 0)
        times = {n: (self.output / n).stat().st_mtime_ns for n in OUTPUTS}
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(before, {n: (self.source / n).read_bytes() for n in INPUTS})
        self.assertEqual(times, {n: (self.output / n).stat().st_mtime_ns for n in OUTPUTS})

    def test_any_drifted_source_prevents_all_writes(self):
        for name in INPUTS:
            with self.subTest(name=name):
                path = self.source / name
                before = path.read_bytes()
                path.write_bytes(before + b"\n")
                self.assertEqual(self.invoke().returncode, 1)
                for out in OUTPUTS: self.assertEqual((self.output / out).read_text(), "keep " + out)
                path.write_bytes(before)

    def test_source_subtree_or_ancestor_cannot_be_output(self):
        for path in (self.source, self.source / "generated", self.root):
            with self.subTest(path=path): self.assertEqual(self.invoke(path).returncode, 1)

    def test_input_and_output_aliases_rejected_before_writes(self):
        for direction, name in product(("input-file", "input-directory", "output-symlink", "output-hardlink"), INPUTS):
            with self.subTest(direction=direction, source=name), tempfile.TemporaryDirectory() as directory:
                source, output = Path(directory) / "source", Path(directory) / "build"
                shutil.copytree(self.source, source)
                output.mkdir()
                for item in INPUTS: shutil.copyfile(source / item, output / Path(item).name)
                original = {n: (source / n).read_bytes() for n in INPUTS}
                target = source / name
                out = output / Path(name).name
                if direction == "input-file":
                    target.unlink()
                    target.symlink_to(out)
                elif direction == "input-directory":
                    target.unlink()
                    target.parent.rmdir()
                    target.parent.symlink_to(output, target_is_directory=True)
                else:
                    out.unlink()
                    if direction == "output-symlink": out.symlink_to(target)
                    else: os.link(target, out)
                result = subprocess.run([sys.executable, str(ROOT / "prepare_scheduler.py"),
                    "--source", str(source), "--output", str(output)], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(original, {n: (source / n).read_bytes() for n in INPUTS})
                self.assertEqual((output / OUTPUTS[0]).read_bytes(), original[INPUTS[0]])


class SchedulerBuildSelectionTests(unittest.TestCase):
    def test_real_manualcontrol_feature_selection_matches_initializer_fixture(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build:
            self.skipTest("real generated IDF compile command not supplied")
        commands = json.loads((Path(build) / "compile_commands.json").read_text())
        command = next(entry for entry in commands if Path(entry["file"]).name == "manualcontrol.c")
        args = shlex.split(command["command"])
        output_index = args.index("-o")
        del args[output_index:output_index + 2]
        args.remove("-c")
        result = subprocess.run(args + ["-dM", "-E"], cwd=command["directory"],
            capture_output=True, text=True, check=True, timeout=30)
        macros = {line.split()[1] for line in result.stdout.splitlines() if line.startswith("#define ")}
        self.assertIn("USE_ESP32", macros)
        self.assertNotIn("PIOS_EXCLUDE_ADVANCED_FEATURES", macros,
            "ManualControl initializer fixture must match the firmware feature selection")

    def test_real_firmware_graph_selects_and_watches_adapted_scheduler(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build:
            self.skipTest("real generated IDF build graph not supplied")
        build = Path(build).resolve()
        commands = json.loads((build / "compile_commands.json").read_text())
        for name in OUTPUTS:
            with self.subTest(source=name):
                selected = [Path(entry["file"]).resolve() for entry in commands
                            if Path(entry["file"]).name == name]
                expected = build / "esp-idf/main/litewing_scheduler" / name
                self.assertEqual(selected, [expected])
                self.assertTrue(expected.is_file())
        configure = next(line for line in (build / "build.ninja").read_text().splitlines()
                         if line.startswith("build build.ninja") and ": RERUN_CMAKE " in line)
        for dependency in ("prepare_scheduler.py", "prepare_startup.py",
                           "scheduler_start.inc", "scheduler_create.inc", "system_start.inc", *INPUTS):
            with self.subTest(dependency=dependency):
                self.assertTrue(dependency in configure, "missing configure dependency: " + dependency)
