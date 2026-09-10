"""Checked inner-loop initialization against real generated UAVObjects."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InnerloopStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight checkout not supplied")
        cls.flight = Path(flight)
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        subprocess.run([sys.executable, str(ROOT / "prepare_stabilization.py"),
                        "--source", str(cls.flight / "flight/modules"),
                        "--output", str(cls.output)], check=True)
        cls.binary = cls.compile(cls.output / "innerloop.c", "innerloop")

    @classmethod
    def compile(cls, source, name):
        synth = cls.flight / "build/uavobject-synthetics/flight"
        args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                "-Wno-address-of-packed-member", "-DTEST_INPUT_LIFECYCLE",
                '-DMODULE_SOURCE="' + str(source) + '"']
        for path in (ROOT / "tests/outerloop_stubs", ROOT / "tests/thrust_stubs",
                     ROOT / "target/include", synth,
                     cls.flight / "flight/uavobjects/inc", cls.flight / "flight/libraries/inc",
                     cls.flight / "flight/libraries/math", cls.flight / "flight/pios/inc",
                     cls.flight / "flight/modules/Stabilization/inc"):
            args += ["-I", str(path)]
        sources = [ROOT / "tests/innerloop_startup_test.c",
                   cls.flight / "flight/pios/common/pios_deltatime.c",
                   cls.flight / "flight/libraries/math/pid.c"]
        objects = "ratedesired actuatordesired gyrostate stabilizationstatus flightstatus manualcontrolcommand stabilizationdesired stabilizationbank"
        sources += [synth / (name + ".c") for name in objects.split()]
        binary = cls.output / name
        result = subprocess.run(args + [str(path) for path in sources] + ["-lm", "-o", str(binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    def run_case(self, case, binary=None, success=True):
        result = subprocess.run([str(binary or self.binary), case], capture_output=True,
                                text=True, timeout=5)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL:", result.stderr)

    def test_each_object_registration_failure_stops_before_scheduler_creation(self):
        for index in range(1, 8):
            with self.subTest(object=index): self.run_case("object-" + str(index))

    def test_scheduler_callback_and_initial_schedule_failures_propagate(self):
        for case in ("scheduler", "callback", "schedule"):
            with self.subTest(case=case): self.run_case(case)

    def test_existing_objects_succeed_and_initialization_is_one_shot(self):
        self.run_case("existing")
        self.run_case("nominal")

    def test_omitted_initialization_checks_are_detected(self):
        code = (self.output / "innerloop.c").read_text()
        mutations = {
            "object-result": ("if (!RateDesiredHandle() && (RateDesiredInitialize() != 0 || !RateDesiredHandle())) return -1;",
                              "(void)RateDesiredInitialize();", "object-1"),
            "scheduler-result": ("if (!callbackHandle) return -1;", "if (!callbackHandle && false) return -1;", "scheduler"),
            "callback-result": ("if (GyroStateConnectCallback(GyroStateUpdatedCb) != 0) return -1;",
                                "if (GyroStateConnectCallback(GyroStateUpdatedCb) != 0 && false) return -1;", "callback"),
            "schedule-result": ("CALLBACK_UPDATEMODE_LATER) != 1) return -1;",
                                "CALLBACK_UPDATEMODE_LATER) != 1 && false) return -1;", "schedule"),
            "one-shot": ("if (innerloopInitAttempted) return -1;",
                         "if (innerloopInitAttempted && false) return -1;", "nominal"),
        }
        for name, (old, new, case) in mutations.items():
            with self.subTest(mutant=name):
                self.assertEqual(code.count(old), 1, name)
                source = self.output / (name + ".c")
                source.write_text(code.replace(old, new))
                binary = self.compile(source, name)
                self.run_case(case, binary, success=False)
