"""Optional real pinned-mbedTLS host KAT; firmware-target execution is separate."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = "98fcfd6d2cea90d306e8fde8e5bffd6087c9cda8"


class PilotCryptoVectorTests(unittest.TestCase):
    def test_real_pinned_mbedtls_vectors(self):
        path = os.environ.get("LRRK_TEST_MBEDTLS_ROOT")
        if not path:
            self.skipTest("pinned mbedTLS checkout not supplied")
        source = Path(path).resolve()
        revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        self.assertEqual(revision, PIN)
        dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True)
        self.assertEqual(dirty, "", "mbedTLS tracked source must be clean")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "pilot_crypto_config.h").write_text(
                "#define MBEDTLS_MD_C\n#define MBEDTLS_SHA256_C\n")
            binary = out / "crypto-kat"
            command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                       '-DMBEDTLS_CONFIG_FILE="pilot_crypto_config.h"',
                       "-I", str(out), "-I", str(source / "include"),
                       "-I", str(ROOT / "target/include")]
            command += [str(source / "library" / name) for name in
                        ("md.c", "sha256.c", "platform_util.c")]
            command += [str(ROOT / "target/litewing_pilot_wire.c"),
                        str(ROOT / "target/pios_litewing_pilot_mac.c"),
                        str(ROOT / "tests/pilot_crypto_vector_test.c"), "-o", str(binary)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
