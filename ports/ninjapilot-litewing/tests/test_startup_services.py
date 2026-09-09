"""Real event/alarm libraries -> actual board initializer -> actual entry gate.

Lower-level RTOS allocation, callback registration and object storage are host
boundaries. This is not a complete callback scheduler or hardware execution.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartupServicesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight checkout not supplied")
        flight = Path(flight)
        synth = flight / "build/uavobject-synthetics/flight"
        if not (synth / "systemalarms.h").is_file():
            raise AssertionError("generate pinned flight objects before startup service tests")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        output = Path(cls.directory.name)
        for name in ("pios_board.c", "pios_board.h", "litewing.c"):
            shutil.copyfile(ROOT / "target/firmware" / name, output / name)
        for name in ("inc/openpilot.h", "pios_com_priv.h", "pios_debuglog.h",
                     "pios_gcsrcvr_priv.h", "pios_rcvr_priv.h", "pios_esp32_priv.h",
                     "freertos/FreeRTOS.h", "freertos/task.h", "fw_version_info.h",
                     "esp_system.h", "systemmod.h"):
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "board_test.h"\n')
        if os.environ.get("LRRK_TEST_ORIGINAL_STARTUP_SERVICES") == "1":
            for source, name in (("uavobjects/eventdispatcher.c", "eventdispatcher.c"),
                                 ("libraries/alarms.c", "alarms.c")):
                shutil.copyfile(flight / "flight" / source, output / name)
        else:
            subprocess.run([sys.executable, str(ROOT / "prepare_startup.py"),
                            "--source", str(flight / "flight"), "--output", str(output)],
                           check=True, capture_output=True, text=True, timeout=5)
        # Original alarm source has a relative inc/alarms.h include.
        shutil.copyfile(flight / "flight/libraries/inc/alarms.h", output / "inc/alarms.h")
        cls.binary = output / "startup-services"
        args = ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-Wno-address-of-packed-member", "-ftrivial-auto-var-init=pattern",
                "-include", str(ROOT / "tests/service_stubs/openpilot.h")]
        includes = [output, ROOT / "tests/service_stubs", ROOT / "tests/board_stubs",
                    ROOT / "tests/thrust_stubs", ROOT / "target/include", synth,
                    flight / "flight/uavobjects/inc", flight / "flight/libraries/inc",
                    flight / "flight/pios/inc"]
        for path in includes:
            args += ["-I", str(path)]
        args += [str(output / name) for name in ("pios_board.c", "litewing.c", "alarms.c", "eventdispatcher.c")]
        args += [str(ROOT / "target/litewing_settings_recovery.c"),
                 str(ROOT / "tests/startup_services_test.c"), "-o", str(cls.binary)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def case(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_event_resource_failures_propagate_to_zero_module_start(self):
        for resource in ("event-mutex", "event-queue", "event-callback"):
            with self.subTest(resource=resource):
                self.case(resource)

    def test_alarm_mutex_failure_propagates_to_zero_module_start(self):
        self.case("alarm-mutex")

    def test_alarm_object_failure_is_not_successful_initialization(self):
        self.case("alarm-object")

    def test_preexisting_alarm_object_is_not_reinitialized_or_cleared(self):
        self.case("alarm-direct-existing")

    def test_missing_alarm_object_receives_registration_defaults(self):
        self.case("alarm-direct-create")

    def test_periodic_registration_allocation_failure_releases_mutex(self):
        self.case("periodic-allocation")

    def test_nominal_queue_dispatch_and_alarm_grace_remain_usable(self):
        self.case("nominal")

    def test_original_service_failures_are_rejected_as_negative_control(self):
        env = dict(os.environ, LRRK_TEST_ORIGINAL_STARTUP_SERVICES="1")
        result = subprocess.run([sys.executable, "-m", "unittest",
            "test_startup_services.StartupServicesTests.test_event_resource_failures_propagate_to_zero_module_start",
            "test_startup_services.StartupServicesTests.test_alarm_mutex_failure_propagates_to_zero_module_start",
            "test_startup_services.StartupServicesTests.test_periodic_registration_allocation_failure_releases_mutex",
        ], cwd=ROOT / "tests", env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        for evidence in ("queue_live && locks[0].live", "cb == (DelayedCallbackInfo *)&callback_token",
                         "failed && !PIOS_LiteWing_BoardServicesInitialized()", "locks[0].held == 0"):
            self.assertIn(evidence, result.stderr)
