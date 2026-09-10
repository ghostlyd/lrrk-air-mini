"""Admission neutral check rejects unsafe/malformed persisted mappings."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Channel(ctypes.Structure):
    _fields_ = [("channel", ctypes.c_uint8), ("minimum", ctypes.c_int16),
                ("neutral", ctypes.c_int16), ("maximum", ctypes.c_int16)]

class PilotNeutralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        binary = Path(cls.tmp.name) / "neutral.so"
        result = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-shared", "-fPIC", "-I", str(ROOT / "target/include"),
            str(ROOT / "target/litewing_pilot_neutral.c"), "-o", str(binary)],
            capture_output=True, text=True, timeout=30)
        if result.returncode: raise AssertionError(result.stderr)
        cls.lib = ctypes.CDLL(str(binary))
        cls.check = cls.lib.lw_pilot_neutral
        cls.check.argtypes = [ctypes.POINTER(Channel), ctypes.POINTER(ctypes.c_uint16)]
        cls.check.restype = ctypes.c_int

    def fixture(self):
        # Deliberately permuted mapping: throttle on channel 4, yaw on channel 1.
        return ((Channel * 5)(*[Channel(n,1000,1500,2000) for n in (4,2,3,1,5)]),
                (ctypes.c_uint16 * 8)(1500,1500,1500,1000,1500,1500,1500,1500))

    def test_calibrated_mapping_and_reversed_throttle(self):
        settings, channels = self.fixture()
        self.assertEqual(self.check(settings,channels),1)
        settings[0].minimum, settings[0].maximum = 2000,1000
        channels[3]=2000
        self.assertEqual(self.check(settings,channels),1)
        channels[3]=1000
        self.assertEqual(self.check(settings,channels),0)

    def test_every_primary_control_must_be_neutral(self):
        for index in range(5):
            settings, channels = self.fixture()
            channels[settings[index].channel-1] += 1
            self.assertEqual(self.check(settings,channels),0)

    def test_invalid_mapping_and_calibration(self):
        for field,value in (("channel",0),("channel",9),("channel",2),
                            ("minimum",999),("maximum",2001),("neutral",2001),
                            ("maximum",1000)):
            settings, channels = self.fixture()
            setattr(settings[0],field,value)
            self.assertEqual(self.check(settings,channels),0,(field,value))
        settings, channels = self.fixture()
        channels[7]=0
        self.assertEqual(self.check(settings,channels),0)
        self.assertEqual(self.check(None,channels),0)
        self.assertEqual(self.check(settings,None),0)
