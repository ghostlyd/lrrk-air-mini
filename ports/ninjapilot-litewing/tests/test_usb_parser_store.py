"""Complete Python frames through actual parser/worker/store; no hardware."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ParserStoreTests(unittest.TestCase):
    def test_full_host_frames_and_actual_firmware_responses(self):
        flight = os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not flight:
            self.skipTest('pinned flight checkout not supplied')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            source = Path(flight) / 'flight/uavtalk'
            def run(command):
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
            run([sys.executable, str(ROOT/'prepare_uavtalk.py'), '--source', str(source), '--output', str(out)])
            flags = ['cc', '-std=c11', '-D_XOPEN_SOURCE=700', '-Wall', '-Wextra', '-Werror',
                     '-Wno-unused-parameter', '-pthread', '-fsanitize=address,undefined',
                     '-fno-sanitize-recover=all']
            for include in ('tests/maintenance_stubs', 'tests/gcs_stubs', 'tests/nvs_stubs', 'target/include'):
                flags += ['-I', str(ROOT/include)]
            flags += ['-I', str(out), '-I', str(source/'inc')]
            run(flags + ['-Dlw_wifi_config_store=integrated_store', '-c',
                         str(ROOT/'target/pios_litewing_usb_maintenance.c'), '-o', str(out/'worker.o')])
            sources = [str(out/'worker.o'), str(out/'uavtalk.c')] + [str(ROOT/path) for path in (
                'target/pios_litewing_wifi_store.c', 'target/pios_litewing_gcsrcvr.c',
                'target/litewing_wifi_config.c', 'target/litewing_battery_pack.c',
                'target/litewing_battery_voltage.c', 'tests/gcs_session_unused.c',
                'tests/usb_maintenance_store_test.c', 'tests/usb_parser_store_bridge.c')]
            binary = out/'integrated'
            run(flags + ['-DTEST_HOST_PARSER'] + sources + ['-o', str(binary)])
            sys.path.insert(0, str(ROOT.parents[1]/'ai_assistant/src'))
            try:
                from lrrk_litewing_ai.usb_provisioning_wire import encode_config, submission, parse_status, parse_receipt
                tx = b't'*16
                frame = submission(tx, encode_config('host-fixture', 'p'*24, b'k'*32))
                for case, expected in (('success',4), ('uncertain',3), ('not-written',2),
                                       ('armed',0), ('readback-failure',3), ('readback-mismatch',3)):
                    with self.subTest(case=case):
                        result = subprocess.run([str(binary),case],input=frame,capture_output=True,timeout=5)
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertEqual(len(result.stdout),46)
                        self.assertTrue(parse_receipt(result.stdout[:11]))
                        status = parse_status(result.stdout[11:],tx)
                        self.assertEqual((status.phase,status.result),(6,expected))
            finally:
                sys.path.pop(0)
