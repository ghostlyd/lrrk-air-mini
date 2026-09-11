"""Reset-neutral POSIX callout access for the read-side USB transport."""
import os
import time

class ResetNeutralPosixPort:
    """Open a POSIX callout device without changing DTR or RTS.

    LiteWing routes those CH340 modem-control lines through its ESP32-S3 auto
    reset circuit. pyserial applies modem-line state while opening, so even a
    nominally read-only probe can restart the controller. This descriptor path
    configures only tty data framing and exclusive ownership; it deliberately
    issues no TIOCM modem-control ioctl and does not flush inbound bytes.
    """
    WRITE_TIMEOUT_SECONDS = .02

    def __init__(self, device, baud, *, os_api=os, termios_api=None,
                 fcntl_api=None, select_api=None, clock=time.monotonic):
        if baud != 57600 or not isinstance(device, str) or not device.startswith('/dev/cu.'):
            raise OSError('reset-neutral port requires a 57600-baud POSIX callout device')
        if termios_api is None:
            try:
                import termios as termios_api
            except ImportError as exc:
                raise OSError('reset-neutral serial access requires POSIX termios') from exc
        if fcntl_api is None:
            import fcntl as fcntl_api
        if select_api is None:
            import select as select_api
        self._os = os_api
        self._termios = termios_api
        self._select = select_api
        self._clock = clock
        self._fd = None
        try:
            self._fd = os_api.open(
                device, os_api.O_RDWR | os_api.O_NOCTTY | os_api.O_NONBLOCK
            )
            if not os_api.isatty(self._fd):
                raise OSError('serial device is not a tty')
            attrs = termios_api.tcgetattr(self._fd)
            attrs[0] = 0
            attrs[1] = 0
            control_mask = (
                termios_api.CSIZE | termios_api.PARENB | termios_api.CSTOPB |
                termios_api.HUPCL |
                getattr(termios_api, 'CRTSCTS', 0)
            )
            attrs[2] = (attrs[2] & ~control_mask) | (
                termios_api.CS8 | termios_api.CREAD | termios_api.CLOCAL
            )
            attrs[3] = 0
            attrs[4] = termios_api.B57600
            attrs[5] = termios_api.B57600
            attrs[6][termios_api.VMIN] = 0
            attrs[6][termios_api.VTIME] = 0
            termios_api.tcsetattr(self._fd, termios_api.TCSANOW, attrs)
            # TIOCEXCL reserves the tty but does not alter DTR/RTS.
            fcntl_api.ioctl(self._fd, termios_api.TIOCEXCL)
        except Exception as exc:
            self.close()
            if isinstance(exc, OSError):
                raise
            raise OSError('reset-neutral serial configuration failed: ' + str(exc)) from exc

    def write(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise OSError('serial write requires bytes')
        view = memoryview(data)
        total = 0
        deadline = self._clock() + self.WRITE_TIMEOUT_SECONDS
        while view:
            if self._clock() >= deadline:
                raise OSError('serial write deadline exceeded')
            try:
                written = self._os.write(self._fd, view)
            except BlockingIOError:
                written = 0
            if written < 0 or written > len(view):
                raise OSError('invalid serial write result')
            if written:
                total += written
                view = view[written:]
                if self._clock() >= deadline:
                    raise OSError('serial write deadline exceeded')
                continue
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise OSError('serial write deadline exceeded')
            if not self._select.select([], [self._fd], [], remaining)[1]:
                raise OSError('serial write deadline exceeded')
        return total

    def read_available(self, max_bytes):
        if type(max_bytes) is not int or not 1 <= max_bytes <= 4096:
            raise OSError('invalid serial read limit')
        try:
            return self._os.read(self._fd, max_bytes)
        except BlockingIOError:
            return b''

    def close(self):
        if self._fd is not None:
            fd, self._fd = self._fd, None
            self._os.close(fd)


