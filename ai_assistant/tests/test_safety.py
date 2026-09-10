import math
import sys
import unittest
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.approval import ApprovalStateMachine  # noqa: E402
from lrrk_litewing_ai.jsonl import canonical_json  # noqa: E402
from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot  # noqa: E402
from lrrk_litewing_ai.safety import SafetyPolicy, run_preflight  # noqa: E402


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
NUMERIC_POLICY_FIELDS = (
    "max_link_age_ms",
    "max_future_skew_ms",
    "min_battery_voltage_v",
    "warn_battery_percent",
)
ZERO_ALLOWED_POLICY_FIELDS = (
    "max_link_age_ms",
    "max_future_skew_ms",
    "warn_battery_percent",
)


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
    def test_accepted_imu_identities_reject_malformed_collections_and_entries(self):
        malformed_collections = (
            "MPU6050",
            b"MPU6050",
            None,
            42,
            {"MPU6050"},
            frozenset(("MPU6050",)),
            {"identity": "MPU6050"},
        )
        for value in malformed_collections:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError, "accepted_imu_identities must be a list or tuple"
                ):
                    SafetyPolicy(accepted_imu_identities=value)

        malformed_entries = (
            [""],
            ["   "],
            [None],
            [104],
            [True],
            [b"MPU6050"],
            ("MPU6050", ""),
        )
        for value in malformed_entries:
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError, "accepted_imu_identities must contain non-empty strings"
                ):
                    SafetyPolicy(accepted_imu_identities=value)

    def test_accepted_imu_identities_are_exact_canonical_immutable_values(self):
        list_policy = SafetyPolicy(
            accepted_imu_identities=["0x68", "CUSTOM-B", "MPU6050", "0x68"]
        )
        tuple_policy = SafetyPolicy(
            accepted_imu_identities=("CUSTOM-B", "0x68", "MPU6050")
        )

        expected = ("MPU6050", "0x68", "CUSTOM-B")
        self.assertEqual(list_policy.accepted_imu_identities, expected)
        self.assertEqual(tuple_policy.accepted_imu_identities, expected)
        self.assertIsInstance(list_policy.accepted_imu_identities, tuple)
        self.assertEqual(list_policy.policy_hash(), tuple_policy.policy_hash())

        exact_policy = SafetyPolicy(accepted_imu_identities=["MPU6050"])
        state = snapshot(sensors=SensorHealth(True, "MPU", True))
        report = run_preflight(state, policy=exact_policy, now=NOW)
        self.assertEqual(
            next(item for item in report.findings if item.finding_id == "imu.identity").status,
            "BLOCK",
        )

    def test_malformed_imu_policy_cannot_be_hashed_or_analyzed(self):
        policy = SafetyPolicy()
        object.__setattr__(policy, "accepted_imu_identities", "MPU6050")
        operations = {
            "identity": policy.policy_hash,
            "preflight": lambda: run_preflight(
                snapshot(sensors=SensorHealth(True, "MPU", True)), policy=policy, now=NOW
            ),
        }
        for operation, call in operations.items():
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(
                    ValueError, "accepted_imu_identities must be a list or tuple"
                ):
                    call()

    def test_nonfinite_policy_values_are_rejected_at_construction(self):
        self.assertEqual(
            set(NUMERIC_POLICY_FIELDS),
            {field.name for field in fields(SafetyPolicy)} - {"accepted_imu_identities"},
        )
        for name in NUMERIC_POLICY_FIELDS:
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=name, value=value):
                    with self.assertRaisesRegex(ValueError, name + " must be finite"):
                        SafetyPolicy(**{name: value})

    def test_nonfinite_policy_values_cannot_be_hashed_analyzed_or_proposed(self):
        for name in NUMERIC_POLICY_FIELDS:
            for value in (float("nan"), float("inf"), float("-inf")):
                policy = SafetyPolicy()
                object.__setattr__(policy, name, value)
                operations = {
                    "identity": policy.policy_hash,
                    "preflight": lambda: run_preflight(snapshot(), policy=policy, now=NOW),
                    "proposal": lambda: ApprovalStateMachine("operator-1", policy=policy).create_proposal(
                        snapshot(), "inspect_telemetry", "inspect", "show report", now=NOW
                    ),
                }
                for operation, call in operations.items():
                    with self.subTest(field=name, value=value, operation=operation):
                        with self.assertRaisesRegex(ValueError, name + " must be finite"):
                            call()

    def test_policy_numeric_types_and_ranges_are_validated(self):
        for name in NUMERIC_POLICY_FIELDS:
            for value in (True, False, None, "500"):
                with self.subTest(field=name, value=value):
                    with self.assertRaisesRegex(ValueError, name + " must be numeric"):
                        SafetyPolicy(**{name: value})

        invalid_ranges = {
            "max_link_age_ms": (-0.1,),
            "max_future_skew_ms": (-0.1,),
            "min_battery_voltage_v": (-0.1, 0.0),
            "warn_battery_percent": (-0.1, 100.1),
        }
        for name, values in invalid_ranges.items():
            for value in values:
                with self.subTest(field=name, value=value):
                    with self.assertRaisesRegex(ValueError, name + " is outside its valid range"):
                        SafetyPolicy(**{name: value})

    def test_equivalent_integer_and_float_policy_values_share_identity(self):
        integer_policy = SafetyPolicy(
            max_link_age_ms=500,
            max_future_skew_ms=5000,
            min_battery_voltage_v=4,
            warn_battery_percent=20,
        )
        float_policy = SafetyPolicy(
            max_link_age_ms=500.0,
            max_future_skew_ms=5000.0,
            min_battery_voltage_v=4.0,
            warn_battery_percent=20.0,
        )
        self.assertEqual(integer_policy, float_policy)
        self.assertEqual(integer_policy.policy_hash(), float_policy.policy_hash())

    def test_signed_zero_policy_values_share_canonical_identity(self):
        for name in ZERO_ALLOWED_POLICY_FIELDS:
            with self.subTest(field=name):
                positive = SafetyPolicy(**{name: 0.0})
                negative = SafetyPolicy(**{name: -0.0})
                self.assertEqual(positive.policy_hash(), negative.policy_hash())
                self.assertEqual(math.copysign(1.0, getattr(negative, name)), 1.0)

    def test_canonical_json_rejects_nonstandard_numeric_constants(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    canonical_json({"value": value})

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
