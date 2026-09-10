"""One-shot application-key reachability over a caller-connected UDP socket.

No CLAIM, operator session, flight controls, AP association or reboot. A HELLO
does create temporary challenge state on the responder; do not run concurrently
with pilot admission. Root-key proof is not firmware or device attestation.
"""
import secrets
import socket
import argparse
import ipaddress
from pathlib import Path
import time
from .pilot_admission import PilotAdmission
from .provisioning_bundle import load_pending, BundleError


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


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True,help='private pending bundle retained after provisioning')
    parser.add_argument('--host',required=True,help='explicit IPv4 endpoint on the already joined network')
    args=parser.parse_args(argv)
    sock=None
    verified=False
    try:
        host=str(ipaddress.IPv4Address(args.host))
        _,blob=load_pending(args.bundle)
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        sock.settimeout(.02)
        sock.connect((host,2390))
        owned,sock=sock,None
        verified=probe_udp(owned,blob[8:40],lambda:time.monotonic_ns()//1000)
    except (OSError,ValueError,BundleError):
        verified=False
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                verified=False
    print('application key reachable; ownership and flight not verified' if verified
          else 'application key reachability unverified; credentials retained')
    return 0 if verified else 2


if __name__=='__main__':
    raise SystemExit(main())
