import contextlib
import io
import unittest
from unittest.mock import patch, Mock
from lrrk_litewing_ai import keyboard_pilot


class CLITests(unittest.TestCase):
    def test_demo_is_explicit_and_never_accepts_credentials(self):
        parse = getattr(keyboard_pilot, 'parse_options', None)
        self.assertIsNotNone(parse)
        self.assertTrue(parse(['--demo']).demo)
        for args in ([], ['--live'], ['--demo','--bundle','private'],
                     ['--live','--bundle','private','--host','not-an-ip']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): parse(args)

    def test_live_endpoint_is_explicit(self):
        parse = getattr(keyboard_pilot, 'parse_options', None)
        self.assertIsNotNone(parse)
        options = parse(['--live','--bundle','private','--host','192.0.2.1'])
        self.assertEqual(options.host, '192.0.2.1')
        self.assertTrue(options.live)

    def test_live_connector_defers_keys_and_uses_only_neutral_admission(self):
        factory = getattr(keyboard_pilot, 'live_connector', None)
        self.assertIsNotNone(factory)
        with patch('lrrk_litewing_ai.provisioning_bundle.load_pending',
                   return_value=(b't'*16,bytes(8)+b'k'*32)) as load, \
             patch('socket.socket') as socket_factory, \
             patch('lrrk_litewing_ai.pilot_udp.admit_udp') as admit:
            connect = factory('private','192.0.2.1')
            load.assert_not_called(); socket_factory.assert_not_called()
            link = connect()
            self.assertIs(link,admit.return_value)
            args = admit.call_args.args
            self.assertEqual(args[1], b'k'*32)
            self.assertEqual(args[2](),(1000,1500,1500,1500,1500,1500,1500,1500))
            socket_factory.return_value.connect.assert_called_once_with(('192.0.2.1',2390))

    def test_failed_socket_connection_is_closed(self):
        factory = getattr(keyboard_pilot, 'live_connector', None)
        self.assertIsNotNone(factory)
        sock = Mock(); sock.connect.side_effect = OSError('unavailable')
        with patch('lrrk_litewing_ai.provisioning_bundle.load_pending',
                   return_value=(b't'*16,bytes(8)+b'k'*32)), \
             patch('socket.socket',return_value=sock):
            with self.assertRaises(OSError): factory('private','192.0.2.1')()
            sock.close.assert_called_once()
