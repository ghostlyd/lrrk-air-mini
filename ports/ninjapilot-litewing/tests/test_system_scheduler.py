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
