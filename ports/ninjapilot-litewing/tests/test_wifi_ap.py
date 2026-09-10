"""AP adapter test using explicit optional IDF 5.3.2 headers.

Set LRRK_TEST_IDF_ROOT (preferred test override) or IDF_PATH to run the C fixture.
No target build/config is needed; wifi_ap_stubs/sdkconfig.h selects S3 types.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class WifiAPTests(unittest.TestCase):
    def test_lifecycle_and_sdk_failures(self):
        path = os.environ.get('LRRK_TEST_IDF_ROOT') or os.environ.get('IDF_PATH')
        if not path:
            self.skipTest('optional IDF SDK not supplied; set LRRK_TEST_IDF_ROOT or IDF_PATH')
        sdk = Path(path)
        required = ('esp_wifi/include/esp_wifi_types_generic.h',
                    'esp_event/include/esp_event_base.h',
                    'esp_hw_support/include/esp_interface.h')
        missing = [header for header in required if not (sdk / 'components' / header).is_file()]
        if missing:
            self.skipTest('optional IDF SDK headers unavailable: ' + ', '.join(missing))
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'wifi-ap'
            includes = [ROOT / 'target/include', ROOT / 'tests/wifi_ap_stubs',
                        ROOT / 'tests/nvs_stubs']
            includes += [sdk / 'components' / p for p in (
                'esp_wifi/include', 'esp_event/include',
                'esp_hw_support/include')]
            command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                       '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                       '-pthread']
            for path in includes:
                command += ['-I', str(path)]
            command += [str(ROOT / p) for p in (
                'target/pios_litewing_wifi_ap.c', 'target/litewing_wifi_config.c',
                'target/pios_litewing_wifi_config.c', 'tests/wifi_ap_test.c')]
            command += ['-o', str(binary)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


class WifiAPDependencyTests(unittest.TestCase):
    # Catch implicit machine-local SDK discovery and attempts to compile with
    # absent optional headers. Exercise the actual test's dependency gate.
    def assert_dependency_skip(self, environment):
        env = {key: value for key, value in os.environ.items()
               if key not in ('IDF_PATH', 'LRRK_TEST_IDF_ROOT')}
        env.update(environment)
        with patch.dict(os.environ, env, clear=True):
            result = unittest.TestResult()
            WifiAPTests('test_lifecycle_and_sdk_failures').run(result)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        self.assertEqual(len(result.skipped), 1)
        self.assertIn('SDK', result.skipped[0][1])

    def test_sdk_not_supplied(self):
        self.assert_dependency_skip({})

    def test_sdk_headers_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assert_dependency_skip({'LRRK_TEST_IDF_ROOT': directory})
