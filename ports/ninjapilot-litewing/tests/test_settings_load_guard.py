"""A queued settings load must not bypass admission/ownership exclusion."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class SettingsLoadGuardTests(unittest.TestCase):
    def test_actual_load_wrapper_and_receiver_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'load'
            result=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I',str(ROOT/'target/include'),'-I',str(ROOT/'tests/gcs_stubs'),
                str(ROOT/'target/pios_litewing_gcsrcvr.c'),
                str(ROOT/'target/litewing_uavobject_load.c'),
                str(ROOT/'tests/gcs_session_unused.c'),
                str(ROOT/'tests/settings_load_guard_test.c'),'-o',str(binary)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
