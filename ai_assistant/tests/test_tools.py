import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.approval import ABORTED, APPROVED, PROPOSAL_READY, ApprovalError  # noqa: E402
from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot  # noqa: E402
from lrrk_litewing_ai.safety import SafetyPolicy  # noqa: E402
from lrrk_litewing_ai.tools import (  # noqa: E402
    AssistantRuntime,
    TOOL_SCHEMAS,
    compare_snapshots,
    explain_finding,
    get_latest_telemetry,
    propose_action,
    run_preflight_tool,
)


def make_snapshot(snapshot_id="tools-1"):
    return TelemetrySnapshot(
        snapshot_id=snapshot_id,
        captured_at=datetime.now(timezone.utc),
        source=SourceIdentity("test", board="LiteWing V2.6.C"),
        link_age_ms=20,
        armed=False,
        flight_mode="attitude",
        battery=BatteryState(voltage_v=3.9, percent=80),
        sensors=SensorHealth(imu_present=True, imu_identity="MPU6050", imu_healthy=True),
        actuators=(0, 0, 0, 0),
        alarms=(),
    )


class ToolTests(unittest.TestCase):
    def test_nan_battery_policy_cannot_approve_three_volt_snapshot(self):
        with self.assertRaisesRegex(ValueError, "min_battery_voltage_v must be finite"):
            runtime = AssistantRuntime(policy=SafetyPolicy(min_battery_voltage_v=float("nan")))
            state = TelemetrySnapshot.from_dict(dict(
                make_snapshot().to_dict(),
                battery={"voltage_v": 3.0, "current_a": None, "percent": 80},
            ))
            runtime.ingest(state)
            proposal = propose_action(runtime, "review_battery", "inspect", "show report")["proposal"]
            runtime.approvals.approve(
                proposal["proposal_id"], "human-confirmation", state, now=state.captured_at
            )

    def test_changed_snapshot_ingestion_immediately_aborts_active_records(self):
        for approved in (False, True):
            for changes in ({"snapshot_id": "new-observation"}, {"armed": True}, {"alarms": None}):
                with self.subTest(approved=approved, changes=changes):
                    runtime = AssistantRuntime()
                    snapshot = make_snapshot()
                    original = snapshot.to_dict()
                    runtime.ingest(snapshot)
                    proposal = propose_action(runtime, "inspect_telemetry", "inspect", "show report")["proposal"]
                    if approved:
                        runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot,
                                                  now=snapshot.captured_at)
                    changed = TelemetrySnapshot.from_dict(dict(original, **changes))
                    runtime.ingest(changed)
                    self.assertEqual(runtime.approvals.state, ABORTED)
                    self.assertIsNone(runtime.approvals._approval_digest)
                    self.assertFalse(runtime.approvals.approval_is_current(snapshot, now=snapshot.captured_at))
                    self.assertEqual(get_latest_telemetry(runtime)["snapshot_hash"], changed.snapshot_hash())
                    self.assertEqual(runtime.previous, snapshot)
                    self.assertEqual(snapshot.to_dict(), original)
                    with self.assertRaises(ApprovalError):
                        runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot,
                                                  now=snapshot.captured_at)

    def test_identical_snapshot_ingestion_preserves_active_records(self):
        for approved in (False, True):
            with self.subTest(approved=approved):
                runtime = AssistantRuntime()
                snapshot = make_snapshot()
                runtime.ingest(snapshot)
                proposal = propose_action(runtime, "inspect_telemetry", "inspect", "show report")["proposal"]
                if approved:
                    runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot,
                                              now=snapshot.captured_at)
                digest = runtime.approvals._approval_digest
                for identical in (snapshot, TelemetrySnapshot.from_dict(snapshot.to_dict())):
                    runtime.ingest(identical)
                    self.assertEqual(runtime.approvals.state, APPROVED if approved else PROPOSAL_READY)
                    self.assertEqual(runtime.approvals._approval_digest, digest)
                    self.assertEqual(runtime.approvals.proposal.to_dict(), proposal)
                if not approved:
                    runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot,
                                              now=snapshot.captured_at)
                self.assertTrue(runtime.approvals.approval_is_current(snapshot, now=snapshot.captured_at))

    def test_ingestion_compares_with_proposal_bound_snapshot(self):
        runtime = AssistantRuntime()
        snapshot = make_snapshot()
        runtime.approvals.create_proposal(snapshot, "inspect_telemetry", "inspect", "show report")
        runtime.ingest(TelemetrySnapshot.from_dict(dict(snapshot.to_dict(), snapshot_id="changed")))
        self.assertEqual(runtime.approvals.state, ABORTED)

    def test_runtime_policy_replacement_aborts_active_records_and_updates_preflight(self):
        for approved in (False, True):
            with self.subTest(approved=approved):
                runtime = AssistantRuntime()
                snapshot = make_snapshot()
                runtime.ingest(snapshot)
                proposal = propose_action(runtime, "review_battery", "inspect", "show report")["proposal"]
                if approved:
                    runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot,
                                              now=snapshot.captured_at)
                run_preflight_tool(runtime)
                runtime.policy = SafetyPolicy(min_battery_voltage_v=4.10)
                self.assertEqual(runtime.approvals.state, ABORTED)
                self.assertIsNone(runtime.approvals._approval_digest)
                self.assertIsNone(runtime.last_report)
                self.assertEqual(run_preflight_tool(runtime)["overall"], "BLOCKED")
                replacement = propose_action(runtime, "review_battery", "inspect again", "show report")["proposal"]
                self.assertNotEqual(proposal["policy_hash"], replacement["policy_hash"])
                self.assertEqual(replacement["policy_hash"], runtime.policy.policy_hash())
                with self.assertRaises(ApprovalError):
                    runtime.approvals.approve(replacement["proposal_id"], "human-confirmation", snapshot,
                                              now=snapshot.captured_at)

    def test_runtime_and_state_machine_share_policy_updates(self):
        runtime = AssistantRuntime()
        snapshot = make_snapshot()
        runtime.ingest(snapshot)
        with patch("lrrk_litewing_ai.safety._now", return_value=snapshot.captured_at):
            self.assertEqual(run_preflight_tool(runtime)["overall"], "PASS")
        self.assertIsNotNone(runtime.last_report)
        runtime.approvals.policy = SafetyPolicy(min_battery_voltage_v=4.10)
        self.assertIsNone(runtime.last_report)
        with patch("lrrk_litewing_ai.safety._now", return_value=snapshot.captured_at):
            self.assertEqual(run_preflight_tool(runtime)["overall"], "BLOCKED")
        self.assertEqual(runtime.policy.policy_hash(), runtime.approvals.policy.policy_hash())

    def test_direct_policy_replacement_rejects_malformed_policy_before_installing_it(self):
        runtime = AssistantRuntime()
        snapshot = make_snapshot()
        runtime.ingest(snapshot)
        with patch("lrrk_litewing_ai.safety._now", return_value=snapshot.captured_at):
            run_preflight_tool(runtime)
        original_policy = runtime.policy
        original_report = runtime.last_report
        malformed = SafetyPolicy()
        object.__setattr__(malformed, "min_battery_voltage_v", float("nan"))

        with self.assertRaisesRegex(ValueError, "min_battery_voltage_v must be finite"):
            runtime.approvals.policy = malformed

        self.assertIs(runtime.policy, original_policy)
        self.assertIs(runtime.last_report, original_report)

    def test_configured_battery_block_cannot_be_approved(self):
        runtime = AssistantRuntime(policy=SafetyPolicy(min_battery_voltage_v=4.10))
        snapshot = make_snapshot()
        runtime.ingest(snapshot)
        with patch("lrrk_litewing_ai.safety._now", return_value=snapshot.captured_at):
            self.assertEqual(run_preflight_tool(runtime)["overall"], "BLOCKED")
        proposal = propose_action(runtime, "review_battery", "inspect battery", "show report")["proposal"]
        with self.assertRaises(ApprovalError):
            runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot, now=snapshot.captured_at)
        self.assertEqual(runtime.approvals.state, ABORTED)

    def test_approval_and_currentness_use_configured_freshness_budget(self):
        runtime = AssistantRuntime(policy=SafetyPolicy(max_link_age_ms=2000.0))
        snapshot = make_snapshot()
        runtime.ingest(snapshot)
        proposal = propose_action(runtime, "inspect_telemetry", "inspect", "show report")["proposal"]
        try:
            runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot,
                                      now=snapshot.captured_at + timedelta(seconds=1))
        except ApprovalError:
            self.fail("configured 2000 ms freshness budget must allow approval at 1020 ms")
        self.assertTrue(runtime.approvals.approval_is_current(
            snapshot, now=snapshot.captured_at + timedelta(milliseconds=1980)))
        self.assertFalse(runtime.approvals.approval_is_current(
            snapshot, now=snapshot.captured_at + timedelta(milliseconds=1981)))
        self.assertEqual(runtime.approvals.state, ABORTED)

    def test_currentness_does_not_fall_back_to_default_freshness_budget(self):
        runtime = AssistantRuntime(policy=SafetyPolicy(max_link_age_ms=2000.0))
        snapshot = make_snapshot()
        runtime.ingest(snapshot)
        proposal = propose_action(runtime, "inspect_telemetry", "inspect", "show report")["proposal"]
        runtime.approvals.approve(proposal["proposal_id"], "human-confirmation", snapshot, now=snapshot.captured_at)
        self.assertTrue(runtime.approvals.approval_is_current(
            snapshot, now=snapshot.captured_at + timedelta(seconds=1)))

    def test_no_snapshot_is_explicitly_unavailable(self):
        self.assertFalse(get_latest_telemetry(AssistantRuntime())["available"])

    def test_preflight_and_explanation_are_structured(self):
        runtime = AssistantRuntime()
        runtime.ingest(make_snapshot())
        report = run_preflight_tool(runtime)
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(explain_finding(runtime, "link.freshness")["status"], "PASS")

    def test_proposal_is_not_execution(self):
        runtime = AssistantRuntime(operator_session="test-session")
        runtime.ingest(make_snapshot())
        result = propose_action(runtime, "review_orientation", "verify orientation", "show bench checklist")
        self.assertEqual(result["state"], "PROPOSAL_READY")
        self.assertNotIn("execute", result)

    def test_explanation_rechecks_elapsed_link_freshness(self):
        runtime = AssistantRuntime()
        snapshot = make_snapshot()
        runtime.ingest(snapshot)
        with patch("lrrk_litewing_ai.safety._now", return_value=snapshot.captured_at):
            self.assertEqual(run_preflight_tool(runtime)["overall"], "PASS")
        later = snapshot.captured_at + timedelta(seconds=2)
        with patch("lrrk_litewing_ai.safety._now", return_value=later):
            finding = explain_finding(runtime, "link.freshness")
        self.assertEqual(finding["status"], "BLOCK")
        self.assertEqual(runtime.last_report.overall, "BLOCKED")
        self.assertEqual(runtime.last_report.generated_at, later)

    def test_explanation_without_telemetry_is_explicitly_rejected(self):
        with self.assertRaisesRegex(ValueError, "telemetry snapshot is required"):
            explain_finding(AssistantRuntime(), "link.freshness")

    def test_snapshot_compare_preserves_unknown_delta(self):
        before = make_snapshot()
        after = make_snapshot("tools-2")
        self.assertEqual(compare_snapshots(before, after)["battery_voltage_delta_v"], 0.0)

    def test_tool_surface_has_no_write_or_motor_command(self):
        names = " ".join(item["name"] + " " + item["description"] for item in TOOL_SCHEMAS).lower()
        self.assertNotIn("motor output", names)
        self.assertNotIn("write actuator", names)
        self.assertNotIn("arm", names)


if __name__ == "__main__":
    unittest.main()
