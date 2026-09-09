"""Narrow characterization: current pinned counter/monitor integration has no warm-up validity.

This is evidence for issue27, NOT a readiness gate or an acceptance of the bug.
Replace the characterization with validity/consumer tests when that fix lands.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FLIGHT_PIN = "ac77304a58de6c8bd552f94668b46903adb71cb2"
REFERENCE_PIN = "7233c97f844c0377930bcdf22998e289638b64c6"


class StartupRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        reference = os.environ.get("LRRK_TEST_REFERENCE_ROOT")
        if not flight or not reference:
            raise unittest.SkipTest("both pinned source trees must be supplied")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        output = Path(cls.directory.name)
        # Compile bytes from immutable Git objects, not a possibly modified file.
        def pinned(root, pin, path):
            head = subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True).strip()
            if head != pin:
                raise AssertionError("wrong pinned source revision")
            data = subprocess.check_output(["git", "-C", root, "show", pin + ":" + path])
            file = output / Path(path).name
            file.write_bytes(data)
            return file
        runtime = pinned(reference, REFERENCE_PIN, "pios/esp32/pios_task_runtime.c")
        monitor = pinned(flight, FLIGHT_PIN, "flight/pios/common/pios_task_monitor.c")
        pinned(flight, FLIGHT_PIN, "flight/pios/inc/pios_task_monitor.h")
        cls.binary = output / "startup-runtime"
        cls.mutant = output / "runtime-zero-delta"
        def compile_binary(destination):
            args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "tests/startup_stubs"), "-I", str(output),
                '-DRUNTIME_SOURCE="' + str(runtime) + '"',
                '-DMONITOR_SOURCE="' + str(monitor) + '"',
                str(ROOT / "tests/startup_runtime_test.c"), "-o", str(destination)]
            result = subprocess.run(args, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise AssertionError(result.stderr)
        compile_binary(cls.binary)
        # A lost runtime delta must be caught, not silently pass this fixture.
        code = runtime.read_text()
        old = "return (UBaseType_t)delta;"
        if code.count(old) != 1:
            raise AssertionError("runtime mutation anchor changed")
        runtime.write_text(code.replace(old, "return (UBaseType_t)(delta * 0);"))
        compile_binary(cls.mutant)

    def run_case(self, case, expected):
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), expected)

    def test_first_baseline_cannot_distinguish_later_loads(self):
        for case, expected in (("20", "first_idle=0 second_idle=20"),
                               ("50", "first_idle=0 second_idle=50"),
                               ("80", "first_idle=0 second_idle=80")):
            with self.subTest(case=case): self.run_case(case, expected)

    def test_missing_snapshot_is_indistinguishable_from_zero_idle(self):
        self.run_case("missing-idle", "first_idle=0 second_idle=0")

    def test_matching_counter_wrap_preserves_delta(self):
        self.run_case("wrap", "first_idle=0 second_idle=50")

    def test_zero_delta_mutation_is_rejected(self):
        result = subprocess.run([str(self.mutant), "50"], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("second == percent", result.stderr)
