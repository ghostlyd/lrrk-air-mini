import hashlib
import json
import sys
import unittest
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.approval import APPROVED, ABORTED, EXPIRED, PROPOSAL_READY, ApprovalError, ApprovalStateMachine  # noqa: E402
from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot  # noqa: E402
from lrrk_litewing_ai.safety import SafetyPolicy  # noqa: E402


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
POLICY_CHANGES = {
    "max_link_age_ms": 2000.0,
    "max_future_skew_ms": 1000.0,
    "min_battery_voltage_v": 4.10,
    "warn_battery_percent": 90.0,
    "accepted_imu_identities": ("0x68",),
}
ZERO_ALLOWED_POLICY_FIELDS = (
    "max_link_age_ms",
    "max_future_skew_ms",
    "warn_battery_percent",
)


def snapshot(snapshot_id="approval-1", complete=True):
    return TelemetrySnapshot(
        snapshot_id=snapshot_id,
        captured_at=NOW,
        source=SourceIdentity("test", board="LiteWing V2.6.C"),
        link_age_ms=20,
        armed=False,
        flight_mode="attitude",
        battery=BatteryState(voltage_v=3.9, percent=80),
        sensors=SensorHealth(imu_present=True, imu_identity="MPU6050", imu_healthy=True) if complete else SensorHealth(),
        actuators=(0, 0, 0, 0),
        alarms=(),
    )


class ApprovalTests(unittest.TestCase):
    def test_bare_string_imu_policy_cannot_reach_approved(self):
        policy = SafetyPolicy()
        object.__setattr__(policy, "accepted_imu_identities", "MPU6050")
        state = replace(snapshot(), sensors=SensorHealth(True, "MPU", True))

        with self.assertRaisesRegex(
            ValueError, "accepted_imu_identities must be a list or tuple"
        ):
            machine = ApprovalStateMachine("operator-1", policy=policy)
            proposal = machine.create_proposal(
                state, "inspect_telemetry", "inspect", "show report", now=NOW
            )
            machine.approve(
                proposal.proposal_id, "human-confirmation", state, now=NOW
            )
            self.assertNotEqual(machine.state, APPROVED)

    def test_policy_replacement_aborts_pending_and_approved_records(self):
        for name, value in POLICY_CHANGES.items():
            for approved in (False, True):
                with self.subTest(field=name, approved=approved):
                    machine = ApprovalStateMachine("operator-1")
                    proposal = machine.create_proposal(
                        snapshot(), "inspect_telemetry", "inspect", "show report", now=NOW)
                    if approved:
                        machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)
                    machine.policy = replace(SafetyPolicy(), **{name: value})
                    self.assertEqual(machine.state, ABORTED)
                    self.assertIsNone(machine._approval_digest)
                    self.assertFalse(machine.approval_is_current(snapshot(), now=NOW))
                    machine.policy = SafetyPolicy()
                    with self.assertRaises(ApprovalError):
                        machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)

    def test_equivalent_policy_replacement_preserves_pending_and_approved_records(self):
        machine = ApprovalStateMachine("operator-1")
        proposal = machine.create_proposal(snapshot(), "inspect_telemetry", "inspect", "show report", now=NOW)
        machine.policy = SafetyPolicy()
        self.assertEqual(machine.state, PROPOSAL_READY)
        machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)
        machine.policy = SafetyPolicy()
        self.assertEqual(machine.state, APPROVED)
        self.assertTrue(machine.approval_is_current(snapshot(), now=NOW))

    def test_signed_zero_policy_replacement_preserves_active_records(self):
        state = replace(snapshot(), link_age_ms=0)
        for name in ZERO_ALLOWED_POLICY_FIELDS:
            for approved in (False, True):
                with self.subTest(field=name, approved=approved):
                    machine = ApprovalStateMachine(
                        "operator-1", policy=SafetyPolicy(**{name: 0.0})
                    )
                    proposal = machine.create_proposal(
                        state, "inspect_telemetry", "inspect", "show report", now=NOW
                    )
                    if approved:
                        machine.approve(
                            proposal.proposal_id,
                            "human-confirmation",
                            state,
                            now=NOW,
                        )

                    machine.policy = SafetyPolicy(**{name: -0.0})

                    expected = APPROVED if approved else PROPOSAL_READY
                    self.assertEqual(machine.state, expected)
                    if approved:
                        self.assertTrue(machine.approval_is_current(state, now=NOW))
                    else:
                        machine.approve(
                            proposal.proposal_id,
                            "human-confirmation",
                            state,
                            now=NOW,
                        )
                        self.assertEqual(machine.state, APPROVED)

    def test_analyzer_drift_is_rechecked_before_approval_and_currentness(self):
        for check in ("approve", "pending_currentness", "approved_currentness"):
            with self.subTest(check=check):
                machine = ApprovalStateMachine("operator-1")
                proposal = machine.create_proposal(
                    snapshot(), "inspect_telemetry", "inspect", "show report", now=NOW)
                if check == "approved_currentness":
                    machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)
                with patch("lrrk_litewing_ai.safety.ANALYZER_VERSION", "litewing-safety-next"):
                    if check == "approve":
                        with self.assertRaises(ApprovalError):
                            machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)
                    else:
                        self.assertFalse(machine.approval_is_current(snapshot(), now=NOW))
                self.assertEqual(machine.state, ABORTED)
                self.assertIsNone(machine._approval_digest)

    def test_proposal_policy_identity_is_canonical_and_shared_with_approval(self):
        machine = ApprovalStateMachine("operator-1", policy=SafetyPolicy(min_battery_voltage_v=3.8))
        proposal = machine.create_proposal(snapshot(), "review_battery", "inspect", "show report", now=NOW)
        record = proposal.to_dict()
        self.assertIn("policy_version", record)
        self.assertIn("policy_hash", record)
        # Independent canonical wire fixture: every effective field plus analyzer version.
        policy_bytes = (b'{"analyzer_version":"litewing-safety-4","policy":{'
                        b'"accepted_imu_identities":["MPU6050","0x68","0x69","104","105"],'
                        b'"max_future_skew_ms":5000.0,"max_link_age_ms":500.0,'
                        b'"min_battery_voltage_v":3.8,"warn_battery_percent":20.0}}')
        self.assertEqual(record["policy_version"], "litewing-safety-4")
        self.assertEqual(record["policy_hash"], hashlib.sha256(policy_bytes).hexdigest())
        hash_fields = {key: value for key, value in record.items() if key != "proposal_hash"}
        self.assertEqual(record["proposal_hash"], hashlib.sha256(json.dumps(
            hash_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest())
        result = machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)
        self.assertEqual(result["policy_version"], record["policy_version"])
        self.assertEqual(result["policy_hash"], record["policy_hash"])
        self.assertNotIn("human-confirmation", json.dumps(result))
        self.assertNotIn("human-confirmation", repr(vars(machine)))

    def test_every_policy_field_changes_proposal_identity(self):
        self.assertEqual(set(POLICY_CHANGES), {field.name for field in fields(SafetyPolicy)})
        records = []
        # Hold random ID and time constant so only the policy can change the hash.
        with patch("lrrk_litewing_ai.approval.uuid.uuid4", return_value="fixed-proposal-id"):
            for policy in [SafetyPolicy(), SafetyPolicy()] + [
                replace(SafetyPolicy(), **{name: value}) for name, value in POLICY_CHANGES.items()
            ]:
                machine = ApprovalStateMachine("operator-1", policy=policy)
                records.append(machine.create_proposal(
                    snapshot(), "inspect_telemetry", "inspect", "show report", now=NOW).to_dict())
        self.assertEqual(records[0], records[1])
        for name, record in zip(POLICY_CHANGES, records[2:]):
            with self.subTest(field=name):
                self.assertNotEqual(record["proposal_hash"], records[0]["proposal_hash"])
                self.assertNotEqual(record["policy_hash"], records[0]["policy_hash"])

    def test_analyzer_version_changes_policy_and_proposal_identity(self):
        records = []
        with patch("lrrk_litewing_ai.approval.uuid.uuid4", return_value="fixed-proposal-id"):
            for version in ("litewing-safety-3", "litewing-safety-next"):
                with patch("lrrk_litewing_ai.safety.ANALYZER_VERSION", version, create=True):
                    machine = ApprovalStateMachine("operator-1")
                    records.append(machine.create_proposal(
                        snapshot(), "inspect_telemetry", "inspect", "show report", now=NOW).to_dict())
        self.assertNotEqual(records[0]["proposal_hash"], records[1]["proposal_hash"])
        self.assertNotEqual(records[0]["policy_hash"], records[1]["policy_hash"])
        self.assertEqual(records[1]["policy_version"], "litewing-safety-next")

    def test_missing_evidence_cannot_authorize_a_proposal(self):
        for changed in ({"alarms": None}, {"flight_mode": None}, {"actuators": [0]}):
            with self.subTest(changed=changed):
                state = TelemetrySnapshot.from_dict(dict(snapshot().to_dict(), **changed))
                machine = ApprovalStateMachine("operator-1")
                proposal = machine.create_proposal(state, "inspect_telemetry", "inspect", "show report", now=NOW)
                with self.assertRaises(ApprovalError):
                    machine.approve(proposal.proposal_id, "human-confirmation", state, now=NOW)
                self.assertEqual(machine.state, ABORTED)

    def test_negative_capability_mapping_cannot_reach_approval(self):
        for version in (1, 2):
            with self.subTest(version=version), self.assertRaises(ValueError):
                state = TelemetrySnapshot.from_dict(dict(snapshot().to_dict(),
                    schema_version=version, flight_mode="position_hold", capabilities={"gps": False}))
                machine = ApprovalStateMachine("operator-1")
                proposal = machine.create_proposal(state, "inspect_telemetry", "inspect", "show report", now=NOW)
                machine.approve(proposal.proposal_id, "human-confirmation", state, now=NOW)

    def test_existing_approval_is_invalidated_when_snapshot_ages(self):
        machine = ApprovalStateMachine("operator-1")
        state = snapshot()
        proposal = machine.create_proposal(state, "inspect_telemetry", "inspect", "show report", now=NOW)
        machine.approve(proposal.proposal_id, "human-confirmation", state, now=NOW)
        self.assertTrue(machine.approval_is_current(state, now=NOW + timedelta(milliseconds=480)))
        self.assertFalse(machine.approval_is_current(state, now=NOW + timedelta(milliseconds=481)))
        self.assertEqual(machine.state, ABORTED)

    def test_unchanged_snapshot_becomes_stale_before_proposal_expires(self):
        machine = ApprovalStateMachine("operator-1")
        proposal = machine.create_proposal(snapshot(), "review_orientation", "verify frame", "show checklist", now=NOW)
        with self.assertRaises(ApprovalError):
            machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW + timedelta(seconds=1))
        self.assertEqual(machine.state, ABORTED)

    def test_human_approval_is_bound_to_current_snapshot(self):
        machine = ApprovalStateMachine("operator-1")
        proposal = machine.create_proposal(snapshot(), "review_orientation", "verify frame", "show checklist", now=NOW)
        self.assertEqual(machine.state, PROPOSAL_READY)
        result = machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)
        self.assertEqual(machine.state, APPROVED)
        self.assertEqual(result["proposal_hash"], proposal.proposal_hash)
        with self.assertRaises(ApprovalError):
            machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW)

    def test_snapshot_drift_aborts_proposal(self):
        machine = ApprovalStateMachine("operator-1")
        proposal = machine.create_proposal(snapshot(), "review_orientation", "verify frame", "show checklist", now=NOW)
        with self.assertRaises(ApprovalError):
            machine.approve(proposal.proposal_id, "human-confirmation", snapshot("changed"), now=NOW)
        self.assertEqual(machine.state, ABORTED)

    def test_expiry_cannot_be_approved(self):
        machine = ApprovalStateMachine("operator-1")
        proposal = machine.create_proposal(snapshot(), "review_battery", "check battery", "show battery status", expiry_seconds=1, now=NOW)
        with self.assertRaises(ApprovalError):
            machine.approve(proposal.proposal_id, "human-confirmation", snapshot(), now=NOW + timedelta(seconds=2))
        self.assertEqual(machine.state, EXPIRED)

    def test_forbidden_action_is_not_proposable(self):
        machine = ApprovalStateMachine("operator-1")
        with self.assertRaises(ApprovalError):
            machine.create_proposal(snapshot(), "arm", "arm now", "motor output", now=NOW)

    def test_incomplete_safety_report_cannot_be_approved(self):
        machine = ApprovalStateMachine("operator-1")
        proposal = machine.create_proposal(snapshot(complete=False), "inspect_telemetry", "inspect state", "show report", now=NOW)
        with self.assertRaises(ApprovalError):
            machine.approve(proposal.proposal_id, "human-confirmation", snapshot(complete=False), now=NOW)
        self.assertEqual(machine.state, ABORTED)


if __name__ == "__main__":
    unittest.main()
