"""Private pending records; only synthetic credentials, no serial access."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lrrk_litewing_ai.usb_provisioning_wire import encode_config
from lrrk_litewing_ai.provisioning_bundle import save_pending, load_pending, BundleError


@unittest.skipUnless(os.name == 'posix', 'descriptor-based POSIX bundle backend')
class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.tx = b't' * 16
        self.blob = encode_config('test-only', 'p' * 24, b'k' * 32)

    def test_roundtrip_private_and_never_overwrites(self):
        path = save_pending(self.directory, self.tx, self.blob)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_pending(path), (self.tx, self.blob))
        original = path.read_bytes()
        with self.assertRaises(BundleError):
            save_pending(self.directory, self.tx, self.blob)
        other = save_pending(self.directory, b'u' * 16, self.blob)
        self.assertEqual(path.read_bytes(), original)
        self.assertNotEqual(other, path)

    def test_rejects_public_directory_and_repository(self):
        self.directory.chmod(0o755)
        with self.assertRaises(BundleError):
            save_pending(self.directory, self.tx, self.blob)
        self.directory.chmod(0o700)
        (self.directory / '.git').mkdir()
        with self.assertRaises(BundleError):
            save_pending(self.directory, self.tx, self.blob)

    def test_symlink_and_hardlink_rejected_on_load(self):
        path = save_pending(self.directory, self.tx, self.blob)
        alias = self.directory / 'alias'
        alias.symlink_to(path)
        with self.assertRaises(BundleError):
            load_pending(alias)
        alias.unlink()
        os.link(path, alias)
        with self.assertRaises(BundleError):
            load_pending(path)

    def test_short_write_completed_and_sync_failure_not_success(self):
        write = os.write
        with patch('os.write', side_effect=lambda fd, data: write(fd, data[:7])):
            path = save_pending(self.directory, self.tx, self.blob)
        self.assertEqual(load_pending(path), (self.tx, self.blob))
        with patch('os.fsync', side_effect=OSError('synthetic sensitive detail')):
            with self.assertRaises(BundleError) as error:
                save_pending(self.directory, b'u' * 16, self.blob)
        self.assertNotIn('sensitive', str(error.exception))
        self.assertEqual(load_pending(path), (self.tx, self.blob))

    def test_corrupt_or_public_file_rejected(self):
        path = save_pending(self.directory, self.tx, self.blob)
        path.chmod(0o644)
        with self.assertRaises(BundleError):
            load_pending(path)
        path.chmod(0o600)
        path.write_bytes(b'bad')
        with self.assertRaises(BundleError):
            load_pending(path)
