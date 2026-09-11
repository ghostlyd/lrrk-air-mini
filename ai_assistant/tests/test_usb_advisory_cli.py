import contextlib
import importlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_live_uavtalk import FakeTransport, complete_stream
from lrrk_litewing_ai.audit import validate_replay


class USBAdvisoryCLITests(unittest.TestCase):
    def module(self):
        name = 'lrrk_litewing_ai.usb_advisory_cli'
        self.assertIsNotNone(importlib.util.find_spec(name), 'streaming launcher missing')
        return importlib.import_module(name)

    def test_offline_launcher_streams_and_records_historical_analysis(self):
        module = self.module()
        transport = FakeTransport([complete_stream()])
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = ['--device', '/dev/cu.fixture', '--usb-location', 'fixture',
                    '--private-capture', str(root/'capture'), '--audit-log', str(root/'audit'),
                    '--duration', '.2']
            with patch.object(module, 'SerialTelemetryTransport', return_value=transport):
                with contextlib.redirect_stdout(output):
                    result = module.main(args)
            self.assertTrue((root/'capture').exists())
            self.assertTrue((root/'audit').exists())
        self.assertEqual(result, 0)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(any(item.get('historical') is True for item in records))
        self.assertTrue(transport.closed)

    def test_invalid_duration_rejected_before_serial_open(self):
        module = self.module()
        with patch.object(module, 'SerialTelemetryTransport') as transport:
            with contextlib.redirect_stderr(io.StringIO()):
                result = module.main(['--device', '/dev/cu.fixture', '--usb-location', 'fixture',
                    '--private-capture', '/tmp/unused-capture', '--audit-log', '/tmp/unused-audit',
                    '--duration', 'nan'])
        self.assertEqual(result, 2)
        transport.assert_not_called()

    def test_framing_failure_records_terminal_audit_without_raw_error(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(module, 'SerialTelemetryTransport',
                              return_value=FakeTransport([complete_stream(), b'bad'])):
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    result = module.main(['--device', '/dev/cu.fixture', '--usb-location', 'fixture',
                        '--private-capture', str(root/'capture'), '--audit-log', str(root/'audit'),
                        '--duration', '.2'])
            events = validate_replay(root/'audit')
        self.assertEqual(result, 2)
        self.assertEqual(events[-1]['event_type'], 'usb_session_failed')
        self.assertEqual(events[-1]['payload'], {'error_class': 'UAVTalkLiveError'})

    def test_live_mode_uses_bounded_provider_and_labels_response_historical(self):
        module = self.module()
        self.assertTrue(hasattr(module, '_live_prompt'), 'live provider not connected')
        output, calls = io.StringIO(), []
        def provider(runtime, prompt, **kwargs):
            calls.append(kwargs)
            return 'Advisory only'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(module, 'SerialTelemetryTransport',
                              return_value=FakeTransport([complete_stream()])):
                with patch.object(module, '_live_prompt', new=provider):
                    with contextlib.redirect_stdout(output):
                        result = module.main(['--device', '/dev/cu.fixture',
                            '--usb-location', 'fixture', '--private-capture', str(root/'capture'),
                            '--audit-log', str(root/'audit'), '--duration', '.2', '--live-agent'])
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['timeout_s'], 30)
        self.assertTrue(calls[0]['stop']())
        record = json.loads(output.getvalue().splitlines()[0])
        self.assertTrue(record['historical'])
        self.assertEqual(record['assistant'], 'Advisory only')
