"""Fixed LWPL session-key transcript using RFC5869 HKDF-SHA-256.

No credential discovery or command authority. Python bytes cannot promise secure
erasure; callers must keep these values out of logs and model tool responses.
"""
from dataclasses import dataclass, field
import hmac


@dataclass(frozen=True)
class SessionKeys:
    c2b: bytes = field(repr=False)
    b2c: bytes = field(repr=False)
    telemetry: bytes = field(repr=False)


def derive_keys(root: bytes, host_nonce: bytes, board_nonce: bytes,
                session: bytes) -> SessionKeys:
    """Derive three 32-byte role-separated keys from the authenticated transcript."""
    for value, size in ((root, 32), (host_nonce, 32), (board_nonce, 32), (session, 16)):
        if type(value) is not bytes or len(value) != size:
            raise ValueError("invalid key transcript input")
    prk = hmac.digest(host_nonce + board_nonce, root, "sha256")
    # Each requested output is one SHA-256 block, so RFC5869's first expansion
    # block is the complete output. Labels exclude a C-string terminator.
    keys = [hmac.digest(prk, label + session + b"\x01", "sha256")
            for label in (b"LWPL/v1/c2b/", b"LWPL/v1/b2c/", b"LWPL/v1/telemetry/")]
    return SessionKeys(*keys)
