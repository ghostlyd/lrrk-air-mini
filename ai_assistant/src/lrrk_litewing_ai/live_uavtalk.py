"""Bounded live UAVTalk telemetry collection for the LiteWing USB bridge.

The only outbound frames are the GCS telemetry handshake, selected object-read
requests, and acknowledgements for selected inbound objects. There is no API
for receiver, arming, settings, persistence, actuator, or flight-control writes.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import stat
import struct
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Protocol, Tuple

from .models import SourceIdentity, TelemetrySnapshot
from .uavobjects import (
    ACTUATOR_COMMAND,
    ATTITUDE_STATE,
    BATTERY_STATE,
    FLIGHT_STATUS,
    SYSTEM_ALARMS,
    snapshot_from_frame,
)
from .uavtalk import UAVTalkDecoder, UAVTalkError, UAVTalkFrame, crc8


GCST_TELEMETRY_STATS = 0xCAD1DC0A
FLIGHT_TELEMETRY_STATS = 0x6737BB5A
SELECTED_OBJECT_IDS = frozenset((
    ATTITUDE_STATE,
    FLIGHT_STATUS,
    BATTERY_STATE,
    SYSTEM_ALARMS,
    ACTUATOR_COMMAND,
))
_ACK_OBJECT_IDS = SELECTED_OBJECT_IDS | frozenset((FLIGHT_TELEMETRY_STATS,))
_FRAME_TYPES = frozenset((0x20, 0x21, 0x22, 0x23, 0x24, 0xA0, 0xA2))
_CAPTURE_LIMIT = 1024 * 1024


class UAVTalkLiveError(RuntimeError):
    """Live transport or telemetry failed a bounded safety check."""


def _packet(message_type: int, object_id: int, payload: bytes = b"",
            instance_id: int = 0) -> bytes:
    header_size = 12 if message_type & 0x80 else 10
    if header_size != 10:
        raise UAVTalkLiveError("outbound timestamped frames are not allowed")
    packet = struct.pack(
        "<BBHIH", 0x3C, message_type, header_size + len(payload),
        object_id, instance_id,
    ) + payload
    return packet + bytes((crc8(packet),))


class OutboundProtocol:
    """Construct only the three reviewed classes of read-side traffic."""

    def __init__(self, write: Callable[[bytes], int]):
        self._write = write

    def _send(self, packet: bytes) -> None:
        written = self._write(packet)
        if type(written) is not int or written != len(packet):
            raise UAVTalkLiveError("incomplete serial write")

    def handshake(self, status_value: int) -> None:
        if status_value not in (1, 3):
            raise UAVTalkLiveError("outbound handshake status is not allowed")
        payload = bytes(36) + bytes((status_value,))
        self._send(_packet(0x20, GCST_TELEMETRY_STATS, payload))

    def request(self, object_id: int) -> None:
        if object_id not in SELECTED_OBJECT_IDS:
            raise UAVTalkLiveError("outbound object request is not allowed")
        self._send(_packet(0x21, object_id))

    def ack(self, object_id: int, instance_id: int) -> None:
        if object_id not in _ACK_OBJECT_IDS or instance_id != 0:
            raise UAVTalkLiveError("outbound acknowledgement is not allowed")
        self._send(_packet(0x23, object_id))


class TelemetryTransport(Protocol):
    identity: str

    def handshake(self, status_value: int) -> None:
        ...

    def request(self, object_id: int) -> None:
        ...

    def ack(self, object_id: int, instance_id: int) -> None:
        ...

    def read(self, maximum: int) -> bytes:
        ...

    def close(self) -> None:
        ...


class SerialTelemetryTransport:
    """Exclusive 57600-baud CH340 transport with exact USB identity matching."""

    def __init__(
        self,
        device: str,
        location: str,
        *,
        serial_factory: Optional[Callable[..., Any]] = None,
        comports: Optional[Callable[[], Any]] = None,
    ) -> None:
        if not isinstance(device, str) or not device.startswith("/dev/cu."):
            raise UAVTalkLiveError("a /dev/cu.* serial device is required")
        if not isinstance(location, str) or not location:
            raise UAVTalkLiveError("an exact USB location is required")
        if comports is None:
            try:
                from serial.tools import list_ports
            except ImportError as exc:
                raise UAVTalkLiveError(
                    "pyserial is required for live UAVTalk telemetry"
                ) from exc
            comports = list_ports.comports
        try:
            matches = [
                item for item in comports()
                if item.device == device and item.vid == 0x1A86 and item.pid == 0x7522
                and item.location == location
            ]
        except Exception as exc:
            raise UAVTalkLiveError("USB serial identity enumeration failed") from exc
        if len(matches) != 1:
            raise UAVTalkLiveError("expected 1A86:7522 USB identity/location is not present")

        self.identity = "usb-serial:1a86:7522:%s" % location
        self._reset_neutral = serial_factory is None
        if serial_factory is None:
            from .serial_posix import ResetNeutralPosixPort
            try:
                self._port = ResetNeutralPosixPort(device, 57600)
            except Exception as exc:
                raise UAVTalkLiveError("reset-neutral serial port open failed") from exc
            self._outbound = OutboundProtocol(self._write)
            return
        try:
            self._port = serial_factory(
                port=None,
                baudrate=57600,
                timeout=0.02,
                write_timeout=0.2,
                exclusive=True,
            )
        except Exception as exc:
            raise UAVTalkLiveError("serial transport construction failed") from exc
        try:
            self._port.dtr = False
            self._port.rts = False
            self._port.port = device
            self._port.open()
        except Exception as exc:
            try:
                self._port.close()
            finally:
                raise UAVTalkLiveError("serial port open failed") from exc
        self._outbound = OutboundProtocol(self._write)

    def _write(self, packet: bytes) -> int:
        return self._port.write(packet)

    def handshake(self, status_value: int) -> None:
        self._outbound.handshake(status_value)

    def request(self, object_id: int) -> None:
        self._outbound.request(object_id)

    def ack(self, object_id: int, instance_id: int) -> None:
        self._outbound.ack(object_id, instance_id)

    def read(self, maximum: int) -> bytes:
        if type(maximum) is not int or not 1 <= maximum <= 4096:
            raise UAVTalkLiveError("invalid serial read bound")
        if self._reset_neutral:
            data = self._port.read_available(maximum)
            if not isinstance(data, bytes) or len(data) > maximum:
                raise UAVTalkLiveError("serial read exceeded its bound")
            return data
        pending = getattr(self._port, "in_waiting", 0)
        if type(pending) is not int or pending < 0:
            pending = 0
        data = self._port.read(min(max(pending, 1), maximum))
        if not isinstance(data, bytes) or len(data) > maximum:
            raise UAVTalkLiveError("serial read exceeded its bound")
        return data

    def close(self) -> None:
        self._port.close()


class _PrivateCapture:
    def __init__(self, path: Path):
        self.path = path
        self.total = 0
        self.digest = hashlib.sha256()
        self.stream = None

    def open(self) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise UAVTalkLiveError("private capture must be a new file") from exc
        try:
            os.fchmod(descriptor, 0o600)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise UAVTalkLiveError("private capture must be a regular file")
            self.stream = os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            raise

    def write(self, data: bytes) -> None:
        if self.stream is None:
            raise UAVTalkLiveError("private capture is not open")
        if self.total + len(data) > _CAPTURE_LIMIT:
            raise UAVTalkLiveError("private capture exceeded one megabyte")
        if self.stream.write(data) != len(data):
            raise UAVTalkLiveError("incomplete private capture write")
        self.total += len(data)
        self.digest.update(data)

    def close(self) -> None:
        if self.stream is not None:
            self.stream.flush()
            os.fsync(self.stream.fileno())
            self.stream.close()
            self.stream = None


class _Synchronizer:
    """Find one valid initial frame, then make all later corruption fatal."""

    def __init__(self) -> None:
        self.decoder = UAVTalkDecoder()
        self.initial = bytearray()
        self.synchronized = False
        self.discarded = 0
        self.received_before_sync = 0

    def feed(self, data: bytes) -> list[UAVTalkFrame]:
        if len(data) > 4096:
            raise UAVTalkLiveError("serial read exceeds 4096 bytes")
        if not self.synchronized:
            self.received_before_sync += len(data)
            if self.received_before_sync > 4096:
                self.initial.clear()
                raise UAVTalkLiveError("initial synchronization bound exceeded")
            self.initial.extend(data)
            while self.initial:
                if len(self.initial) < 4:
                    return []
                message_type = self.initial[1]
                size = int.from_bytes(self.initial[2:4], "little")
                header_size = 12 if message_type & 0x80 else 10
                plausible = (
                    self.initial[0] == 0x3C
                    and message_type in _FRAME_TYPES
                    and header_size <= size <= header_size + UAVTalkDecoder.MAX_PAYLOAD
                )
                if plausible and len(self.initial) < size + 1:
                    return []
                if plausible and crc8(bytes(self.initial[:size])) == self.initial[size]:
                    self.synchronized = True
                    data = bytes(self.initial)
                    self.initial.clear()
                    break
                del self.initial[0]
                self.discarded += 1
                if self.discarded >= 4096:
                    raise UAVTalkLiveError("no UAVTalk synchronization within 4096 bytes")
            if not self.synchronized:
                return []
        try:
            return self.decoder.feed(data)
        except (TypeError, UAVTalkError) as exc:
            raise UAVTalkLiveError("invalid live UAVTalk framing: %s" % exc) from exc

    @property
    def bytes_to_frame_boundary(self) -> int:
        return self.decoder.bytes_to_frame_boundary

    def finish(self) -> None:
        if not self.synchronized:
            raise UAVTalkLiveError("no valid UAVTalk frame was received")
        try:
            self.decoder.finish()
        except UAVTalkError as exc:
            raise UAVTalkLiveError("truncated live UAVTalk frame") from exc


class LiveUAVTalkCollector:
    """Collect one current aggregate from five selected UAVObjects."""

    def __init__(
        self,
        transport: TelemetryTransport,
        capture_path: Path,
        *,
        duration_s: float = 2.0,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if (isinstance(duration_s, bool) or not isinstance(duration_s, (int, float))
                or not math.isfinite(duration_s) or not 0.1 <= duration_s <= 5.0):
            raise UAVTalkLiveError("live collection duration must be 0.1..5.0 seconds")
        self.transport = transport
        self.capture_path = Path(capture_path)
        self.duration_s = float(duration_s)
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._sleep = sleep
        self.capture_bytes = 0
        self.capture_sha256 = hashlib.sha256(b"").hexdigest()
        self.initial_discarded_bytes = 0
        self._latest: Dict[int, Tuple[TelemetrySnapshot, float, datetime]] = {}
        self._last_clock: Optional[float] = None
        self._handshake_status = 1
        self._connected = False

    def _now(self) -> float:
        value = self._monotonic()
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise UAVTalkLiveError("host monotonic clock is invalid")
        current = float(value)
        if self._last_clock is not None and current < self._last_clock:
            raise UAVTalkLiveError("host monotonic clock regressed")
        self._last_clock = current
        return current

    def _wall_now(self) -> datetime:
        value = self._wall_clock()
        if (not isinstance(value, datetime) or value.tzinfo is None
                or value.utcoffset() is None):
            raise UAVTalkLiveError("host wall clock must be timezone-aware")
        return value

    def _observe(
        self,
        frame: UAVTalkFrame,
        received_mono: float,
        received_wall: datetime,
        *,
        respond: bool = True,
    ) -> None:
        if frame.object_id == FLIGHT_TELEMETRY_STATS:
            if frame.instance_id != 0 or len(frame.payload) != 37:
                raise UAVTalkLiveError("invalid FlightTelemetryStats object")
            status_value = frame.payload[-1]
            if status_value not in (0, 1, 2, 3):
                raise UAVTalkLiveError("invalid FlightTelemetryStats status")
            if status_value == 2:
                if not self._connected:
                    self._latest.clear()
                self._handshake_status = 3
                self._connected = True
                if respond:
                    self.transport.handshake(3)
            elif status_value == 3:
                if not self._connected:
                    self._latest.clear()
                self._handshake_status = 3
                self._connected = True
            else:
                reconnecting = not self._connected
                self._latest.clear()
                self._handshake_status = 1
                self._connected = False
                # A request received while firmware is still CONNECTED first
                # transitions it to DISCONNECTED. Complete the second step
                # without waiting for the periodic retry/stream timeout race.
                if respond and reconnecting and status_value == 0:
                    self.transport.handshake(1)
            return
        if frame.object_id not in SELECTED_OBJECT_IDS:
            return
        try:
            snapshot = snapshot_from_frame(frame, received_wall)
        except UAVTalkError as exc:
            raise UAVTalkLiveError("selected live object is invalid: %s" % exc) from exc
        if snapshot is None:
            raise UAVTalkLiveError("selected live object did not produce telemetry")
        self._latest[frame.object_id] = (snapshot, received_mono, received_wall)

    def _aggregate(self) -> TelemetrySnapshot:
        if not self._connected:
            raise UAVTalkLiveError("live telemetry handshake is incomplete")
        missing = SELECTED_OBJECT_IDS.difference(self._latest)
        if missing:
            names = ["0x%08x" % value for value in sorted(missing)]
            raise UAVTalkLiveError("live telemetry is incomplete: %s" % ", ".join(names))
        newest_mono = max(value[1] for value in self._latest.values())
        oldest_mono = min(value[1] for value in self._latest.values())
        newest_wall = max(value[2] for value in self._latest.values())
        parts = [self._latest[value][0] for value in sorted(SELECTED_OBJECT_IDS)]
        digest = hashlib.sha256(
            "".join(value.snapshot_hash() for value in parts).encode("ascii")
        ).hexdigest()[:16]
        by_id = {value: self._latest[value][0] for value in SELECTED_OBJECT_IDS}
        system_alarms = by_id[SYSTEM_ALARMS].alarms or ()
        actuator_alarms = by_id[ACTUATOR_COMMAND].alarms or ()
        return TelemetrySnapshot(
            snapshot_id="uavtalk-live-%s" % digest,
            captured_at=newest_wall,
            source=SourceIdentity(
                adapter="uavtalk-live-ac77304",
                transport=self.transport.identity,
            ),
            link_age_ms=(newest_mono - oldest_mono) * 1000.0,
            armed=by_id[FLIGHT_STATUS].armed,
            flight_mode=by_id[FLIGHT_STATUS].flight_mode,
            attitude=by_id[ATTITUDE_STATE].attitude,
            battery=by_id[BATTERY_STATE].battery,
            alarms=tuple(system_alarms) + tuple(actuator_alarms),
            actuators=by_id[ACTUATOR_COMMAND].actuators,
        )

    def _finish_current_frame(
        self,
        synchronizer: _Synchronizer,
        capture: _PrivateCapture,
    ) -> None:
        completion_started = self._now()
        while synchronizer.bytes_to_frame_boundary:
            if self._now() - completion_started >= 0.25:
                raise UAVTalkLiveError("current-frame completion timed out")
            maximum = synchronizer.bytes_to_frame_boundary
            received_mono = self._now()
            received_wall = self._wall_now()
            data = self.transport.read(maximum)
            after_read = self._now()
            if data:
                # The capture records every byte consumed from the device,
                # even when the completion deadline expires during this read.
                capture.write(data)
            if after_read - completion_started >= 0.25:
                raise UAVTalkLiveError("current-frame completion timed out")
            if not data:
                self._sleep(0.005)
                continue
            frames = synchronizer.feed(data)
            for frame in frames:
                # The aggregate is already complete: validate and incorporate
                # only this started frame, with no new ACK or handshake write.
                was_connected = self._connected
                self._observe(
                    frame,
                    received_mono,
                    received_wall,
                    respond=False,
                )
                if was_connected and not self._connected:
                    raise UAVTalkLiveError("live telemetry disconnected")
        synchronizer.finish()

    def stream(
        self,
        offer: Callable[[TelemetrySnapshot], object],
        stop: Callable[[], bool],
        *,
        duration_s: float,
    ) -> int:
        """Offer snapshots on one connection; offer must be nonblocking.

        This acquisition primitive does not invoke providers. Each delivery
        requires a new observation of every selected object. Cancellation
        closes immediately, without sending a final protocol transaction.
        """
        capture = _PrivateCapture(self.capture_path)
        synchronizer = _Synchronizer()
        delivered = 0
        refreshed = set()
        try:
            if not callable(offer) or not callable(stop):
                raise UAVTalkLiveError("stream callbacks must be callable")
            if (isinstance(duration_s, bool)
                    or not isinstance(duration_s, (int, float))
                    or not math.isfinite(duration_s)
                    or not 0.1 <= duration_s <= 60):
                raise UAVTalkLiveError("stream duration must be 0.1..60 seconds")
            if stop():
                return 0
            capture.open()
            started = self._now()
            next_handshake = next_request = started
            last_complete = started
            while not stop() and self._now() - started < duration_s:
                now = self._now()
                if now - last_complete >= 1.0:
                    raise UAVTalkLiveError("complete telemetry stream timed out")
                if now >= next_handshake:
                    self.transport.handshake(self._handshake_status)
                    next_handshake = now + 1.0
                if now >= next_request:
                    for object_id in sorted(SELECTED_OBJECT_IDS):
                        self.transport.request(object_id)
                    next_request = now + 0.2
                data = self.transport.read(4096)
                received_mono = self._now()
                received_wall = self._wall_now()
                if data:
                    capture.write(data)
                    for frame in synchronizer.feed(data):
                        if frame.message_type in (0x22, 0xA2) and frame.object_id in _ACK_OBJECT_IDS:
                            self.transport.ack(frame.object_id, frame.instance_id)
                        was_connected = self._connected
                        self._observe(frame, received_mono, received_wall)
                        if was_connected and not self._connected:
                            raise UAVTalkLiveError("live telemetry disconnected")
                        if self._connected and frame.object_id in SELECTED_OBJECT_IDS:
                            refreshed.add(frame.object_id)
                    if self._connected and refreshed == SELECTED_OBJECT_IDS:
                        offer(self._aggregate())
                        delivered += 1
                        last_complete = received_mono
                        refreshed.clear()
                self._sleep(0.005)
            if not stop():
                if synchronizer.bytes_to_frame_boundary:
                    self._finish_current_frame(synchronizer, capture)
                else:
                    synchronizer.finish()
                if not delivered:
                    raise UAVTalkLiveError("stream ended without complete telemetry")
            return delivered
        finally:
            try:
                capture.close()
            finally:
                self.capture_bytes = capture.total
                self.capture_sha256 = capture.digest.hexdigest()
                self.initial_discarded_bytes = synchronizer.discarded
                self.transport.close()

    def collect(self) -> TelemetrySnapshot:
        capture = _PrivateCapture(self.capture_path)
        synchronizer = _Synchronizer()
        try:
            capture.open()
            started = self._now()
            next_handshake = started
            next_request = started
            while self._now() - started < self.duration_s:
                now = self._now()
                if now >= next_handshake:
                    self.transport.handshake(self._handshake_status)
                    next_handshake = now + 1.0
                if now >= next_request:
                    for object_id in sorted(SELECTED_OBJECT_IDS):
                        self.transport.request(object_id)
                    next_request = now + 0.2
                received_mono = self._now()
                received_wall = self._wall_now()
                data = self.transport.read(4096)
                self._now()
                if data:
                    capture.write(data)
                    frames = synchronizer.feed(data)
                    for frame in frames:
                        if frame.message_type in (0x22, 0xA2) and frame.object_id in _ACK_OBJECT_IDS:
                            self.transport.ack(frame.object_id, frame.instance_id)
                        self._observe(frame, received_mono, received_wall)
                    if (self._connected
                            and not SELECTED_OBJECT_IDS.difference(self._latest)):
                        if synchronizer.bytes_to_frame_boundary:
                            self._finish_current_frame(synchronizer, capture)
                        else:
                            synchronizer.finish()
                        return self._aggregate()
                self._sleep(0.005)
            synchronizer.finish()
            return self._aggregate()
        finally:
            try:
                capture.close()
            finally:
                self.capture_bytes = capture.total
                self.capture_sha256 = capture.digest.hexdigest()
                self.initial_discarded_bytes = synchronizer.discarded
                self.transport.close()
