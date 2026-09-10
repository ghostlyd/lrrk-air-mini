"""Operator-client mutual admission, without networking or flight commands.

Caller supplies a fresh CSPRNG host nonce per attempt and monotonic microseconds.
This object is single-use and caller-serialized. `established` records only the
handshake result, not current link health, ownership, arming, or flight readiness.
Do not expose this object or its keys to assistant tools. Python cannot guarantee
secure erasure of immutable bytes; close drops references, not physical copies.
"""
import hmac
import struct
from .pilot_keys import derive_keys
from .pilot_wire import Envelope, decode, encode


class PilotAdmission:
    def __init__(self, root: bytes, host_nonce: bytes):
        for value in (root, host_nonce):
            if type(value) is not bytes or len(value) != 32:
                raise ValueError("invalid admission input")
        self._root = root
        self._host = host_nonce
        self._keys = None
        self._session = self._challenge = None
        self._phase = "new"
        self._sampled_claim = False
        self._started = self._last = None

    @property
    def established(self) -> bool:
        return self._phase == "established"

    @property
    def closed(self) -> bool:
        return self._phase == "closed"

    def check_time(self, now_us):
        if self._phase in ("new", "closed"):
            raise ValueError("admission not active")
        self._time(now_us)

    def close(self) -> None:
        self._root = self._host = self._keys = None
        self._session = self._challenge = None
        self._phase = "closed"
        self._sampled_claim = False

    def _time(self, now: int) -> None:
        if type(now) is not int or not 0 <= now < 2**63:
            self.close()
            raise ValueError("invalid monotonic time")
        if self._last is not None and (now < self._last or now - self._started >= 1_000_000):
            self.close()
            raise ValueError("admission expired or clock rolled back")
        self._last = now

    def begin(self, now_us: int) -> bytes:
        if self._phase != "new":
            raise ValueError("admission already started or closed")
        self._time(now_us)
        self._started = now_us
        hello = encode(Envelope(0, 1, bytes(16), 0, bytes(16), self._host), self._root)
        self._phase = "challenge"
        return hello

    def receive_challenge(self, datagram: bytes, now_us: int,
                          samples: tuple[int, ...] | None = None) -> bytes:
        """Supply operator samples captured after receipt of this challenge.

        None preserves the legacy handshake-only fixture transcript; the runtime
        controller rejects that empty CLAIM and never grants it ownership.
        """
        frame = self._board_proof(datagram, now_us)
        return self._claim(frame, samples)

    def verify_challenge_only(self, datagram: bytes, now_us: int) -> None:
        """Verify fresh root-key reachability, then retire without making CLAIM.

        No operator keys/session are produced. This neither establishes flight
        ownership nor proves the AP password, firmware identity or reboot.
        """
        try:
            self._board_proof(datagram, now_us)
        finally:
            self.close()

    def _board_proof(self, datagram, now_us):
        if self._phase != "challenge":
            raise ValueError("not awaiting challenge")
        self._time(now_us)
        frame = decode(datagram, self._root, 1)
        if (frame.kind != 2 or frame.sequence != 0 or len(frame.payload) != 64
                or not hmac.compare_digest(frame.payload[:32], self._host)):
            raise ValueError("invalid board proof")
        return frame

    def receive_challenge_sampled(self, datagram, received_us, sample, clock):
        """Authenticate before invoking the operator, bound its sampling delay."""
        if self._phase != "challenge":
            raise ValueError("not awaiting challenge")
        try:
            now=clock()
            self._time(now)
            if (type(received_us) is not int or not 0<=received_us<=now
                    or now-received_us>75_000):
                raise ValueError("invalid board-proof receive time")
        except BaseException:
            self.close()
            raise
        frame=self._board_proof(datagram,now)
        try:
            samples=sample()
            if samples is None:
                raise ValueError("operator samples required")
            end=clock()
            self._time(end)
            if end-received_us>75_000:
                raise ValueError("admission sample expired")
            return self._claim(frame,samples)
        except BaseException:
            self.close()
            raise

    def _claim(self, frame, samples):
        if samples is not None and (type(samples) is not tuple or len(samples) != 8
                or any(type(v) is not int or not 1000 <= v <= 2000 for v in samples)):
            raise ValueError("invalid admission samples")
        payload = b"" if samples is None else struct.pack("!8H", *samples)
        keys = derive_keys(self._root, self._host, frame.payload[32:], frame.session)
        claim = encode(Envelope(0, 3, frame.session, 1, frame.challenge, payload), keys.c2b)
        self._keys = keys
        self._session, self._challenge = frame.session, frame.challenge
        self._root = self._host = None
        self._phase = "accept"
        self._sampled_claim = samples is not None
        return claim

    def receive_accept(self, datagram: bytes, now_us: int) -> None:
        if self._phase != "accept":
            raise ValueError("not awaiting acceptance")
        self._time(now_us)
        frame = decode(datagram, self._keys.b2c, 1)
        if (frame.kind != 4 or frame.sequence != 1 or frame.payload
                or frame.session != self._session or frame.challenge != self._challenge):
            raise ValueError("invalid board acceptance")
        self._phase = "established"

    def take_operator_session(self, now_us: int):
        """Transfer accepted sampled admission once; never expose to AI tools."""
        if self._phase != "established" or not self._sampled_claim:
            raise ValueError("sampled admission not established")
        self._time(now_us)
        from .pilot_operator import OperatorSession
        operator = OperatorSession(self._session, self._keys, now_us)
        self.close()
        return operator
