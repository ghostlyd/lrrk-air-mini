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
