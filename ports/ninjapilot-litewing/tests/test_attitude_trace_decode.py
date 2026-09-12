import importlib.util
from pathlib import Path
import struct
import unittest

PATH=Path(__file__).resolve().parents[1]/'diagnostics/attitude_trace.py'

class TraceDecodeTests(unittest.TestCase):
    def load(self):
        self.assertTrue(PATH.exists(),'trace decoder missing')
        spec=importlib.util.spec_from_file_location('trace_decode',PATH)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def wire(self,index=0,state=3):
        return struct.pack('<4I19f8H3H6B',1000+index*2000,1,936+index,99,
            .002,1,2,3,4,5,6,7,8,9,10,11,12,3,3,3,1,2,3,
            23,0,0,0,47,0,0,0,512,64,index,2,state,1,15,0,0)

    def test_literal_wire_and_full_capture_order(self):
        m=self.load();r=m.decode(self.wire())
        self.assertEqual(r['timestamp_us'],4294968296)
        self.assertEqual(r['gyro'],[4,5,6]); self.assertEqual(r['corrected'],[7,8,9])
        self.assertEqual(r['submitted'],[47,0,0,0])
        self.assertEqual(r['pre_bias'],[3,3,3])
        self.assertEqual(r['applied_bias'],[1,2,3])
        rows=[m.decode(self.wire(i)) for i in range(512)]
        m.validate_capture(rows)
        with self.assertRaises(ValueError):m.validate_capture(rows[:-1])
        rows[3],rows[4]=rows[4],rows[3]
        with self.assertRaises(ValueError):m.validate_capture(rows)

    def test_reject_bad_wire_and_partial_frozen_state(self):
        m=self.load()
        for wire in (self.wire()[:-1],self.wire()+b'\0',self.wire(512)):
            with self.assertRaises(ValueError):m.decode(wire)
        for offset,value in ((114,1),(115,4),(116,2),(117,16),(119,1)):
            wire=bytearray(self.wire());wire[offset]=value
            with self.assertRaises(ValueError):m.decode(wire)
        wire=bytearray(self.wire());wire[108:110]=b'\x01\x00'
        with self.assertRaises(ValueError):m.decode(wire)
