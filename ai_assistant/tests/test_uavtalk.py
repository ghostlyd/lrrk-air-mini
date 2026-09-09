import contextlib
import io
import unittest

from lrrk_litewing_ai.uavtalk import UAVTalkDecoder, UAVTalkError, crc8, main, read_frames

# Synthetic headers following the pinned sendSingleObject implementation.
# Fixed checksums independently computed using its pios_crc.c lookup table.
OBJECT = bytes.fromhex("3c200d00785634120200616263eb")
TIMESTAMPED = bytes.fromhex("3ca00f00785634120200341261626320")
ACK = bytes.fromhex("3c230a00785634120200e5")


class UAVTalkTests(unittest.TestCase):
    def test_known_crc_check_value(self):
        self.assertEqual(crc8(b"123456789"), 0xF4)

    def test_independent_vectors_at_every_split(self):
        for packet in (OBJECT, TIMESTAMPED, ACK):
            for split in range(len(packet) + 1):
                decoder = UAVTalkDecoder()
                frames = decoder.feed(packet[:split]) + decoder.feed(packet[split:])
                decoder.finish()
                self.assertEqual(len(frames), 1)
                frame = frames[0]
                self.assertEqual(frame.object_id, 0x12345678)
                self.assertEqual(frame.instance_id, 2)
                self.assertEqual(frame.payload, b"" if packet == ACK else b"abc")
                self.assertEqual(frame.timestamp_ticks, 0x1234 if packet == TIMESTAMPED else None)

    def test_bytewise_and_concatenated_streams(self):
        data = OBJECT + TIMESTAMPED + ACK
        decoder = UAVTalkDecoder()
        frames = []
        for byte in data:
            frames.extend(decoder.feed(bytes([byte])))
        decoder.finish()
        self.assertEqual(frames, list(read_frames(io.BytesIO(data))))
        self.assertEqual(len(frames), 3)

    def test_rejects_all_single_bit_corruptions(self):
        for index in range(len(OBJECT)):
            for bit in range(8):
                bad = bytearray(OBJECT)
                bad[index] ^= 1 << bit
                decoder = UAVTalkDecoder()
                with self.assertRaises(UAVTalkError):
                    decoder.feed(bytes(bad))
                    decoder.finish()

    def test_truncations_are_not_accepted_at_eof(self):
        for end in range(1, len(TIMESTAMPED)):
            with self.assertRaises(UAVTalkError):
                list(read_frames(io.BytesIO(TIMESTAMPED[:end])))

    def test_invalid_headers_fail_before_waiting_for_payload(self):
        for header in ("00200a00", "3c250a00", "3ca10c00", "3c200900",
                       "3ca00b00", "3c20ffff", "3c210b00"):
            with self.assertRaises(UAVTalkError):
                UAVTalkDecoder().feed(bytes.fromhex(header))

    def test_limit_and_recovery(self):
        decoder = UAVTalkDecoder()
        decoder.feed(OBJECT[:4])
        with self.assertRaises(UAVTalkError):
            decoder.feed(b"x" * 4097)
        self.assertEqual(len(decoder.feed(ACK)), 1)
        decoder.finish()

    def test_payload_bound(self):
        for length in (217, 218):
            size = 10 + length
            raw = b"\x3c\x20" + size.to_bytes(2, "little") + b"\0" * 6 + b"a" * length
            packet = raw + bytes([crc8(raw)])
            if length == 217:
                self.assertEqual(len(UAVTalkDecoder().feed(packet)[0].payload), length)
            else:
                with self.assertRaises(UAVTalkError):
                    UAVTalkDecoder().feed(packet)

    def test_capture_cli_rejects_device(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["/dev/null"]), 2)


if __name__ == "__main__":
    unittest.main()
