import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.approval import APPROVED, ABORTED, EXPIRED, PROPOSAL_READY, ApprovalError, ApprovalStateMachine  # noqa: E402
from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot  # noqa: E402


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


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
    )


class ApprovalTests(unittest.TestCase):
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
