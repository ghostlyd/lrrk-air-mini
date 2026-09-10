"""Synthetic stream tests; no device opening or real credentials."""
import struct
import os
import tempfile
from pathlib import Path
import unittest

from lrrk_litewing_ai.provisioning_transport import save_and_submit, reconcile
from lrrk_litewing_ai.usb_provisioning_wire import encode_config, status_request, submission, STATUS_ID
from lrrk_litewing_ai.uavtalk import crc8
from lrrk_litewing_ai.provisioning_bundle import BundleError, save_pending


def status(tx, phase=6, result=4):
    payload = bytes([1, phase, result, 0]) + tx + bytes(4)
    body = struct.pack('<BBHIH', 0x3c, 0x20, 34, STATUS_ID, 0) + payload
    return body + bytes([crc8(body)])


class Port:
    timeout = .02
    write_timeout = .2
    def __init__(self, chunks=(), short=False):
        self.chunks = list(chunks)
        self.writes = []
        self.time = 0.0
        self.short = short
    def write(self, data):
        self.writes.append(data)
        return len(data) - 1 if self.short else len(data)
    def read(self, size):
        self.time += .02
        return self.chunks.pop(0) if self.chunks else b''
    def clock(self):
        return self.time


@unittest.skipUnless(os.name == 'posix', 'POSIX pending storage backend')
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.tx = b't' * 16
        self.blob = encode_config('test-only', 'p' * 24, b'k' * 32)

    def test_fragmented_verified_status_after_lost_ack(self):
        frame = status(self.tx)
        for split in range(1, len(frame)):
            with self.subTest(split=split):
                directory = self.directory / str(split)
                directory.mkdir(mode=0o700)
                port = Port([frame[:split], frame[split:]])
                result = save_and_submit(directory, self.tx, self.blob, port, clock=port.clock)
                self.assertTrue(result.verified)
                self.assertEqual(port.writes.count(submission(self.tx, self.blob)), 1)
                self.assertTrue((directory / (self.tx.hex() + '.pending')).exists())

    def test_save_failure_prevents_all_io(self):
        self.directory.chmod(0o755)
        port = Port()
        with self.assertRaises(BundleError):
            save_and_submit(self.directory, self.tx, self.blob, port, clock=port.clock)
        self.assertEqual(port.writes, [])
        self.assertEqual(port.time, 0)

    def test_short_write_is_unknown_without_retry(self):
        port = Port(short=True)
        result = save_and_submit(self.directory, self.tx, self.blob, port, clock=port.clock)
        self.assertFalse(result.verified)
        self.assertEqual(result.outcome, 'unknown')
        self.assertEqual(len(port.writes), 1)

    def test_reconcile_never_resubmits_credentials(self):
        path = save_pending(self.directory, self.tx, self.blob)
        port = Port([status(self.tx)])
        self.assertTrue(reconcile(path, port, clock=port.clock).verified)
        self.assertEqual(port.writes, [status_request()])

    def test_mismatch_corruption_cleanup_and_silence_are_not_verified(self):
        for index, chunks in enumerate(([status(b'u' * 16)], [b'bad'],
                                       [status(self.tx, 5, 4)], [])):
            directory = self.directory / str(index)
            directory.mkdir(mode=0o700)
            port = Port(chunks)
            result = save_and_submit(directory, self.tx, self.blob, port, clock=port.clock)
            self.assertFalse(result.verified)
            self.assertLessEqual(len(port.writes), 27)
            self.assertEqual(port.writes.count(submission(self.tx, self.blob)), 1)

    def test_invalid_timeout_sends_nothing(self):
        port = Port()
        port.timeout = None
        result = save_and_submit(self.directory, self.tx, self.blob, port, clock=port.clock)
        self.assertFalse(result.verified)
        self.assertEqual(port.writes, [])
