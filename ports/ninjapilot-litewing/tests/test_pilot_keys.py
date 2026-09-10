"""Cross-language HKDF contract with real pinned mbedTLS, no device access."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / "ai_assistant/src"))
from lrrk_litewing_ai.pilot_keys import derive_keys
from test_pilot_crypto_vectors import PIN


class PilotKeyTests(unittest.TestCase):
    def test_real_sdk_matches_host_and_clears_invalid_output(self):
        source = os.environ.get("LRRK_TEST_MBEDTLS_ROOT")
        if not source:
            self.skipTest("pinned mbedTLS checkout not supplied")
        source = Path(source)
        self.assertEqual(subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(), PIN)
        self.assertEqual(subprocess.check_output(
            ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
            text=True), "")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "key_config.h").write_text(
                "#define MBEDTLS_MD_C\n#define MBEDTLS_SHA256_C\n#define MBEDTLS_HKDF_C\n")
            library = out / "keys.so"
            command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                       '-DMBEDTLS_CONFIG_FILE="key_config.h"', "-I", str(out),
                       "-I", str(source / "include"), "-I", str(ROOT / "target/include")]
            command += [str(source / "library" / name) for name in
                        ("md.c", "sha256.c", "hkdf.c", "platform_util.c")]
            command += [str(ROOT / "tests/pilot_keys_failure_fixture.c"), "-o", str(library)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            sdk = ctypes.CDLL(str(library))
            # RFC5869 A.1, also in the pinned SDK's test_suite_hkdf.data.
            kat = ctypes.create_string_buffer(42)
            sdk.lw_test_rfc5869.argtypes = [ctypes.c_void_p]
            sdk.lw_test_rfc5869.restype = ctypes.c_int
            self.assertEqual(sdk.lw_test_rfc5869(kat), 0)
            self.assertEqual(kat.raw.hex(),
                "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865")
            derive = sdk.lw_pilot_derive_keys
            derive.argtypes = [ctypes.c_void_p] * 5
            derive.restype = ctypes.c_int
            values = [b"r" * 32, b"h" * 32, b"b" * 32, b"s" * 16]
            for index in range(4):
                for byte in (0, 1, 127, 255):
                    inputs = values.copy()
                    inputs[index] = bytes([byte]) * len(inputs[index])
                    expected = derive_keys(*inputs)
                    output = ctypes.create_string_buffer(96)
                    self.assertEqual(derive(*inputs, output), 0)
                    self.assertEqual(output.raw, expected.c2b + expected.b2c + expected.telemetry)
            for index in range(4):
                inputs = values.copy()
                inputs[index] = None
                output = ctypes.create_string_buffer(b"x" * 96, 96)
                self.assertEqual(derive(*inputs, output), -1)
                self.assertEqual(output.raw, bytes(96))
            self.assertEqual(derive(*values, None), -1)
            for failure in (1, 2, 3):
                sdk.lw_test_fail_at(failure)
                output = ctypes.create_string_buffer(b"x" * 96, 96)
                self.assertEqual(derive(*values, output), -1)
                self.assertEqual(output.raw, bytes(96))
            sdk.lw_test_fail_at(0)
            self.assertEqual(derive(*values, output), 0)
