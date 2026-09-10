import contextlib
import io
import os
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from lrrk_litewing_ai import provisioning_cli as cli
from lrrk_litewing_ai.provisioning_bundle import load_pending, save_pending
from lrrk_litewing_ai.usb_provisioning_wire import encode_config
from test_provisioning_transport import Port, status
from test_provisioning_serial import Port as DriverPort
from lrrk_litewing_ai.provisioning_serial import ProvisioningSerial
from lrrk_litewing_ai.usb_provisioning_wire import status_request
from lrrk_litewing_ai.uavtalk import crc8


@unittest.skipUnless(os.name == 'posix', 'POSIX bundle storage')
class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = ['--device', '/dev/cu.synthetic', '--location', 'synthetic']

    def test_create_saves_before_open_and_never_prints_credentials(self):
        ports = []
        def opener(*args, **kwargs):
            files = list(self.root.glob('*.pending'))
            self.assertEqual(len(files), 1)
            tx, blob = load_pending(files[0])
            self.assertEqual(kwargs['request'][10:26], tx)
            self.assertEqual(kwargs['request'][26:-1], blob)
            port = Port([status(tx)])
            port.close = lambda: ports.append('closed')
            return port
        output = io.StringIO()
        with patch.object(cli, 'ProvisioningSerial', side_effect=opener), contextlib.redirect_stdout(output):
            result = cli.main(['create', '--directory', str(self.root), *self.args])
        self.assertEqual(result, 0)
        self.assertEqual(ports, ['closed'])
        self.assertEqual(output.getvalue(), 'verified; pending bundle retained; activation not verified\n')

    def test_save_failure_never_opens(self):
        self.root.chmod(0o755)
        with patch.object(cli, 'ProvisioningSerial') as opener, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['create', '--directory', str(self.root), *self.args]), 2)
        opener.assert_not_called()

    def test_reconcile_opens_without_credential_write_authority(self):
        path = save_pending(self.root, b't'*16, encode_config('test', 'p'*24, b'k'*32))
        port = Port([status(b't'*16)])
        port.close = lambda: None
        with patch.object(cli, 'ProvisioningSerial', return_value=port) as opener, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['reconcile', '--bundle', str(path), *self.args]), 0)
        self.assertIsNone(opener.call_args.kwargs['request'])
        self.assertTrue(path.exists())

    def test_actual_host_stack_over_driver_double(self):
        root = self.root
        class Driver(DriverPort):
            tx = bytes(16)
            def open(self):
                super().open()
                self.saved = load_pending(next(root.glob('*.pending')))
            def write(self, packet):
                result = super().write(packet)
                if packet == status_request():
                    self.data.extend(status(self.tx))
                else:
                    self.tx = packet[10:26]
                    self.assert_saved = (self.tx, packet[26:-1]) == self.saved
                return result
        ordinary = struct.pack('<BBHIH', 0x3c, 0x20, 10, 1234, 0)
        driver = Driver(b'initial noise' + ordinary + bytes([crc8(ordinary)]))
        def opener(device, location, **kwargs):
            return ProvisioningSerial(device, location, **kwargs,
                serial_factory=lambda **settings: driver,
                comports=lambda: [SimpleNamespace(device=device, location=location,
                                                   vid=0x1a86, pid=0x7522)],
                clock=driver.clock)
        with patch.object(cli, 'ProvisioningSerial', side_effect=opener), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['create', '--directory', str(root), *self.args]), 0)
        self.assertTrue(driver.assert_saved)
        self.assertTrue(driver.closed)
        self.assertEqual(len(driver.writes), 3)  # alignment query, one write, status query
