"""Actual loopback datagrams, synthetic keys, no drone or external network."""
import socket
import time
import threading
import itertools
import unittest
from datetime import datetime, timezone
from lrrk_litewing_ai.telemetry_wire import TelemetryRecord, encode_telemetry
from lrrk_litewing_ai.pilot_keys import SessionKeys
from lrrk_litewing_ai.pilot_wire import Envelope, encode, decode
from lrrk_litewing_ai.pilot_operator import OperatorSession
from lrrk_litewing_ai.pilot_udp import OperatorUDP, admit_udp
from lrrk_litewing_ai.pilot_keys import derive_keys

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

    def test_real_udp_admission_then_pilot_and_stop(self):
        host,board=self.pair(); board.settimeout(2)
        root=b'r'*32; errors=[]; received=[]
        def board_peer():
            try:
                wire,peer=board.recvfrom(1024)
                hello=decode(wire,root,0)
                self.assertEqual((hello.kind,hello.sequence),(1,0))
                board_nonce=b'n'*32
                keys=derive_keys(root,hello.payload,board_nonce,self.identity)
                board.sendto(encode(Envelope(1,2,self.identity,0,b'q'*16,
                    hello.payload+board_nonce),root),peer)
                wire,_=board.recvfrom(1024)
                claim=decode(wire,keys.c2b,0)
                self.assertEqual((claim.kind,claim.sequence,len(claim.payload)),(3,1,16))
                self.assertEqual(claim.payload[:2],b'\x03\xe8')
                board.sendto(encode(Envelope(1,4,self.identity,1,b'q'*16,b''),keys.b2c),peer)
                board.sendto(encode_telemetry(
                    TelemetryRecord(0xEF69B6BC,1000,None,bytes(8)),
                    self.identity,1,keys.telemetry),peer)
                board.sendto(encode(Envelope(1,2,self.identity,2,b'z'*16,b''),keys.b2c),peer)
                for kind in (5,6):
                    wire,_=board.recvfrom(1024)
                    frame=decode(wire,keys.c2b,0)
                    self.assertEqual(frame.kind,kind)
                    received.append(frame.sequence)
            except BaseException as error: errors.append(error)
        worker=threading.Thread(target=board_peer,daemon=True); worker.start()
        samples=lambda:(1000,1500,1500,1500,1500,1500,1500,1500)
        link=admit_udp(host,root,samples,self.clock)
        self.addCleanup(link.close)
        self.assertFalse(link.step(samples))
        self.assertFalse(link.take_telemetry().snapshot.armed)
        self.assertTrue(link.step(samples))
        self.assertTrue(link.stop())
        worker.join(3)
        self.assertFalse(worker.is_alive())
        if errors: raise errors[0]
        self.assertEqual(received,[2,3])
    def test_admission_silence_retires_and_closes_socket(self):
        host,board=self.pair()
        ticks=itertools.count(0,100000)
        calls=[]
        with self.assertRaises(ValueError):
            admit_udp(host,b'r'*32,lambda:calls.append(1),lambda:next(ticks))
        self.assertEqual(calls,[])
        self.assertEqual(host.fileno(),-1)
        hello,_=board.recvfrom(1024)
        self.assertEqual(decode(hello,b'r'*32,0).kind,1)
        with self.assertRaises(socket.timeout): board.recvfrom(1024)

    def telemetry(self, sequence=1, key=None):
        return encode_telemetry(TelemetryRecord(0xEF69B6BC, 1000, None, bytes(8)),
                                self.identity, sequence, self.keys.telemetry if key is None else key)

    def test_telemetry_demux_does_not_sample_or_send_and_replaces_pending(self):
        host,board=self.pair()
        wall=datetime(2026,9,10,tzinfo=timezone.utc)
        session=OperatorSession(self.identity,self.keys,1000)
        link=OperatorUDP(session,host,lambda:2000,wall_clock=lambda:wall)
        self.addCleanup(link.close)
        calls=[]
        for seq in (1,2):
            board.sendto(self.telemetry(seq),host.getsockname())
            self.assertFalse(link.step(lambda:calls.append(1)))
        observation=link.take_telemetry()
        self.assertTrue(observation.snapshot.snapshot_id.endswith('-2'))
        self.assertEqual(observation.received_at,wall)
        self.assertEqual(observation.received_monotonic_us,2000)
        self.assertIsNone(observation.snapshot.link_age_ms)
        self.assertIsNone(link.take_telemetry())
        self.assertEqual(calls,[])
        with self.assertRaises(socket.timeout): board.recvfrom(1024)

    def test_telemetry_replay_and_wrong_key_never_renew_control(self):
        host,board=self.pair()
        now=[2000]
        session=OperatorSession(self.identity,self.keys,1000)
        link=OperatorUDP(session,host,lambda:now[0]); self.addCleanup(link.close)
        calls=[]
        for wire in (self.telemetry(),self.telemetry(),self.telemetry(2,self.keys.b2c)):
            board.sendto(wire,host.getsockname())
            self.assertFalse(link.step(lambda:calls.append(1)))
        self.assertTrue(link.take_telemetry().snapshot.snapshot_id.endswith('-1'))
        now[0]=101000
        board.sendto(self.telemetry(3),host.getsockname())
        with self.assertRaises(ValueError): link.step(lambda:calls.append(1))
        self.assertTrue(link.closed)
        self.assertIsNone(link.take_telemetry())
        self.assertEqual(calls,[])
        self.assertEqual(host.fileno(),-1)

    def test_stop_discards_pending_telemetry_and_preserves_control_sequence(self):
        host,board=self.pair()
        link=OperatorUDP(OperatorSession(self.identity,self.keys,1000),host,lambda:2000)
        self.addCleanup(link.close)
        board.sendto(self.proof(),host.getsockname())
        self.assertTrue(link.step(lambda:(1500,)*8))
        self.assertEqual(decode(board.recvfrom(1024)[0],self.keys.c2b,0).sequence,2)
        board.sendto(self.telemetry(),host.getsockname())
        self.assertFalse(link.step(lambda:self.fail('telemetry sampled controls')))
        self.assertTrue(link.stop())
        stop=decode(board.recvfrom(1024)[0],self.keys.c2b,0)
        self.assertEqual((stop.kind,stop.sequence),(6,3))
        self.assertIsNone(link.take_telemetry())

    def test_observation_polling_enforces_session_expiry(self):
        host,board=self.pair()
        now=[2000]
        session=OperatorSession(self.identity,self.keys,1000)
        link=OperatorUDP(session,host,lambda:now[0]); self.addCleanup(link.close)
        board.sendto(self.telemetry(),host.getsockname())
        self.assertFalse(link.step(lambda:(1500,)*8))
        now[0]=101000
        with self.assertRaises(ValueError): link.take_telemetry()
        self.assertTrue(session.closed)
        self.assertIsNone(link.take_telemetry())

    def test_telemetry_clock_failure_closes_both_paths(self):
        host,board=self.pair()
        def broken_wall(): raise RuntimeError('wall clock failure')
        session=OperatorSession(self.identity,self.keys,1000)
        link=OperatorUDP(session,host,lambda:2000,wall_clock=broken_wall)
        board.sendto(self.telemetry(),host.getsockname())
        with self.assertRaises(RuntimeError): link.step(lambda:(1500,)*8)
        self.assertTrue(session.closed)
        self.assertEqual(host.fileno(),-1)
        self.assertIsNone(link.take_telemetry())

    def test_invalid_wall_clock_value_clears_proof_and_telemetry(self):
        for invalid in (None,datetime(2026,9,10)):
            with self.subTest(invalid=invalid):
                host,board=self.pair()
                wall=[datetime(2026,9,10,tzinfo=timezone.utc)]
                session=OperatorSession(self.identity,self.keys,1000)
                link=OperatorUDP(session,host,lambda:2000,wall_clock=lambda:wall[0])
                self.addCleanup(link.close)
                board.sendto(self.proof(),host.getsockname())
                self.assertTrue(link.step(lambda:(1500,)*8))
                self.assertEqual(decode(board.recvfrom(1024)[0],self.keys.c2b,0).kind,5)
                board.sendto(self.telemetry(),host.getsockname())
                self.assertFalse(link.step(lambda:(1500,)*8))
                wall[0]=invalid
                board.sendto(self.telemetry(2),host.getsockname())
                with self.assertRaises(ValueError): link.step(lambda:(1500,)*8)
                self.assertTrue(session.closed)
                self.assertEqual(host.fileno(),-1)
                self.assertIsNone(link.take_telemetry())
                self.assertFalse(link.stop())
