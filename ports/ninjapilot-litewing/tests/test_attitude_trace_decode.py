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
        return struct.pack('<15I19f12H50B',1000+index*2000,1,936+index,99,
            55+index,0,0,950+index*2000,0,0,970+index*2000,0,0,55+index,55+index,
            .002,1,2,3,4,5,6,7,8,9,10,11,12,3,3,3,1,2,3,
            23,0,0,0,47,0,0,0,512,64,index,1,3,state,1,15,0,0,
            *range(14),*([0]*28),1,0)

    def test_literal_wire_and_full_capture_order(self):
        m=self.load();r=m.decode(self.wire())
        self.assertEqual(r['timestamp_us'],4294968296)
        self.assertEqual(r['gyro'],[4,5,6]); self.assertEqual(r['corrected'],[7,8,9])
        self.assertEqual(r['submitted'],[47,0,0,0])
        self.assertEqual(r['pre_bias'],[3,3,3])
        self.assertEqual(r['applied_bias'],[1,2,3])
        self.assertEqual(r['raw_samples'][0]['bytes'],list(range(14)))
        self.assertEqual(r['raw_samples'][0]['sequence'],55)
        self.assertEqual(r['raw_samples'][0]['start_us'],4294968246)
        self.assertTrue(r['raw_complete'])
        rows=[m.decode(self.wire(i)) for i in range(512)]
        m.validate_capture(rows)
        with self.assertRaises(ValueError):m.validate_capture(rows[:-1])
        rows[3],rows[4]=rows[4],rows[3]
        with self.assertRaises(ValueError):m.validate_capture(rows)

    def test_reject_bad_wire_and_partial_frozen_state(self):
        m=self.load()
        for wire in (self.wire()[:-1],self.wire()+b'\0',self.wire(512)):
            with self.assertRaises(ValueError):m.decode(wire)
        for offset,value in ((160,1),(161,4),(162,2),(163,16),(165,1),
                             (208,4),(209,128),(158,0),(180,1)):
            wire=bytearray(self.wire());wire[offset]=value
            with self.assertRaises(ValueError):m.decode(wire)
        wire=bytearray(self.wire());wire[152:154]=b'\x01\x00'
        with self.assertRaises(ValueError):m.decode(wire)

    def test_timestamp_wrap_and_stale_read_rejection(self):
        m=self.load();wire=bytearray(self.wire())
        struct.pack_into('<I',wire,0,10)
        struct.pack_into('<I',wire,28,0xfffffff0)
        struct.pack_into('<I',wire,40,5)
        sample=m.decode(wire)['raw_samples'][0]
        self.assertEqual(sample['start_us'],4294967280)
        self.assertEqual(sample['end_us'],4294967301)
        struct.pack_into('<I',wire,28,0xffe00000)
        with self.assertRaises(ValueError):m.decode(wire)

    def test_overflow_is_retained_but_never_claimed_complete(self):
        m=self.load();wire=bytearray(self.wire())
        struct.pack_into('<3I',wire,16,55,56,57)
        struct.pack_into('<2I',wire,32,980,990)
        struct.pack_into('<2I',wire,44,985,995)
        struct.pack_into('<I',wire,56,58)
        struct.pack_into('<H',wire,158,4)
        wire[208]=3;wire[209]=1
        result=m.decode(wire)
        self.assertEqual(result['raw_consumed'],4)
        self.assertEqual(len(result['raw_samples']),3)
        self.assertFalse(result['raw_complete'])
        wire[209]=0
        with self.assertRaises(ValueError):m.decode(wire)

    def test_reject_reused_samples_and_incoherent_last_sequence(self):
        m=self.load();rows=[m.decode(self.wire(i)) for i in range(512)]
        rows[1]['raw_first']=55
        with self.assertRaises(ValueError):m.validate_capture(rows)
        wire=bytearray(self.wire())
        struct.pack_into('<H',wire,158,4);wire[208]=3;wire[209]=5
        struct.pack_into('<3I',wire,16,55,55,57)
        with self.assertRaises(ValueError):m.decode(wire)

    def test_truncated_sequence_reserves_room_for_omitted_samples(self):
        m=self.load();wire=bytearray(self.wire())
        struct.pack_into('<3I',wire,16,55,56,60)
        struct.pack_into('<2I',wire,32,980,990)
        struct.pack_into('<2I',wire,44,985,995)
        struct.pack_into('<I',wire,56,60)
        struct.pack_into('<H',wire,158,4);wire[208]=3;wire[209]=5
        with self.assertRaises(ValueError):m.decode(wire)
        struct.pack_into('<I',wire,56,61)
        self.assertFalse(m.decode(wire)['raw_complete'])
