"""Catch malformed credential acceptance and stale secret output on failure."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class WifiConfigTests(unittest.TestCase):
    def test_real_decoder(self):
        self.compile_run('wifi_config_test.c',[])

    def test_read_only_loader_and_failures(self):
        self.compile_run('wifi_config_load_test.c',[
            str(ROOT/'target/pios_litewing_wifi_config.c')])

    def compile_run(self,fixture,extra):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'config'
            result=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I',str(ROOT/'target/include'),
                '-I',str(ROOT/'tests/nvs_stubs'),
                str(ROOT/'target/litewing_wifi_config.c'),
                *extra,str(ROOT/'tests'/fixture),'-o',str(binary)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
