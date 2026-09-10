"""Serial boundary doubles; never open a real port."""
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from lrrk_litewing_ai.provisioning_serial import ProvisioningSerial, SerialProvisioningError
from lrrk_litewing_ai.usb_provisioning_wire import status_request, submission, encode_config
from lrrk_litewing_ai.uavtalk import crc8
from lrrk_litewing_ai.provisioning_transport import _exchange
from test_provisioning_transport import status


class Port:
    def __init__(self, data):
        self.data = bytearray(data)
        self.writes = []
        self.closed = False
        self.time = 0.0
        self.dtr = self.rts = True
    def open(self):
        assert not self.dtr and not self.rts
    def close(self):
        self.closed = True
    def read(self, count):
        self.time += .001
        out = bytes(self.data[:count])
        del self.data[:count]
        return out
    def write(self, data):
        self.writes.append(data)
        return len(data)
    def clock(self):
        return self.time


class SerialTests(unittest.TestCase):
    def setUp(self):
        raw = struct.pack('<BBHIH', 0x3c, 0x20, 34, 0x4C575048, 0)
        raw += bytes([1, 1, 0, 0]) + bytes(20)
        self.frame = raw + bytes([crc8(raw)])
        self.packet = submission(b't'*16, encode_config('test', 'p'*24, b'k'*32))
        self.device = '/dev/cu.synthetic'
        self.ports = lambda: [SimpleNamespace(device=self.device, vid=0x1a86,
                                             pid=0x7522, location='synthetic')]

    def open(self, port, **kwargs):
        self.factory = Mock(return_value=port)
        return ProvisioningSerial(self.device, 'synthetic', request=self.packet,
                                  serial_factory=self.factory, comports=self.ports,
                                  clock=port.clock, **kwargs)

    def test_alignment_leaves_next_frame_and_submission_is_one_shot(self):
        port = Port(b'garbage' + self.frame + self.frame)
        stream = self.open(port)
        self.assertEqual(port.writes, [status_request()])
        self.assertEqual(stream.read(256), self.frame)
        self.assertEqual(stream.write(self.packet), len(self.packet))
        with self.assertRaises(SerialProvisioningError):
            stream.write(self.packet)
        with self.assertRaises(SerialProvisioningError):
            stream.write(b'other command')
        stream.close()
        self.assertTrue(port.closed)
        self.factory.assert_called_once_with(port=None, baudrate=57600, timeout=.02,
                                             write_timeout=.2, exclusive=True)

    def test_identity_mismatch_does_not_construct_port(self):
        factory = Mock()
        with self.assertRaises(SerialProvisioningError):
            ProvisioningSerial(self.device, 'wrong', serial_factory=factory, comports=self.ports)
        factory.assert_not_called()

    def test_lost_first_status_recovers_without_submitting_credentials(self):
        frame = self.frame
        class LostQueryPort(Port):
            def write(self, data):
                size = super().write(data)
                if len(self.writes) == 2:
                    self.data.extend(frame)
                return size
        port = LostQueryPort(b'')
        stream = self.open(port)
        self.assertEqual(port.writes, [status_request(), status_request()])
        self.assertGreaterEqual(port.time, .2)
        self.assertLess(port.time, 2)
        self.assertEqual(stream.write(self.packet), len(self.packet))
        with self.assertRaises(SerialProvisioningError): stream.write(self.packet)
        stream.close()

    def test_delayed_alignment_replies_do_not_poison_matching_exchange(self):
        alignment, secret = self.frame, self.packet
        class DelayedPort(Port):
            def write(self, data):
                size = super().write(data)
                if len(self.writes) == 2:
                    self.data.extend(alignment + alignment)
                if data == secret:
                    self.data.extend(status(b't' * 16))
                return size
        port = DelayedPort(b'')
        stream = self.open(port)
        try:
            result = _exchange(stream, b't' * 16, self.packet, port.clock)
            self.assertTrue(result.verified)
            self.assertEqual(port.writes.count(self.packet), 1)
        finally:
            stream.close()

    def test_silence_and_garbage_close_without_secrets(self):
        for data in (b'', b'x' * 5000):
            port = Port(data)
            with self.assertRaises(SerialProvisioningError):
                self.open(port)
            self.assertTrue(port.closed)
            self.assertGreaterEqual(len(port.writes), 2)
            self.assertLessEqual(len(port.writes), 10)
            self.assertTrue(all(packet == status_request() for packet in port.writes))
            self.assertLess(port.time, 2.01)

    def test_partial_secret_write_cannot_be_retried(self):
        port = Port(self.frame)
        stream = self.open(port)
        port.write = Mock(return_value=4)
        self.assertEqual(stream.write(self.packet), 4)
        with self.assertRaises(SerialProvisioningError):
            stream.write(self.packet)
        self.assertEqual(port.write.call_count, 1)
        stream.close()
