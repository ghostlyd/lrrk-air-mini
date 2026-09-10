"""End-to-end encoded pilot input to the real receiver, without hardware."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_pilot_crypto_vectors import PIN

ROOT = Path(__file__).resolve().parents[1]

class PilotReceiverTests(unittest.TestCase):
    def test_real_session_publication_and_failure_cases(self):
        path = os.environ.get("LRRK_TEST_MBEDTLS_ROOT")
        if not path:
            self.skipTest("pinned mbedTLS checkout not supplied")
        source = Path(path)
        self.assertEqual(subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"],text=True).strip(), PIN)
        self.assertEqual(subprocess.check_output(["git","-C",str(source),"status","--porcelain","--untracked-files=no"],text=True), "")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "config.h").write_text("#define MBEDTLS_MD_C\n#define MBEDTLS_SHA256_C\n#define MBEDTLS_HKDF_C\n")
            binary = out / "receiver"
            command = ["cc","-std=c11","-Wall","-Wextra","-Werror","-pthread",
                "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                '-DMBEDTLS_CONFIG_FILE="config.h"',"-I",str(out),"-I",str(source/"include"),
                "-I",str(ROOT/"tests/gcs_stubs"),"-I",str(ROOT/"target/include")]
            command += [str(source/"library"/name) for name in ("md.c","sha256.c","hkdf.c","platform_util.c")]
            command += [str(ROOT/"target"/name) for name in ("litewing_pilot_session.c",
                "litewing_pilot_wire.c","pios_litewing_pilot_mac.c","pios_litewing_pilot_keys.c","pios_litewing_gcsrcvr.c")]
            command += [str(ROOT/"tests/pilot_receiver_integration.c"),"-o",str(binary)]
            result = subprocess.run(command,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            for case in ("publish","delayed","wrong-owner","stop"):
                with self.subTest(case=case):
                    result = subprocess.run([str(binary),case],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
