"""Exclusive macOS operator provisioning serial boundary, never an AI tool.

Opening a serial port may cause driver/platform line transients despite setting
DTR/RTS false before open. This code never deliberately resets or flashes.
The caller must save pending credentials before constructing a writable stream.
"""
import math
import time

from .live_uavtalk import _Synchronizer
from .usb_provisioning_wire import submission, status_request, STATUS_ID


class SerialProvisioningError(OSError):
    """Static messages exclude serial identity, raw input and credentials."""


class ProvisioningSerial:
    timeout = .02
    write_timeout = .2

    def __init__(self, device, location, *, request=None, serial_factory=None,
                 comports=None, clock=time.monotonic):
        self._port = None
        self._request = None
        self._attempted = False
        self._alignment_status = None
        try:
            if (type(device) is not str or not device.startswith('/dev/cu.')
                    or type(location) is not str or not location):
                raise ValueError()
            if request is not None:
                if (type(request) is not bytes or len(request) != 163
                        or submission(request[10:26], request[26:-1]) != request):
                    raise ValueError()
            if serial_factory is None or comports is None:
                import serial
                from serial.tools import list_ports
                serial_factory = serial_factory or serial.Serial
                comports = comports or list_ports.comports
            matches = [item for item in comports() if item.device == device
                       and item.vid == 0x1a86 and item.pid == 0x7522 and item.location == location]
            if len(matches) != 1:
                raise ValueError()
            self._port = serial_factory(port=None, baudrate=57600, timeout=self.timeout,
                                        write_timeout=self.write_timeout, exclusive=True)
            self._port.dtr = False
            self._port.rts = False
            self._port.port = device
            self._port.open()
            self._align(clock)
            self._request = request
        except Exception:
            self.close()
            raise SerialProvisioningError('provisioning serial setup failed') from None

    def _align(self, clock):
        start = previous = clock()
        if type(start) not in (int, float) or not math.isfinite(start) or start < 0:
            raise ValueError()
        next_poll = start
        polls = 0
        sync = _Synchronizer()
        for _ in range(4096):
            now = clock()
            if (type(now) not in (int, float) or not math.isfinite(now)
                    or now < previous or now - start >= 2):
                raise ValueError()
            previous = now
            # A query immediately after port opening can be lost. Only repeat
            # this read-only status request; credentials remain unavailable
            # until alignment returns. Polling never renews the deadline.
            if now >= next_poll and polls < 10:
                if self.write(status_request()) != len(status_request()):
                    raise ValueError()
                polls += 1
                next_poll = now + .2
            data = self.read(1)  # consume the alignment query's status, not just telemetry
            now = clock()
            if (type(now) not in (int, float) or not math.isfinite(now)
                    or now < previous or now - start >= 2):
                raise ValueError()
            previous = now
            for frame in sync.feed(data):
                if frame.object_id != STATUS_ID:
                    continue
                payload = frame.payload
                if (frame.message_type != 0x20 or frame.instance_id != 0
                        or frame.timestamp_ticks is not None or len(payload) != 24
                        or payload[0] != 1 or payload[1] > 6 or payload[2] > 4
                        or payload[3] or any(payload[20:24])):
                    raise ValueError()
                # Any transaction (including zero) is allowed for alignment
                # only. It is not returned as a persistence result.
                sync.finish()
                self._alignment_status = payload
                return
        raise ValueError()

    @property
    def alignment_status(self):
        """Validated pre-submission payload; never evidence of new storage."""
        return self._alignment_status

    def read(self, maximum):
        try:
            if self._port is None or type(maximum) is not int or not 1 <= maximum <= 256:
                raise ValueError()
            data = self._port.read(maximum)
            if type(data) is not bytes or len(data) > maximum:
                raise ValueError()
            return data
        except Exception:
            raise SerialProvisioningError('provisioning serial read failed') from None

    def write(self, packet):
        if self._port is None or type(packet) is not bytes:
            raise SerialProvisioningError('provisioning write denied')
        if packet != status_request():
            if self._request is None or packet != self._request or self._attempted:
                raise SerialProvisioningError('provisioning write denied')
            self._attempted = True  # an exception/short write consumes permission
            self._request = None
        try:
            return self._port.write(packet)
        except Exception:
            raise SerialProvisioningError('provisioning serial write failed') from None

    def close(self):
        port, self._port = self._port, None
        self._request = None
        self._alignment_status = None
        if port is not None:
            try:
                port.close()
            except Exception:
                raise SerialProvisioningError('provisioning serial close failed') from None
