"""LWPL v1 authenticated envelope, not a session or command authorizer.

Callers must independently enforce session, replay, challenge age, and ownership.
No networking, credential discovery, or flight-control side effects live here.
"""
from dataclasses import dataclass
import hmac
import struct

_HEADER = struct.Struct("!4sBBBB16sQ16sH")
_KINDS = {0: frozenset((1, 3, 5, 6)), 1: frozenset((2, 4, 7))}
_MAX_PAYLOAD = 512
_TAG_SIZE = 32


@dataclass(frozen=True)
class Envelope:
    direction: int
    kind: int
    session: bytes
    sequence: int
    challenge: bytes
    payload: bytes


def _direction(value: int) -> None:
    if type(value) is not int or value not in _KINDS:
        raise ValueError("invalid direction")


def _key(value: bytes) -> None:
    if type(value) is not bytes or len(value) != 32:
        raise ValueError("key must contain exactly 32 bytes")


def _validate(frame: Envelope) -> None:
    if type(frame) is not Envelope:
        raise ValueError("invalid envelope")
    _direction(frame.direction)
    if type(frame.kind) is not int or frame.kind not in _KINDS[frame.direction]:
        raise ValueError("invalid message kind for direction")
    if type(frame.sequence) is not int or not 0 <= frame.sequence < 2**64:
        raise ValueError("sequence outside uint64")
    for identity in (frame.session, frame.challenge):
        if type(identity) is not bytes or len(identity) != 16:
            raise ValueError("identity must contain exactly 16 bytes")
    if type(frame.payload) is not bytes or len(frame.payload) > _MAX_PAYLOAD:
        raise ValueError("invalid payload")


def encode(envelope: Envelope, key: bytes) -> bytes:
    """Encode a canonical frame; possession of a key does not grant ownership."""
    _key(key)
    _validate(envelope)
    unsigned = _HEADER.pack(b"LWPL", 1, envelope.direction, envelope.kind, 0,
                            envelope.session, envelope.sequence,
                            envelope.challenge, len(envelope.payload)) + envelope.payload
    return unsigned + hmac.digest(key, unsigned, "sha256")


def decode(datagram: bytes, key: bytes, expected_direction: int) -> Envelope:
    """Authenticate one exact datagram, returning no partial result on failure."""
    _key(key)
    _direction(expected_direction)
    if (type(datagram) is not bytes
            or not _HEADER.size + _TAG_SIZE <= len(datagram)
            <= _HEADER.size + _MAX_PAYLOAD + _TAG_SIZE):
        raise ValueError("invalid datagram size or type")
    magic, version, direction, kind, flags, session, sequence, challenge, size = _HEADER.unpack_from(datagram)
    if (magic != b"LWPL" or version != 1 or flags != 0
            or direction != expected_direction
            or len(datagram) != _HEADER.size + size + _TAG_SIZE):
        raise ValueError("invalid envelope header")
    frame = Envelope(direction, kind, session, sequence, challenge,
                     datagram[_HEADER.size:-_TAG_SIZE])
    _validate(frame)
    expected = hmac.digest(key, datagram[:-_TAG_SIZE], "sha256")
    if not hmac.compare_digest(expected, datagram[-_TAG_SIZE:]):
        raise ValueError("authentication failed")
    return frame
