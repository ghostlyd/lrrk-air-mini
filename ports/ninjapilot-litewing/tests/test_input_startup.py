"""Full Attitude/Receiver startup consumers; real generated objects, controlled OS."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InputStartupTests(unittest.TestCase):
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
        cls.binaries = {}
        for name in ("Attitude", "Receiver"):
            source = cls.output / (name.lower() + ".c")
            if not source.is_file():
                raise AssertionError("missing adapted input module: " + str(source))
            cls.binaries[name] = cls.compile(name, source, name)

    @classmethod
    def compile(cls, module, source, name, original=False):
        synth = cls.flight / "build/uavobject-synthetics/flight"
        objects = "flightstatus manualcontrolcommand systemsettings"
        if module == "Attitude":
            objects += " attitudestate attitudesettings accelgyrosettings accelstate gyrostate"
        else:
            objects += " accessorydesired receiveractivity manualcontrolsettings stabilizationsettings vtolpathfollowersettings flighttelemetrystats"
        args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                "-Wno-address-of-packed-member", "-DTEST_INPUT_LIFECYCLE",
                '-DMODULE_SOURCE="' + str(source) + '"']
        if module == "Attitude": args += ["-DTEST_ATTITUDE"]
        if original:
            # The pinned Receiver has the independently characterized enum /
            # byte API defect. Keep it visible, but let this negative control
            # reach startup behavior; adapted sources retain -Werror.
            args += ["-Wno-error=incompatible-pointer-types"]
        for path in (ROOT / "tests/input_stubs", ROOT / "target/include", synth,
                     cls.flight / "flight/uavobjects/inc", cls.flight / "flight/libraries/inc",
                     cls.flight / "flight/libraries/math", cls.flight / "flight/pios/inc",
                     cls.flight / "flight/modules/Attitude/inc"):
            args += ["-I", str(path)]
        binary = cls.output / name
        args += [str(ROOT / "tests/input_startup_test.c"), str(ROOT / "target/firmware/InitMods.c")]
        if module == "Attitude":
            args += [str(cls.flight / "flight/libraries/CoordinateConversions.c"),
                     str(cls.flight / "flight/pios/common/pios_deltatime.c")]
        args += [str(synth / (obj + ".c")) for obj in objects.split()]
        result = subprocess.run(args + ["-lm", "-o", str(binary)], capture_output=True, text=True, timeout=60)
        if result.returncode: raise AssertionError(result.stderr)
        return binary

    def run_case(self, module, case, binary=None, success=True):
        result = subprocess.run([str(binary or self.binaries[module]), case],
                                capture_output=True, text=True, timeout=5)
        if success: self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL:", result.stderr)

    def test_each_object_registration_failure_stops_later_modules(self):
        for module, count in (("Attitude", 5), ("Receiver", 7)):
            for index in range(1, count + 1):
                with self.subTest(module=module, object=index): self.run_case(module, f"object-{index}")

    def test_each_callback_failure_stops_startup(self):
        for module in self.binaries:
            for index in (1, 2):
                with self.subTest(module=module, callback=index): self.run_case(module, f"callback-{index}")

    def test_task_and_watchdog_failures_stop_later_modules(self):
        for module in self.binaries:
            for case in ("task", "watchdog"):
                with self.subTest(module=module, case=case): self.run_case(module, case)

    def test_workers_own_monitor_registration_before_any_startup_reads(self):
        for module in self.binaries:
            for timing in ("early", "deferred"):
                with self.subTest(module=module, timing=timing): self.run_case(module, "monitor-" + timing)

    def test_one_shot_order_and_nominal_early_deferred_existing_resources(self):
        for module in self.binaries:
            for case in ("early", "deferred", "existing", "premature", "repeat"):
                with self.subTest(module=module, case=case): self.run_case(module, case)

    def test_attitude_quaternion_read_write_and_buffer_failures_stop_initialization(self):
        for case in ("init-read", "init-write", "allocation"):
            with self.subTest(case=case): self.run_case("Attitude", case)

    def test_receiver_verifies_required_accessory_instance_growth(self):
        for case in ("instance-1", "instance-2", "instance-zero-1", "instance-zero-2", "instance-zero-grown"):
            with self.subTest(case=case): self.run_case("Receiver", case)

    def test_attitude_failed_sensor_startup_retires_or_parks_monitored_worker(self):
        for fault in ("sensor-test", "sensor-queue"):
            for suffix in ("-early", "-deferred", "-park-early", "-park-deferred"):
                with self.subTest(fault=fault, suffix=suffix): self.run_case("Attitude", fault + suffix)

    def test_receiver_failed_initial_reads_retire_or_park_monitored_worker(self):
        for fault in ("runtime-command", "runtime-flight"):
            for suffix in ("-early", "-deferred", "-park-early", "-park-deferred"):
                with self.subTest(fault=fault, suffix=suffix): self.run_case("Receiver", fault + suffix)

    def test_original_modules_fail_behavioral_startup_checks(self):
        for module, count in (("Attitude", 5), ("Receiver", 7)):
            binary = self.compile(module, self.flight / "flight/modules" / module / (module.lower() + ".c"), "original-" + module, original=True)
            cases = [f"object-{n}" for n in range(1, count + 1)]
            cases += ["callback-1", "callback-2", "watchdog", "task", "monitor-early", "monitor-deferred", "premature", "repeat"]
            cases += ["allocation", "init-read", "init-write"] if module == "Attitude" else ["instance-1", "instance-2"]
            for case in cases:
                with self.subTest(module=module, case=case): self.run_case(module, case, binary, success=False)

    def test_targeted_omissions_fail_at_checked_boundaries(self):
        for module in self.binaries:
            code = (self.output / (module.lower() + ".c")).read_text()
            watchdog = "ATTITUDE" if module == "Attitude" else "MANUAL"
            fault = "sensor-test" if module == "Attitude" else "runtime-command"
            mutations = {
                "single-parking-delay": ("for (;;) vTaskDelay(portMAX_DELAY);", "vTaskDelay(portMAX_DELAY);", fault + "-park-deferred"),
                "fallback-stack": ("STACK_SIZE_BYTES / 4,", ("135," if module == "Attitude" else "288,"), "early"),
                "watchdog-result": (f"if (!PIOS_WDG_RegisterFlag(PIOS_WDG_{watchdog}))", f"if (!PIOS_WDG_RegisterFlag(PIOS_WDG_{watchdog}) && false)", "watchdog"),
                "task-result": ("TASK_PRIORITY, NULL) != pdPASS)", "TASK_PRIORITY, NULL) != pdPASS && false)", "task"),
                "monitor-result": ("xTaskGetCurrentTaskHandle()) != 0)", "xTaskGetCurrentTaskHandle()) != 0 && false)", "monitor-early"),
                "shutdown": ("\n    PIOS_LiteWing_BrushedPWM_Shutdown();", "\n    /* removed shutdown */", "monitor-deferred"),
                "alarm": ("    AlarmsSet(SYSTEMALARMS_ALARM_BOOTFAULT, SYSTEMALARMS_ALARM_CRITICAL);", "    /* removed fault alarm */", "monitor-early"),
                "unregister-result": (f"PIOS_TASK_MONITOR_UnregisterTask(TASKINFO_RUNNING_{module.upper()}) != 0)", f"PIOS_TASK_MONITOR_UnregisterTask(TASKINFO_RUNNING_{module.upper()}) != 0 && false)", fault + "-park-deferred"),
                "retire-monitored": ("        stopInputTask(true);", "        stopInputTask(false);", fault + "-early"),
                "repeat-init": ("    if (inputInitAttempted) return -1;", "    /* removed one-shot init */", "repeat"),
                "repeat-start": ("!inputResourcesReady || inputStartAttempted", "!inputResourcesReady", "repeat"),
                "start-order": ("!inputResourcesReady || inputStartAttempted", "inputStartAttempted", "premature"),
            }
            if module == "Attitude":
                mutations.update({
                    "initial-settings": ("    settingsUpdatedCb(AttitudeSettingsHandle());", "    /* removed initial settings application */", "deferred"),
                    "allocation-result": ("if (!mpu6000_data) return -1;", "if (!mpu6000_data && false) return -1;", "allocation"),
                    "init-read": ("if (AttitudeStateGet(&attitude) != 0)", "if (AttitudeStateGet(&attitude) != 0 && false)", "init-read"),
                    "init-write": ("if (AttitudeStateSet(&attitude) != 0)", "if (AttitudeStateSet(&attitude) != 0 && false)", "init-write"),
                    "sensor-test": ("!gyro_test || !ATTITUDE_IMU_DRIVER.get_queue(0)", "!ATTITUDE_IMU_DRIVER.get_queue(0)", "sensor-test-deferred"),
                    "sensor-queue": ("!gyro_test || !ATTITUDE_IMU_DRIVER.get_queue(0)", "!gyro_test", "sensor-queue-early"),
                    "duplicate-callback": ("AccelGyroSettingsConnectCallback(&settingsUpdatedCb)", "AttitudeSettingsConnectCallback(&settingsUpdatedCb)", "deferred"),
                    "read-before-monitor": ("    if (PIOS_TASK_MONITOR_RegisterTask(", "    settingsUpdatedCb(NULL);\n    if (PIOS_TASK_MONITOR_RegisterTask(", "monitor-early"),
                })
            else:
                mutations.update({
                    "initial-settings": ("    SettingsUpdatedCb(NULL);", "    /* removed initial settings application */", "deferred"),
                    "instance-growth": ("next != count || actual != count + 1", "next != count", "instance-1"),
                    "instance-result": ("next != count || actual != count + 1", "actual != count + 1", "instance-zero-grown"),
                    "runtime-command": ("ManualControlCommandGet(&cmd) != 0 || FlightStatusGet(&flightStatus) != 0", "(ManualControlCommandGet(&cmd), false) || FlightStatusGet(&flightStatus) != 0", "runtime-command-deferred"),
                    "runtime-flight": ("ManualControlCommandGet(&cmd) != 0 || FlightStatusGet(&flightStatus) != 0", "ManualControlCommandGet(&cmd) != 0 || (FlightStatusGet(&flightStatus), false)", "runtime-flight-early"),
                    "duplicate-callback": ("SystemSettingsConnectCallback(&SettingsUpdatedCb)", "VtolPathFollowerSettingsConnectCallback(&SettingsUpdatedCb)", "deferred"),
                    "read-before-monitor": ("    if (PIOS_TASK_MONITOR_RegisterTask(", "    SettingsUpdatedCb(NULL);\n    if (PIOS_TASK_MONITOR_RegisterTask(", "monitor-early"),
                })
            for name, (old, new, case) in mutations.items():
                with self.subTest(module=module, mutant=name):
                    self.assertEqual(code.count(old), 1, name)
                    source = self.output / (module + "-" + name + ".c")
                    source.write_text(code.replace(old, new))
                    self.run_case(module, case, self.compile(module, source, module + "-" + name), success=False)

    def test_real_build_selects_both_adapted_inputs_and_watches_dependencies(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build: self.skipTest("real IDF graph not supplied")
        build = Path(build).resolve()
        commands = json.loads((build / "compile_commands.json").read_text())
        for module in self.binaries:
            name = module.lower() + ".c"
            selected = [Path(e["file"]).resolve() for e in commands if Path(e["file"]).name == name]
            self.assertEqual(selected, [build / "esp-idf/main/litewing_control" / name])
        configure = next(line for line in (build / "build.ninja").read_text().splitlines()
                         if line.startswith("build build.ninja") and ": RERUN_CMAKE " in line)
        for dependency in ("prepare_control.py", "prepare_input_startup.py", "prepare_startup.py", "target/startup/input_start.inc", "modules/Attitude/attitude.c", "modules/Receiver/receiver.c"):
            with self.subTest(dependency=dependency): self.assertIn(dependency, configure)

    def test_sdk_feature_selection_matches_input_fixture(self):
        build = os.environ.get("LRRK_IDF_BUILD_DIR")
        if not build: self.skipTest("real IDF graph not supplied")
        commands = json.loads((Path(build) / "compile_commands.json").read_text())
        for module in self.binaries:
            with self.subTest(module=module):
                entry = next(e for e in commands if Path(e["file"]).name == module.lower() + ".c")
                args = shlex.split(entry["command"])
                index = args.index("-o"); del args[index:index + 2]; args.remove("-c")
                result = subprocess.run(args + ["-dM", "-E"], cwd=entry["directory"], capture_output=True,
                                        text=True, check=True, timeout=30)
                macros = {line.split()[1] for line in result.stdout.splitlines() if line.startswith("#define ")}
                values = {line.split()[1]: line.split(maxsplit=2)[2] for line in result.stdout.splitlines()
                          if line.startswith("#define ") and len(line.split(maxsplit=2)) == 3}
                fixture_bytes = subprocess.run([str(self.binaries[module]), "stack-bytes"], check=True,
                                               capture_output=True, text=True, timeout=5).stdout.strip()
                self.assertEqual(int(fixture_bytes), int(values["PIOS_" + module.upper() + "_STACK_SIZE"]))
                for name in ("USE_ESP32", "PIOS_INCLUDE_WDG", "PIOS_INCLUDE_ICM20602", "PIOS_QUATERNION_STABILIZATION"):
                    self.assertIn(name, macros)
                for name in ("PIOS_EXCLUDE_ADVANCED_FEATURES", "PIOS_INCLUDE_RAW_SENSORS", "PIOS_INCLUDE_ADXL345", "PIOS_INCLUDE_ADC", "USE_INPUT_LPF", "PIOS_INCLUDE_USB_RCTX"):
                    self.assertNotIn(name, macros)
