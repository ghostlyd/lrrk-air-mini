"""Real Actuator entry points and module table, with generated objects and OS faults."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ActuatorLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight checkout not supplied")
        cls.flight = Path(flight)
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        subprocess.run([sys.executable, str(ROOT / "prepare_control.py"),
                        "--source", str(cls.flight / "flight/modules"),
                        "--output", str(cls.output)], check=True)
        cls.binary = cls.compile(cls.output / "actuator.c", "adapted")

    @classmethod
    def compile(cls, source, name, original=False):
        synth = cls.flight / "build/uavobject-synthetics/flight"
        objects = "actuatorsettings mixersettings actuatordesired accessorydesired actuatorcommand vtolpathfollowersettings systemsettings flightstatus manualcontrolcommand"
        args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                "-Wno-address-of-packed-member", "-DTEST_ACTUATOR_LIFECYCLE",
                '-DMODULE_SOURCE="' + str(source) + '"']
        if original:
            args += ["-Wno-error=incompatible-pointer-types"]
        for path in (ROOT / "tests/thrust_stubs", ROOT / "target/include", synth,
                     cls.flight / "flight/uavobjects/inc", cls.flight / "flight/libraries/inc",
                     cls.flight / "flight/libraries/math", cls.flight / "flight/modules/Actuator/inc"):
            args += ["-I", str(path)]
        binary = cls.output / name
        args += [str(ROOT / "tests/actuator_lifecycle_test.c"),
                 str(ROOT / "target/firmware/InitMods.c")]
        args += [str(synth / (obj + ".c")) for obj in objects.split()]
        result = subprocess.run(args + ["-lm", "-o", str(binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        return binary

    def run_case(self, case, binary=None, success=True):
        result = subprocess.run([str(binary or self.binary), case],
                                capture_output=True, text=True, timeout=5)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL:", result.stderr)

    def test_each_missing_object_stops_module_initialization(self):
        for index in range(1, 8):
            with self.subTest(object=index): self.run_case(f"object-{index}")

    def test_each_callback_failure_stops_module_initialization(self):
        for index in range(1, 5):
            with self.subTest(callback=index): self.run_case(f"callback-{index}")

    def test_queue_allocation_failure_never_publishes_null_queue(self):
        self.run_case("queue")

    def test_failed_queue_connection_releases_only_unpublished_queue(self):
        self.run_case("connection")

    def test_watchdog_registration_failure_prevents_task_creation(self):
        self.run_case("watchdog")

    def test_task_creation_failure_stops_later_modules(self):
        self.run_case("task")

    def test_monitor_failure_retires_worker_before_any_output_setup(self):
        for mode in ("early", "deferred"):
            with self.subTest(mode=mode): self.run_case("monitor-" + mode)

    def test_nominal_worker_registers_before_output_setup(self):
        for mode in ("early", "deferred", "existing"):
            with self.subTest(mode=mode): self.run_case(mode)

    def test_premature_start_has_no_side_effects_and_initialization_still_works(self):
        self.run_case("premature")

    def test_initialization_and_start_cannot_be_repeated(self):
        self.run_case("repeat")

    def test_original_source_fails_behavioral_lifecycle_checks(self):
        binary = self.compile(self.flight / "flight/modules/Actuator/actuator.c", "original", original=True)
        cases = [f"object-{n}" for n in range(1, 8)] + [f"callback-{n}" for n in range(1, 5)]
        cases += ["queue", "connection", "watchdog", "task", "monitor-early", "monitor-deferred",
                  "early", "deferred", "existing", "premature", "repeat"]
        for case in cases:
            with self.subTest(case=case): self.run_case(case, binary, success=False)

    def test_omitted_safety_checks_are_detected(self):
        code = (self.output / "actuator.c").read_text()
        mutations = {
            "duplicate-subscription": ("if (VtolPathFollowerSettingsConnectCallback(&SettingsUpdatedCb) != 0)", "if (SystemSettingsConnectCallback(&SettingsUpdatedCb) != 0)", "deferred"),
            "settings-before-monitor": ("    /* The task owns its monitor handle.", "    SettingsUpdatedCb(NULL);\n    MixerSettingsUpdatedCb(NULL);\n    /* The task owns its monitor handle.", "monitor-early"),
            "task-result": ("TASK_PRIORITY, NULL) != pdPASS)", "TASK_PRIORITY, NULL) != pdPASS && false)", "task"),
            "watchdog-result": ("if (!PIOS_WDG_RegisterFlag(PIOS_WDG_ACTUATOR))", "if (!PIOS_WDG_RegisterFlag(PIOS_WDG_ACTUATOR) && false)", "watchdog"),
            "queue-free": ("        vQueueDelete(queue);", "        /* removed unpublished queue cleanup */", "connection"),
            "monitor-result": ("xTaskGetCurrentTaskHandle()) != 0)", "xTaskGetCurrentTaskHandle()) != 0 && false)", "monitor-early"),
            "monitor-shutdown": ("        PIOS_LiteWing_BrushedPWM_Shutdown();", "        /* removed shutdown */", "monitor-deferred"),
            "monitor-alarm": ("        AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);", "        /* removed alarm */", "monitor-deferred"),
            "repeat-init": ("    if (actuatorInitAttempted) return -1;", "    /* removed one-shot init guard */", "repeat"),
            "repeat-start": ("!actuatorResourcesReady || actuatorStartAttempted", "!actuatorResourcesReady", "repeat"),
            "start-order": ("!actuatorResourcesReady || actuatorStartAttempted", "actuatorStartAttempted", "premature"),
        }
        for name, (old, new, case) in mutations.items():
            with self.subTest(mutant=name):
                self.assertEqual(code.count(old), 1, name)
                source = self.output / (name + ".c")
                source.write_text(code.replace(old, new))
                binary = self.compile(source, name)
                self.run_case(case, binary, success=False)

    def test_real_firmware_feature_selection_matches_fixture(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build:
            self.skipTest("real generated IDF compile command not supplied")
        commands = json.loads((Path(build) / "compile_commands.json").read_text())
        command = next(e for e in commands if Path(e["file"]).name == "actuator.c")
        args = shlex.split(command["command"])
        index = args.index("-o")
        del args[index:index + 2]
        args.remove("-c")
        result = subprocess.run(args + ["-dM", "-E"], cwd=command["directory"],
                                capture_output=True, text=True, check=True, timeout=30)
        macros = {line.split()[1] for line in result.stdout.splitlines() if line.startswith("#define ")}
        self.assertIn("USE_ESP32", macros)
        self.assertIn("PIOS_INCLUDE_WDG", macros)
        self.assertNotIn("PIOS_EXCLUDE_ADVANCED_FEATURES", macros)
        self.assertNotIn("DIAG_MIXERSTATUS", macros)

    def test_real_build_selects_generated_actuator_and_watches_startup_fragment(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build:
            self.skipTest("real generated IDF build graph not supplied")
        build = Path(build).resolve()
        commands = json.loads((build / "compile_commands.json").read_text())
        selected = [Path(e["file"]).resolve() for e in commands if Path(e["file"]).name == "actuator.c"]
        self.assertEqual(selected, [build / "esp-idf/main/litewing_control/actuator.c"])
        configure = next(line for line in (build / "build.ninja").read_text().splitlines()
                         if line.startswith("build build.ninja") and ": RERUN_CMAKE " in line)
        for dependency in ("prepare_control.py", "target/startup/actuator_start.inc", "modules/Actuator/actuator.c"):
            with self.subTest(dependency=dependency): self.assertIn(dependency, configure)
