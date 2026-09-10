"""Execute the C telemetry codec with independent and Python wire vectors."""
import ctypes as C
import hmac
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / "ai_assistant/src"))
from lrrk_litewing_ai.telemetry_wire import TelemetryRecord, encode_record, decode_record, encode_telemetry, decode_telemetry
from lrrk_litewing_ai.pilot_keys import derive_keys
from test_pilot_wire import Frame, U8, MAC


class Record(C.Structure):
    _fields_ = [("object_id", C.c_uint32), ("serialized_us", C.c_uint64),
                ("sample_age_us", C.c_uint64), ("data_len", C.c_uint16), ("data", U8*30)]


class TelemetryCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.source = ROOT / "target/litewing_telemetry_wire.c"
        if not cls.source.exists():
            return
        binary = Path(cls.temp.name) / "telemetry.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-I", str(ROOT / "target/include"), str(cls.source),
                        str(ROOT / "target/litewing_pilot_wire.c"), "-o", str(binary)], check=True)
        cls.lib = C.CDLL(str(binary))
        cls.lib.lw_telemetry_payload_decode.argtypes = [C.POINTER(U8), C.c_size_t, C.POINTER(Record)]
        cls.lib.lw_telemetry_payload_encode.argtypes = [C.POINTER(Record), C.POINTER(U8), C.c_size_t, C.POINTER(C.c_size_t)]
        cls.lib.lw_telemetry_frame_validate.argtypes = [C.POINTER(Frame), C.POINTER(Record)]
        cls.lib.lw_wire_decode.argtypes = [C.POINTER(U8), C.c_size_t, U8, MAC, C.c_void_p, C.POINTER(Frame)]
        cls.lib.lw_wire_encode.argtypes = [C.POINTER(Frame), MAC, C.c_void_p, C.POINTER(U8), C.c_size_t, C.POINTER(C.c_size_t)]

    def setUp(self):
        self.assertTrue(hasattr(self, "lib"), "C telemetry codec not implemented")

    def unpack(self, payload):
        out = Record()
        C.memset(C.byref(out), 0xa5, C.sizeof(out))
        data = (U8*len(payload)).from_buffer_copy(payload)
        rc = self.lib.lw_telemetry_payload_decode(data, len(payload), C.byref(out))
        if rc:
            self.assertEqual(bytes(out), bytes(C.sizeof(out)))
        return rc, out

    def test_cross_language_and_capacity(self):
        frozen = bytes.fromhex("01000008ef69b6bc00000000000003e8ffffffffffffffff0000000000000000")
        self.assertEqual(self.unpack(frozen)[0], 0)
        for obj, size in ((0xD7E0D964, 28), (0xEF69B6BC, 8), (0x26962352, 30),
                          (0x6B7639EC, 25), (0xB8229FE4, 29)):
            for stamp in (0, 1000, 2**63-1):
                for age in (0, stamp, None):
                    record = TelemetryRecord(obj, stamp, age, bytes(range(size)))
                    payload = encode_record(record)
                    rc, out = self.unpack(payload)
                    self.assertEqual(rc, 0)
                    self.assertEqual((out.object_id, out.serialized_us, out.sample_age_us, out.data_len),
                                     (obj, stamp, 2**64-1 if age is None else age, size))
                    for capacity in range(len(payload)+1):
                        buf = (U8*56)(*([0xa5]*56))
                        written = C.c_size_t(999)
                        rc = self.lib.lw_telemetry_payload_encode(C.byref(out),
                            C.cast(C.byref(buf, 1), C.POINTER(U8)), capacity, C.byref(written))
                        self.assertEqual((buf[0], buf[55]), (0xa5, 0xa5))
                        if capacity < len(payload):
                            self.assertEqual((rc, written.value, bytes(buf)), (-1, 0, b"\xa5"*56))
                        else:
                            self.assertEqual(rc, 0)
                            result = bytes(buf[1:1+written.value])
                            self.assertEqual(result, payload)
                            self.assertEqual(decode_record(result), record)

    def test_malformed_payloads_and_encoder_metadata(self):
        payload = encode_record(TelemetryRecord(0xEF69B6BC, 1000, None, bytes(8)))
        invalid = [payload[:i] for i in range(len(payload))] + [payload+b"x"]
        for offset, value in ((0, 2), (1, 1), (3, 7), (4, 0), (8, 128), (16, 0)):
            changed = bytearray(payload)
            changed[offset] = value
            invalid.append(bytes(changed))
        for wire in invalid:
            self.assertEqual(self.unpack(wire)[0], -1)
        for field, value in (("object_id", 0), ("data_len", 7), ("data_len", 31),
                             ("serialized_us", 2**63), ("sample_age_us", 1001)):
            _, record = self.unpack(payload)
            setattr(record, field, value)
            buf, written = (U8*54)(*([0xa5]*54)), C.c_size_t(99)
            self.assertEqual(self.lib.lw_telemetry_payload_encode(C.byref(record), buf, 54, C.byref(written)), -1)
            self.assertEqual((written.value, bytes(buf)), (0, b"\xa5"*54))

    def test_frame_contract(self):
        payload = encode_record(TelemetryRecord(0xEF69B6BC, 1000, None, bytes(8)))
        def frame():
            out = Frame()
            out.direction, out.kind, out.sequence = 1, 8, 1
            out.session[:] = b"s"*16
            out.payload_len = len(payload)
            out.payload[:len(payload)] = payload
            return out
        out = Record()
        good = frame()
        self.assertEqual(self.lib.lw_telemetry_frame_validate(C.byref(good), C.byref(out)), 0)
        for field, value in (("direction", 0), ("kind", 7), ("sequence", 0), ("payload_len", 513)):
            bad = frame()
            setattr(bad, field, value)
            C.memset(C.byref(out), 0xa5, C.sizeof(out))
            self.assertEqual(self.lib.lw_telemetry_frame_validate(C.byref(bad), C.byref(out)), -1)
            self.assertEqual(bytes(out), bytes(C.sizeof(out)))
        for field, value in (("session", bytes(16)), ("challenge", b"c"*16)):
            bad = frame()
            getattr(bad, field)[:] = value
            self.assertEqual(self.lib.lw_telemetry_frame_validate(C.byref(bad), C.byref(out)), -1)

    def test_null_contracts(self):
        out, written, buf = Record(), C.c_size_t(99), (U8*54)()
        C.memset(C.byref(out), 0xa5, C.sizeof(out))
        self.assertEqual(self.lib.lw_telemetry_payload_decode(None, 54, C.byref(out)), -1)
        self.assertEqual(bytes(out), bytes(C.sizeof(out)))
        self.assertEqual(self.lib.lw_telemetry_payload_decode(buf, 54, None), -1)
        self.assertEqual(self.lib.lw_telemetry_payload_encode(None, buf, 54, C.byref(written)), -1)
        self.assertEqual(written.value, 0)
        self.assertEqual(self.lib.lw_telemetry_payload_encode(C.byref(out), None, 54, C.byref(written)), -1)
        self.assertEqual(self.lib.lw_telemetry_payload_encode(C.byref(out), buf, 54, None), -1)
        self.assertEqual(self.lib.lw_telemetry_frame_validate(None, C.byref(out)), -1)
        self.assertEqual(self.lib.lw_telemetry_frame_validate(None, None), -1)

    def test_authenticated_cross_language_and_key_separation(self):
        root, session = b"r"*32, b"s"*16
        keys = derive_keys(root, b"h"*32, b"b"*32, session)
        key = keys.telemetry
        @MAC
        def mac(ctx, message, length, out):
            C.memmove(out, hmac.digest(key, C.string_at(message, length), "sha256"), 32)
            return 0
        record = TelemetryRecord(0x26962352, 1000, None, bytes(30))
        packet = encode_telemetry(record, session, 1, key)
        self.assertEqual(len(packet), 136)
        frame, out = Frame(), Record()
        def unpack(wire):
            data = (U8*len(wire)).from_buffer_copy(wire)
            return self.lib.lw_wire_decode(data, len(wire), 1, mac, None, C.byref(frame))
        self.assertEqual(unpack(packet), 0)
        self.assertEqual(self.lib.lw_telemetry_frame_validate(C.byref(frame), C.byref(out)), 0)
        buf, written = (U8*136)(), C.c_size_t()
        self.assertEqual(self.lib.lw_wire_encode(C.byref(frame), mac, None, buf, 136, C.byref(written)), 0)
        self.assertEqual(bytes(buf), packet)
        self.assertEqual(decode_telemetry(bytes(buf), key)[1], record)
        for key in (root, keys.c2b, keys.b2c):
            self.assertEqual(unpack(packet), -1)
            with self.assertRaises(ValueError):
                decode_telemetry(packet, key)
        key = keys.telemetry
        for index in range(len(packet)):
            changed = bytearray(packet)
            changed[index] ^= 1
            self.assertEqual(unpack(bytes(changed)), -1)
            self.assertEqual(unpack(packet[:index]), -1)
        self.assertEqual(unpack(packet+b"x"), -1)

    def test_all_wrong_object_lengths(self):
        for obj, size in ((0xD7E0D964, 28), (0xEF69B6BC, 8), (0x26962352, 30),
                          (0x6B7639EC, 25), (0xB8229FE4, 29)):
            payload = encode_record(TelemetryRecord(obj, 0, None, bytes(size)))
            for wrong in range(32):
                if wrong == size:
                    continue
                wire = payload[:2] + wrong.to_bytes(2, "big") + payload[4:24] + bytes(wrong)
                self.assertEqual(self.unpack(wire)[0], -1)

    def test_memory_sanitizers(self):
        binary = Path(self.temp.name) / "telemetry-sanitizers"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        "-fno-omit-frame-pointer", "-I", str(ROOT / "target/include"),
                        str(self.source), str(ROOT / "tests/telemetry_wire_memory_test.c"),
                        "-o", str(binary)], check=True, capture_output=True, text=True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
