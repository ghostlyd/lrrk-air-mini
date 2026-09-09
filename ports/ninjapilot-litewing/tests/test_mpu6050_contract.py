import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LiteWingMpu6050Tests(unittest.TestCase):
    def test_protocol_decoder_and_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "mpu6050-protocol-test"
            result = subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(ROOT / "target" / "include"),
                    str(ROOT / "target" / "litewing_mpu6050_protocol.c"),
                    str(ROOT / "tests" / "mpu6050_protocol_test.c"),
                    "-o",
                    str(binary),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                [str(binary)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_driver_contains_hardware_fault_gates(self):
        source = (ROOT / "target" / "pios_litewing_mpu6050.c").read_text()
        for marker in (
            "PIOS_ESP32_I2C_Probe",
            "LITEWING_MPU6050_REG_WHO_AM_I",
            "litewing_mpu6050_identity_valid",
            "PIOS_I2C_Transfer",
            "LITEWING_IMU_INT_GPIO",
            "gpio_install_isr_service",
            "PIOS_LiteWing_BrushedPWM_SetImuHealthy(healthy)",
            "set_health(false)",
            "LITEWING_MPU6050_STALE_TIMEOUT_MS",
            "first (I2C0) bus",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("i2c_id == 0u", source)


if __name__ == "__main__":
    unittest.main()
