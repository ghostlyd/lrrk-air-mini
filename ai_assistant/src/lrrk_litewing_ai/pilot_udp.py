"""Bounded transport for a mutually admitted human operator, never AI tools.

Caller provides an already-connected UDP socket and an accepted OperatorSession.
This object owns both on entry, including constructor failure. It neither finds
credentials nor chooses a peer, starts admission, or reconnects automatically.
One serialized owner calls step frequently; no background sender or retransmit.
"""
import socket
import secrets
from .pilot_operator import OperatorSession
from .pilot_admission import PilotAdmission


def admit_udp(sock: socket.socket, root: bytes, sample, clock):
    """Own the connected socket; perform one bounded sampled admission attempt.

    CSPRNG nonce per attempt. No retransmission or automatic re-admission.
    Timeout, callback or send failure closes the socket and credential references.
    Invalid packets cannot invoke the sampler; work is capped at 64 receive
    attempts and the admission core's one-second monotonic deadline.
    """
    admission=None
    transferred=False
    try:
        if sock.type!=socket.SOCK_DGRAM:
            raise ValueError("connected UDP socket required")
        sock.getpeername()
        sock.settimeout(0.02)
        admission=PilotAdmission(root,secrets.token_bytes(32))
        hello=admission.begin(clock())
        if sock.send(hello)!=len(hello): raise OSError("incomplete HELLO send")
        awaiting_claim=True
        for _ in range(64):
            admission.check_time(clock())
            try:
                wire=sock.recv(595)
            except socket.timeout:
                continue
            received=clock()
            if len(wire)>594: continue
            try:
                if awaiting_claim:
                    claim=admission.receive_challenge_sampled(wire,received,sample,clock)
                else:
                    admission.receive_accept(wire,received)
            except ValueError:
                if admission.closed: raise
                continue
            if awaiting_claim:
                if sock.send(claim)!=len(claim): raise OSError("incomplete CLAIM send")
                awaiting_claim=False
            else:
                session=admission.take_operator_session(clock())
                link=OperatorUDP(session,sock,clock)
                transferred=True
                return link
        raise TimeoutError("admission receive-work budget exhausted")
    finally:
        if admission is not None: admission.close()
        if not transferred: sock.close()


class OperatorUDP:
    def __init__(self, session: OperatorSession, sock: socket.socket, clock):
        self._session, self._socket, self._clock = session, sock, clock
        self._closed = False
        self._proof = None
        self._received = None
        try:
            if session.closed or sock.type != socket.SOCK_DGRAM:
                raise ValueError("accepted session and UDP socket required")
            sock.getpeername()  # Refuse unconnected sockets; kernel filters peer.
            sock.settimeout(0.02)
        except BaseException:
            self.close()
            raise

    @property
    def closed(self): return self._closed or self._session.closed

    def close(self):
        if not self._closed:
            self._closed=True
            self._proof=self._received=None
            self._session.close()
            self._socket.close()

    def _send(self, wire):
        if self._socket.send(wire)!=len(wire):
            raise OSError("incomplete operator datagram send")

    def step(self, sample):
        """Process at most one datagram; true means sent, not board-accepted."""
        if self.closed:
            self.close()
            raise ValueError("operator transport closed")
        try:
            try:
                # One byte over the schema maximum detects oversized/truncated
                # datagrams without relying on platform-specific recvmsg flags.
                wire=self._socket.recv(595)
            except socket.timeout:
                self._session.check_time(self._clock())
                return False
            received=self._clock()
            self._session.check_time(received)
            if len(wire)>594: return False
            try:
                command=self._session.pilot(wire,received,sample,self._clock)
            except ValueError:
                if self._session.closed: raise
                return False  # Bad authentication/replay: no sampler or renewal.
            self._send(command)
            self._proof, self._received=wire,received
            return True
        except BaseException:
            self.close()
            raise

    def stop(self):
        """Send one authenticated STOP if a cached proof is live, then close.

        False means no STOP was sent. Board link-loss failsafe remains necessary;
        even true is only a local send result, not a motor-stop acknowledgement.
        """
        try:
            if self.closed or self._proof is None: return False
            try:
                wire=self._session.stop(self._proof,self._received,self._clock)
            except ValueError:
                return False
            self._send(wire)
            return True
        finally:
            self.close()
