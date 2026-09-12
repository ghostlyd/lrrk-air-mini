"""Run the production PWM driver; fake only unavailable hardware/RTOS seams."""
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BrushedPwmDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "brushed-driver-test"
        compile_result = subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DPIOS_INCLUDE_SERVO",
            "-I", str(ROOT / "tests" / "hal_stubs"),
            "-I", str(ROOT / "target" / "include"),
            "-I", str(ROOT / "contract"),
            str(ROOT / "target" / "pios_litewing_brushed_pwm.c"),
            str(ROOT / "contract" / "litewing_contract.c"),
            str(ROOT / "tests" / "brushed_pwm_driver_test.c"),
            "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=30)
        if compile_result.returncode:
            raise AssertionError(compile_result.stderr)

    def run_scenario(self, scenario, channel=0):
        result = subprocess.run([str(self.binary), scenario, str(channel)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_feasible_timer_and_staged_clamped_duty(self):
        self.run_scenario("duty")

    def test_observation_distinguishes_request_commit_and_suppression(self):
        self.run_scenario("observation")

    def test_observation_marks_failed_hardware_output_unknown(self):
        self.run_scenario("observation-failure")

    def test_disarm_zeroes_outputs(self):
        self.run_scenario("disarm")

    def test_imu_fault_zeroes_and_blocks_updates(self):
        self.run_scenario("imu")

    def test_failsafe_zeroes_and_blocks_updates(self):
        self.run_scenario("failsafe")

    def test_shutdown_zeroes_and_blocks_updates(self):
        self.run_scenario("shutdown")

    def test_watchdog_expires_after_100_ms(self):
        self.run_scenario("watchdog")

    def test_stage_error_stops_all_channels_and_latches(self):
        for channel in range(4):
            with self.subTest(channel=channel):
                self.run_scenario("set-failure", channel)

    def test_update_error_stops_all_channels_and_latches(self):
        for channel in range(4):
            with self.subTest(channel=channel):
                self.run_scenario("update-failure", channel)

    def test_stop_error_does_not_skip_other_stops_or_reenable(self):
        for channel in range(4):
            with self.subTest(channel=channel):
                self.run_scenario("stop-failure", channel)

    def test_initial_zero_write_error_is_not_successful_initialization(self):
        for channel in range(4):
            with self.subTest(channel=channel):
                self.run_scenario("init-write-failure", channel)

    def test_missing_watchdog_cannot_be_hidden_by_reinitializing(self):
        self.run_scenario("watchdog-create-failure")

    def test_initial_zero_update_error_is_not_successful_initialization(self):
        for channel in range(4):
            with self.subTest(channel=channel):
                self.run_scenario("init-update-failure", channel)
