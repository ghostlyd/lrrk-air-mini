"""Authentication/framing only: accepted envelopes do not authorize flight."""
import hashlib
import hmac
import unittest

from lrrk_litewing_ai.pilot_wire import Envelope, decode, encode


class PilotWireTests(unittest.TestCase):
    key = b"k" * 32  # Synthetic public test key, never provisioned.

    def envelope(self, **changes):
        fields = dict(direction=0, kind=5, session=b"s"*16, sequence=9,
                      challenge=b"c"*16, payload=b"\x01\x02")
        fields.update(changes)
        return Envelope(**fields)

    def test_header_is_canonical(self):
        packet = encode(self.envelope(), self.key)
        self.assertEqual(packet[:8], b"LWPL\x01\x00\x05\x00")
        self.assertEqual(packet[8:24], b"s"*16)
        self.assertEqual(packet[24:32], b"\0\0\0\0\0\0\0\x09")
        self.assertEqual(packet[32:48], b"c"*16)
        self.assertEqual(packet[48:52], b"\x00\x02\x01\x02")
        self.assertEqual(len(packet), 84)

    def test_frozen_synthetic_packet(self):
        packet = bytes.fromhex(
            "4c57504c01000500737373737373737373737373737373730000000000000009"
            "6363636363636363636363636363636300026162"
            "d30dfa9f0d0637cdf7dfc393c62f8630e567f3cf62fd5382741c7e236a76e70e")
        expected = self.envelope(payload=b"ab")
        self.assertEqual(encode(expected, self.key), packet)
        self.assertEqual(decode(packet, self.key, 0), expected)

    def test_decodes_independently_constructed_packet(self):
        unsigned = (b"LWPL\x01\x01\x07\x00" + b"S"*16
                    + b"\0"*7 + b"\x03" + b"C"*16 + b"\x00\x01z")
        packet = unsigned + hmac.new(self.key, unsigned, hashlib.sha256).digest()
        self.assertEqual(decode(packet, self.key, 1),
                         Envelope(1, 7, b"S"*16, 3, b"C"*16, b"z"))

    def test_all_transmitted_bytes_are_authenticated_or_validated(self):
        packet = encode(self.envelope(), self.key)
        for index in range(len(packet)):
            corrupt = bytearray(packet)
            corrupt[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ValueError):
                decode(bytes(corrupt), self.key, 0)

    def test_wrong_key_and_reflected_direction_are_rejected(self):
        packet = encode(self.envelope(), self.key)
        for key, direction in ((b"x"*32, 0), (self.key, 1)):
            with self.assertRaises(ValueError):
                decode(packet, key, direction)

    def test_all_truncations_and_trailing_bytes_are_rejected(self):
        packet = encode(self.envelope(), self.key)
        for size in range(len(packet)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                decode(packet[:size], self.key, 0)
        with self.assertRaises(ValueError):
            decode(packet + b"\0", self.key, 0)

    def test_payload_and_sequence_boundaries(self):
        for payload in (b"", b"p"*512):
            for sequence in (0, 2**64-1):
                expected = self.envelope(payload=payload, sequence=sequence)
                self.assertEqual(decode(encode(expected, self.key), self.key, 0), expected)

    def test_invalid_encode_fields(self):
        bad = dict(direction=(-1, 2, True, 0.0), kind=(0, 8, 2, True, 5.0),
                   session=(b"s"*15, b"s"*17, "s"*16, bytearray(16)),
                   sequence=(-1, 2**64, True, 9.0),
                   challenge=(b"c"*15, b"c"*17, "c"*16),
                   payload=(b"p"*513, "text", bytearray(2)))
        for field, values in bad.items():
            for value in values:
                with self.subTest(field=field, value_type=type(value)), self.assertRaises(ValueError):
                    encode(self.envelope(**{field: value}), self.key)

    def test_valid_kind_direction_pairs(self):
        for direction, kinds in ((0, (1, 3, 5, 6)), (1, (2, 4, 7, 8))):
            for kind in kinds:
                expected = self.envelope(direction=direction, kind=kind)
                self.assertEqual(decode(encode(expected, self.key), self.key, direction), expected)

    def test_malformed_headers_rejected_even_with_valid_tag(self):
        unsigned = bytearray(encode(self.envelope(), self.key)[:-32])
        for offset, value in ((0, 0), (4, 2), (5, 2), (6, 8), (6, 2), (7, 1), (49, 3)):
            candidate = bytearray(unsigned)
            candidate[offset] = value
            packet = bytes(candidate) + hmac.new(self.key, candidate, hashlib.sha256).digest()
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                decode(packet, self.key, 0)

    def test_invalid_api_inputs_are_rejected(self):
        packet = encode(self.envelope(), self.key)
        for key in (b"", b"k"*31, b"k"*33, "k"*32, bytearray(32), None):
            with self.assertRaises(ValueError):
                encode(self.envelope(), key)
            with self.assertRaises(ValueError):
                decode(packet, key, 0)
        for direction in (-1, 2, True, None):
            with self.assertRaises(ValueError):
                decode(packet, self.key, direction)
        for data in (None, "packet", bytearray(packet), b"x"*595):
            with self.assertRaises(ValueError):
                decode(data, self.key, 0)
        with self.assertRaises(ValueError):
            encode(None, self.key)
