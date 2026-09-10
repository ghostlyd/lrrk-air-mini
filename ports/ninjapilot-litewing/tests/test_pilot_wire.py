"""Real C codec interoperates with Python; MAC callback is a host test boundary."""
import ctypes as C
import hmac
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / "ai_assistant/src"))
from lrrk_litewing_ai.pilot_wire import Envelope, encode, decode

U8 = C.c_uint8
MAC = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(U8), C.c_size_t, C.POINTER(U8))


class Frame(C.Structure):
    _fields_ = [("direction", U8), ("kind", U8), ("session", U8*16),
                ("sequence", C.c_uint64), ("challenge", U8*16),
                ("payload_len", C.c_uint16), ("payload", U8*512)]


class PilotWireCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        source = ROOT / "target/litewing_pilot_wire.c"
        if not source.exists():
            return
        binary = Path(cls.temp.name) / "wire.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-I", str(ROOT / "target/include"), str(source), "-o", str(binary)], check=True)
        cls.lib = C.CDLL(str(binary))
        cls.lib.lw_wire_decode.argtypes = [C.POINTER(U8), C.c_size_t, U8, MAC, C.c_void_p, C.POINTER(Frame)]
        cls.lib.lw_wire_encode.argtypes = [C.POINTER(Frame), MAC, C.c_void_p, C.POINTER(U8), C.c_size_t, C.POINTER(C.c_size_t)]

    def setUp(self):
        self.assertTrue(hasattr(self, "lib"), "C pilot codec is not implemented")
        self.key = b"k"*32
        self.fail_mac = False
        self.calls = 0
        @MAC
        def mac(ctx, message, length, out):
            self.calls += 1
            if self.fail_mac:
                return -1
            tag = hmac.digest(self.key, C.string_at(message, length), "sha256")
            C.memmove(out, tag, 32)
            return 0
        self.mac = mac

    def unpack(self, packet, direction=0):
        out = Frame()
        C.memset(C.byref(out), 0xa5, C.sizeof(out))
        data = (U8*len(packet)).from_buffer_copy(packet)
        rc = self.lib.lw_wire_decode(data, len(packet), direction, self.mac, None, C.byref(out))
        if rc:
            self.assertEqual(bytes(out), b"\0"*C.sizeof(out))
        return rc, out

    def test_cross_language_round_trip_and_capacity_guards(self):
        for direction, kind in ((0, 1), (0, 3), (0, 5), (0, 6), (1, 2), (1, 4), (1, 7), (1, 8)):
            for payload in (b"", b"ab", bytes(range(256))*2):
                env = Envelope(direction, kind, b"s"*16, 2**64-1, b"c"*16, payload)
                packet = encode(env, self.key)
                rc, frame = self.unpack(packet, direction)
                self.assertEqual(rc, 0)
                for capacity in range(len(packet)+1):
                    buffer = (U8*596)(*([0xa5]*596))
                    written = C.c_size_t(999)
                    rc = self.lib.lw_wire_encode(C.byref(frame), self.mac, None,
                        C.cast(C.byref(buffer, 1), C.POINTER(U8)), capacity, C.byref(written))
                    self.assertEqual((buffer[0], buffer[595]), (0xa5, 0xa5))
                    if capacity < len(packet):
                        self.assertEqual((rc, written.value), (-1, 0))
                        self.assertEqual(bytes(buffer), b"\xa5"*596)
                    else:
                        result = bytes(buffer[1:1+written.value])
                        self.assertEqual(result, packet)
                        self.assertEqual(decode(result, self.key, direction), env)
                        tampered = bytearray(result)
                        tampered[-1] ^= 1
                        self.assertEqual(self.unpack(bytes(tampered), direction)[0], -1)
                        if payload:
                            tampered = bytearray(result)
                            tampered[50] ^= 1
                            self.assertEqual(self.unpack(bytes(tampered), direction)[0], -1)

    def test_tamper_truncation_extra_bytes_and_wrong_direction(self):
        packet = encode(Envelope(0, 5, b"s"*16, 9, b"c"*16, b"ab"), self.key)
        for index in range(len(packet)):
            damaged = bytearray(packet)
            damaged[index] ^= 1
            self.assertEqual(self.unpack(bytes(damaged))[0], -1)
        for length in range(len(packet)):
            self.assertEqual(self.unpack(packet[:length])[0], -1)
        self.assertEqual(self.unpack(packet+b"x")[0], -1)
        self.assertEqual(self.unpack(packet, 1)[0], -1)
        self.fail_mac = True
        self.assertEqual(self.unpack(packet)[0], -1)

    def test_encode_mac_failure_and_invalid_frame(self):
        packet = encode(Envelope(0, 5, b"s"*16, 0, b"c"*16, b""), self.key)
        _, frame = self.unpack(packet)
        buffer = (U8*594)()
        written = C.c_size_t(123)
        self.fail_mac = True
        self.assertEqual(self.lib.lw_wire_encode(C.byref(frame), self.mac, None, buffer, 594, C.byref(written)), -1)
        self.assertEqual(written.value, 0)
        self.fail_mac = False
        frame.payload_len = 513
        self.assertEqual(self.lib.lw_wire_encode(C.byref(frame), self.mac, None, buffer, 594, C.byref(written)), -1)
        self.assertEqual(written.value, 0)

    def test_standalone_memory_sanitizers(self):
        binary = Path(self.temp.name) / "wire-sanitizers"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        "-fno-omit-frame-pointer",
                        "-I", str(ROOT / "target/include"),
                        str(ROOT / "target/litewing_pilot_wire.c"),
                        str(ROOT / "tests/pilot_wire_memory_test.c"),
                        "-o", str(binary)], check=True, capture_output=True, text=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_valid_mac_cannot_bypass_header_validation(self):
        unsigned = encode(Envelope(0, 5, b"s"*16, 9, b"c"*16, b"ab"), self.key)[:-32]
        for offset, value in ((4, 2), (5, 2), (6, 2), (6, 8), (7, 1), (48, 3), (49, 1)):
            changed = bytearray(unsigned)
            changed[offset] = value
            packet = bytes(changed) + hmac.digest(self.key, changed, "sha256")
            self.assertEqual(self.unpack(packet)[0], -1)

    def test_null_pointer_contract(self):
        out = Frame()
        C.memset(C.byref(out), 0xa5, C.sizeof(out))
        self.assertEqual(self.lib.lw_wire_decode(None, 82, 0, self.mac, None, C.byref(out)), -1)
        self.assertEqual(bytes(out), b"\0"*C.sizeof(out))
        self.assertEqual(self.lib.lw_wire_decode(None, 0, 0, self.mac, None, None), -1)
        written = C.c_size_t(99)
        self.assertEqual(self.lib.lw_wire_encode(None, self.mac, None, None, 594, C.byref(written)), -1)
        self.assertEqual(written.value, 0)
        packet = encode(Envelope(0, 5, b"s"*16, 0, b"c"*16, b""), self.key)
        data = (U8*len(packet)).from_buffer_copy(packet)
        self.assertEqual(self.lib.lw_wire_decode(data, len(packet), 0, MAC(), None, C.byref(out)), -1)
        self.assertEqual(bytes(out), b"\0"*C.sizeof(out))
        _, frame = self.unpack(packet)
        buffer = (U8*594)()
        self.assertEqual(self.lib.lw_wire_encode(C.byref(frame), MAC(), None, buffer, 594, C.byref(written)), -1)
        self.assertEqual(written.value, 0)
        self.assertEqual(self.lib.lw_wire_encode(C.byref(frame), self.mac, None, None, 594, C.byref(written)), -1)
        self.assertEqual(written.value, 0)
        self.assertEqual(self.lib.lw_wire_encode(C.byref(frame), self.mac, None, buffer, 594, None), -1)
