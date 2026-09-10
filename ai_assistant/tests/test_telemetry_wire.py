"""Canonical layout, bounded metadata, and authenticated telemetry framing."""
from dataclasses import replace
import unittest

from lrrk_litewing_ai.telemetry_wire import (
    TelemetryRecord, encode_record, decode_record, encode_telemetry, decode_telemetry)
from lrrk_litewing_ai.pilot_wire import Envelope, encode


class TelemetryWireTests(unittest.TestCase):
    record = TelemetryRecord(0xEF69B6BC, 1000, None, bytes(8))
    key = b"k" * 32

    def test_frozen_payload(self):
        expected = bytes.fromhex(
            "01000008ef69b6bc00000000000003e8ffffffffffffffff0000000000000000")
        self.assertEqual(encode_record(self.record), expected)
        self.assertEqual(decode_record(expected), self.record)

    def test_exact_allowlist_and_age_boundaries(self):
        for obj, size in ((0xD7E0D964, 28), (0xEF69B6BC, 8), (0x26962352, 30),
                          (0x6B7639EC, 25), (0xB8229FE4, 29)):
            for stamp in (0, 1000, 2**63-1):
                for age in (None, 0, stamp):
                    record = TelemetryRecord(obj, stamp, age, bytes(range(size)))
                    self.assertEqual(decode_record(encode_record(record)), record)
            for wrong in range(31):
                if wrong != size:
                    with self.assertRaises(ValueError):
                        encode_record(TelemetryRecord(obj, 0, None, bytes(wrong)))

    def test_invalid_record_inputs(self):
        changes = dict(object_id=(0, True, 0xEF69B6BC + 2**32, 1.0),
                       serialized_us=(-1, 2**63, True, 1.0),
                       sample_age_us=(-1, 1001, 2**64-1, True, 1.0),
                       data=(bytes(7), bytes(9), bytearray(8), "abcdefgh"))
        for name, values in changes.items():
            for value in values:
                with self.subTest(field=name, value=value), self.assertRaises(ValueError):
                    encode_record(replace(self.record, **{name: value}))
        with self.assertRaises(ValueError):
            encode_record(None)

    def test_malformed_payloads(self):
        payload = encode_record(self.record)
        invalid = [payload[:i] for i in range(len(payload))] + [payload+b"x", None, bytearray(payload)]
        for offset, value in ((0, 2), (1, 1), (3, 7), (4, 0), (8, 128), (16, 0)):
            changed = bytearray(payload)
            changed[offset] = value
            invalid.append(bytes(changed))
        for value in invalid:
            with self.assertRaises(ValueError):
                decode_record(value)

    def test_authenticated_wrapper(self):
        packet = encode_telemetry(self.record, b"s"*16, 1, self.key)
        frame, record = decode_telemetry(packet, self.key)
        self.assertEqual(record, self.record)
        self.assertEqual((frame.direction, frame.kind, frame.sequence, frame.challenge),
                         (1, 8, 1, bytes(16)))
        for i in range(len(packet)):
            changed = bytearray(packet)
            changed[i] ^= 1
            with self.assertRaises(ValueError):
                decode_telemetry(bytes(changed), self.key)
            with self.assertRaises(ValueError):
                decode_telemetry(packet[:i], self.key)
        for wrong in (packet+b"x", b"x"*137):
            with self.assertRaises(ValueError):
                decode_telemetry(wrong, self.key)
        with self.assertRaises(ValueError):
            decode_telemetry(packet, b"z"*32)

    def test_valid_mac_does_not_bypass_telemetry_contract(self):
        good = Envelope(1, 8, b"s"*16, 1, bytes(16), encode_record(self.record))
        for changes in (dict(direction=0, kind=5), dict(kind=7), dict(session=bytes(16)),
                        dict(sequence=0), dict(challenge=b"c"*16)):
            with self.assertRaises(ValueError):
                decode_telemetry(encode(replace(good, **changes), self.key), self.key)
        for session, sequence in ((bytes(16), 1), (b"s"*16, 0), (b"s"*16, True)):
            with self.assertRaises(ValueError):
                encode_telemetry(self.record, session, sequence, self.key)
