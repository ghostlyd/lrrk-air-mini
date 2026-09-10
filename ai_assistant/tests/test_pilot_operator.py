import unittest
from lrrk_litewing_ai.pilot_keys import SessionKeys
from lrrk_litewing_ai.pilot_wire import Envelope, encode, decode
from lrrk_litewing_ai.pilot_operator import OperatorSession

class OperatorTests(unittest.TestCase):
    keys=SessionKeys(b'c'*32,b'b'*32,b't'*32)
    identity=b's'*16
    def proof(self, sequence=2, key=None, **changes):
        values=dict(direction=1,kind=2,session=self.identity,sequence=sequence,
                    challenge=b'q'*16,payload=b'')
        values.update(changes)
        return encode(Envelope(**values),key or self.keys.b2c)
    def make(self): return OperatorSession(self.identity,self.keys,1000)
    def test_authentication_precedes_sampling_and_replay_never_resamples(self):
        session=self.make(); calls=[]
        sample=lambda: calls.append(1) or (1000,1500,1500,1500,1500,1000,2000,1234)
        for wire in (self.proof(key=self.keys.telemetry),self.proof(sequence=1),
                     self.proof(session=b'x'*16),self.proof(payload=b'x')):
            with self.assertRaises(ValueError): session.pilot(wire,2000,sample,lambda:2100)
        self.assertEqual(calls,[])
        command=session.pilot(self.proof(),2000,sample,lambda:2100)
        frame=decode(command,self.keys.c2b,0)
        self.assertEqual((frame.kind,frame.sequence,frame.challenge),(5,2,b'q'*16))
        self.assertEqual(frame.payload,b'\x03\xe8\x05\xdc\x05\xdc\x05\xdc\x05\xdc\x03\xe8\x07\xd0\x04\xd2')
        with self.assertRaises(ValueError): session.pilot(self.proof(),2200,sample,lambda:2300)
        self.assertEqual(calls,[1])
    def test_slow_sampler_fault_and_timeout_retire(self):
        for end in (1999,77001,102000):
            session=self.make(); times=iter((2100,end))
            with self.assertRaises(ValueError):
                session.pilot(self.proof(),2000,lambda:(1500,)*8,lambda:next(times))
            self.assertTrue(session.closed)
        session=self.make()
        def failed(): raise RuntimeError("input disconnected")
        with self.assertRaises(RuntimeError): session.pilot(self.proof(),2000,failed,lambda:2100)
        self.assertTrue(session.closed)
        session=self.make()
        with self.assertRaises(ValueError): session.pilot(self.proof(),101000,lambda:(1500,)*8,lambda:101000)
        self.assertTrue(session.closed)
    def test_stop_is_authenticated_once_and_retires(self):
        session=self.make()
        command=session.stop(self.proof(),2000,lambda:2100)
        frame=decode(command,self.keys.c2b,0)
        self.assertEqual((frame.kind,frame.sequence,frame.payload),(6,2,b''))
        self.assertTrue(session.closed)
        with self.assertRaises(ValueError): session.stop(self.proof(3),3000,lambda:3100)
    def test_stop_can_reuse_last_live_proof_without_waiting_for_next_challenge(self):
        session=self.make()
        session.pilot(self.proof(),2000,lambda:(1500,)*8,lambda:2100)
        command=session.stop(self.proof(),2200,lambda:2300)
        self.assertEqual(decode(command,self.keys.c2b,0).sequence,3)
        self.assertTrue(session.closed)
    def test_invalid_operator_values_never_emit(self):
        for values in ((True,)*8,(999,)*8,(2001,)*8,(1500,)*7,[1500]*8):
            session=self.make()
            with self.assertRaises(ValueError): session.pilot(self.proof(),2000,lambda:values,lambda:2100)
            self.assertTrue(session.closed)
