import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot  # noqa: E402
from lrrk_litewing_ai.safety import run_preflight  # noqa: E402


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def snapshot(**changes):
    values = {
        "snapshot_id": "safety-1",
        "captured_at": NOW,
        "source": SourceIdentity("test", board="LiteWing V2.6.C"),
        "link_age_ms": 20,
        "armed": False,
        "flight_mode": "attitude",
        "battery": BatteryState(voltage_v=3.9, percent=80),
        "sensors": SensorHealth(imu_present=True, imu_identity="MPU6050", imu_healthy=True),
        "actuators": (0, 0, 0, 0),
        "alarms": (),
    }
    values.update(changes)
    return TelemetrySnapshot(**values)


class SafetyTests(unittest.TestCase):
    def test_complete_snapshot_passes(self):
        report = run_preflight(snapshot(), now=NOW)
        self.assertEqual(report.overall, "PASS")
        self.assertFalse(any(item.status == "BLOCK" for item in report.findings))

    def test_unknown_alarm_state_is_not_a_clear_report(self):
        state = TelemetrySnapshot.from_dict(dict(snapshot().to_dict(), alarms=None))
        report = run_preflight(state, now=NOW)
        self.assertEqual(report.overall, "INCOMPLETE")
        self.assertEqual(next(f.status for f in report.findings if f.finding_id == "flight.alarms"), "UNKNOWN")

    def test_missing_mode_is_unknown(self):
        for mode in (None, "", "   "):
            with self.subTest(mode=mode):
                report = run_preflight(snapshot(flight_mode=mode), now=NOW)
                self.assertEqual(report.overall, "INCOMPLETE")
                self.assertEqual(next(f.status for f in report.findings if f.finding_id == "capabilities.mode"), "UNKNOWN")

    def test_motor_evidence_requires_exactly_four_channels(self):
        for count in (0, 1, 2, 3, 5, 12):
            with self.subTest(count=count):
                report = run_preflight(snapshot(actuators=(0,) * count), now=NOW)
                self.assertEqual(report.overall, "INCOMPLETE")
                self.assertEqual(next(f.status for f in report.findings if f.finding_id == "actuators.availability"), "UNKNOWN")

    def test_reported_bad_motor_value_is_not_hidden_by_incomplete_vector(self):
        report = run_preflight(snapshot(actuators=(1200,)), now=NOW)
        self.assertEqual(report.overall, "BLOCKED")

    def test_missing_alarm_json_cannot_become_no_alarms(self):
        record = snapshot().to_dict()
        del record["alarms"]
        result = TelemetrySnapshot.from_dict(record)
        self.assertEqual(run_preflight(result, now=NOW).overall, "INCOMPLETE")

    def test_stale_link_blocks(self):
        report = run_preflight(snapshot(link_age_ms=1000), now=NOW)
        self.assertEqual(report.overall, "BLOCKED")
        self.assertEqual(next(item for item in report.findings if item.finding_id == "link.freshness").status, "BLOCK")

    def test_old_snapshot_cannot_reuse_a_fresh_recorded_link_age(self):
        report = run_preflight(snapshot(captured_at=NOW - timedelta(days=1)), now=NOW)
        self.assertEqual(report.overall, "BLOCKED")
        self.assertEqual(next(item for item in report.findings if item.finding_id == "time.freshness").status, "BLOCK")

    def test_elapsed_time_consumes_remaining_link_budget(self):
        for elapsed, expected in ((480, "PASS"), (481, "BLOCKED")):
            report = run_preflight(snapshot(), now=NOW + timedelta(milliseconds=elapsed))
            self.assertEqual(report.overall, expected)

    def test_unknown_link_is_incomplete_not_safe(self):
        report = run_preflight(snapshot(link_age_ms=None), now=NOW)
        self.assertEqual(report.overall, "INCOMPLETE")

    def test_armed_snapshot_blocks(self):
        report = run_preflight(snapshot(armed=True), now=NOW)
        self.assertEqual(report.overall, "BLOCKED")

    def test_wrong_imu_identity_blocks(self):
        report = run_preflight(snapshot(sensors=SensorHealth(True, "ICM20602", True)), now=NOW)
        self.assertEqual(next(item for item in report.findings if item.finding_id == "imu.identity").status, "BLOCK")

    def test_low_battery_blocks(self):
        report = run_preflight(snapshot(battery=BatteryState(voltage_v=3.1, percent=10)), now=NOW)
        self.assertEqual(report.overall, "BLOCKED")

    def test_actuator_overflow_blocks(self):
        report = run_preflight(snapshot(actuators=(1200, 0, 0, 0)), now=NOW)
        self.assertEqual(next(item for item in report.findings if item.finding_id == "actuators.range").status, "BLOCK")

    def test_future_timestamp_blocks(self):
        report = run_preflight(snapshot(captured_at=NOW + timedelta(seconds=10)), now=NOW)
        self.assertEqual(next(item for item in report.findings if item.finding_id == "time.freshness").status, "BLOCK")

    def test_position_mode_without_optional_sensor_blocks(self):
        report = run_preflight(snapshot(flight_mode="position_hold"), now=NOW)
        self.assertEqual(next(item for item in report.findings if item.finding_id == "capabilities.mode").status, "BLOCK")


if __name__ == "__main__":
    unittest.main()
