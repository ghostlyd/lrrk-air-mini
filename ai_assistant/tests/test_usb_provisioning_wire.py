"""Maintenance framing is separate from the advisory/receive-only adapter."""
import unittest
import importlib.util
if importlib.util.find_spec("lrrk_litewing_ai.usb_provisioning_wire"):
    from lrrk_litewing_ai import usb_provisioning_wire as wire
else:
    wire = None
from lrrk_litewing_ai.uavtalk import crc8


def status_frame(phase=6, result=4, transaction=b"t"*16):
    # Literal wire layout from the USB specification, not production encoding.
    data = bytes.fromhex("3c2022004850574c0000") + bytes([1, phase, result, 0]) + transaction + b"\0"*4
    return data + bytes([crc8(data)])


class ProvisioningWireTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(wire,"maintenance wire codec not implemented")
        self.blob = b"LWCF\x01\x01\x10\x00" + b"k"*32 + b"x" + b"\0"*31 + b"p"*16 + b"\0"*48

    def test_submission_exact_layout_and_crc(self):
        packet = wire.submission(b"t"*16, self.blob)
        self.assertEqual(len(packet), 163)
        self.assertEqual(packet[:10], bytes.fromhex("3c22a2004650574c0000"))
        self.assertEqual(packet[10:26], b"t"*16)
        self.assertEqual(packet[26:-1], self.blob)
        self.assertEqual(packet[-1], crc8(packet[:-1]))

    def test_status_request_has_no_secret_payload(self):
        packet = wire.status_request()
        self.assertEqual(packet[:-1], bytes.fromhex("3c210a004850574c0000"))
        self.assertEqual(len(packet), 11)
        self.assertEqual(packet[-1], crc8(packet[:-1]))

    def test_blob_encoding_matches_firmware_layout(self):
        self.assertEqual(wire.encode_config("x", "p"*16, b"k"*32), self.blob)
        for ssid, password, key in (("", "p"*16, b"k"*32), ("x"*33,"p"*16,b"k"*32),
                                    ("x","p"*15,b"k"*32), ("x","p"*64,b"k"*32),
                                    ("é","p"*16,b"k"*32), ("x","\n"*16,b"k"*32),
                                    ("x","p"*16,b"\0"*32), ("x","p"*16,b"k"*31)):
            with self.subTest(ssid_length=len(ssid), password_length=len(password)):
                with self.assertRaises(wire.ProvisioningWireError):
                    wire.encode_config(ssid,password,key)

    def test_invalid_submission_does_not_echo_credentials(self):
        bad_blobs = [self.blob[:-1], self.blob+b"x"]
        for index, value in ((0,0), (4,2), (5,0), (6,64), (7,1), (41,1), (135,1), (72,10)):
            changed=bytearray(self.blob); changed[index]=value; bad_blobs.append(bytes(changed))
        bad_blobs.append(self.blob[:8]+b"\0"*32+self.blob[40:])
        for blob in bad_blobs:
            with self.assertRaises(wire.ProvisioningWireError) as caught:
                wire.submission(b"t"*16,blob)
            self.assertNotIn("kkkk",str(caught.exception))
            self.assertNotIn("pppp",str(caught.exception))
        for transaction in (b"", b"\0"*16, b"t"*15, b"t"*17):
            with self.assertRaises(wire.ProvisioningWireError):
                wire.submission(transaction,self.blob)

    def test_verified_write_is_not_completion_until_cleanup_finishes(self):
        for phase in range(7):
            for result in range(5):
                state=wire.parse_status(status_frame(phase,result),b"t"*16)
                self.assertEqual((state.phase,state.result),(phase,result))
                self.assertEqual(state.persisted_and_finished,phase==6 and result==4)

    def test_status_rejects_wrong_transaction_corruption_and_extra_bytes(self):
        good=status_frame()
        for packet in (good[:-1],good+b"\0",good[:-1]+bytes([good[-1]^1]),
                       status_frame(transaction=b"s"*16),status_frame(7),status_frame(result=5)):
            with self.assertRaises(wire.ProvisioningWireError):
                wire.parse_status(packet,b"t"*16)
        # Repair CRC after semantic corruption to exercise validation, not CRC alone.
        for index, value in ((0,0),(1,0xA0),(2,33),(4,0),(8,1),(10,2),(13,1),(30,1),(33,1)):
            packet=bytearray(good); packet[index]=value; packet[-1]=crc8(packet[:-1])
            with self.subTest(index=index):
                with self.assertRaises(wire.ProvisioningWireError):
                    wire.parse_status(bytes(packet),b"t"*16)

    def test_ack_only_means_queued(self):
        for message, accepted in ((0x23,True),(0x24,False)):
            packet=bytes([0x3c,message])+bytes.fromhex("0a004650574c0000")
            self.assertIs(wire.parse_receipt(packet+bytes([crc8(packet)])),accepted)
        with self.assertRaises(wire.ProvisioningWireError):
            wire.parse_receipt(status_frame())
