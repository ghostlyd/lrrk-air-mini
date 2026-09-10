import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LiteWingBrushedOutputTests(unittest.TestCase):
    def test_backend_is_brushed_duty_not_servo_pulse(self):
        source = (ROOT / "target" / "pios_litewing_brushed_pwm.c").read_text()
        for marker in (
            "LEDC_LOW_SPEED_MODE",
            "LITEWING_PWM_HZ",
            "LITEWING_MOTOR_GPIO_1",
            "LITEWING_MOTOR_GPIO_4",
            "litewing_sanitize_frame",
            "force_zero_locked",
            "LITEWING_OUTPUT_WATCHDOG_MS",
            "FlightStatusArmedGet",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("mcpwm_", source.lower())

    def test_source_fragment_excludes_reference_output_and_imu_drivers(self):
        source = (ROOT / "target" / "sources.cmake").read_text()
        self.assertIn("pios_litewing_brushed_pwm.c", source)
        self.assertIn("pios_litewing_mpu6050.c", source)
        self.assertNotIn("pios_servo.c", source)
        self.assertNotIn("pios_icm20602.c", source)

    def test_board_mixer_uses_reviewed_motor_direction_contract(self):
        source = (ROOT / "target/firmware/pios_board.c").read_text()
        for index in range(1, 5):
            self.assertIn(f"LITEWING_MOTOR_{index}_MIXER_YAW", source)


if __name__ == "__main__":
    unittest.main()
