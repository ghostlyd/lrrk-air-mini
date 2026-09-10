import socket
import unittest
import threading
import time
from lrrk_litewing_ai.pilot_probe import probe_udp
from lrrk_litewing_ai.pilot_wire import Envelope, encode, decode


class Socket:
    type = socket.SOCK_DGRAM
    def __init__(self, root, invalid=False):
        self.root = root
        self.invalid = invalid
        self.sent = []
        self.closed = False
    def getpeername(self): return ('127.0.0.1',2390)
    def settimeout(self,value): self.timeout=value
    def send(self,packet): self.sent.append(packet); return len(packet)
    def recv(self,size):
        hello = decode(self.sent[0],self.root,0)
        payload = (b'x'*32 if self.invalid else hello.payload) + b'b'*32
        return encode(Envelope(1,2,b's'*16,0,b'c'*16,payload),self.root)
    def close(self): self.closed=True


class ProbeTests(unittest.TestCase):
    def test_authenticated_loopback_exchange_emits_hello_only(self):
        root=b'r'*32
        seen=[]
        failures=[]
        server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        server.bind(('127.0.0.1',0))
        server.settimeout(.2)
        def respond():
            try:
                packet,peer=server.recvfrom(595)
                hello=decode(packet,root,0)
                seen.append(hello.kind)
                reply=encode(Envelope(1,2,b's'*16,0,b'c'*16,hello.payload+b'b'*32),root)
                server.sendto(reply,peer)
                try:
                    packet,_=server.recvfrom(595)
                    seen.append(decode(packet,root,0).kind)
                except socket.timeout:
                    pass
            except Exception as error:
                failures.append(type(error).__name__)
            finally:
                server.close()
        client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        client.connect(server.getsockname())
        worker=threading.Thread(target=respond)
        worker.start()
        try:
            self.assertTrue(probe_udp(client,root,lambda:time.monotonic_ns()//1000))
        finally:
            worker.join(timeout=2)
            client.close()
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures,[])
        self.assertEqual(seen,[1])

    def test_proves_key_without_claim_and_closes(self):
        sock=Socket(b'r'*32)
        self.assertTrue(probe_udp(sock,b'r'*32,lambda:100))
        self.assertTrue(sock.closed)
        self.assertEqual(len(sock.sent),1)
        self.assertEqual(decode(sock.sent[0],b'r'*32,0).kind,1)

    def test_wrong_nonce_rejected_and_never_claimed(self):
        sock=Socket(b'r'*32,True)
        self.assertFalse(probe_udp(sock,b'r'*32,lambda:100))
        self.assertEqual(len(sock.sent),1)
        self.assertTrue(sock.closed)

    def test_timeout_has_iteration_bound_even_with_static_clock(self):
        sock=Socket(b'r'*32)
        calls=[]
        def timeout(size):
            calls.append(size)
            raise socket.timeout()
        sock.recv=timeout
        self.assertFalse(probe_udp(sock,b'r'*32,lambda:100))
        self.assertEqual(len(calls),64)
        self.assertEqual(len(sock.sent),1)
        self.assertTrue(sock.closed)
