"""Pure physical-USB maintenance codec, never an AI tool or serial transport.

These functions perform no I/O and generate no credentials. The future operator
transport must durably save its private pending bundle before submission, avoid
logging these bytes, and poll status after a lost ACK rather than retransmit.
Python immutable copies cannot be reliably erased. CRC is not authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from .uavtalk import crc8

SUBMISSION_ID = 0x4C575046
STATUS_ID = 0x4C575048


class ProvisioningWireError(ValueError):
    """Malformed maintenance data; messages deliberately omit input values."""


def _transaction(value: bytes) -> None:
    if type(value) is not bytes or len(value) != 16 or not any(value):
        raise ProvisioningWireError("invalid transaction ID")


def _text(value: str, minimum: int, maximum: int) -> bytes:
    if type(value) is not str or not minimum <= len(value) <= maximum:
        raise ProvisioningWireError("invalid credential text")
    if any(not 32 <= ord(character) <= 126 for character in value):
        raise ProvisioningWireError("invalid credential text")
    return value.encode("ascii")


def encode_config(ssid: str, password: str, root: bytes) -> bytes:
    """LWCF v1 serialization. Validation does not establish key entropy."""
    name = _text(ssid, 1, 32)
    secret = _text(password, 16, 63)
    if type(root) is not bytes or len(root) != 32 or not any(root):
        raise ProvisioningWireError("invalid application key")
    return (b"LWCF" + bytes((1, len(name), len(secret), 0)) + root
            + name.ljust(32, b"\0") + secret.ljust(64, b"\0"))


def _config(blob: bytes) -> None:
    if (type(blob) is not bytes or len(blob) != 136 or blob[:4] != b"LWCF"
            or blob[4] != 1 or blob[7] != 0 or not any(blob[8:40])
            or not 1 <= blob[5] <= 32 or not 16 <= blob[6] <= 63):
        raise ProvisioningWireError("invalid credential blob")
    for start, used, capacity in ((40, blob[5], 32), (72, blob[6], 64)):
        if (any(not 32 <= byte <= 126 for byte in blob[start:start+used])
                or any(blob[start+used:start+capacity])):
            raise ProvisioningWireError("invalid credential blob")


def _packet(message: int, object_id: int, payload: bytes = b"") -> bytes:
    packet = struct.pack("<BBHIH", 0x3C, message, 10+len(payload), object_id, 0) + payload
    return packet + bytes((crc8(packet),))


def submission(transaction: bytes, blob: bytes) -> bytes:
    """Construct an exact OBJ_ACK request; caller must already hold saved bytes."""
    _transaction(transaction)
    _config(blob)
    return _packet(0x22, SUBMISSION_ID, transaction + blob)


def status_request() -> bytes:
    return _packet(0x21, STATUS_ID)


def _frame(packet: bytes, message: int, object_id: int, size: int) -> bytes:
    if type(packet) is not bytes or len(packet) != size+11:
        raise ProvisioningWireError("invalid maintenance frame length")
    if packet[:10] != struct.pack("<BBHIH", 0x3C, message, size+10, object_id, 0):
        raise ProvisioningWireError("invalid maintenance frame header")
    if crc8(packet[:-1]) != packet[-1]:
        raise ProvisioningWireError("invalid maintenance frame checksum")
    return packet[10:-1]


@dataclass(frozen=True)
class ProvisioningStatus:
    phase: int
    result: int
    transaction: bytes

    @property
    def persisted_and_finished(self) -> bool:
        """Commit/readback and cleanup completed, not power-loss or radio proof."""
        return self.phase == 6 and self.result == 4


def parse_status(packet: bytes, expected_transaction: bytes) -> ProvisioningStatus:
    """Validate one complete response for an existing pending transaction.

    Fragment assembly belongs to the bounded serial transport. Unknown outcomes
    raise rather than promote or delete either old or pending credential bundle.
    """
    _transaction(expected_transaction)
    payload = _frame(packet, 0x20, STATUS_ID, 24)
    if (payload[0] != 1 or payload[1] > 6 or payload[2] > 4
            or payload[3] or any(payload[20:24])):
        raise ProvisioningWireError("invalid maintenance status")
    if payload[4:20] != expected_transaction:
        raise ProvisioningWireError("maintenance transaction mismatch")
    return ProvisioningStatus(payload[1], payload[2], payload[4:20])


def parse_receipt(packet: bytes) -> bool:
    """True=queued ACK, False=rejected NACK. Neither establishes persistence.

    UAVTalk ACK carries no transaction ID; status correlation is mandatory.
    """
    if type(packet) is not bytes or len(packet) != 11 or packet[1] not in (0x23, 0x24):
        raise ProvisioningWireError("invalid maintenance receipt")
    _frame(packet, packet[1], SUBMISSION_ID, 0)
    return packet[1] == 0x23
