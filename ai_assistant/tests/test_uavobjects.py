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
    def test_alarm_capture_exposes_critical_and_uninitialised_evidence(self):
        # Pinned generated layout: 21 alarm bytes, 2 extended enums, 2 substatus.
        # Representative bench condition, not a raw owner capture.
        payload = bytes([1, 0, 1, 1, 1, 1, 1, 3, 1, 3, 1,
                         0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        result = snapshot_from_frame(frame(0x6B7639EC, payload), CAPTURED)
        self.assertIsNotNone(result)
        self.assertIn("Receiver:Critical", result.alarms)
        self.assertIn("Actuator:Critical", result.alarms)
        self.assertIn("BootFault:Uninitialised", result.alarms)
        self.assertEqual(run_preflight(result, now=CAPTURED).overall, "BLOCKED")
        self.assertIsNone(result.armed)
        self.assertIsNone(result.link_age_ms)
        self.assertIsNone(result.sensors.imu_healthy)

    def test_all_clear_alarm_report_does_not_invent_other_evidence(self):
        result = snapshot_from_frame(frame(0x6B7639EC, bytes([1] * 21 + [0] * 4)), CAPTURED)
        self.assertIsNotNone(result)
        self.assertEqual(result.alarms, ())
        report = run_preflight(result, now=CAPTURED)
        self.assertEqual(next(f.status for f in report.findings if f.finding_id == "flight.alarms"), "PASS")
        self.assertEqual(report.overall, "INCOMPLETE")

    def test_uninitialised_alarm_report_is_unknown_not_clear(self):
        result = snapshot_from_frame(frame(0x6B7639EC, bytes(25)), CAPTURED)
        self.assertIsNotNone(result)
        report = run_preflight(result, now=CAPTURED)
        self.assertEqual(next(f.status for f in report.findings if f.finding_id == "flight.alarms"), "UNKNOWN")
        self.assertEqual(report.overall, "INCOMPLETE")

    def test_extended_alarm_and_substatus_are_not_discarded(self):
        for tail, expected in (([1, 0, 0, 0], "SystemConfiguration:RebootRequired"),
                               ([0, 0, 0, 7], "BootFault:SubStatus=7")):
            result = snapshot_from_frame(frame(0x6B7639EC, bytes([1] * 21 + tail)), CAPTURED)
            self.assertIsNotNone(result)
            self.assertIn(expected, result.alarms)
            self.assertEqual(run_preflight(result, now=CAPTURED).overall, "BLOCKED")

    def test_actuator_capture_maps_four_brushed_motor_channels_without_clamping(self):
        payload = struct.pack("<12hHHB", -1, 100, 1000, 1200, *([0] * 8), 2, 4, 0)
        result = snapshot_from_frame(frame(0xB8229FE4, payload), CAPTURED)
        self.assertIsNotNone(result)
        self.assertEqual(result.actuators, (-1, 100, 1000, 1200))
        self.assertIsNone(result.alarms)
        self.assertIsNone(result.source.board)
        self.assertEqual(run_preflight(result, now=CAPTURED).overall, "BLOCKED")

    def test_actuator_failures_and_unmapped_channels_remain_blocking(self):
        for channels, failures, expected in (([0] * 12, 3, "ActuatorCommand:FailedUpdates=3"),
                                             ([0] * 4 + [7] + [0] * 7, 0, "ActuatorCommand:UnmappedChannel5=7")):
            result = snapshot_from_frame(frame(0xB8229FE4, struct.pack("<12hHHB", *channels, 0, 0, failures)), CAPTURED)
            self.assertIsNotNone(result)
            self.assertIn(expected, result.alarms)
            self.assertEqual(run_preflight(result, now=CAPTURED).overall, "BLOCKED")

    def test_alarm_and_actuator_schemas_reject_malformed_objects(self):
        for oid, size in ((0x6B7639EC, 25), (0xB8229FE4, 29)):
            for length in (0, size - 1, size + 1):
                with self.subTest(oid=oid, length=length), self.assertRaises(UAVTalkError):
                    snapshot_from_frame(frame(oid, bytes(length)), CAPTURED)
            with self.assertRaises(UAVTalkError):
                snapshot_from_frame(frame(oid, bytes(size), instance=1), CAPTURED)
        for index in range(23):
            payload = bytearray([1] * 21 + [0] * 4)
            payload[index] = 5
            with self.subTest(index=index), self.assertRaises(UAVTalkError):
                snapshot_from_frame(frame(0x6B7639EC, bytes(payload)), CAPTURED)

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

    def test_battery_unavailable_fields_remain_unknown_and_json_safe(self):
        for voltage, expected in ((3.75, 3.75), (float("nan"), None)):
            payload = struct.pack("<7f2B", voltage, *([float("nan")] * 6), 1, 0)
            result = snapshot_from_frame(frame(BATTERY_STATE, payload), CAPTURED)
            self.assertEqual(result.battery.voltage_v, expected)
            self.assertIsNone(result.battery.current_a)
            self.assertIsNone(result.battery.percent)
            json.dumps(result.to_dict(), allow_nan=False)
            if expected is None:
                finding = next(f for f in run_preflight(result, now=CAPTURED).findings
                               if f.finding_id == "battery.availability")
                self.assertEqual(finding.status, "UNKNOWN")

    def test_battery_infinity_is_corruption_not_unavailable(self):
        for index in range(7):
            for value in (float("inf"), -float("inf")):
                fields = [float("nan")] * 7
                fields[index] = value
                with self.subTest(index=index, value=value), self.assertRaises(UAVTalkError):
                    snapshot_from_frame(frame(BATTERY_STATE,
                                              struct.pack("<7f2B", *fields, 1, 0)), CAPTURED)

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

    def test_cli_alarm_report_and_audit_preserve_critical_evidence(self):
        payload = bytes([1] * 7 + [3, 1, 3] + [1] * 11 + [0] * 4)
        packet = struct.pack("<BBHIH", 0x3C, 0x20, 35, 0x6B7639EC, 0) + payload
        packet += bytes([crc8(packet)])
        with tempfile.TemporaryDirectory() as directory:
            path, audit = Path(directory) / "alarms.bin", Path(directory) / "audit.jsonl"
            path.write_bytes(packet)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = main(["--input", str(path), "--input-format", "uavtalk",
                           "--captured-at", CAPTURED.isoformat(), "--audit-log", str(audit),
                           "--json", "--prompt", "run preflight"])
            self.assertEqual(rc, 0)
            records = [json.loads(line) for line in output.getvalue().splitlines()]
            for report in (records[0], records[1]["assistant"]):
                self.assertEqual(report["overall"], "BLOCKED")
                finding = next(f for f in report["findings"] if f["finding_id"] == "flight.alarms")
                self.assertIn("Receiver:Critical", finding["evidence"])
                self.assertIn("Actuator:Critical", finding["evidence"])
            received = json.loads(audit.read_text().splitlines()[0])["payload"]["snapshot"]
            self.assertIsNone(received["link_age_ms"])
            self.assertIn("Receiver:Critical", received["alarms"])


if __name__ == "__main__":
    unittest.main()
