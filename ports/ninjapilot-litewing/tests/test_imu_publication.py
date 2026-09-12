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
            cases = ('normal', 'reserved', 'initial-publish', 'runtime-publish', 'create', 'register',
                     'queue-delay', 'reset-completion') + tuple(
                         f'{failure}-{register}' for failure in ('mismatch', 'readfail')
                         for register in ('19', '1a', '1b', '1c', '37', '38', '6b'))
            # Each documented bit matters, including self-test, sleep and reset.
            masks = {'19': 0xff, '1a': 0x3f, '1b': 0xf8, '1c': 0xf8,
                     '37': 0xfe, '38': 0x19, '6b': 0xef}
            cases += tuple(f'mismatch-{reg}-{1 << bit:02x}'
                           for reg, mask in masks.items() for bit in range(8)
                           if mask & (1 << bit))
            for case in cases:
                with self.subTest(case=case):
                    result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=15)
                    print('RUN:', binary, case, result.stdout, result.stderr, flush=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(command[:1] + ['-DCONFIG_LRRK_ATTITUDE_TRACE=1'] + command[1:],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary), 'raw-provenance'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
