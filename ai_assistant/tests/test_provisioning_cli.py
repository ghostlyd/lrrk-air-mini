import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lrrk_litewing_ai import provisioning_cli as cli
from lrrk_litewing_ai.provisioning_bundle import load_pending, save_pending
from lrrk_litewing_ai.usb_provisioning_wire import encode_config
from test_provisioning_transport import Port, status


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
