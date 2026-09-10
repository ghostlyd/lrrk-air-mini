"""One-shot application-key reachability over a caller-connected UDP socket.

No CLAIM, operator session, flight controls, AP association or reboot. A HELLO
does create temporary challenge state on the responder; do not run concurrently
with pilot admission. Root-key proof is not firmware or device attestation.
"""
import secrets
import socket
from .pilot_admission import PilotAdmission


def probe_udp(sock, root: bytes, clock) -> bool:
    """Own and close socket. Clock returns monotonic integer microseconds."""
    admission = None
    verified = False
    try:
        if sock.type != socket.SOCK_DGRAM:
            raise ValueError()
        sock.getpeername()
        sock.settimeout(.02)
        admission = PilotAdmission(root,secrets.token_bytes(32))
        hello = admission.begin(clock())
        if sock.send(hello) != len(hello):
            raise OSError()
        for _ in range(64):
            admission.check_time(clock())
            try:
                wire = sock.recv(595)
            except socket.timeout:
                continue
            admission.verify_challenge_only(wire,clock())
            verified = True
            break
    except (ValueError, TypeError, OSError):
        verified = False
    finally:
        if admission is not None:
            admission.close()
        try:
            sock.close()
        except OSError:
            verified = False
    return verified
