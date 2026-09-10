"""Actual worker + scoped store + receiver/arming; NVS/RTOS/radio doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
import struct

ROOT = Path(__file__).resolve().parents[1]


class IntegratedStoreTests(unittest.TestCase):
    def test_worker_real_store_and_failure_propagation(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            flags = ['cc', '-std=c11', '-D_XOPEN_SOURCE=700', '-Wall', '-Wextra',
                     '-Werror', '-pthread', '-fsanitize=address,undefined',
                     '-fno-sanitize-recover=all']
            for include in ('tests/maintenance_stubs', 'tests/gcs_stubs',
                            'tests/nvs_stubs', 'target/include'):
                flags += ['-I', str(ROOT / include)]
            def run(command):
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
            run(flags + ['-Dlw_wifi_config_store=integrated_store', '-c',
                         str(ROOT / 'target/pios_litewing_usb_maintenance.c'),
                         '-o', str(out / 'worker.o')])
            sources = [str(out / 'worker.o')] + [str(ROOT / source) for source in (
                'target/pios_litewing_wifi_store.c', 'target/pios_litewing_gcsrcvr.c',
                'target/litewing_wifi_config.c', 'tests/gcs_session_unused.c',
                'tests/usb_maintenance_store_test.c')]
            run(flags + sources + ['-o', str(out / 'combined')])
            for case in ('success', 'uncertain', 'not-written', 'armed', 'owner',
                         'admission', 'fresh-input', 'timeout', 'rollback', 'cleanup',
                         'readback-failure', 'readback-mismatch'):
                with self.subTest(case=case):
                    run([str(out / 'combined'), case])
            run(flags + ['-DTEST_BYPASS_STORE'] + sources + ['-o', str(out / 'bypass')])
            mutant = subprocess.run([str(out / 'bypass'), 'success'],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(mutant.returncode, 0)
            self.assertIn('nvs_sets', mutant.stderr)
            run(flags + ['-DTEST_HOST_PAYLOAD'] + sources + ['-o', str(out / 'host')])
            sys.path.insert(0, str(ROOT.parents[1] / 'ai_assistant/src'))
            try:
                from lrrk_litewing_ai.usb_provisioning_wire import encode_config, submission, parse_status, STATUS_ID
                from lrrk_litewing_ai.uavtalk import crc8
                tx = b't' * 16
                wire = submission(tx, encode_config('host-fixture', 'p' * 24, b'k' * 32))
                for case, expected in (('success', 4), ('uncertain', 3), ('not-written', 2), ('armed', 0)):
                    result = subprocess.run([str(out / 'host'), case], input=wire[10:-1],
                                            capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(len(result.stdout), 24)
                    body = struct.pack('<BBHIH', 0x3c, 0x20, 34, STATUS_ID, 0) + result.stdout
                    decoded = parse_status(body + bytes([crc8(body)]), tx)
                    self.assertEqual((decoded.phase, decoded.result), (6, expected))
            finally:
                sys.path.pop(0)
