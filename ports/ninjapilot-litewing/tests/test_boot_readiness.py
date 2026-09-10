"""Production boot-ready publication requires every flight-critical service."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BootReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "boot-readiness"
        result = subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "tests/readiness_stubs"),
            "-I", str(ROOT / "target/include"),
            str(ROOT / "target/litewing_boot_readiness.c"),
            str(ROOT / "tests/boot_readiness_test.c"),
            "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)

    def case(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nominal_and_eventual_readiness_clear_boot_fault_once(self):
        for scenario in ("nominal", "already-ok", "eventual"):
            with self.subTest(scenario=scenario): self.case(scenario)

    def test_board_imu_and_each_required_task_are_fail_closed(self):
        for scenario in ("board", "imu", "task-0", "task-5", "task-7",
                         "task-9", "task-14", "task-15"):
            with self.subTest(scenario=scenario): self.case(scenario)

    def test_existing_or_emerging_boot_fault_is_never_masked(self):
        for scenario in ("warning", "critical", "error", "fault-during-wait"):
            with self.subTest(scenario=scenario): self.case(scenario)

    def test_alarm_clear_must_succeed_and_read_back_ok(self):
        for scenario in ("clear-fails", "clear-no-effect"):
            with self.subTest(scenario=scenario): self.case(scenario)


if __name__ == "__main__":
    unittest.main()
