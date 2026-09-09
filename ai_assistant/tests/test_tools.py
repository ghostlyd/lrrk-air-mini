import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lrrk_litewing_ai.models import BatteryState, SensorHealth, SourceIdentity, TelemetrySnapshot  # noqa: E402
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
        captured_at=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        source=SourceIdentity("test", board="LiteWing V2.6.C"),
        link_age_ms=20,
        armed=False,
        flight_mode="attitude",
        battery=BatteryState(voltage_v=3.9, percent=80),
        sensors=SensorHealth(imu_present=True, imu_identity="MPU6050", imu_healthy=True),
        actuators=(0, 0, 0, 0),
    )


class ToolTests(unittest.TestCase):
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
