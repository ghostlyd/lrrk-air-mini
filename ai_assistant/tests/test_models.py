import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.models import (  # noqa: E402
    Attitude,
    BatteryState,
    SensorHealth,
    SourceIdentity,
    TelemetrySnapshot,
)


class ModelTests(unittest.TestCase):
    def make_snapshot(self):
        return TelemetrySnapshot(
            snapshot_id="model-1",
            captured_at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
            source=SourceIdentity("jsonl", board="LiteWing V2.6.C"),
            link_age_ms=10,
            armed=False,
            flight_mode="attitude",
            attitude=Attitude(roll_deg=1, pitch_deg=2, yaw_deg=3),
            battery=BatteryState(voltage_v=3.9, percent=80),
            sensors=SensorHealth(imu_present=True, imu_identity="MPU6050", imu_healthy=True),
            actuators=(0, 100, 200, 300),
        )

    def test_round_trip_and_hash_are_stable(self):
        snapshot = self.make_snapshot()
        decoded = TelemetrySnapshot.from_json(snapshot.to_json())
        self.assertEqual(decoded.to_dict(), snapshot.to_dict())
        self.assertEqual(decoded.snapshot_hash(), snapshot.snapshot_hash())

    def test_unknown_values_remain_null(self):
        snapshot = self.make_snapshot()
        self.assertIsNone(snapshot.battery.current_a)
        self.assertIsNone(snapshot.sensors.optical_flow_present)
        self.assertIsNone(TelemetrySnapshot.from_dict(snapshot.to_dict()).battery.current_a)

    def test_alarm_unknown_and_explicit_clear_survive_json_round_trip(self):
        record = self.make_snapshot().to_dict()
        record.pop("alarms")
        unknown = TelemetrySnapshot.from_dict(record)
        clear = TelemetrySnapshot.from_dict(dict(record, alarms=[]))
        self.assertIsNone(unknown.alarms)
        self.assertIsNone(TelemetrySnapshot.from_json(unknown.to_json()).alarms)
        self.assertEqual(clear.alarms, ())
        self.assertNotEqual(unknown.snapshot_hash(), clear.snapshot_hash())
        self.assertEqual(clear.to_dict()["schema_version"], 2)
        for version in (1, 2):
            self.assertIsNone(TelemetrySnapshot.from_dict(dict(record, schema_version=version, alarms=None)).alarms)
            self.assertEqual(TelemetrySnapshot.from_dict(dict(record, schema_version=version, alarms=[])).alarms, ())

    def test_malformed_alarm_containers_are_rejected_not_cleared(self):
        for alarms in (False, 0, "", {}, "Receiver:Critical", [""], ["   "], [None]):
            with self.subTest(alarms=alarms), self.assertRaises(ValueError):
                TelemetrySnapshot.from_dict(dict(self.make_snapshot().to_dict(), alarms=alarms))

    def test_motor_vector_cannot_hide_null_or_boolean_values(self):
        for value in (None, True, False):
            with self.subTest(value=value), self.assertRaises(ValueError):
                TelemetrySnapshot.from_dict(dict(self.make_snapshot().to_dict(), actuators=[value, 0, 0, 0]))

    def test_malformed_optional_containers_are_rejected_in_both_schemas(self):
        malformed = {
            "capabilities": (False, 0, "", {}, "gps", {"gps": False}, [False], [" "]),
            "actuators": (False, 0, "", {}, "0000", {"0": 0}),
            "attitude": (False, 0, "", [], [0]),
            "battery": (False, 0, "", [], [0]),
            "sensors": (False, 0, "", [], [0]),
        }
        for version in (1, 2):
            for field, values in malformed.items():
                for value in values:
                    with self.subTest(version=version, field=field, value=value), self.assertRaises(ValueError):
                        TelemetrySnapshot.from_dict(dict(self.make_snapshot().to_dict(),
                                                         schema_version=version, **{field: value}))

    def test_absent_and_null_optional_containers_remain_unknown(self):
        for field in ("capabilities", "actuators", "attitude", "battery", "sensors"):
            record = self.make_snapshot().to_dict()
            record.pop(field)
            omitted = TelemetrySnapshot.from_dict(record)
            null = TelemetrySnapshot.from_dict(dict(record, **{field: None}))
            self.assertEqual(getattr(omitted, field), getattr(null, field))

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            TelemetrySnapshot(
                snapshot_id="bad",
                captured_at=datetime(2026, 9, 9, 12, 0),
                source=SourceIdentity("jsonl"),
            )

    def test_actuator_observation_is_finite_but_analyzer_decides_range(self):
        snapshot = self.make_snapshot()
        out_of_range = TelemetrySnapshot.from_dict(dict(snapshot.to_dict(), actuators=[1200, 0, 0, 0]))
        self.assertEqual(out_of_range.actuators[0], 1200.0)


if __name__ == "__main__":
    unittest.main()
