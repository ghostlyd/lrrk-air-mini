"""Checked top-level Stabilization lifecycle and explicit module-table propagation."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StabilizationStartupTests(unittest.TestCase):
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
        cls.binary = cls.compile(cls.output / "stabilization.c", "stabilization")

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
        sources = [ROOT / "tests/stabilization_startup_test.c",
                   ROOT / "target/firmware/InitMods.c",
                   cls.flight / "flight/libraries/math/pid.c"]
        objects = "stabilizationdesired stabilizationsettings stabilizationstatus stabilizationbank stabilizationsettingsbank1 stabilizationsettingsbank2 stabilizationsettingsbank3 ratedesired manualcontrolcommand relaytuningsettings relaytuning flightstatus"
        sources += [synth / (object_name + ".c") for object_name in objects.split()]
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

    def test_each_object_and_loop_initialization_failure_stops_later_modules(self):
        for case in [f"object-{index}" for index in range(1, 12)] + ["sin", "outer", "inner"]:
            with self.subTest(case=case): self.run_case(case)

    def test_each_callback_and_watchdog_failure_stops_later_modules(self):
        for case in [f"callback-{index}" for index in range(1, 9)] + ["watchdog"]:
            with self.subTest(case=case): self.run_case(case)

    def test_each_initial_state_read_and_write_failure_stops_later_modules(self):
        for case in ("read-settings", "read-desired", "write-status", "read-manual",
                     "read-bank-settings", "write-bank", "read-bank"):
            with self.subTest(case=case): self.run_case(case)

    def test_existing_objects_nominal_order_and_one_shot_guards(self):
        for case in ("existing", "nominal", "premature"):
            with self.subTest(case=case): self.run_case(case)

    def test_original_module_fails_checked_lifecycle_cases(self):
        binary = self.compile(self.flight / "flight/modules/Stabilization/stabilization.c", "original")
        cases = ([f"object-{index}" for index in range(1, 12)] + ["sin", "outer", "inner"] +
                 [f"callback-{index}" for index in range(1, 9)] + ["watchdog", "read-settings",
                  "read-desired", "write-status", "read-manual", "read-bank-settings",
                  "write-bank", "read-bank", "existing", "nominal", "premature"])
        for case in cases:
            with self.subTest(case=case): self.run_case(case, binary, success=False)

    def test_omitted_lifecycle_checks_are_detected(self):
        code = (self.output / "stabilization.c").read_text()
        mutations = {
            "object-result": ("if (!StabilizationDesiredHandle() && (StabilizationDesiredInitialize() != 0 || !StabilizationDesiredHandle())) return -1;",
                              "(void)StabilizationDesiredInitialize();", "object-1"),
            "sin-result": ("if (sin_lookup_initalize() != 0) return -1;",
                           "if (sin_lookup_initalize() != 0 && false) return -1;", "sin"),
            "outer-result": ("if (PIOS_LiteWing_StabilizationOuterloopInitialize() != 0) return -1;",
                             "if (PIOS_LiteWing_StabilizationOuterloopInitialize() != 0 && false) return -1;", "outer"),
            "inner-result": ("if (PIOS_LiteWing_StabilizationInnerloopInitialize() != 0) return -1;",
                             "if (PIOS_LiteWing_StabilizationInnerloopInitialize() != 0 && false) return -1;", "inner"),
            "watchdog-result": ("if (!PIOS_WDG_RegisterFlag(PIOS_WDG_STABILIZATION)) return -1;",
                                "if (!PIOS_WDG_RegisterFlag(PIOS_WDG_STABILIZATION) && false) return -1;", "watchdog"),
            "callback-result": ("if (StabilizationSettingsConnectCallback(SettingsUpdatedCb) != 0) return -1;",
                                "if (StabilizationSettingsConnectCallback(SettingsUpdatedCb) != 0 && false) return -1;", "callback-1"),
            "initial-read": ("if (StabilizationSettingsGet(&stabSettings.settings) != 0)",
                             "if (StabilizationSettingsGet(&stabSettings.settings) != 0 && false)", "read-settings"),
            "desired-read": ("if (StabilizationDesiredGet(&desired) != 0)",
                              "if (StabilizationDesiredGet(&desired) != 0 && false)", "read-desired"),
            "initial-write": ("if (StabilizationStatusSet(&status) != 0)",
                              "if (StabilizationStatusSet(&status) != 0 && false)", "write-status"),
            "manual-read": ("if (ManualControlCommandGet(&command) != 0)",
                            "if (ManualControlCommandGet(&command) != 0 && false)", "read-manual"),
            "bank-settings-read": ("if (StabilizationSettingsBank1Get((StabilizationSettingsBank1Data *)&stabSettings.stabBank) != 0)",
                                   "if (StabilizationSettingsBank1Get((StabilizationSettingsBank1Data *)&stabSettings.stabBank) != 0 && false)",
                                   "read-bank-settings"),
            "bank-write": ("if (StabilizationBankSet(&stabSettings.stabBank) != 0)",
                           "if (StabilizationBankSet(&stabSettings.stabBank) != 0 && false)", "write-bank"),
            "bank-read": ("if (StabilizationBankGet(&stabSettings.stabBank) != 0)",
                          "if (StabilizationBankGet(&stabSettings.stabBank) != 0 && false)", "read-bank"),
            "resource-ready": ("    stabilizationResourcesReady = true;", "    /* omitted ready state */", "nominal"),
            "repeat-init": ("if (stabilizationInitAttempted) return -1;",
                            "if (stabilizationInitAttempted && false) return -1;", "nominal"),
            "repeat-start": ("!stabilizationResourcesReady || stabilizationStartAttempted",
                             "!stabilizationResourcesReady", "nominal"),
            "start-order": ("!stabilizationResourcesReady || stabilizationStartAttempted",
                            "stabilizationStartAttempted", "premature"),
        }
        for name, (old, new, case) in mutations.items():
            with self.subTest(mutant=name):
                self.assertEqual(code.count(old), 1, name)
                source = self.output / (name + ".c")
                source.write_text(code.replace(old, new))
                binary = self.compile(source, name)
                self.run_case(case, binary, success=False)
