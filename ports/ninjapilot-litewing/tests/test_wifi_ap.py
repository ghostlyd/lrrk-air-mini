"""Exercise the real AP adapter; replace only SDK network/flash boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SDK = Path(os.environ.get('IDF_PATH',
    '/Users/lrrk-ultra/Documents/LiteWing/.toolchains/esp-idf-v5.3.2'))


class WifiAPTests(unittest.TestCase):
    def test_lifecycle_and_sdk_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'wifi-ap'
            includes = [ROOT / 'target/include', ROOT / 'tests/wifi_ap_stubs',
                        ROOT / 'tests/nvs_stubs', ROOT / 'esp-idf/build/config']
            includes += [SDK / 'components' / p for p in (
                'esp_wifi/include', 'esp_event/include', 'esp_common/include',
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
