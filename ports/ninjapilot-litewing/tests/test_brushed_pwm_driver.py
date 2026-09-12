"""Run the production PWM driver; fake only unavailable hardware/RTOS seams."""
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BrushedPwmDriverTests(unittest.TestCase):
    compile_flags = []
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "brushed-driver-test"
        compile_result = subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DPIOS_INCLUDE_SERVO", *cls.compile_flags,
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


class BenchPwmDriverTests(unittest.TestCase):
    compile_flags = ["-DCONFIG_LRRK_BENCH_OUTPUT_LIMIT=1"]
    setUpClass = classmethod(BrushedPwmDriverTests.setUpClass.__func__)
    run_scenario = BrushedPwmDriverTests.run_scenario

    def test_controller_saturation_is_clamped_per_motor(self):
        self.run_scenario("bench-cap")

    def test_fresh_updates_cannot_extend_first_output_deadline(self):
        self.run_scenario("bench-deadline")

    def test_watchdog_enforces_deadline_even_with_fresh_updates(self):
        self.run_scenario("bench-watchdog")

    def test_zero_or_suppressed_requests_do_not_start_timer(self):
        self.run_scenario("bench-start")

    def test_expiry_cannot_be_cleared_by_arm_or_init(self):
        self.run_scenario("bench-latch")

    def test_zero_and_disarm_interruption_does_not_renew_interval(self):
        self.run_scenario("bench-interruption")

    def test_imu_loss_blocks_output_without_renewing_interval(self):
        self.run_scenario("bench-imu")

    def test_failsafe_blocks_output_without_renewing_interval(self):
        self.run_scenario("bench-failsafe")

    def test_peripheral_failures_at_expiry_stop_all_and_latch(self):
        for failure in ("set", "update", "stop"):
            for channel in range(4):
                with self.subTest(failure=failure, channel=channel):
                    self.run_scenario(f"bench-expiry-{failure}-failure", channel)


class TenSecondBenchTests(unittest.TestCase):
    compile_flags = ["-DCONFIG_LRRK_BENCH_OUTPUT_LIMIT=1",
                     "-DCONFIG_LRRK_BENCH_OUTPUT_DURATION_MS=10000"]
    setUpClass = classmethod(BrushedPwmDriverTests.setUpClass.__func__)
    run_scenario = BrushedPwmDriverTests.run_scenario

    def test_ten_second_interval_expires_without_renewal(self):
        self.run_scenario("bench-ten-second")

    def test_watchdog_also_enforces_ten_second_boundary(self):
        self.run_scenario("bench-ten-second-watchdog")


class SingleMotorBenchTests(unittest.TestCase):
    compile_flags = ["-DCONFIG_LRRK_BENCH_OUTPUT_LIMIT=1",
                     "-DCONFIG_LRRK_BENCH_OUTPUT_DURATION_MS=10000",
                     "-DCONFIG_LRRK_BENCH_SINGLE_MOTOR=1"]
    setUpClass = classmethod(BrushedPwmDriverTests.setUpClass.__func__)
    run_scenario = BrushedPwmDriverTests.run_scenario

    def test_fixed_single_output_zero_stop_and_nonrenewing_deadline(self):
        self.run_scenario("single-fixed")

    def test_single_motor_faults_zero_output(self):
        for cause in ('imu', 'failsafe', 'disarm', 'shutdown', 'stale', 'expiry'):
            with self.subTest(cause=cause):
                self.run_scenario('single-'+cause)

    def test_single_motor_write_faults_latch(self):
        for channel in range(4):
            with self.subTest(channel=channel):
                self.run_scenario('single-write-fault', channel)
