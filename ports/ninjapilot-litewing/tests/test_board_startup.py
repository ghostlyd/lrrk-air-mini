"""Execute the production board/entry control flow, not the underlying services.

Breaks caught: continuing after a reported failure, starting modules anyway,
using uninitialized alarm/LED services, or reinitializing a failed board.
This suite does not prove that upstream services report every internal failure.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoardStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight checkout not supplied")
        flight = Path(flight)
        synth = flight / "build/uavobject-synthetics/flight"
        if not (synth / "firmwareiapobj.h").is_file():
            raise AssertionError("generate pinned flight UAVObjects before board startup tests")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        output = Path(cls.directory.name)
        # Copy bytes unchanged so the board's relative inc/openpilot.h resolves
        # to a host boundary. No production body is rewritten in the normal run.
        for name in ("pios_board.c", "pios_board.h", "litewing.c"):
            shutil.copyfile(ROOT / "target/firmware" / name, output / name)
        boundary_headers = (
            "inc/openpilot.h", "pios_com_priv.h", "pios_debuglog.h",
            "pios_gcsrcvr_priv.h", "pios_rcvr_priv.h", "pios_esp32_priv.h",
            "freertos/FreeRTOS.h", "freertos/task.h", "fw_version_info.h",
            "lrrk_wrapper_identity.h", "esp_system.h", "systemmod.h",
        )
        for name in boundary_headers:
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "board_test.h"\n')
        mutant = os.environ.get("LRRK_TEST_BOARD_MUTANT")
        if mutant:
            if mutant == "entry-gate":
                path = output / "litewing.c"
                old = "if (!PIOS_LiteWing_BoardServicesInitialized())"
                new = "if (false)"
            elif mutant == "monitor-return":
                path = output / "pios_board.c"
                old = ("if (PIOS_TASK_MONITOR_Initialize(TASKINFO_RUNNING_NUMELEM) != 0) {\n"
                       "        board_set_boot_fault();\n        return;\n    }")
                new = "(void)PIOS_TASK_MONITOR_Initialize(TASKINFO_RUNNING_NUMELEM);"
            elif mutant == "double-free":
                path = output / "pios_board.c"
                old = "pios_free(tx_buffer);"
                new = "pios_free(rx_buffer);"
            elif mutant == "transferred-free":
                path = output / "pios_board.c"
                old = "    return result;"
                new = "    if (result == 0) pios_free(rx_buffer);\n" + old
            elif mutant == "repeat-status":
                path = output / "pios_board.c"
                old = "    if (board_init_started) {\n        return;\n    }"
                new = ("    if (board_init_started) {\n"
                       "        board_services_initialized = false;\n        return;\n    }")
            else:
                raise AssertionError("unknown board mutation")
            code = path.read_text()
            if code.count(old) != 1:
                raise AssertionError("board mutation anchor changed")
            path.write_text(code.replace(old, new))
        cls.binary = output / "board-startup-test"
        includes = [output, ROOT / "tests/board_stubs", ROOT / "target/include", ROOT / "contract",
                    synth, flight / "flight/uavobjects/inc",
                    flight / "flight/libraries/inc", flight / "flight/pios/inc"]
        args = ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-Wno-address-of-packed-member", "-ftrivial-auto-var-init=pattern",
                "-include", str(ROOT / "tests/board_stubs/board_test.h")]
        for path in includes:
            args += ["-I", str(path)]
        args += [str(output / "pios_board.c"), str(output / "litewing.c"),
                 str(ROOT / "target/litewing_settings_recovery.c"),
                 str(ROOT / "tests/board_startup_test.c"), "-o", str(cls.binary)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def case(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reported_prerequisite_failures_stop_before_dependent_services(self):
        for name in ("delay", "led", "monitor", "scheduler", "events", "storage",
                     "manager", "identity-get", "identity-set", "settings-health",
                     "inspect0", "inspect1", "inspect2", "load0", "load1", "load2",
                     "marker", "alarms", "uart", "rx", "tx", "com", "gcs", "rcvr",
                     "hardware"):
            with self.subTest(service=name):
                self.case(name)

    def test_missing_required_object_handles_cannot_start_modules(self):
        for name in ("alarm-handle", "gcs-handle", "mixer-handle",
                     "actuator-handle", "manual-handle"):
            with self.subTest(handle=name):
                self.case(name)

    def test_nominal_returns_start_modules_without_claiming_boot_success(self):
        self.case("nominal")

    def test_watchdog_previous_reset_flags_are_not_a_status_code(self):
        self.case("watchdog-flags")

    def test_behavioral_negative_controls_are_rejected(self):
        failures = "test_reported_prerequisite_failures_stop_before_dependent_services"
        nominal = "test_nominal_returns_start_modules_without_claiming_boot_success"
        cases = (
            ("entry-gate", failures, "modules == 0 && system_inits == 0"),
            ("monitor-return", failures, "PIOS_LiteWing_BoardServicesInitialized() == nominal"),
            ("double-free", failures, "owned[index] && !transferred"),
            ("transferred-free", nominal, "owned[index] && !transferred"),
            ("repeat-status", nominal, "PIOS_LiteWing_BoardServicesInitialized() == nominal"),
        )
        for mutant, method, assertion in cases:
            with self.subTest(mutant=mutant):
                env = dict(os.environ, LRRK_TEST_BOARD_MUTANT=mutant)
                result = subprocess.run([
                    sys.executable, "-m", "unittest",
                    "test_board_startup.BoardStartupTests." + method,
                ], cwd=ROOT / "tests", env=env, capture_output=True,
                    text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                # Require the behavior assertion, not a missing/compiler error.
                self.assertIn(assertion, result.stderr)
