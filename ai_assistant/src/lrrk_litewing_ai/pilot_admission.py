"""Operator-client mutual admission, without networking or flight commands.

Caller supplies a fresh CSPRNG host nonce per attempt and monotonic microseconds.
This object is single-use and caller-serialized. `established` records only the
handshake result, not current link health, ownership, arming, or flight readiness.
Do not expose this object or its keys to assistant tools. Python cannot guarantee
secure erasure of immutable bytes; close drops references, not physical copies.
"""
import hmac
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
        self._started = self._last = None

    @property
    def established(self) -> bool:
        return self._phase == "established"

    def close(self) -> None:
        self._root = self._host = self._keys = None
        self._session = self._challenge = None
        self._phase = "closed"

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

    def receive_challenge(self, datagram: bytes, now_us: int) -> bytes:
        if self._phase != "challenge":
            raise ValueError("not awaiting challenge")
        self._time(now_us)
        frame = decode(datagram, self._root, 1)
        if (frame.kind != 2 or frame.sequence != 0 or len(frame.payload) != 64
                or not hmac.compare_digest(frame.payload[:32], self._host)):
            raise ValueError("invalid board proof")
        keys = derive_keys(self._root, self._host, frame.payload[32:], frame.session)
        claim = encode(Envelope(0, 3, frame.session, 1, frame.challenge, b""), keys.c2b)
        self._keys = keys
        self._session, self._challenge = frame.session, frame.challenge
        self._root = self._host = None
        self._phase = "accept"
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
