"""Stored is not active; preserve pending and older private credentials."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lrrk_litewing_ai.provisioning_bundle import save_pending, load_pending, record_stored, BundleError
from lrrk_litewing_ai.usb_provisioning_wire import encode_config, ProvisioningStatus


@unittest.skipUnless(os.name == 'posix', 'POSIX bundle backend')
class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tx = b't'*16
        self.blob = encode_config('test', 'p'*24, b'k'*32)
        self.path = save_pending(self.root, self.tx, self.blob)

    def test_matching_verified_copy_is_private_idempotent_and_retains_pending(self):
        old = save_pending(self.root, b'o'*16, self.blob)
        status = ProvisioningStatus(6,4,self.tx)
        stored = record_stored(self.path,status)
        self.assertEqual(stored.suffix,'.stored')
        self.assertEqual(stored.stat().st_mode & 0o777,0o600)
        self.assertEqual(stored.read_bytes(),self.path.read_bytes())
        self.assertEqual(record_stored(self.path,status),stored)
        self.assertEqual(load_pending(self.path),(self.tx,self.blob))
        self.assertTrue(old.exists())
        self.assertFalse(any('active' in item.name for item in self.root.iterdir()))

    def test_wrong_transaction_cleanup_pending_or_uncertain_never_promoted(self):
        for status in (ProvisioningStatus(6,4,b'u'*16), ProvisioningStatus(5,4,self.tx),
                       ProvisioningStatus(6,3,self.tx), ProvisioningStatus(2,0,self.tx)):
            with self.assertRaises(BundleError):
                record_stored(self.path,status)
        self.assertEqual(list(self.root.glob('*.stored')),[])

    def test_existing_corrupt_copy_not_overwritten(self):
        stored = record_stored(self.path,ProvisioningStatus(6,4,self.tx))
        stored.write_bytes(b'corrupt')
        with self.assertRaises(BundleError):
            record_stored(self.path,ProvisioningStatus(6,4,self.tx))
        self.assertEqual(stored.read_bytes(),b'corrupt')
        self.assertEqual(load_pending(self.path),(self.tx,self.blob))

    def test_sync_failure_never_loses_pending(self):
        with patch('os.fsync',side_effect=OSError('synthetic')):
            with self.assertRaises(BundleError):
                record_stored(self.path,ProvisioningStatus(6,4,self.tx))
        self.assertEqual(load_pending(self.path),(self.tx,self.blob))
