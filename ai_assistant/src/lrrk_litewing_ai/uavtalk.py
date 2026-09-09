"""Receive-only framing for the manifest-pinned NinjaPilot UAVTalk dialect.

This dialect always carries a two-byte instance ID, including single-instance
objects. CRC integrity is not sender authentication. Payload interpretation and
state freshness require a separately verified UAVObject schema.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Optional


class UAVTalkError(ValueError):
    """Capture contains malformed or incomplete framing."""


def crc8(data: bytes) -> int:
    """CRC-8: polynomial 0x07, initial zero, no reflection or final XOR."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ (0x07 if crc & 0x80 else 0)) & 0xFF
    return crc


@dataclass(frozen=True)
class UAVTalkFrame:
    message_type: int
    object_id: int
    instance_id: int
    timestamp_ticks: Optional[int]
    payload: bytes


class UAVTalkDecoder:
    """Strict incremental parser. Errors clear pending bytes and raise.

    Input must start on a frame boundary; silently skipping corruption could
    hide lost telemetry. The payload cap is 217 bytes, UAVOBJECTS_LARGEST from
    the generated headers at ac77304a58de6c8bd552f94668b46903adb71cb2.
    """

    MAX_PAYLOAD = 217
    MAX_CHUNK = 4096
    _TYPES = frozenset((0x20, 0x21, 0x22, 0x23, 0x24, 0xA0, 0xA2))
    _CONTROL = frozenset((0x21, 0x23, 0x24))

    def __init__(self) -> None:
        self._pending = bytearray()

    def feed(self, chunk: bytes) -> list[UAVTalkFrame]:
        if not isinstance(chunk, bytes):
            raise TypeError("UAVTalk input must be bytes")
        if len(chunk) > self.MAX_CHUNK:
            self._pending.clear()
            raise UAVTalkError("input chunk exceeds 4096 bytes")
        self._pending.extend(chunk)
        frames = []
        try:
            while self._pending:
                if self._pending[0] != 0x3C:
                    raise UAVTalkError("invalid sync byte")
                if len(self._pending) < 2:
                    break
                kind = self._pending[1]
                if kind not in self._TYPES:
                    raise UAVTalkError("unsupported message type")
                if len(self._pending) < 4:
                    break
                size = int.from_bytes(self._pending[2:4], "little")
                header_size = 12 if kind & 0x80 else 10
                if not header_size <= size <= header_size + self.MAX_PAYLOAD:
                    raise UAVTalkError("invalid packet length")
                if kind in self._CONTROL and size != header_size:
                    raise UAVTalkError("control frame must have no payload")
                if len(self._pending) < size + 1:
                    break
                packet = bytes(self._pending[:size])
                if crc8(packet) != self._pending[size]:
                    raise UAVTalkError("CRC mismatch")
                frames.append(UAVTalkFrame(
                    message_type=kind,
                    object_id=int.from_bytes(packet[4:8], "little"),
                    instance_id=int.from_bytes(packet[8:10], "little"),
                    timestamp_ticks=(int.from_bytes(packet[10:12], "little")
                                     if kind & 0x80 else None),
                    payload=packet[header_size:],
                ))
                del self._pending[:size + 1]
        except UAVTalkError:
            self._pending.clear()
            raise
        return frames

    def finish(self) -> None:
        if self._pending:
            self._pending.clear()
            raise UAVTalkError("truncated frame at end of capture")


def read_frames(stream: BinaryIO) -> Iterator[UAVTalkFrame]:
    """Decode a binary capture without requesting or acknowledging objects."""
    decoder = UAVTalkDecoder()
    while True:
        chunk = stream.read(decoder.MAX_CHUNK)
        if not chunk:
            break
        yield from decoder.feed(chunk)
    decoder.finish()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a saved UAVTalk binary capture")
    parser.add_argument("capture", type=Path)
    args = parser.parse_args(argv)
    try:
        # A capture is an ordinary file; this command must never open a device.
        if not args.capture.is_file():
            raise UAVTalkError("capture must be a regular file")
        with args.capture.open("rb") as stream:
            for frame in read_frames(stream):
                record = asdict(frame)
                record["payload"] = frame.payload.hex()
                print(json.dumps(record, sort_keys=True))
    except (OSError, UAVTalkError) as exc:
        print("capture rejected: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
