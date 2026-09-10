"""Host provisioning cannot emit a LWCF blob rejected by the actual C decoder."""
import ctypes as C
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / "ai_assistant/src"))
from lrrk_litewing_ai.usb_provisioning_wire import encode_config, submission, ProvisioningWireError


class Config(C.Structure):
    _fields_ = [("ssid", C.c_char*33), ("password", C.c_char*64), ("root", C.c_uint8*32)]


class USBConfigInteropTests(unittest.TestCase):
    def test_real_c_decoder_agrees_with_host_for_boundaries_and_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/"config.so"
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                            "-I", str(ROOT/"target/include"), str(ROOT/"target/litewing_wifi_config.c"),
                            "-o", str(binary)], check=True, capture_output=True)
            library = C.CDLL(str(binary))
            library.lw_wifi_config_decode.argtypes = [C.c_void_p, C.c_size_t, C.POINTER(Config)]
            valid = [encode_config("x", "p"*16, b"k"*32),
                     encode_config(" "*32, "~"*63, bytes(range(32)))]
            cases = valid + [valid[0][:-1], valid[0]+b"\0"]
            for offset in range(136):
                for bit in range(8):
                    mutated = bytearray(valid[0]); mutated[offset] ^= 1 << bit
                    cases.append(bytes(mutated))
            for index, blob in enumerate(cases):
                with self.subTest(case=index):
                    out = Config(); C.memset(C.byref(out),0xA5,C.sizeof(out))
                    buffer = C.create_string_buffer(blob)
                    accepted = library.lw_wifi_config_decode(buffer,len(blob),C.byref(out)) == 0
                    try:
                        packet = submission(b"t"*16,blob)
                        host = True
                        self.assertEqual(packet[26:-1],blob)
                    except ProvisioningWireError:
                        host = False
                    self.assertEqual(host,accepted)
                    if not accepted:
                        self.assertEqual(bytes(out),b"\0"*C.sizeof(out))
