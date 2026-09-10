"""Actual loopback datagrams, synthetic keys, no drone or external network."""
import socket
import time
import unittest
from lrrk_litewing_ai.pilot_keys import SessionKeys
from lrrk_litewing_ai.pilot_wire import Envelope, encode, decode
from lrrk_litewing_ai.pilot_operator import OperatorSession
from lrrk_litewing_ai.pilot_udp import OperatorUDP

class UDPTests(unittest.TestCase):
    keys=SessionKeys(b'c'*32,b'b'*32,b't'*32)
    identity=b's'*16
    def pair(self, socket_type=socket.socket):
        board=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.addCleanup(board.close)
        board.bind(('127.0.0.1',0)); board.settimeout(.2)
        host=socket_type(socket.AF_INET,socket.SOCK_DGRAM)
        self.addCleanup(host.close)
        host.connect(board.getsockname())
        return host,board
    def clock(self): return time.monotonic_ns()//1000
    def proof(self):
        return encode(Envelope(1,2,self.identity,2,b'q'*16,b''),self.keys.b2c)
    def test_authenticated_loopback_pilot_and_stop(self):
        host,board=self.pair()
        session=OperatorSession(self.identity,self.keys,self.clock())
        link=OperatorUDP(session,host,self.clock); self.addCleanup(link.close)
        board.sendto(self.proof(),host.getsockname())
        self.assertTrue(link.step(lambda:(1000,1500,1500,1500,1500,1500,1500,1500)))
        wire,_=board.recvfrom(1024)
        frame=decode(wire,self.keys.c2b,0)
        self.assertEqual((frame.kind,frame.sequence,frame.payload[:2]),(5,2,b'\x03\xe8'))
        self.assertTrue(link.stop())
        wire,_=board.recvfrom(1024)
        frame=decode(wire,self.keys.c2b,0)
        self.assertEqual((frame.kind,frame.sequence,frame.payload),(6,3,b''))
        self.assertTrue(link.closed)
        self.assertEqual(host.fileno(),-1)
    def test_invalid_and_oversized_datagrams_do_not_sample_or_transmit(self):
        host,board=self.pair()
        session=OperatorSession(self.identity,self.keys,1000)
        link=OperatorUDP(session,host,lambda:2000); self.addCleanup(link.close)
        calls=[]
        for wire in (b'x'*2048,self.proof()[:-1]+b'!'):
            board.sendto(wire,host.getsockname())
            self.assertFalse(link.step(lambda:calls.append(1)))
        self.assertEqual(calls,[])
        with self.assertRaises(socket.timeout): board.recvfrom(1024)
    def test_silence_expires_session_without_new_packet(self):
        host,board=self.pair()
        session=OperatorSession(self.identity,self.keys,1000)
        link=OperatorUDP(session,host,lambda:101000)
        with self.assertRaises(ValueError): link.step(lambda:(1500,)*8)
        self.assertTrue(link.closed)
        self.assertEqual(host.fileno(),-1)
    def test_sampler_fault_closes_socket_and_stop_without_proof_sends_nothing(self):
        host,board=self.pair()
        link=OperatorUDP(OperatorSession(self.identity,self.keys,self.clock()),host,self.clock)
        board.sendto(self.proof(),host.getsockname())
        def fail(): raise RuntimeError('input disconnected')
        with self.assertRaises(RuntimeError): link.step(fail)
        self.assertTrue(link.closed)
        self.assertEqual(host.fileno(),-1)
        host,board=self.pair()
        link=OperatorUDP(OperatorSession(self.identity,self.keys,self.clock()),host,self.clock)
        self.assertFalse(link.stop())
        self.assertTrue(link.closed)
    def test_send_failure_retires_without_retry(self):
        class FailedSend(socket.socket):
            def send(self, data, *args): raise OSError('injected send failure')
        host,board=self.pair(FailedSend)
        session=OperatorSession(self.identity,self.keys,self.clock())
        link=OperatorUDP(session,host,self.clock)
        board.sendto(self.proof(),host.getsockname())
        with self.assertRaises(OSError): link.step(lambda:(1500,)*8)
        self.assertTrue(session.closed)
        self.assertEqual(host.fileno(),-1)
        with self.assertRaises(socket.timeout): board.recvfrom(1024)
    def test_connected_socket_filters_other_peer(self):
        host,board=self.pair()
        other=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.addCleanup(other.close)
        link=OperatorUDP(OperatorSession(self.identity,self.keys,1000),host,lambda:2000)
        self.addCleanup(link.close)
        other.sendto(self.proof(),host.getsockname())
        calls=[]
        self.assertFalse(link.step(lambda:calls.append(1)))
        self.assertEqual(calls,[])
