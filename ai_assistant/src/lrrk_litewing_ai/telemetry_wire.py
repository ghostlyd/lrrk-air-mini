"""Bounded telemetry framing only; no replay, freshness or control authority.

Caller supplies the telemetry-derived key, never root/c2b/b2c. Key provenance
cannot be inferred from arbitrary bytes. Numeric object values require the
separate pinned snapshot parser before use. No credential discovery or I/O.
"""
from dataclasses import dataclass
import struct

from .pilot_wire import Envelope, decode, encode

_HEADER = struct.Struct("!BBHIQQ")
_SIZES = {0xD7E0D964: 28, 0xEF69B6BC: 8, 0x26962352: 30,
          0x6B7639EC: 25, 0xB8229FE4: 29}
_UNKNOWN = 2**64-1
_MAX_TIME = 2**63-1


@dataclass(frozen=True)
class TelemetryRecord:
    object_id: int
    serialized_us: int
    sample_age_us: int | None
    data: bytes


def _validate(record: TelemetryRecord) -> None:
    if type(record) is not TelemetryRecord:
        raise ValueError("invalid telemetry record")
    if type(record.object_id) is not int or record.object_id not in _SIZES:
        raise ValueError("unsupported telemetry object")
    if type(record.data) is not bytes or len(record.data) != _SIZES[record.object_id]:
        raise ValueError("invalid telemetry object length or type")
    if type(record.serialized_us) is not int or not 0 <= record.serialized_us <= _MAX_TIME:
        raise ValueError("invalid serialization timestamp")
    if record.sample_age_us is not None and (
            type(record.sample_age_us) is not int
            or not 0 <= record.sample_age_us <= record.serialized_us):
        raise ValueError("invalid sample age")


def encode_record(record: TelemetryRecord) -> bytes:
    _validate(record)
    age = _UNKNOWN if record.sample_age_us is None else record.sample_age_us
    return _HEADER.pack(1, 0, len(record.data), record.object_id,
                        record.serialized_us, age) + record.data


def decode_record(payload: bytes) -> TelemetryRecord:
    if type(payload) is not bytes or not 32 <= len(payload) <= 54:
        raise ValueError("invalid telemetry payload size or type")
    version, reserved, size, obj, stamp, age = _HEADER.unpack_from(payload)
    if version != 1 or reserved != 0 or len(payload) != 24 + size:
        raise ValueError("invalid telemetry payload header")
    record = TelemetryRecord(obj, stamp, None if age == _UNKNOWN else age, payload[24:])
    _validate(record)
    return record


def _frame_validate(frame: Envelope) -> None:
    if (frame.direction != 1 or frame.kind != 8 or frame.session == bytes(16)
            or frame.sequence == 0 or frame.challenge != bytes(16)):
        raise ValueError("invalid telemetry envelope")


def encode_telemetry(record: TelemetryRecord, session: bytes, sequence: int, key: bytes) -> bytes:
    frame = Envelope(1, 8, session, sequence, bytes(16), encode_record(record))
    _frame_validate(frame)
    return encode(frame, key)


def decode_telemetry(datagram: bytes, key: bytes) -> tuple[Envelope, TelemetryRecord]:
    if type(datagram) is not bytes or not 114 <= len(datagram) <= 136:
        raise ValueError("invalid telemetry datagram size or type")
    frame = decode(datagram, key, 1)
    _frame_validate(frame)
    return frame, decode_record(frame.payload)
