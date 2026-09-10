"""Synthetic key fixtures only; no live credential loading."""
import unittest
from lrrk_litewing_ai.pilot_keys import derive_keys


class PilotKeyTests(unittest.TestCase):
    inputs = (b"r"*32, b"h"*32, b"b"*32, b"s"*16)

    def test_frozen_openssl_hkdf_transcript(self):
        # Independently generated with OpenSSL 3.6.4 `kdf HKDF`, SHA256,
        # root as IKM, host||board as salt, role label||session as info.
        keys = derive_keys(*self.inputs)
        self.assertEqual(keys.c2b.hex(),
                         "4b95fffb3fec209c3ea232ddfa8c6000b1f947fef5574731ab8982b9ac59bf7a")
        self.assertEqual(keys.b2c.hex(),
                         "0cfac70f8a9f5858dfd4d0a47b5553743cac31252887218720961fb03c8c1509")
        self.assertEqual(keys.telemetry.hex(),
                         "2c557374b81628f559db3c377adee5a90039bd859751fb3a55d6360ecc2ef8f9")

    def test_separates_roles_and_binds_every_input(self):
        keys = derive_keys(*self.inputs)
        self.assertEqual(len({keys.c2b, keys.b2c, keys.telemetry}), 3)
        self.assertTrue(all(len(k)==32 for k in (keys.c2b, keys.b2c, keys.telemetry)))
        for index in range(4):
            changed = list(self.inputs)
            changed[index] = b"x"*len(changed[index])
            other = derive_keys(*changed)
            for field in ("c2b", "b2c", "telemetry"):
                self.assertNotEqual(getattr(keys, field), getattr(other, field))

    def test_rejects_invalid_lengths_and_types(self):
        for index, original in enumerate(self.inputs):
            for invalid in (None, "x"*len(original), bytearray(original),
                            original[:-1], original+b"x", b""):
                args = list(self.inputs)
                args[index] = invalid
                with self.subTest(index=index), self.assertRaises(ValueError):
                    derive_keys(*args)

    def test_keys_do_not_appear_in_repr(self):
        keys = derive_keys(*self.inputs)
        self.assertEqual(repr(keys), "SessionKeys()")
