import contextlib
import io
import json
import struct
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from lrrk_litewing_ai.cli import main
from lrrk_litewing_ai.safety import run_preflight
from lrrk_litewing_ai.uavobjects import ATTITUDE_STATE, BATTERY_STATE, FLIGHT_STATUS, snapshot_from_frame
from lrrk_litewing_ai.uavtalk import UAVTalkError, UAVTalkFrame, crc8

CAPTURED = datetime(2026, 9, 9, tzinfo=timezone.utc)


def frame(object_id, payload, instance=0, kind=0x20):
    return UAVTalkFrame(kind, object_id, instance, None, payload)


class UAVObjectTests(unittest.TestCase):
    def test_attitude_offsets_and_unknown_fields(self):
        # q1=1, q2=q3=q4=0, roll=10, pitch=-20, yaw=90 (IEEE754 LE).
        payload = bytes.fromhex("0000803f000000000000000000000000000020410000a0c10000b442")
        result = snapshot_from_frame(frame(ATTITUDE_STATE, payload), CAPTURED)
        self.assertEqual(result.attitude.to_dict(), {"roll_deg": 10, "pitch_deg": -20, "yaw_deg": 90})
        self.assertIsNone(result.armed)
        self.assertIsNone(result.link_age_ms)
        self.assertIsNone(result.battery.voltage_v)
        self.assertIsNone(result.sensors.imu_healthy)
        self.assertIsNone(result.source.firmware)
        self.assertEqual(result.captured_at, CAPTURED)
        self.assertNotEqual(run_preflight(result, now=CAPTURED).overall, "PASS")

    def test_battery_units_and_no_invented_percentage(self):
        payload = struct.pack("<7f2B", 3.75, 0.5, 3.3, 1, 0.4, 12, 60, 1, 1)
        result = snapshot_from_frame(frame(BATTERY_STATE, payload), CAPTURED)
        self.assertEqual(result.battery.voltage_v, 3.75)
        self.assertEqual(result.battery.current_a, 0.5)
        self.assertIsNone(result.battery.percent)
        self.assertEqual(result.actuators, ())

    def test_arming_is_never_disarmed(self):
        for armed in range(3):
            payload = bytes([armed, 8, 0, 0, 0, 1, 0, 0])
            result = snapshot_from_frame(frame(FLIGHT_STATUS, payload), CAPTURED)
            self.assertEqual(result.armed, armed != 0)
            self.assertEqual(result.flight_mode, "position_hold")
            self.assertNotEqual(run_preflight(result, now=CAPTURED).overall, "PASS")

    def test_bad_enums_sizes_instances_and_nonfinite_rejected(self):
        invalid = [frame(FLIGHT_STATUS, bytes([3]) + bytes(7)),
                   frame(FLIGHT_STATUS, bytes([0, 18]) + bytes(6)),
                   frame(FLIGHT_STATUS, bytes(7) + bytes([2])),
                   frame(FLIGHT_STATUS, bytes(8), instance=1),
                   frame(BATTERY_STATE, struct.pack("<7f2B", *([0] * 7), 1, 2))]
        for value in (float("nan"), float("inf"), -float("inf")):
            invalid.append(frame(ATTITUDE_STATE, struct.pack("<7f", value, *([0] * 6))))
        for size in range(40):
            if size != 28:
                invalid.append(frame(ATTITUDE_STATE, bytes(size)))
        for item in invalid:
            with self.assertRaises(UAVTalkError):
                snapshot_from_frame(item, CAPTURED)

    def test_unknown_and_control_objects_are_skipped(self):
        self.assertIsNone(snapshot_from_frame(frame(0xFFFFFFFF, b""), CAPTURED))
        self.assertIsNone(snapshot_from_frame(frame(FLIGHT_STATUS, b"", kind=0x23), CAPTURED))

    def test_cli_capture_reaches_assistant_and_audit(self):
        payload = bytes(8)
        packet = struct.pack("<BBHIH", 0x3C, 0x20, 18, FLIGHT_STATUS, 0) + payload
        packet += bytes([crc8(packet)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.bin"
            audit = Path(directory) / "audit.jsonl"
            path.write_bytes(packet)
            args = ["--input", str(path), "--input-format", "uavtalk", "--json"]
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
                self.assertEqual(main(args + ["--captured-at", "2026-09-09"]), 2)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = main(args + ["--captured-at", CAPTURED.isoformat(), "--prompt", "status",
                                  "--audit-log", str(audit)])
            self.assertEqual(rc, 0)
            records = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertNotEqual(records[0]["overall"], "PASS")
            self.assertIn("assistant", records[1])
            audit_records = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertEqual(audit_records[0]["source"]["adapter"], "uavtalk-capture-ac77304")
            path.write_bytes(packet[:-1])
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args + ["--captured-at", CAPTURED.isoformat()]), 2)


if __name__ == "__main__":
    unittest.main()
