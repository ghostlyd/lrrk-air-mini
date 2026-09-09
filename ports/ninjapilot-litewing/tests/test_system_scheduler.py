"""Real System caller must stop on errors from the real adapted scheduler."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SystemSchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight tree not supplied")
        flight = Path(flight)
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        output = Path(cls.directory.name)
        subprocess.run([sys.executable, str(ROOT / "prepare_scheduler.py"),
            "--source", str(flight / "flight"), "--output", str(output)],
            check=True, capture_output=True, text=True, timeout=5)
        if os.environ.get("LRRK_TEST_ORIGINAL_SYSTEM") == "1":
            shutil.copyfile(flight / "flight/modules/System/systemmod.c", output / "systemmod.c")
            # Only the original source keeps its source-relative include.
            (output / "inc").mkdir()
            shutil.copyfile(flight / "flight/modules/System/inc/systemmod.h", output / "inc/systemmod.h")
        cls.binary = output / "system-scheduler"
        args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-address-of-packed-member", "-ftrivial-auto-var-init=pattern"]
        for include in (ROOT / "tests/scheduler_stubs", ROOT / "tests/thrust_stubs", ROOT / "target/include",
                        flight / "flight/modules/System/inc", flight / "build/uavobject-synthetics/flight",
                        flight / "flight/pios/inc", flight / "flight/libraries/inc",
                        flight / "flight/uavobjects/inc"):
            args += ["-I", str(include)]
        args += [str(output / "pios_callbackscheduler.c"), str(output / "systemmod.c"),
                 str(ROOT / "tests/system_scheduler_test.c"), "-o", str(cls.binary)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def test_failed_scheduler_start_stops_system_before_normal_boot_work(self):
        for name in ("task", "monitor"):
            with self.subTest(name=name):
                result = subprocess.run([str(self.binary), name], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_nominal_system_starts_scheduler_and_reaches_monitoring_loop(self):
        result = subprocess.run([str(self.binary), "nominal"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_system_ignoring_scheduler_error_fails_regression(self):
        result = subprocess.run([sys.executable, "-m", "unittest",
            "test_system_scheduler.SystemSchedulerTests.test_failed_scheduler_start_stops_system_before_normal_boot_work"],
            cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_ORIGINAL_SYSTEM="1"),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED (failures=2)", result.stderr)
        self.assertIn("shutdowns == 1 && fault_alarms == 1 && system_deletes == 1", result.stderr)
