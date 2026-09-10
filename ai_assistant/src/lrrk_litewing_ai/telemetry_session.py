"""Session-bound receive-only telemetry interpretation.

Trusted local pilot code supplies only the derived telemetry key and session.
There is no socket, credential discovery, admission, keepalive or command API.
HMAC is possession proof, not board attestation. Unknown transit/sample ages
remain unknown; no clock synchronization or flight-readiness claim is made.
"""
from dataclasses import dataclass, replace
from datetime import datetime
import secrets
from threading import Lock

from .models import SourceIdentity, TelemetrySnapshot
from .telemetry_wire import decode_telemetry
from .uavobjects import snapshot_from_frame
from .uavtalk import UAVTalkFrame


@dataclass(frozen=True)
class TelemetryObservation:
    snapshot: TelemetrySnapshot
    serialized_us: int
    sample_age_us: int | None
    received_monotonic_us: int
    received_at: datetime


class TelemetrySession:
    """One serialized replay state, retired explicitly by its local owner.

    Invalid input never advances accepted state. Equal clock ticks are allowed;
    sequences must strictly increase. A delayed unseen packet can be observed
    but cannot establish link freshness. Returned observations are historical
    values, not a live session-validity token. On STOP/loss/rotation the owner
    must call close(); creating a new consumer is a new trusted handoff.
    close() drops key references, not a secure erase of immutable Python bytes.
    """

    def __init__(self, session: bytes, telemetry_key: bytes):
        if type(session) is not bytes or len(session) != 16 or session == bytes(16):
            raise ValueError("invalid telemetry session")
        if type(telemetry_key) is not bytes or len(telemetry_key) != 32:
            raise ValueError("invalid telemetry key")
        self._lock = Lock()
        self._session = session
        self._key = telemetry_key
        self._sequence = 0
        self._board_us = -1
        self._received_us = -1
        # A local observation namespace, not a board/session identifier.
        self._observation_id = secrets.token_hex(8)

    def close(self) -> None:
        with self._lock:
            self._key = None
            self._session = None

    def receive(self, datagram: bytes, received_monotonic_us: int,
                received_at: datetime) -> TelemetryObservation:
        with self._lock:
            if self._key is None:
                raise ValueError("telemetry session closed")
            if (type(received_monotonic_us) is not int
                    or not 0 <= received_monotonic_us <= 2**63-1
                    or received_monotonic_us < self._received_us):
                raise ValueError("invalid telemetry receipt clock")
            if (not isinstance(received_at, datetime) or received_at.tzinfo is None
                    or received_at.utcoffset() is None):
                raise ValueError("telemetry receipt time must be timezone-aware")
            frame, record = decode_telemetry(datagram, self._key)
            if (frame.session != self._session or frame.sequence <= self._sequence
                    or record.serialized_us < self._board_us):
                raise ValueError("telemetry session, sequence or board clock rejected")
            # Reuse the pinned semantic parser, never the unrestricted UAVTalk
            # receive/write path. Instance zero and object-data type are fixed.
            snapshot = snapshot_from_frame(
                UAVTalkFrame(0x20, record.object_id, 0, None, record.data), received_at)
            if snapshot is None:
                raise ValueError("unsupported telemetry snapshot")
            snapshot = replace(
                snapshot,
                snapshot_id="wifi-%s-%d" % (self._observation_id, frame.sequence),
                source=SourceIdentity(adapter="wifi-telemetry-v1-receipt-time",
                                      transport="authenticated-udp"),
                link_age_ms=None,
            )
            observation = TelemetryObservation(snapshot, record.serialized_us,
                record.sample_age_us, received_monotonic_us, received_at)
            # Commit only after authentication, framing and semantic validation.
            self._sequence = frame.sequence
            self._board_us = record.serialized_us
            self._received_us = received_monotonic_us
            return observation
