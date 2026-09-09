"""Complete pinned scheduler lifecycle with deterministic RTOS failure/preemption."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SchedulerStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not flight:
            raise unittest.SkipTest("pinned flight tree not supplied")
        flight = Path(flight)
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        output = Path(cls.directory.name)
        source = output / "pios_callbackscheduler.c"
        if os.environ.get("LRRK_TEST_ORIGINAL_SCHEDULER") == "1":
            shutil.copyfile(flight / "flight/pios/common/pios_callbackscheduler.c", source)
        else:
            subprocess.run([sys.executable, str(ROOT / "prepare_scheduler.py"),
                "--source", str(flight / "flight"), "--output", str(output)],
                check=True, capture_output=True, text=True, timeout=5)
        cls.binary = output / "scheduler"
        args = ["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-address-of-packed-member", "-ftrivial-auto-var-init=pattern"]
        for include in (ROOT / "tests/scheduler_stubs", ROOT / "tests/thrust_stubs",
                        flight / "build/uavobject-synthetics/flight",
                        flight / "flight/pios/inc", flight / "flight/libraries/inc",
                        flight / "flight/uavobjects/inc"):
            args += ["-I", str(include)]
        args += [str(source), str(ROOT / "tests/scheduler_lifecycle_test.c"), "-o", str(cls.binary)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def case(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_registration_resource_failures_release_owned_resources(self):
        for name in ("mutex", "alloc-task", "alloc-info", "signal"):
            with self.subTest(name=name): self.case(name)

    def test_partial_start_failure_removes_workers_and_cannot_retry(self):
        for name in ("start-task1", "start-task2", "start-monitor1", "start-monitor2"):
            with self.subTest(name=name): self.case(name)

    def test_stack_can_grow_only_before_worker_starts(self):
        for name in ("grow-before-start", "late-too-large"):
            with self.subTest(name=name): self.case(name)

    def test_failed_late_registration_preserves_existing_worker(self):
        for name in ("late-task", "late-monitor", "late-info"):
            with self.subTest(name=name): self.case(name)

    def test_nominal_pending_and_redispatch_execute_real_callback_loop(self):
        self.case("nominal")

    def test_late_registration_runs_on_existing_or_new_worker(self):
        for name in ("late-shared", "late-normal"):
            with self.subTest(name=name): self.case(name)

    def test_original_scheduler_is_rejected_by_behavioral_regressions(self):
        env = dict(os.environ, LRRK_TEST_ORIGINAL_SCHEDULER="1")
        result = subprocess.run([sys.executable, "-m", "unittest",
            "test_scheduler_startup.SchedulerStartupTests.test_partial_start_failure_removes_workers_and_cannot_retry",
            "test_scheduler_startup.SchedulerStartupTests.test_registration_resource_failures_release_owned_resources",
            "test_scheduler_startup.SchedulerStartupTests.test_stack_can_grow_only_before_worker_starts",
            "test_scheduler_startup.SchedulerStartupTests.test_failed_late_registration_preserves_existing_worker"],
            cwd=ROOT / "tests", env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED (failures=10)", result.stderr)
        self.assertIn("registering invalid task handle", result.stderr)
        self.assertIn("live_allocations == 0", result.stderr)
        self.assertIn("create(CALLBACK_TASK_FLIGHTCONTROL, 2048) == NULL", result.stderr)
