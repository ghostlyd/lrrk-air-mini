"""Bounded operator-only USB transactions over an already opened private stream.

No device opening, resets, credential generation, capture, AI registration or
bundle promotion. Caller exclusively owns a bounded-timeout stream positioned
at a UAVTalk frame boundary. CRC is not authentication. Serial exceptions and
protocol uncertainty never authorize retransmission or deletion of bundles.
"""
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import time

from .provisioning_bundle import save_pending, load_pending
from .uavtalk import UAVTalkDecoder, UAVTalkError, crc8
from .usb_provisioning_wire import (
    STATUS_ID, SUBMISSION_ID, submission, status_request, parse_status,
    parse_receipt, ProvisioningWireError,
)


@dataclass(frozen=True)
class TransactionResult:
    outcome: str  # verified, not_written, unknown, unavailable

    @property
    def verified(self):
        """Firmware reports readback + cleanup, not activated or power-loss proof."""
        return self.outcome == 'verified'


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _exchange(port, transaction, request, clock):
    # Enforce the transport contract before transmitting. A malicious/custom
    # implementation can still ignore its timeouts; this is not a thread kill.
    try:
        if any(not _finite(value) or not 0 < value <= limit
               for value, limit in ((port.timeout, .05), (port.write_timeout, .2))):
            return TransactionResult('unavailable')
        start = last = clock()
        if not _finite(start) or start < 0:
            return TransactionResult('unavailable')
        if request is not None and port.write(request) != len(request):
            return TransactionResult('unknown')
        decoder = UAVTalkDecoder()
        next_poll = start
        polls = 0
        for _ in range(512):
            now = clock()
            if not _finite(now) or now < last or now - start >= 5:
                return TransactionResult('unknown')
            last = now
            if now >= next_poll and polls < 25:
                query = status_request()
                if port.write(query) != len(query):
                    return TransactionResult('unknown')
                polls += 1
                next_poll = now + .2
            chunk = port.read(256)
            now = clock()
            if not _finite(now) or now < last or now - start >= 5:
                return TransactionResult('unknown')
            last = now
            if type(chunk) is not bytes or len(chunk) > 256:
                return TransactionResult('unknown')
            for frame in decoder.feed(chunk):
                if frame.object_id not in (STATUS_ID, SUBMISSION_ID):
                    continue  # never acknowledge or capture ordinary telemetry
                # Reconstitute only a CRC-validated frame for the exact wire
                # codec; reject timestamped/noncanonical maintenance replies.
                if frame.timestamp_ticks is not None:
                    return TransactionResult('unknown')
                body = struct.pack('<BBHIH', 0x3c, frame.message_type,
                                   10 + len(frame.payload), frame.object_id,
                                   frame.instance_id) + frame.payload
                packet = body + bytes((crc8(body),))
                if frame.object_id == SUBMISSION_ID:
                    parse_receipt(packet)  # ACK/NACK alone never proves outcome
                    continue
                status = parse_status(packet, transaction)
                if status.persisted_and_finished:
                    return TransactionResult('verified')
                if status.phase == 6:
                    return TransactionResult('not_written' if status.result in (0, 1, 2)
                                             else 'unknown')
        return TransactionResult('unknown')
    except (OSError, ValueError, TypeError, AttributeError, UAVTalkError, ProvisioningWireError):
        # No raw transport or protocol exception is copied into logs/results.
        return TransactionResult('unknown')


def save_and_submit(directory: Path, transaction: bytes, blob: bytes, port,
                    *, clock=time.monotonic) -> TransactionResult:
    """Create/fsync pending bytes before any stream operation; send once only."""
    save_pending(directory, transaction, blob)
    return _exchange(port, transaction, submission(transaction, blob), clock)


def reconcile(path: Path, port, *, clock=time.monotonic) -> TransactionResult:
    """Poll a saved transaction after ambiguity without sending credentials."""
    transaction, _ = load_pending(path)
    return _exchange(port, transaction, None, clock)
