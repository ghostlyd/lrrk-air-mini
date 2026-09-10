"""Real generated settings/flight headers; only UAVObject storage is simulated."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class PilotMappingTests(unittest.TestCase):
    def test_persisted_mapping_reads_and_rejections(self):
        path=os.environ.get("LRRK_TEST_FLIGHT_ROOT")
        if not path: self.skipTest("pinned flight checkout not supplied")
        flight=Path(path)
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/"mapping"
            result=subprocess.run(["cc","-std=c11","-Wall","-Wextra","-Werror",
                "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                "-I",str(ROOT/"tests/admission_stubs"),
                "-I",str(flight/"flight/uavobjects/inc"),
                "-I",str(flight/"build/uavobject-synthetics/flight"),
                "-I",str(ROOT/"target/include"),
                str(ROOT/"target/pios_litewing_pilot_mapping.c"),
                str(ROOT/"target/litewing_pilot_neutral.c"),
                str(ROOT/"tests/pilot_mapping_test.c"),"-o",str(binary)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            for case in ("valid","armed","arming","read-error","wrong-group",
                         "accessory","duplicate","bad-calibration",
                         "settings-read-error","recheck-error","late-arm"):
                with self.subTest(case=case):
                    result=subprocess.run([str(binary),case],capture_output=True,text=True,timeout=5)
                    self.assertEqual(result.returncode,0,result.stderr)
