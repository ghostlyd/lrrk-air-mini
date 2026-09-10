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
            (output / "inc").mkdir(exist_ok=True)
            shutil.copyfile(flight / "flight/modules/System/inc/systemmod.h", output / "inc/systemmod.h")
        # Compile the actual entry point with platform headers at the RTOS
        # boundary; do not replace its System initializer consumer.
        (output / "inc").mkdir(exist_ok=True)
        (output / "inc/openpilot.h").write_text("#include <openpilot.h>\n")
        (output / "esp_system.h").write_text("/* No SDK system calls in this entry point. */\n")
        (output / "freertos").mkdir()
        (output / "freertos/FreeRTOS.h").write_text("#include <pios.h>\n")
        shutil.copyfile(ROOT / "target/firmware/litewing.c", output / "litewing.c")
        shutil.copyfile(ROOT / "target/firmware/InitMods.c", output / "InitMods.c")
        module_mutant = os.environ.get("LRRK_TEST_MODULE_MUTANT")
        if module_mutant:
            mutations = {
                "table-error": ("InitMods.c", "if (rc != 0) return rc;", "if (rc != 0 && false) return rc;"),
                "init-consumer": ("litewing.c", "if (PIOS_LiteWing_ModulesInitialize() != 0)",
                    "if (PIOS_LiteWing_ModulesInitialize() != 0 && false)"),
                "start-consumer": ("systemmod.c", "if (PIOS_LiteWing_ModulesStart() != 0)",
                    "if (PIOS_LiteWing_ModulesStart() != 0 && false)"),
                "retry-init": ("InitMods.c", "if (initAttempted) return -1;", "if (initAttempted && false) return -1;"),
                "start-order": ("InitMods.c", "if (!initialized || startAttempted)", "if (startAttempted)"),
                "retry-start": ("InitMods.c", "if (!initialized || startAttempted)", "if (!initialized)"),
            }
            filename, old, new = mutations[module_mutant]
            path = output / filename
            code = path.read_text()
            assert code.count(old) == 1
            path.write_text(code.replace(old, new))
        mutant = os.environ.get("LRRK_TEST_SYSTEM_MUTANT")
        if mutant:
            path = output / ("litewing.c" if mutant == "entry-error" else "systemmod.c")
            code = path.read_text()
            if mutant == "creator-register":
                # Reintroduce the creator-side registration after a task may
                # already have stopped and deleted itself.
                start = code.index("int32_t SystemModStart(void)")
                end = code.index("\n}\n", start) + 3
                old = code[start:end]
                new = old.replace("    if (xTaskCreate(systemTask,", "    xTaskHandle created;\n    if (xTaskCreate(systemTask,")
                new = new.replace("TASK_PRIORITY, NULL)", "TASK_PRIORITY, &created)")
                new = new.replace("    return 0;", "    PIOS_TASK_MONITOR_RegisterTask(TASKINFO_RUNNING_SYSTEM, created);\n    return 0;")
            elif mutant == "skip-unregister":
                old = "registered && PIOS_TASK_MONITOR_UnregisterTask(TASKINFO_RUNNING_SYSTEM) != 0"
                new = "registered && false"
            elif mutant == "queue-leak":
                old = "    if (SystemModStart() != 0) {\n        releaseSystemQueue();"
                new = "    if (SystemModStart() != 0) {"
            elif mutant == "entry-error":
                old = "if (SystemModInitialize() != 0)"
                new = "if (SystemModInitialize() != 0 && false)"
            elif mutant == "repeat-init":
                old = "if (systemInitAttempted) return -1;"
                new = "if (systemInitAttempted && false) return -1;"
            elif mutant == "monitor-error":
                old = "xTaskGetCurrentTaskHandle()) != 0)"
                new = "xTaskGetCurrentTaskHandle()) != 0 && false)"
            elif mutant == "park-once":
                old = "        for (;;) {\n            vTaskDelay(portMAX_DELAY);\n        }"
                new = "        vTaskDelay(portMAX_DELAY);"
            else:
                raise AssertionError("unknown System mutant")
            if code.count(old) != 1 or old == new:
                raise AssertionError("System mutation anchor changed")
            path.write_text(code.replace(old, new))
        cls.binary = output / "system-scheduler"
        args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-address-of-packed-member", "-ftrivial-auto-var-init=pattern"]
        for include in (output, ROOT / "tests/scheduler_stubs", ROOT / "tests/thrust_stubs", ROOT / "target/include",
                        flight / "flight/modules/System/inc", flight / "build/uavobject-synthetics/flight",
                        flight / "flight/pios/inc", flight / "flight/libraries/inc",
                        flight / "flight/uavobjects/inc"):
            args += ["-I", str(include)]
        args += [str(output / "pios_callbackscheduler.c"), str(output / "systemmod.c"),
                 str(output / "litewing.c"), str(ROOT / "tests/system_scheduler_test.c"), "-o", str(cls.binary)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        if os.environ.get("LRRK_TEST_ORIGINAL_SYSTEM") == "1":
            return  # Legacy negative control does not exercise the new table.
        cls.table_binary = output / "module-table"
        result = subprocess.run(args[:-2] + ["-DTEST_MODULE_TABLE",
            str(output / "InitMods.c"), "-o", str(cls.table_binary)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

        # Keep the complete ManualControl implementation and real scheduler;
        # only other module entry points and object/OS boundaries are fakes.
        manual_source = output / "manualcontrol.c"
        original_manual = os.environ.get("LRRK_TEST_ORIGINAL_MANUAL") == "1"
        manual_mutant = os.environ.get("LRRK_TEST_MANUAL_START_MUTANT")
        if original_manual and manual_mutant:
            raise AssertionError("original and mutant ManualControl controls are mutually exclusive")
        if original_manual:
            manual_source = flight / "flight/modules/ManualControl/manualcontrol.c"
        if manual_mutant:
            mutations = {
                "start-order": ("if (!manualControlResourcesReady || manualControlStartAttempted) return -1;",
                    "if (manualControlStartAttempted) return -1;"),
                "repeat-start": ("if (!manualControlResourcesReady || manualControlStartAttempted) return -1;",
                    "if (!manualControlResourcesReady) return -1;"),
                "configuration-result": ("if (configuration_check() != 0) return -1;",
                    "if (configuration_check() != 0 && false) return -1;"),
                "alarm-result": ("if (AlarmsClear(SYSTEMALARMS_ALARM_MANUALCONTROL) != 0) return -1;",
                    "if (AlarmsClear(SYSTEMALARMS_ALARM_MANUALCONTROL) != 0 && false) return -1;"),
                "connection-system": ("if (SystemSettingsConnectCallback(configurationUpdatedCb) != 0) return -1;",
                    "if (SystemSettingsConnectCallback(configurationUpdatedCb) != 0 && false) return -1;"),
                "connection-manual": ("if (ManualControlSettingsConnectCallback(configurationUpdatedCb) != 0) return -1;",
                    "if (ManualControlSettingsConnectCallback(configurationUpdatedCb) != 0 && false) return -1;"),
                "connection-command": ("if (ManualControlCommandConnectCallback(commandUpdatedCb) != 0) return -1;",
                    "if (ManualControlCommandConnectCallback(commandUpdatedCb) != 0 && false) return -1;"),
                "callback-wiring": ("SystemSettingsConnectCallback(configurationUpdatedCb)",
                    "SystemSettingsConnectCallback(commandUpdatedCb)"),
                "skip-dispatch": ("    (void)PIOS_CALLBACKSCHEDULER_Dispatch(callbackHandle);",
                    "    /* mutant omitted initial dispatch */"),
                "check-dispatch-return": ("    (void)PIOS_CALLBACKSCHEDULER_Dispatch(callbackHandle);",
                    "    if (PIOS_CALLBACKSCHEDULER_Dispatch(callbackHandle) != pdTRUE) return -1;"),
            }
            if manual_mutant not in mutations:
                raise AssertionError("unknown ManualControl start mutant: " + manual_mutant)
            old, new = mutations[manual_mutant]
            code = manual_source.read_text()
            if code.count(old) != 1 or old == new:
                raise AssertionError("ManualControl start mutation anchor changed")
            manual_source.write_text(code.replace(old, new))
        (output / "manual_module.c").write_text(
            "#define ManualControlInitialize RealManualControlInitialize\n"
            "#define ManualControlStart RealManualControlStart\n"
            '#include "' + str(manual_source) + '"\n')
        cls.manual_binary = output / "manual-module"
        result = subprocess.run(args[:-2] + ["-DTEST_MODULE_TABLE", "-DTEST_MANUAL_MODULE",
            "-Wno-unused-parameter", "-Wno-switch",
            "-I", str(flight / "flight/modules/ManualControl/inc"),
            str(output / "InitMods.c"), str(output / "manual_module.c"),
            "-o", str(cls.manual_binary)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def test_manual_control_resource_errors_reach_entry_output_shutdown(self):
        objects = ("ManualControlCommand", "FlightStatus", "ManualControlSettings",
                   "FlightModeSettings", "SystemSettings", "StabilizationSettings",
                   "VtolSelfTuningStats", "VtolPathFollowerSettings")
        for case in ("malloc1", "malloc2", "signal", "shared-malloc",
            "connect-VtolPathFollowerSettings", "connect-SystemSettings", *(prefix + obj
            for prefix in ("object-", "handle-") for obj in objects)):
            with self.subTest(case=case):
                result = subprocess.run([str(self.manual_binary), "manual-" + case],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_manual_control_preserves_existing_objects_and_registers_fresh_ones(self):
        for case in ("nominal", "fresh"):
            with self.subTest(case=case):
                result = subprocess.run([str(self.manual_binary), "manual-" + case],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_manual_control_start_rejects_premature_and_repeated_calls(self):
        for case in ("premature", "nominal"):
            with self.subTest(case=case):
                result = subprocess.run([str(self.manual_binary), "manual-start-" + case],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_manual_control_reported_start_errors_reach_system_failure_gate(self):
        for case in ("configuration", "alarm", "connection-1", "connection-2", "connection-3"):
            with self.subTest(case=case):
                result = subprocess.run([str(self.manual_binary), "manual-start-" + case],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_manual_control_start_negative_controls_reject_regressions(self):
        cases = {
            "start-order": "test_manual_control_start_rejects_premature_and_repeated_calls",
            "repeat-start": "test_manual_control_start_rejects_premature_and_repeated_calls",
            "configuration-result": "test_manual_control_reported_start_errors_reach_system_failure_gate",
            "alarm-result": "test_manual_control_reported_start_errors_reach_system_failure_gate",
            "connection-system": "test_manual_control_reported_start_errors_reach_system_failure_gate",
            "connection-manual": "test_manual_control_reported_start_errors_reach_system_failure_gate",
            "connection-command": "test_manual_control_reported_start_errors_reach_system_failure_gate",
            "callback-wiring": "test_manual_control_start_rejects_premature_and_repeated_calls",
            "skip-dispatch": "test_manual_control_start_rejects_premature_and_repeated_calls",
            "check-dispatch-return": "test_manual_control_start_rejects_premature_and_repeated_calls",
        }
        for mutant, method in cases.items():
            with self.subTest(mutant=mutant):
                result = subprocess.run([sys.executable, "-m", "unittest",
                    "test_system_scheduler.SystemSchedulerTests." + method],
                    cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_ORIGINAL_MANUAL="0",
                                                  LRRK_TEST_MANUAL_START_MUTANT=mutant),
                    capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("line ", result.stderr)
                self.assertIn("Ran 1 test", result.stderr)
                self.assertIn("FAILED (failures=", result.stderr)
                self.assertNotIn("ERROR", result.stderr)

    def test_original_manualcontrol_start_fails_regression(self):
        result = subprocess.run([sys.executable, "-m", "unittest",
            "test_system_scheduler.SystemSchedulerTests.test_manual_control_start_rejects_premature_and_repeated_calls",
            "test_system_scheduler.SystemSchedulerTests.test_manual_control_reported_start_errors_reach_system_failure_gate"],
            cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_ORIGINAL_MANUAL="1",
                                         LRRK_TEST_MANUAL_START_MUTANT=""),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED (failures=7)", result.stderr)

    def test_manualcontrol_test_controls_cannot_mutate_pinned_source(self):
        source = (Path(os.environ["LRRK_TEST_FLIGHT_ROOT"]) /
                  "flight/modules/ManualControl/manualcontrol.c")
        before = source.read_bytes()
        result = subprocess.run([sys.executable, "-m", "unittest",
            "test_system_scheduler.SystemSchedulerTests.test_manual_control_start_rejects_premature_and_repeated_calls"],
            cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_ORIGINAL_MANUAL="1",
                                         LRRK_TEST_MANUAL_START_MUTANT="start-order"),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("controls are mutually exclusive", result.stderr)
        self.assertEqual(source.read_bytes(), before)

    def test_manualcontrol_test_controls_reject_unknown_mutants(self):
        source = (Path(os.environ["LRRK_TEST_FLIGHT_ROOT"]) /
                  "flight/modules/ManualControl/manualcontrol.c")
        before = source.read_bytes()
        result = subprocess.run([sys.executable, "-m", "unittest",
            "test_system_scheduler.SystemSchedulerTests.test_manual_control_start_rejects_premature_and_repeated_calls"],
            cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_ORIGINAL_MANUAL="0",
                                         LRRK_TEST_MANUAL_START_MUTANT="unexpected-ambient"),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AssertionError: unknown ManualControl start mutant: unexpected-ambient",
                      result.stderr)
        self.assertNotIn("KeyError", result.stderr)
        self.assertEqual(source.read_bytes(), before)

    def test_required_module_errors_reach_real_boot_callers(self):
        for prefix in ("", "early-"):
            for phase in ("init", "start"):
                for index in range(6):
                    with self.subTest(prefix=prefix, phase=phase, index=index):
                        result = subprocess.run([str(self.table_binary), f"{prefix}table-{phase}-{index}"],
                            capture_output=True, text=True, timeout=5)
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nominal_module_table_reaches_scheduler_without_readiness_claim(self):
        for case in ("table-nominal", "early-table-nominal"):
            with self.subTest(case=case):
                result = subprocess.run([str(self.table_binary), case],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_module_table_rejects_out_of_order_and_repeated_boot_calls(self):
        result = subprocess.run([str(self.table_binary), "table-order"],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_manualcontrol_ignoring_resources_fails_regression(self):
        result = subprocess.run([sys.executable, "-m", "unittest",
            "test_system_scheduler.SystemSchedulerTests.test_manual_control_resource_errors_reach_entry_output_shutdown"],
            cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_ORIGINAL_MANUAL="1"),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED (failures=22)", result.stderr)
        self.assertIn("init_calls == 5 && start_calls == 0 && system_creates == 0", result.stderr)

    def test_module_table_negative_controls_reject_lost_errors_and_retries(self):
        for mutant in ("table-error", "init-consumer", "start-consumer", "retry-init", "start-order", "retry-start"):
            method = ("test_required_module_errors_reach_real_boot_callers" if
                mutant in ("table-error", "init-consumer", "start-consumer") else
                "test_module_table_rejects_out_of_order_and_repeated_boot_calls")
            with self.subTest(mutant=mutant):
                result = subprocess.run([sys.executable, "-m", "unittest",
                    "test_system_scheduler.SystemSchedulerTests." + method],
                    cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_MODULE_MUTANT=mutant),
                    capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL:", result.stderr)

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

    def life_case(self, name):
        result = subprocess.run([str(self.binary), "life-" + name], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_system_required_resources_fail_before_task_or_module_start(self):
        for name in ("queue", "system-task", "direct-start", *(prefix + obj
            for prefix in ("object-", "handle-")
            for obj in ("SystemSettings", "SystemStats", "FlightStatus", "ObjectPersistence"))):
            with self.subTest(name=name): self.life_case(name)

    def test_system_monitor_ownership_survives_early_or_delayed_execution(self):
        for prefix in ("", "early-"):
            for name in ("system-monitor", "scheduler-task", "scheduler-monitor", "system-unregister"):
                with self.subTest(name=prefix + name): self.life_case(prefix + name)

    def test_system_nominal_start_is_single_attempt_and_preserves_existing_objects(self):
        for name in ("nominal", "early-nominal", "fresh", "early-fresh"):
            with self.subTest(name=name): self.life_case(name)

    def test_real_entry_point_handles_reported_system_initialization_failure(self):
        for name in ("queue", "system-task", "object-SystemStats", "handle-FlightStatus"):
            with self.subTest(name=name): self.life_case("entry-" + name)

    def test_real_entry_point_nominal_path_requests_but_does_not_claim_full_boot(self):
        for name in ("entry-nominal", "early-entry-nominal"):
            with self.subTest(name=name): self.life_case(name)

    def test_system_lifecycle_negative_controls_reject_regressions(self):
        ownership = "test_system_monitor_ownership_survives_early_or_delayed_execution"
        resources = "test_system_required_resources_fail_before_task_or_module_start"
        cases = (
            ("creator-register", ownership, "handle == &system_token && system_live && !system_monitored"),
            ("skip-unregister", ownership, "!system_monitored && !queue_live"),
            ("queue-leak", resources, "!system_live && !system_monitored && !queue_live && module_starts == 0"),
            ("entry-error", "test_real_entry_point_handles_reported_system_initialization_failure",
             "shutdowns == 1 && fault_alarms == 1 && module_starts == 0"),
            ("repeat-init", resources, "object_inits == objects_before && queue_creates == queues_before"),
            ("monitor-error", ownership, "system_live && system_monitored && queue_live"),
            ("park-once", ownership, "!system_monitored && !queue_live"),
        )
        for mutant, method, assertion in cases:
            with self.subTest(mutant=mutant):
                result = subprocess.run([sys.executable, "-m", "unittest",
                    "test_system_scheduler.SystemSchedulerTests." + method],
                    cwd=ROOT / "tests", env=dict(os.environ, LRRK_TEST_SYSTEM_MUTANT=mutant),
                    capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL:", result.stderr)
                self.assertIn(assertion, result.stderr)
