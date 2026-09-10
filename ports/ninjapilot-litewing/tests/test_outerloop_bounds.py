"""Four-axis outer-loop execution under sanitizers, without SIMPOSIX shortcuts."""
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OuterloopBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight: raise unittest.SkipTest("pinned flight checkout not supplied")
        cls.flight = Path(flight)
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        subprocess.run([sys.executable, str(ROOT / "prepare_stabilization.py"),
                        "--source", str(cls.flight / "flight/modules"),
                        "--output", str(cls.output)], check=True)
        cls.source = cls.output / "outerloop.c"
        cls.binary = cls.compile(cls.source, "outerloop")

    @classmethod
    def compile(cls, source, name, original=False):
        synth = cls.flight / "build/uavobject-synthetics/flight"
        args = ["cc", "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                "-Wno-address-of-packed-member", "-DTEST_INPUT_LIFECYCLE",
                "-fsanitize=address,bounds", "-fno-sanitize-recover=all",
                '-DMODULE_SOURCE="' + str(source) + '"']
        compiler = subprocess.run(["cc", "--version"], capture_output=True, text=True, check=True, timeout=10).stdout
        if original and "clang" not in compiler.lower():
            # GCC diagnoses the original packed quaternion's scalar-to-array
            # overread. Keep it visible, but reach the bounds negative control.
            args += ["-Wno-error=stringop-overread"]
        for path in (ROOT / "tests/outerloop_stubs", ROOT / "tests/thrust_stubs", ROOT / "target/include", synth,
                     cls.flight / "flight/uavobjects/inc", cls.flight / "flight/libraries/inc",
                     cls.flight / "flight/libraries/math", cls.flight / "flight/pios/inc",
                     cls.flight / "flight/modules/Stabilization/inc"):
            args += ["-I", str(path)]
        sources = [ROOT / "tests/outerloop_bounds_test.c", cls.flight / "flight/libraries/CoordinateConversions.c",
                   cls.flight / "flight/pios/common/pios_deltatime.c", cls.flight / "flight/libraries/math/pid.c"]
        sources += [synth / (obj + ".c") for obj in "ratedesired stabilizationdesired attitudestate stabilizationstatus flightstatus manualcontrolcommand".split()]
        binary = cls.output / name
        result = subprocess.run(args + [str(p) for p in sources] + ["-lm", "-o", str(binary)], capture_output=True, text=True, timeout=60)
        if result.returncode: raise AssertionError(result.stderr)
        return binary

    def run_case(self, case, binary=None):
        result = subprocess.run([str(binary or self.binary), case], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_rates_and_each_thrust_value_are_published_without_bounds_errors(self):
        self.run_case("direct")

    def test_attitude_pid_keeps_the_fourth_axis_in_bounds(self):
        for axis in ("roll", "pitch", "yaw"):
            with self.subTest(axis=axis): self.run_case("attitude-" + axis)

    def test_original_module_reproduces_fourth_axis_sanitizer_failure(self):
        binary = self.compile(self.flight / "flight/modules/Stabilization/outerloop.c", "original", original=True)
        for case in ("direct", "attitude-roll", "attitude-pitch", "attitude-yaw"):
            with self.subTest(case=case): self.assert_bounds_failure(binary, case)

    def assert_bounds_failure(self, binary, case):
        result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        # GCC inserts a space before [3]; Clang does not. Require the actual
        # fourth-axis diagnostic, never an arbitrary crash/compile failure.
        self.assertRegex(result.stderr, r"runtime error: index 3 out of bounds for type 'float\s*\[3\]'")

    def test_each_three_element_buffer_reversion_is_detected(self):
        code = self.source.read_text()
        for name, struct in (("stabilizationDesiredAxis", "stabilizationDesired"), ("rateDesiredAxis", "rateDesired")):
            with self.subTest(buffer=name):
                old = f"float {name}[AXES] = {{{struct}.Roll, {struct}.Pitch, {struct}.Yaw, {struct}.Thrust}};"
                new = f"float {name}[3] = {{{struct}.Roll, {struct}.Pitch, {struct}.Yaw}};"
                self.assertEqual(code.count(old), 1)
                source = self.output / (name + ".c")
                source.write_text(code.replace(old, new))
                binary = self.compile(source, name)
                self.assert_bounds_failure(binary, "direct")

    def test_omitted_output_fields_fail_behavioral_checks(self):
        code = self.source.read_text()
        for field in ("Roll", "Pitch", "Yaw", "Thrust"):
            with self.subTest(field=field):
                old = f"    rateDesired.{field} = " + (
                    "stabilizationDesired.Thrust;" if field == "Thrust" else f"rateDesiredAxis[{('Roll', 'Pitch', 'Yaw').index(field)}];")
                self.assertEqual(code.count(old), 1)
                source = self.output / ("omit-" + field + ".c")
                source.write_text(code.replace(old, "    /* omitted publication field */"))
                binary = self.compile(source, "omit-" + field)
                result = subprocess.run([str(binary), "direct"], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL:", result.stderr)

    def test_each_current_quaternion_component_is_used(self):
        code = self.source.read_text()
        old = "const float q_current[4] = {attitudeState.q1, attitudeState.q2, attitudeState.q3, attitudeState.q4};"
        self.assertEqual(code.count(old), 1)
        for component, case in ((1, "attitude-roll"), (2, "attitude-roll"), (3, "attitude-pitch"), (4, "attitude-yaw")):
            with self.subTest(component=component):
                source = self.output / f"omit-q{component}.c"
                source.write_text(code.replace(old, old.replace(f"attitudeState.q{component}", "0.0f")))
                binary = self.compile(source, f"omit-q{component}")
                result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL:", result.stderr)

    def test_mixed_modes_use_current_rpy_for_the_direct_axis(self):
        for axis in ("roll", "pitch", "yaw"):
            with self.subTest(axis=axis): self.run_case("mixed-current-" + axis)

    def test_current_rpy_all_zero_and_observable_components_are_detected(self):
        code = self.source.read_text()
        old = "const float rpy_current[3] = {attitudeState.Roll, attitudeState.Pitch, attitudeState.Yaw};"
        self.assertEqual(code.count(old), 1)
        mutations = {
            "all-zero": ("const float rpy_current[3] = {0, 0, 0};", "mixed-current-pitch"),
            "pitch-zero": (old.replace("attitudeState.Pitch", "0.0f"), "mixed-current-pitch"),
            "yaw-zero": (old.replace("attitudeState.Yaw", "0.0f"), "mixed-current-yaw"),
        }
        for name, (replacement, case) in mutations.items():
            with self.subTest(mutation=name):
                source = self.output / (name + ".c")
                source.write_text(code.replace(old, replacement))
                binary = self.compile(source, name)
                result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL:", result.stderr)

    def test_real_sdk_selects_generated_source_and_watches_inputs(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build: self.skipTest("real IDF graph not supplied")
        build = Path(build).resolve()
        commands = json.loads((build / "compile_commands.json").read_text())
        entries = [e for e in commands if Path(e["file"]).name == "outerloop.c"]
        self.assertEqual(len(entries), 1)
        selected = Path(entries[0]["file"]).resolve()
        self.assertEqual(selected, build / "esp-idf/main/litewing_stabilization/outerloop.c")
        self.assertEqual(selected.read_bytes(), self.source.read_bytes())
        result = subprocess.run([os.environ.get("LRRK_NINJA", "ninja"), "-C", str(build), "-t", "query", "build.ninja"],
                                capture_output=True, text=True, check=True, timeout=30)
        dependencies = {str(Path(line.strip().removeprefix("| ")).resolve())
                        for line in result.stdout.splitlines() if line.strip().removeprefix("| ").startswith("/")}
        for path in (ROOT / "prepare_stabilization.py", ROOT / "prepare_startup.py",
                     self.flight / "flight/modules/Stabilization/outerloop.c"):
            self.assertIn(str(path.resolve()), dependencies)

    def test_real_sdk_features_and_stack_match_host_consumer(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build: self.skipTest("real IDF graph not supplied")
        entries = json.loads((Path(build) / "compile_commands.json").read_text())
        entry = next(e for e in entries if Path(e["file"]).name == "outerloop.c")
        args = shlex.split(entry["command"])
        index = args.index("-o"); del args[index:index + 2]; args.remove("-c")
        result = subprocess.run(args + ["-dM", "-E"], cwd=entry["directory"], capture_output=True,
                                text=True, check=True, timeout=30)
        macros = {line.split()[1]: line.split(maxsplit=2)[2] if len(line.split(maxsplit=2)) > 2 else ""
                  for line in result.stdout.splitlines() if line.startswith("#define ")}
        for name in ("USE_ESP32", "PIOS_QUATERNION_STABILIZATION"):
            self.assertIn(name, macros)
        for name in ("SIMPOSIX", "REVOLUTION"):
            self.assertNotIn(name, macros)
        stack = subprocess.run([str(self.binary), "stack-bytes"], check=True, capture_output=True, text=True, timeout=5).stdout.strip()
        self.assertEqual(int(stack), int(macros["PIOS_STABILIZATION_STACK_SIZE"]))
        self.assertEqual(int(macros["AXES"]), 4)

    def test_real_sdk_rejects_original_packed_math_and_accepts_bounded_copy(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build: self.skipTest("real IDF graph not supplied")
        entries = json.loads((Path(build) / "compile_commands.json").read_text())
        entry = next(e for e in entries if Path(e["file"]).name == "outerloop.c")
        args = shlex.split(entry["command"])
        index = args.index("-o"); del args[index:index + 2]; args.remove("-c")
        args += ["-fsyntax-only", "-Werror=address-of-packed-member", "-Werror=stringop-overread"]
        result = subprocess.run(args, cwd=entry["directory"], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        original = self.flight / "flight/modules/Stabilization/outerloop.c"
        args[args.index(entry["file"])] = str(original)
        result = subprocess.run(args, cwd=entry["directory"], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error: ", result.stderr)
        self.assertIn("address-of-packed-member", result.stderr)
