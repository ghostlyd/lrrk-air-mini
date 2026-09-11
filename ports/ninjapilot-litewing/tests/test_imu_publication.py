"""Execute target driver/worker/packer with deterministic hardware boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImuPublicationTests(unittest.TestCase):
    def test_driver_worker_pack(self):
        self.assertTrue((ROOT / 'target/litewing_imu_health_module.c').exists(),
                        'IMU publication worker is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for name in ('pios.h', 'esp_err.h', 'esp_timer.h', 'driver/gpio.h',
                         'freertos/FreeRTOS.h', 'freertos/task.h', 'pios_constants.h',
                         'pios_sensors.h', 'pios_icm20602.h', 'openpilot.h',
                         'litewingimuhealth.h', 'uavobjectmanager.h'):
                header = out / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text('#include "imu_publication_sdk.h"\n')
            binary = out / 'imu'
            command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                       '-I', str(out), '-I', str(ROOT / 'tests'),
                       '-I', str(ROOT / 'target/include'), '-I', str(ROOT / 'contract'),
                       str(ROOT / 'tests/imu_publication_test.c'),
                       str(ROOT / 'target/litewing_imu_health.c'),
                       str(ROOT / 'target/litewing_mpu6050_protocol.c'),
                       str(ROOT / 'contract/litewing_contract.c'),
                       str(ROOT / 'target/litewing_battery_voltage.c'), '-o', str(binary)]
            print('COMPILE:', ' '.join(command), flush=True)
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for case in ('normal', 'initial-publish', 'runtime-publish', 'create', 'register'):
                result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=15)
                print('RUN:', binary, case, result.stdout, result.stderr, flush=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
